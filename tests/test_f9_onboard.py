"""F9 acceptance: the onboarding tool maps Core A and Core B from scratch in agreement with the hand-written
mappings, maps Core C (never seen) well enough to link its customers to Core A correctly, and its generated
data-quality tests find the injected issues. Build-plan bar: onboard Core B from scratch; same tool on Core C."""
import sys
from collections import Counter

import duckdb
import pandas as pd
import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import local_duckdb as L  # noqa: E402
from onboarding import evaluate as E  # noqa: E402
from onboarding.onboard import build_mapping, name_tokens, write_outputs  # noqa: E402


@pytest.fixture(scope="module")
def env(small_data):
    out, _ = small_data
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, out)
    L.run_silver(con)
    return con, out, E.evaluate(con, out)


def _files(out, core):
    return sorted(p for p in (out / core).iterdir() if p.name.endswith(".csv.gz") and "control" not in p.name)


def test_files_keys_and_links_on_every_core(small_data):
    out, _ = small_data
    expect = {"core_a": ("customers.csv.gz", "CIF_NO", "accounts.csv.gz", "ACCT_NO", "transactions.csv.gz"),
              "core_b": ("party.csv.gz", "party_uuid", "deposit_account.csv.gz", "acct_ref", "txn.csv.gz"),
              "core_c": ("customers.csv.gz", "custId", "accounts.csv.gz", "accountId", "postings.csv.gz")}
    for core, (cf, ck, af, ak, tf) in expect.items():
        m, _ = build_mapping(core, _files(out, core))
        assert (m["customer"]["source_file"], m["customer"]["key"]) == (cf, ck), core
        assert (m["account"]["source_file"], m["account"]["key"]) == (af, ak), core
        assert m["transaction"]["source_file"] == tf, core
        assert m["account"]["fields"]["customer_key"] == f'"{ck}"', core          # found by value overlap
        assert m["transaction"]["fields"]["account_key"] == f'"{ak}"', core


def test_core_b_from_scratch_agrees_with_hand_mapping(env):
    _, _, res = env
    agree = res["core_b"]["agreement_with_hand_mapping_pct"]
    for f in ("first_name", "last_name", "birth_date", "tax_token", "city", "state", "phone", "email"):
        assert agree[f] >= 99.9, (f, agree[f])
    assert agree["zip"] >= 98


def test_core_a_from_scratch_agrees_with_hand_mapping(env):
    _, _, res = env
    agree = res["core_a"]["agreement_with_hand_mapping_pct"]
    assert all(v >= 99.5 for v in agree.values()), agree


def test_core_c_links_to_core_a(env):
    _, _, res = env
    links = res["core_c"]["links_to_core_a"]
    assert links["false_links"] == 0 and links["recall_pct"] >= 95, links


def test_generated_dq_tests_find_the_injected_issues(env):
    con, out, res = env
    gt = pd.read_csv(out / "ground_truth" / "dq_issues.csv.gz", dtype=str)
    want = Counter(zip(gt.issue_type, gt.core))
    found = {(c, ent, check): n for c in ("core_a", "core_b") for ent, check, n, _ in res[c]["dq"]}
    assert found[("core_a", "account", "duplicate keys")] == want[("DQ_DUPLICATE_KEY", "core_a")]
    assert found[("core_a", "customer", "birth_date in the future or before 1900")] == want[("DQ_FUTURE_DOB", "core_a")]
    assert found[("core_a", "customer", "birth_date not parsed or not mapped")] == want[("DQ_MISSING_DOB", "core_a")]
    assert found[("core_b", "customer", "zip not 5 digits or 00000")] == want[("DQ_INVALID_ZIP", "core_b")]
    assert found[("core_b", "account", "orphan accounts (no customer)")] == want[("DQ_ORPHAN_ACCOUNT", "core_b")]


def test_unknown_codes_go_to_review_not_guessed(small_data):
    out, _ = small_data
    m, _ = build_mapping("core_c", _files(out, "core_c"))
    flagged = {r.get("column"): set(r.get("values", [])) for r in m["review"] if "values" in r}
    assert flagged.get("statusCode") == {"1", "2", "9"}
    assert "status" not in m["account"]["fields"]                          # no guessed status mapping
    assert m["account"]["fields"]["product_type"] == "DECODE(\"accountType\", 'CHK', 'CHECKING', 'SVG', 'SAVINGS')"


def test_outputs_are_written(small_data, tmp_path):
    out, _ = small_data
    m, profiles = build_mapping("core_c", _files(out, "core_c"))
    d = write_outputs("core_c", m, profiles, tmp_path / "core_c", "core_c")
    for f in ("mapping.yaml", "10_bronze.sql", "20_canonical.sql", "30_dq_tests.sql", "profile.md"):
        assert (d / f).stat().st_size > 100, f
    assert "COPY INTO RISK_COPILOT.BRONZE.CORE_C_CUSTOMERS" in (d / "10_bronze.sql").read_text()


def test_name_tokens():
    assert name_tokens("familyName") == {"last", "name"}
    assert name_tokens("TAX_ID_TKN") == {"tax", "id", "token"}
    assert name_tokens("postalCode") == {"zip", "code"}
