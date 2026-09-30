"""Score the onboarding tool (F9) on real data, in DuckDB.

  python -m onboarding.evaluate --data data/out/demo

For Core A and Core B, whose hand-written mappings already feed SILVER.CUSTOMER_STD, the generated canonical
customer view is compared with CUSTOMER_STD value by value, field by field. For Core C, which no mapping has
ever covered, generated customers are linked to Core A by tax token and date of birth and the links are
checked against ground truth (300 Core C customers are also Core A customers). The generated data-quality
tests are run as well.
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))
import local_duckdb as L  # noqa: E402
from onboarding.onboard import build_mapping, canonical_sql, dq_sql  # noqa: E402

COMPARE = {"first_name": "first_name", "last_name": "last_name", "birth_date": "birth_date",
           "tax_token": "tax_token", "street": None, "city": "city", "state": "state", "zip": "zip5",
           "phone": "phone", "email": "email"}


def _run(con, sql):
    done, failed = [], []
    for stmt in [x for x in L.translate(sql).split(";\n") if x.strip()]:
        try:
            con.execute(stmt)
            done.append(stmt.split("\n")[0][:80])
        except Exception as e:                        # e.g. a Bronze table this DuckDB build does not have
            failed.append((stmt.split("\n")[0][:80], str(e).splitlines()[0][:160]))
    return done, failed


def build_views(con, core, data):
    files = sorted(p for p in (data / core).iterdir() if p.name.endswith((".csv", ".csv.gz")) and "control" not in p.name)
    mapping, _ = build_mapping(core, files)
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'bronze'").fetchall()]
    by_file = {}
    for t in tables:                                                    # which Bronze table holds which file
        try:
            by_file[con.execute(f"SELECT MIN(_SOURCE_FILE) FROM bronze.{t}").fetchone()[0]] = t
        except Exception:
            pass
    for m in ("customer", "account", "transaction"):
        if m in mapping:
            t = by_file.get(f"{core}/{mapping[m]['source_file']}")
            if t:
                mapping[m]["bronze_table"] = f"BRONZE.{t}"
    done, failed = _run(con, canonical_sql(core, mapping))
    return mapping, failed


def compare_with_std(con, core):
    v = f"silver.{core}_customer"
    cols = {r[0] for r in con.execute(f"SELECT * FROM {v} LIMIT 0").description}
    res = {}
    total = con.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
    for gen, std in COMPARE.items():
        if std is None or gen not in cols:
            continue
        cast = "CAST({} AS DATE)" if gen == "birth_date" else "UPPER(CAST({} AS VARCHAR))"
        agree = con.execute(f"""
            SELECT COUNT(*) FROM {v} g JOIN silver.CUSTOMER_STD s ON s.record_id = g.record_id
             WHERE {cast.format('g.' + gen)} IS NOT DISTINCT FROM {cast.format('s.' + std)}""").fetchone()[0]
        res[gen] = round(100 * agree / total, 2)
    return total, res


def link_core_c(con, data):
    """Link generated Core C customers to Core A (CUSTOMER_STD) by tax token + date of birth; score vs truth."""
    got = set(con.execute("""
        SELECT c.source_key, a.source_key FROM silver.core_c_customer c
          JOIN silver.CUSTOMER_STD a ON a.source_system = 'core_a' AND a.tax_token = c.tax_token
                                   AND CAST(a.birth_date AS DATE) = CAST(c.birth_date AS DATE)""").fetchall())
    pm = con.execute("SELECT person_id, core, customer_ref, record_role FROM eval.GT_PERSON_MAP").df()
    c_rows = pm[(pm.core == "core_c") & (pm.record_role == "core_c_also_in_core_a")]
    a_rows = pm[pm.core == "core_a"].set_index("person_id")["customer_ref"]
    truth = {(r.customer_ref, a_rows[r.person_id]) for r in c_rows.itertuples() if r.person_id in a_rows.index}
    return {"true_links": len(truth), "found": len(got), "correct": len(got & truth), "false_links": len(got - truth),
            "recall_pct": round(100 * len(got & truth) / len(truth), 2) if truth else None}


def run_dq(con, core, mapping):
    try:
        return con.execute(L.translate(dq_sql(core, mapping)).strip().rstrip(";")).fetchall()
    except Exception as e:
        return [("error", str(e).splitlines()[0][:200])]


def evaluate(con, data):
    out = {}
    for core in ("core_a", "core_b"):
        mapping, failed = build_views(con, core, data)
        total, agree = compare_with_std(con, core)
        out[core] = {"customers": total, "agreement_with_hand_mapping_pct": agree,
                     "review_items": len(mapping["review"]), "views_not_built": failed,
                     "dq": [list(r) for r in run_dq(con, core, mapping)]}
    mapping, failed = build_views(con, "core_c", data)
    out["core_c"] = {"links_to_core_a": link_core_c(con, data), "review_items": mapping["review"],
                     "views_not_built": failed,
                     "dq": [list(r) for r in run_dq(con, "core_c", mapping)]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO / "data" / "out" / "demo"))
    a = ap.parse_args()
    data = Path(a.data)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, data)
    L.run_silver(con)
    res = evaluate(con, data)
    out = REPO / "tests" / "results" / f"onboard_eval_{data.name}.json"
    out.write_text(json.dumps(res, indent=2, default=str) + "\n")
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
