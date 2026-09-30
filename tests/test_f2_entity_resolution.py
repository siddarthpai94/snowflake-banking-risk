"""F2 acceptance tests: entity resolution and data-quality checks.

Runs the real Snowflake Silver SQL on DuckDB through scripts/local_duckdb.py (a
pre-flight; the same assertions must be re-run against Snowflake on Thursday).
Build-plan acceptance for F2: ">=95% of injected duplicates matched; every Gold
row traces back to its source row". We add the other side: zero false merges.
"""
import sys

import duckdb
import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import local_duckdb as L  # noqa: E402


@pytest.fixture(scope="module")
def result(small_data):
    out, _ = small_data
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, out)
    L.run_silver(con)
    return L.evaluate(con, out), con


def test_at_least_95_percent_of_duplicates_matched_automatically(result):
    r, _ = result
    assert r["recall_auto_pct"] >= 95.0


def test_no_false_merges(result):
    r, _ = result
    assert r["false_merges"] == 0


def test_lookalikes_are_never_auto_merged(result):
    r, _ = result
    assert r["lookalikes_auto_merged"] == 0


def test_every_true_link_is_linked_or_queued_for_review(result):
    r, _ = result
    assert r["missed_links"] == 0


def test_dq_checks_find_exactly_the_injected_issues(result):
    r, _ = result
    assert r["dq_injected_found"] == r["dq_injected"]
    assert r["dq_extra_found"] == []


def test_every_party_row_traces_to_a_source_row(result):
    _, con = result
    missing = con.execute("""
        SELECT COUNT(*) FROM silver.PARTY_XREF
         WHERE source_file IS NULL OR source_row IS NULL OR party_id IS NULL""").fetchone()[0]
    assert missing == 0


def test_bronze_sql_is_in_sync_with_the_schema_registry():
    import emit_bronze_sql as E
    assert (REPO / "sql" / "10_bronze" / "10_tables.sql").read_text() == E.tables_sql()
    assert (REPO / "sql" / "10_bronze" / "11_copy.sql").read_text() == E.copy_sql()
