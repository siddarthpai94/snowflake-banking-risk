"""Gold model and F4 risk engine acceptance tests.

Runs the real Snowflake Gold and risk-engine SQL on DuckDB (via scripts/local_duckdb.py)
over the small dataset. The Snowflake run is scored by sql/30_gold/91_eval_risk.sql.
No AI anywhere: scores are sums of configured rule weights.
"""
import sys

import duckdb
import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import local_duckdb as L  # noqa: E402


@pytest.fixture(scope="module")
def gold(small_data):
    out, _ = small_data
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, out)
    L.run_silver(con)
    L.run_gold(con)
    return con, out


@pytest.fixture(scope="module")
def patterns(gold):
    con, _ = gold
    return L.evaluate_risk(con)


# ---- Gold model -----------------------------------------------------------------

def test_every_golden_question_is_answered_correctly_from_gold(gold):
    con, out = gold
    bad = [r for r in L.golden_check(con, out) if not r["ok"]]
    assert not bad, bad


def test_every_gold_row_traces_to_a_source_row(gold):
    con, _ = gold
    for t in ("ACCOUNT", "LOAN", "TRANSACTION", "ALERT", "KYC_PROFILE"):
        n = con.execute(f"SELECT COUNT(*) FROM gold.{t} WHERE source_file IS NULL OR source_row IS NULL").fetchone()[0]
        assert n == 0, t


def test_transactions_all_parse_and_link_to_a_customer(gold):
    con, _ = gold
    total, no_ts, no_type, no_party = con.execute(
        "SELECT COUNT(*), COUNT(*) - COUNT(posted_at), COUNT(*) - COUNT(txn_type), COUNT(*) - COUNT(party_id) "
        "FROM gold.TRANSACTION").fetchone()
    bronze = con.execute("SELECT (SELECT COUNT(*) FROM bronze.CORE_A_TXNS) + (SELECT COUNT(*) FROM bronze.CORE_B_TXN)").fetchone()[0]
    assert total == bronze
    assert no_ts == 0 and no_type == 0
    # Only transactions on the injected orphan accounts (flagged by DQ_ORPHAN_ACCOUNT) lack a customer
    orphan_txns = con.execute("""
        SELECT COUNT(*) FROM gold.TRANSACTION t
         WHERE t.party_id IS NULL
           AND SPLIT_PART(t.account_id, ':', 2) NOT IN
               (SELECT record_key FROM silver.DQ_EXCEPTIONS WHERE rule_id = 'DQ_ORPHAN_ACCOUNT')""").fetchone()[0]
    assert orphan_txns == 0 and no_party < 0.01 * total


def test_account_keys_are_unique_after_dedup(gold):
    con, _ = gold
    assert con.execute("SELECT COUNT(*) - COUNT(DISTINCT account_id) FROM gold.ACCOUNT").fetchone()[0] == 0


# ---- F4 risk engine --------------------------------------------------------------

def test_cross_core_structurers_rank_above_everything_else(patterns, gold):
    con, _ = gold
    xcs = patterns[patterns.pattern_type == "XCORE_STRUCTURING"]
    assert xcs.queue_rank.notna().all()
    # stricter than "top 10%" and independent of queue size: they take ranks 1..n
    assert sorted(xcs.queue_rank.astype(int)) == list(range(1, len(xcs) + 1))


def test_cross_core_structurers_have_three_plus_expected_reasons(patterns):
    xcs = patterns[patterns.pattern_type == "XCORE_STRUCTURING"]
    assert (xcs.n_expected_fired >= 3).all()


def test_every_injected_pattern_fires_all_its_expected_reason_codes(patterns):
    risky = patterns[~patterns.expected.str.startswith("EXPECTED_")]
    missing = risky[risky.n_expected_fired < risky.n_expected][["pattern_id", "fired", "expected"]]
    assert missing.empty, missing.to_string()


def test_legitimate_cash_businesses_score_below_every_structurer(patterns):
    cib = patterns[patterns.pattern_type == "CASH_INTENSIVE_LEGITIMATE"]
    structurers = patterns[patterns.pattern_type.str.endswith("STRUCTURING")]
    assert cib.risk_score.max() < structurers.risk_score.min()


def test_ctr_aggregation_days_match_ground_truth(gold):
    con, out = gold
    import json
    d02 = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "demo_answers.json").read_text())["questions"]}["D02"]
    got = con.execute("SELECT COALESCE(SUM(evidence_count), 0) FROM gold.RISK_SIGNAL "
                      "WHERE rule_code = 'CTR_AGGREGATION_MISSED'").fetchone()[0]
    assert got == d02["count"]


def test_top_of_queue_is_the_d05_customer(gold):
    con, out = gold
    import json
    d05 = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "demo_answers.json").read_text())["questions"]}["D05"]
    top = con.execute("SELECT display_name FROM gold.ALERT_QUEUE WHERE queue_rank = 1").fetchone()[0]
    assert top == d05["name"].upper()


def test_scores_are_weight_sums_within_0_and_100(gold):
    con, _ = gold
    bad = con.execute("""
        SELECT COUNT(*) FROM gold.RISK_SCORE s
          JOIN (SELECT party_id, SUM(weight) AS w FROM gold.RISK_SIGNAL GROUP BY party_id) r USING (party_id)
         WHERE s.risk_score <> GREATEST(0, LEAST(100, r.w)) OR s.risk_score NOT BETWEEN 0 AND 100""").fetchone()[0]
    assert bad == 0


def test_every_signal_has_evidence_and_a_configured_rule(gold):
    con, _ = gold
    rules = {r["code"] for r in yaml.safe_load((REPO / "config" / "bank_demo.yaml").read_text())["risk_rules"]}
    df = con.execute("SELECT rule_code, evidence_text FROM gold.RISK_SIGNAL").df()
    assert set(df.rule_code) <= rules
    assert df.evidence_text.notna().all() and (df.evidence_text.str.len() > 10).all()


def test_thresholds_come_from_config_not_code(gold):
    """F14: raising the cross-core threshold in config removes XCORE_CASH_30D without any SQL change."""
    con, _ = gold
    before = con.execute("SELECT COUNT(*) FROM gold.RISK_SIGNAL WHERE rule_code = 'XCORE_CASH_30D'").fetchone()[0]
    assert before > 0
    con.execute("UPDATE gold.CONFIG_PARAM SET num_value = 1e9 WHERE name = 'thresholds.cross_core_cash_total_usd'")
    try:
        sql = L.translate((REPO / "sql" / "30_gold" / "32_risk_engine.sql").read_text())
        for stmt in [s for s in sql.split(";\n") if s.strip()]:
            con.execute(stmt)
        after = con.execute("SELECT COUNT(*) FROM gold.RISK_SIGNAL WHERE rule_code = 'XCORE_CASH_30D'").fetchone()[0]
        assert after == 0
    finally:
        L.run_files(con, "30_gold", ["30_config.sql", "32_risk_engine.sql"])
