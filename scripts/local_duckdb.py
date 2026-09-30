"""Run the Snowflake Silver and Gold SQL locally on DuckDB and score it against ground truth.

  python scripts/local_duckdb.py --data data/out/demo

This is a pre-flight check, not a substitute for running in Snowflake: the same
SQL files are translated with a handful of dialect shims (see translate() and
MACROS). Results are written to tests/results/er_eval_<dataset>.json (F2) and
tests/results/risk_eval_<dataset>.json (golden answers from Gold, and F4).
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
GOLD_FILES = ["30_config.sql", "31_gold_core.sql", "32_risk_engine.sql"]
SEMANTIC_FILES = ["40_metric_views.sql", "41_question_catalog.sql"]
SEARCH_FILES = ["50_policy_chunks.sql", "51_doc_chunk.sql"]

# Snowflake functions DuckDB lacks, defined as macros with Snowflake semantics
MACROS = [
    "CREATE OR REPLACE MACRO iff(c, a, b) AS CASE WHEN c THEN a ELSE b END",
    "CREATE OR REPLACE MACRO jarowinkler_similarity(a, b) AS round(100 * jaro_winkler_similarity(a, b))",
    "CREATE OR REPLACE MACRO regexp_substr(s, p) AS nullif(regexp_extract(s, p), '')",
    "CREATE OR REPLACE MACRO regexp_like(s, p) AS regexp_full_match(s, p)",
    "CREATE OR REPLACE MACRO regexp_replace_all(s, p, r) AS regexp_replace(s, p, r, 'g')",
    "CREATE OR REPLACE MACRO editdistance(a, b) AS levenshtein(a, b)",
]
DATE_FMT = {"YYYYMMDD": "%Y%m%d", "MM/DD/YYYY": "%m/%d/%Y", "YYYY-MM-DD": "%Y-%m-%d", "YYYY/MM/DD": "%Y/%m/%d",
            "YYYYMMDDHH24MISS": "%Y%m%d%H%M%S", 'YYYY-MM-DD"T"HH24:MI:SS': "%Y-%m-%dT%H:%M:%S"}


def rewrite_calls(sql: str, fname: str, fn) -> str:
    """Rewrite every fname(arg1, arg2) call, allowing nested parentheses in arg1."""
    out, i, pat = [], 0, re.compile(rf"\b{fname}\(", re.I)
    while (m := pat.search(sql, i)):
        out.append(sql[i:m.start()])
        depth, j = 1, m.end()
        while depth:
            depth += {"(": 1, ")": -1}.get(sql[j], 0)
            j += 1
        inner = sql[m.end():j - 1]
        arg, fmt = re.match(r"(.*),\s*'([^']+)'\s*$", inner, re.S).groups()
        out.append(fn(rewrite_calls(arg, fname, fn), fmt))
        i = j
    out.append(sql[i:])
    return "".join(out)


def translate(sql: str) -> str:
    sql = "\n".join(l for l in sql.splitlines() if not re.match(r"\s*(USE|GRANT)\s", l, re.I))
    sql = re.sub(r"CREATE OR REPLACE DYNAMIC TABLE (\S+)\s+TARGET_LAG\s*=\s*'[^']*'\s+WAREHOUSE\s*=\s*\w+\s+"
                 r"COMMENT\s*=\s*'(?:[^']|'')*'\s+AS", r"CREATE OR REPLACE TABLE \1 AS", sql)
    sql = re.sub(r"\)\s*COMMENT\s*=\s*'(?:[^']|'')*'\s*;", ");", sql)
    sql = re.sub(r"(CREATE SCHEMA IF NOT EXISTS \w+)\s+COMMENT\s*=\s*'(?:[^']|'')*'", r"\1", sql)
    sql = re.sub(r"\bREGEXP_REPLACE\(", "regexp_replace_all(", sql)
    sql = rewrite_calls(sql, "TRY_TO_DATE", lambda a, f: f"TRY_STRPTIME({a}, '{DATE_FMT[f]}')::DATE")
    sql = rewrite_calls(sql, "TRY_TO_TIMESTAMP", lambda a, f: f"TRY_STRPTIME({a}, '{DATE_FMT[f]}')")
    sql = re.sub(r"LISTAGG\((.+?),\s*('[^']*')\)\s*WITHIN GROUP\s*\(ORDER BY ([^)]+)\)",
                 r"string_agg(\1, \2 ORDER BY \3)", sql)
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


def run_files(con, folder, names):
    for m in MACROS:
        con.execute(m)
    for name in names:
        sql = translate((REPO / "sql" / folder / name).read_text())
        for stmt in [s for s in sql.split(";\n") if s.strip()]:
            try:
                con.execute(stmt)
            except Exception as e:
                raise RuntimeError(f"{folder}/{name} failed:\n{stmt[:400]}\n{e}") from e


def run_silver(con):
    run_files(con, "20_silver", SILVER_FILES)


def run_gold(con):
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    run_files(con, "30_gold", GOLD_FILES)


def run_semantic(con):
    con.execute("CREATE SCHEMA IF NOT EXISTS semantic")
    run_files(con, "40_semantic", SEMANTIC_FILES)


def run_search(con):
    run_files(con, "50_search", SEARCH_FILES)


def executor(con):
    """A function that runs Snowflake SQL text on DuckDB and returns a DataFrame (for semantic/catalog.py)."""
    return lambda sql: con.execute(translate(sql)).df()


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


def golden_check(con, data: Path):
    """Run sql/30_gold/92_golden_check.sql and compare every value with golden_answers.json."""
    got = con.execute(translate((REPO / "sql" / "30_gold" / "92_golden_check.sql").read_text()).strip().rstrip(";")).df()
    got = {(r.question_id, r.metric): r.value for r in got.itertuples()}
    gold = {q["id"]: q["answer"] for q in json.loads((data / "ground_truth" / "golden_answers.json").read_text())["questions"]}
    expected = {("G01", "core_a_records"): gold["G01"]["core_a_records"], ("G01", "core_b_records"): gold["G01"]["core_b_records"],
                ("G02", "unique_customers"): gold["G02"]["unique_customers"], ("G03", "alerts"): gold["G03"]["alerts"],
                ("G04", "false_positive_rate_pct"): gold["G04"]["false_positive_rate_pct"],
                ("G06", "open_over_30_days"): gold["G06"]["open_over_30_days"], ("G06", "open_total"): gold["G06"]["open_total"],
                ("G07", "cash_deposits_usd"): gold["G07"]["cash_deposits_usd"],
                ("G08", "cash_withdrawals_usd"): gold["G08"]["cash_withdrawals_usd"],
                ("G09", "loan_to_deposit_pct"): gold["G09"]["loan_to_deposit_pct"],
                ("G10", "cre_to_capital_pct"): gold["G10"]["cre_to_capital_pct"],
                ("G11", "core_a_deposits_usd"): gold["G11"]["core_a_deposits_usd"],
                ("G11", "core_b_deposits_usd"): gold["G11"]["core_b_deposits_usd"],
                ("G12", "dormant_accounts"): gold["G12"]["dormant_accounts"],
                ("G14", "avg_days_to_close"): gold["G14"]["avg_days_to_close"],
                ("G15", "loans_90_plus"): gold["G15"]["loans_90_plus"], ("G15", "principal_usd"): gold["G15"]["principal_usd"]}
    for i, b in enumerate(gold["G05"]["top3"], 1):
        expected[("G05", f"rank{i}")] = f"{b['branch']}={b['alerts']}"
    for i, c in enumerate(gold["G13"]["top5"], 1):
        expected[("G13", f"rank{i}")] = f"{c['name'].upper()}={c['cash_deposits_usd']}"
    rows = []
    for k, want in sorted(expected.items()):
        have = got.get(k)
        if k == ("G02", "unique_customers"):      # depends on entity resolution; tolerance 0.5%
            ok = have is not None and abs(float(have) - want) / want <= 0.005
        elif isinstance(want, (int, float)):
            ok = have is not None and abs(float(have) - float(want)) < 0.006
        else:
            name_w, n_w = want.rsplit("=", 1)
            name_h, n_h = (have or "=nan").rsplit("=", 1)
            ok = name_h == name_w and abs(float(n_h) - float(n_w)) < 0.006
        rows.append({"question": k[0], "metric": k[1], "expected": want, "got": have, "ok": bool(ok)})
    return rows


def evaluate_risk(con):
    """DuckDB version of sql/30_gold/91_eval_risk.sql: one row per injected pattern."""
    df = con.execute("""
        WITH pat AS (SELECT pattern_id, pattern_type, expected_reason_codes AS expected,
                            unnest(string_split(cores, ';')) AS core, unnest(string_split(customer_refs, ';')) AS cref
                       FROM eval.GT_INJECTED_PATTERNS),
             pp AS (SELECT DISTINCT pat.pattern_id, pat.pattern_type, pat.expected, x.party_id
                      FROM pat JOIN silver.PARTY_XREF x ON x.record_id = pat.core || ':' || pat.cref),
             best AS (SELECT party_id, MIN(queue_rank) AS queue_rank, MAX(queue_size) AS queue_size
                        FROM gold.ALERT_QUEUE GROUP BY party_id),
             fired AS (SELECT party_id, string_agg(rule_code, ';' ORDER BY rule_code) AS fired
                         FROM gold.RISK_SIGNAL GROUP BY party_id)
        SELECT pp.pattern_id, pp.pattern_type, pp.party_id, COALESCE(s.risk_score, 0) AS risk_score,
               b.queue_rank, b.queue_size, f.fired, pp.expected
          FROM pp LEFT JOIN gold.RISK_SCORE s ON s.party_id = pp.party_id
          LEFT JOIN best b ON b.party_id = pp.party_id LEFT JOIN fired f ON f.party_id = pp.party_id
         ORDER BY pp.pattern_id""").df()
    df["fired"] = df["fired"].fillna("")
    df["n_expected"] = [0 if e.startswith("EXPECTED_") else len(e.split(";")) for e in df.expected]
    df["n_expected_fired"] = [0 if e.startswith("EXPECTED_") else len(set(e.split(";")) & set(f.split(";")))
                              for e, f in zip(df.expected, df.fired)]
    return df


def risk_summary(con, data: Path):
    df = evaluate_risk(con)
    qsize = int(con.execute("SELECT COUNT(*) FROM gold.ALERT_QUEUE").fetchone()[0])
    top = con.execute("SELECT display_name, priority_score, reasons FROM gold.ALERT_QUEUE WHERE queue_rank = 1").fetchone()
    demo = {q["id"]: q["answer"] for q in json.loads((data / "ground_truth" / "demo_answers.json").read_text())["questions"]}
    ctr_days = int(con.execute("SELECT COALESCE(SUM(evidence_count), 0) FROM gold.RISK_SIGNAL "
                               "WHERE rule_code = 'CTR_AGGREGATION_MISSED'").fetchone()[0])
    by_type = {}
    for t, g in df.groupby("pattern_type"):
        by_type[t] = {"patterns": len(g), "in_queue": int(g.queue_rank.notna().sum()),
                      "worst_rank": None if g.queue_rank.isna().all() else int(g.queue_rank.max()),
                      "min_score": float(g.risk_score.min()), "max_score": float(g.risk_score.max()),
                      "all_expected_codes_fired": int((g.n_expected_fired == g.n_expected).sum())}
    xcs = df[df.pattern_type == "XCORE_STRUCTURING"]
    return {"queue_size": qsize, "by_pattern_type": by_type,
            "xcs_in_top_10pct": int((xcs.queue_rank <= 0.10 * qsize).sum()), "xcs_total": len(xcs),
            "xcs_with_3plus_expected_codes": int((xcs.n_expected_fired >= 3).sum()),
            "queue_top": {"name": top[0], "priority": float(top[1]), "reasons": top[2]},
            "d05_expected": demo["D05"]["name"],
            "ctr_missed_days": ctr_days, "d02_expected": demo["D02"]["count"]}


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
    run_gold(con)
    t3 = time.time()
    res["seconds"] = {"load_bronze": round(t1 - t0, 1), "silver": round(t2 - t1, 1), "gold_and_risk": round(t3 - t2, 1)}
    out = REPO / "tests" / "results" / f"er_eval_{data.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, default=int) + "\n")
    golden = golden_check(con, data)
    risk = {"dataset": data.name, "engine": "duckdb " + duckdb.__version__ + " (local pre-flight)",
            "golden_questions_ok": f"{sum(r['ok'] for r in golden)}/{len(golden)}", "golden": golden,
            "risk": risk_summary(con, data)}
    (out.parent / f"risk_eval_{data.name}.json").write_text(json.dumps(risk, indent=2, default=str) + "\n")
    print(json.dumps({k: v for k, v in res.items() if not k.endswith("examples")}, indent=2, default=int))
    print(json.dumps({k: v for k, v in risk.items() if k != "golden"}, indent=2, default=str))


if __name__ == "__main__":
    main()
