"""Run the Snowflake Silver SQL locally on DuckDB and score it against ground truth.

  python scripts/local_duckdb.py --data data/out/demo

This is a pre-flight check, not a substitute for running in Snowflake: the same
SQL files are translated with a handful of dialect shims (see TRANSLATIONS and
MACROS). Results are written to tests/results/er_eval_<dataset>.json.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from data_gen.schemas import ALL_TABLES  # noqa: E402

SILVER_FILES = ["20_reference.sql", "21_customer_std.sql", "22_match_candidates.sql",
                "23_party_resolution.sql", "24_dq_exceptions.sql"]

# Snowflake functions DuckDB lacks, defined as macros with Snowflake semantics
MACROS = [
    "CREATE OR REPLACE MACRO iff(c, a, b) AS CASE WHEN c THEN a ELSE b END",
    "CREATE OR REPLACE MACRO jarowinkler_similarity(a, b) AS round(100 * jaro_winkler_similarity(a, b))",
    "CREATE OR REPLACE MACRO regexp_substr(s, p) AS nullif(regexp_extract(s, p), '')",
    "CREATE OR REPLACE MACRO regexp_like(s, p) AS regexp_full_match(s, p)",
    "CREATE OR REPLACE MACRO regexp_replace_all(s, p, r) AS regexp_replace(s, p, r, 'g')",
    "CREATE OR REPLACE MACRO editdistance(a, b) AS levenshtein(a, b)",
]
DATE_FMT = {"YYYYMMDD": "%Y%m%d", "MM/DD/YYYY": "%m/%d/%Y", "YYYY-MM-DD": "%Y-%m-%d", "YYYY/MM/DD": "%Y/%m/%d"}


def translate(sql: str) -> str:
    sql = "\n".join(l for l in sql.splitlines() if not re.match(r"\s*USE\s", l, re.I))
    sql = re.sub(r"CREATE OR REPLACE DYNAMIC TABLE (\S+)\s+TARGET_LAG\s*=\s*'[^']*'\s+WAREHOUSE\s*=\s*\w+\s+"
                 r"COMMENT\s*=\s*'(?:[^']|'')*'\s+AS", r"CREATE OR REPLACE TABLE \1 AS", sql)
    sql = re.sub(r"\)\s*COMMENT\s*=\s*'(?:[^']|'')*'\s*;", ");", sql)
    sql = re.sub(r"\bREGEXP_REPLACE\(", "regexp_replace_all(", sql)
    sql = re.sub(r"TRY_TO_DATE\(([^,()]+),\s*'([^']+)'\)",
                 lambda m: f"TRY_STRPTIME({m.group(1)}, '{DATE_FMT[m.group(2)]}')::DATE", sql)
    sql = sql.replace("CURRENT_DATE()", "CURRENT_DATE")
    return sql


def load_bronze(con, data: Path):
    for s in ("bronze", "silver", "eval"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    for t in ALL_TABLES:
        f = data / t.path
        schema = "eval" if t.source == "ground_truth" else "bronze"
        cols = ", ".join(f"'{c}': 'VARCHAR'" for c, _ in t.columns)
        con.execute(f"""
            CREATE OR REPLACE TABLE {schema}.{t.name} AS
            SELECT *, '{t.path}' AS _SOURCE_FILE, row_number() OVER () AS _SOURCE_ROW, now() AS _LOADED_AT
              FROM read_csv('{f}', header = true, columns = {{{cols}}}, quote = '"', escape = '"')
        """)


def run_silver(con):
    for m in MACROS:
        con.execute(m)
    for name in SILVER_FILES:
        sql = translate((REPO / "sql" / "20_silver" / name).read_text())
        for stmt in [s for s in sql.split(";\n") if s.strip()]:
            con.execute(stmt)


def evaluate(con, data: Path):
    q = lambda s: con.execute(s).df()
    truth = q("SELECT 'core_a:' || core_a_cif AS a_id, 'core_b:' || core_b_party_uuid AS b_id, tier FROM eval.GT_DUPLICATE_LINKS")
    look = q("SELECT 'core_a:' || core_a_cif AS a_id, 'core_b:' || core_b_party_uuid AS b_id, lookalike_type, "
             "core_b_token_missing FROM eval.GT_LOOKALIKE_PAIRS")
    auto = q("SELECT a_id, b_id FROM silver.AUTO_LINKS")
    review = q("SELECT a_id, b_id FROM silver.MATCH_REVIEW_QUEUE")
    tset = set(zip(truth.a_id, truth.b_id))
    aset = set(zip(auto.a_id, auto.b_id))
    rset = set(zip(review.a_id, review.b_id))
    lset = set(zip(look.a_id, look.b_id))
    tp = aset & tset
    false_merges = aset - tset
    in_review = (rset & tset) - aset
    missed = tset - aset - rset
    tier = dict(zip(zip(truth.a_id, truth.b_id), truth.tier))
    by_tier = {}
    for t in sorted(set(truth.tier)):
        pairs = {p for p in tset if tier[p] == t}
        by_tier[t] = {"true_links": len(pairs), "auto_linked": len(pairs & aset),
                      "in_review": len((pairs & rset) - aset), "missed": len(pairs - aset - rset)}
    parties_after_auto = q("SELECT COUNT(DISTINCT party_id) AS n FROM silver.PARTY_XREF").n[0]
    n_unique_true = json.loads((data / "ground_truth" / "golden_answers.json").read_text())["questions"][1]["answer"]["unique_customers"]

    dq_sys = q("SELECT rule_id, record_key FROM silver.DQ_EXCEPTIONS")
    dq_gt = q("SELECT issue_type AS rule_id, record_key FROM eval.GT_DQ_ISSUES")
    s_dq, g_dq = set(zip(dq_sys.rule_id, dq_sys.record_key)), set(zip(dq_gt.rule_id, dq_gt.record_key))

    cand = q("SELECT decision, COUNT(*) AS n FROM silver.MATCH_CANDIDATES GROUP BY 1 ORDER BY 1")
    return {
        "dataset": data.name,
        "engine": "duckdb " + duckdb.__version__ + " (local pre-flight; Snowflake run pending)",
        "candidate_pairs": dict(zip(cand.decision, cand.n.astype(int))),
        "true_links": len(tset),
        "auto_links": len(aset),
        "auto_links_correct": len(tp),
        "false_merges": len(false_merges),
        "precision_pct": round(100 * len(tp) / len(aset), 3) if aset else None,
        "recall_auto_pct": round(100 * len(tp) / len(tset), 2),
        "true_links_in_review": len(in_review),
        "recall_after_review_pct": round(100 * (len(tp) + len(in_review)) / len(tset), 2),
        "missed_links": len(missed),
        "review_queue_size": len(rset),
        "lookalike_pairs": len(lset),
        "lookalikes_auto_merged": len(lset & aset),
        "lookalikes_in_review": len(lset & rset),
        "by_tier": by_tier,
        "parties_after_auto_links": int(parties_after_auto),
        "parties_true": int(n_unique_true),
        "dq_exceptions_found": len(s_dq),
        "dq_injected": len(g_dq),
        "dq_injected_found": len(s_dq & g_dq),
        "dq_extra_found": sorted(f"{r}:{k}" for r, k in (s_dq - g_dq))[:20],
        "dq_by_rule": dq_sys.rule_id.value_counts().sort_index().to_dict(),
        "false_merge_examples": sorted(false_merges)[:10],
        "missed_examples": sorted(missed)[:10],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO / "data" / "out" / "demo"))
    ap.add_argument("--db", default=":memory:")
    a = ap.parse_args()
    data = Path(a.data)
    t0 = time.time()
    con = duckdb.connect(a.db)
    con.execute("SET TimeZone = 'UTC'")
    load_bronze(con, data)
    t1 = time.time()
    run_silver(con)
    t2 = time.time()
    res = evaluate(con, data)
    res["seconds"] = {"load_bronze": round(t1 - t0, 1), "silver": round(t2 - t1, 1)}
    out = REPO / "tests" / "results" / f"er_eval_{data.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, default=int) + "\n")
    print(json.dumps(res, indent=2, default=int))


if __name__ == "__main__":
    main()
