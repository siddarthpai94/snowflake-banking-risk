"""F1 acceptance tests: the synthetic two-core generator.

Build-plan acceptance test for F1: "Re-runs from a seed and produces identical
data; every injected pattern is listed in a ground-truth table." The extra tests
check that each injected pattern really is in the files, in the shape the demo
relies on, by recomputing it from the CSVs rather than trusting the generator.
"""
import gzip
import json
import re

import numpy as np
import pandas as pd
import yaml

from conftest import REPO, SMALL
from data_gen.schemas import ALL_TABLES, columns

PROFILE = yaml.safe_load(SMALL.read_text())
CFG = yaml.safe_load((REPO / "config" / "bank_demo.yaml").read_text())


# ---------- determinism ----------

def test_same_seed_gives_byte_identical_files(small_data, tmp_path):
    from data_gen.generate import run
    _, first = small_data
    again = run(str(SMALL), str(tmp_path / "again"), quiet=True)
    assert again["sha256"] == first["sha256"]


def test_different_seed_changes_the_data(small_data, tmp_path):
    from data_gen.generate import run
    _, first = small_data
    other = run(str(SMALL), str(tmp_path / "other"), seed=PROFILE["seed"] + 1, quiet=True)
    changed = [k for k in first["sha256"] if first["sha256"][k] != other["sha256"][k]]
    assert "core_a/transactions.csv.gz" in changed and "core_b/party.csv.gz" in changed


# ---------- shape of the files ----------

def test_every_file_matches_the_schema_registry(small_data):
    out, _ = small_data
    for t in ALL_TABLES:
        with gzip.open(out / t.path, "rt") as f:
            header = f.readline().strip().split(",")
        assert header == [c for c, _ in t.columns], t.name


def test_cores_use_different_schemas_and_id_formats(read):
    a, b = read("core_a/customers.csv.gz"), read("core_b/party.csv.gz")
    assert not set(a.columns) & set(b.columns)
    assert a["CIF_NO"].str.fullmatch(r"\d{9}").all()
    assert b["party_uuid"].str.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}").all()
    persons = a[a["CUST_TYPE"] == "I"]
    assert persons["BIRTH_DT"].str.fullmatch(r"\d{8}").all()
    assert b.loc[b["dob"] != "", "dob"].str.fullmatch(r"\d{2}/\d{2}/\d{4}").all()


def test_volumes_match_the_profile(read):
    for core, cust, acc, loans in (("core_a", "customers", "accounts", "loans"),
                                   ("core_b", "party", "deposit_account", "loan")):
        p = PROFILE[core]
        assert len(read(f"{core}/{cust}.csv.gz")) == p["individuals"] + p["businesses"]
        n_acc = len(read(f"{core}/{acc}.csv.gz"))
        extra = PROFILE["dq_issues"]["core_a_duplicate_acct_no"] if core == "core_a" else 0
        assert n_acc == p["accounts"] + extra
        assert len(read(f"{core}/{loans}.csv.gz")) == p["loans"]


def test_duplicate_share_and_tiers(read):
    d = read("ground_truth/duplicate_links.csv.gz")
    dup = PROFILE["duplicates"]
    assert (d["tier"] == "A").sum() == dup["tier_a_clean"]
    assert (d["tier"] == "B").sum() == dup["tier_b_variant"]
    assert (d["tier"] == "C").sum() == dup["tier_c_hard"]
    a = read("core_a/customers.csv.gz").set_index("CIF_NO")
    b = read("core_b/party.csv.gz").set_index("party_uuid")
    for _, r in d.iterrows():
        ta = a.at[r["core_a_cif"], "TAX_ID_TKN"].lower()
        tb = b.at[r["core_b_party_uuid"], "ssn_token"]
        if r["tier"] == "C":
            assert tb == ""
        else:
            assert tb == "tkn_" + ta


def test_lookalikes_are_different_people(read):
    la = read("ground_truth/lookalike_pairs.csv.gz")
    L = PROFILE["lookalikes"]
    assert len(la) == L["jr_sr_same_address"] + L["twins"] + L["same_name_same_dob"]
    assert (la["person_id_a"] != la["person_id_b"]).all()
    assert (la["core_b_token_missing"] == "true").sum() == L["core_b_token_missing"]


# ---------- every injected pattern is listed and present ----------

def test_every_injected_pattern_is_in_ground_truth(read):
    g = read("ground_truth/injected_patterns.csv.gz")
    ij = PROFILE["injected"]
    counts = g["pattern_type"].value_counts()
    assert counts["XCORE_STRUCTURING"] == ij["cross_core_structurers"]
    assert counts["SINGLE_CORE_STRUCTURING"] == ij["single_core_structurers"]
    assert counts["CASH_INTENSIVE_LEGITIMATE"] == ij["cash_intensive_businesses"]
    assert counts["RAPID_IN_OUT"] == ij["rapid_in_out"]
    assert counts["DORMANT_REACTIVATION"] == ij["dormant_reactivation"]
    assert g["pattern_id"].is_unique and (g["expected_reason_codes"] != "").all()


def _cash(read):
    """Cash deposits from both cores with the account key and date."""
    ta = read("core_a/transactions.csv.gz")
    ta = ta[ta["TXN_CD"] == "CDEP"]
    a = pd.DataFrame({"acct": ta["ACCT_NO"], "date": pd.to_datetime(ta["POST_DT"]),
                      "usd": ta["AMT_CENTS"].astype(int) / 100, "ctr": ta["CTR_FLG"] == "Y", "core": "core_a"})
    tb = read("core_b/txn.csv.gz")
    tb = tb[tb["txn_type_desc"] == "Cash Deposit"]
    b = pd.DataFrame({"acct": tb["acct_ref"], "date": pd.to_datetime(tb["txn_timestamp"].str[:10]),
                      "usd": tb["amount"].astype(float), "ctr": tb["ctr_filed"] == "true", "core": "core_b"})
    return pd.concat([a, b], ignore_index=True)


def test_cross_core_structuring_is_invisible_to_each_core_alone(read):
    g = read("ground_truth/injected_patterns.csv.gz")
    cash = _cash(read)
    thr = CFG["thresholds"]
    as_of = pd.Timestamp(PROFILE["window_end"])
    lo = as_of - pd.Timedelta(days=thr["cross_core_cash_window_days"] - 1)
    for _, p in g[g["pattern_type"] == "XCORE_STRUCTURING"].iterrows():
        acct_a, acct_b = p["account_refs"].split(";")
        w = cash[(cash["date"] >= lo) & (cash["date"] <= as_of)]
        a = w[w["acct"] == acct_a]
        b = w[w["acct"] == acct_b]
        assert a["usd"].sum() < thr["legacy_per_core_cash_30d_usd"]      # each legacy core sees too little
        assert b["usd"].sum() < thr["legacy_per_core_cash_30d_usd"]
        assert a["usd"].sum() + b["usd"].sum() > thr["cross_core_cash_total_usd"]  # together it is large
        assert (pd.concat([a, b])["usd"] < thr["ctr_cash_threshold_usd"]).all()
        assert not pd.concat([a, b])["ctr"].any()


def test_missed_ctr_aggregation_days_exist(read, small_data):
    out, _ = small_data
    demo = json.loads((out / "ground_truth" / "demo_answers.json").read_text())
    d02 = next(q for q in demo["questions"] if q["id"] == "D02")["answer"]
    assert d02["count"] == PROFILE["injected"]["missed_ctr_aggregation_people"]
    cash = _cash(read).set_index(["acct", "date"])
    g = read("ground_truth/injected_patterns.csv.gz")
    xcs = g[g["pattern_type"] == "XCORE_STRUCTURING"]
    for day in d02["days"]:
        acct_a, acct_b = xcs.loc[xcs["person_id"] == day["person_id"], "account_refs"].iloc[0].split(";")
        d = pd.Timestamp(day["date"])
        total = cash.loc[(acct_a, d), "usd"].sum() + cash.loc[(acct_b, d), "usd"].sum()
        assert total > CFG["thresholds"]["ctr_cash_threshold_usd"]


def test_rapid_in_out_moves_most_money_out_within_48_hours(read):
    g = read("ground_truth/injected_patterns.csv.gz")
    ta = read("core_a/transactions.csv.gz")
    tb = read("core_b/txn.csv.gz")
    for _, p in g[g["pattern_type"] == "RAPID_IN_OUT"].iterrows():
        acct = p["account_refs"]
        if p["cores"] == "core_a":
            t = ta[ta["ACCT_NO"] == acct]
            ts = pd.to_datetime(t["POST_DT"] + t["POST_TM"], format="%Y%m%d%H%M%S")
            amt = t["AMT_CENTS"].astype(int) / 100
        else:
            t = tb[tb["acct_ref"] == acct]
            ts = pd.to_datetime(t["txn_timestamp"].str[:19])
            amt = np.where(t["dr_cr"] == "C", 1, -1) * t["amount"].astype(float)
        amt = pd.Series(np.asarray(amt), index=ts.values)
        big_in = amt[amt >= CFG["thresholds"]["rapid_in_out_min_inflow_usd"]]
        t0, inflow = big_in.index[0], big_in.iloc[0]
        window = amt[(amt.index > t0) & (amt.index <= t0 + pd.Timedelta(hours=48))]
        assert -window[window < 0].sum() >= CFG["thresholds"]["rapid_in_out_pct_out"] * inflow


def test_dormant_reactivation_follows_a_year_of_dormancy(read):
    g = read("ground_truth/injected_patterns.csv.gz")
    acc_a = read("core_a/accounts.csv.gz").drop_duplicates("ACCT_NO").set_index("ACCT_NO")
    acc_b = read("core_b/deposit_account.csv.gz").set_index("acct_ref")
    for _, p in g[g["pattern_type"] == "DORMANT_REACTIVATION"].iterrows():
        acct = p["account_refs"]
        if p["cores"] == "core_a":
            since, react = pd.Timestamp(acc_a.at[acct, "DORM_FLAG_DT"]), pd.Timestamp(acc_a.at[acct, "REACT_DT"])
        else:
            since, react = pd.Timestamp(acc_b.at[acct, "dormant_since"]), pd.Timestamp(acc_b.at[acct, "reactivated_on"])
        assert (react - since).days >= CFG["thresholds"]["dormancy_days"]
        assert float(p["total_amount_usd"]) >= CFG["thresholds"]["reactivation_inflow_usd"]


def test_data_quality_issues_are_really_in_the_files(read):
    dq = read("ground_truth/dq_issues.csv.gz")
    a = read("core_a/customers.csv.gz").set_index("CIF_NO")
    b = read("core_b/party.csv.gz")
    acc_a = read("core_a/accounts.csv.gz")
    acc_b = read("core_b/deposit_account.csv.gz")
    for _, r in dq.iterrows():
        k = r["record_key"]
        if r["issue_type"] == "DQ_MISSING_DOB":
            assert a.at[k, "BIRTH_DT"] == "00000000"
        elif r["issue_type"] == "DQ_FUTURE_DOB":
            assert pd.Timestamp(a.at[k, "BIRTH_DT"]) > pd.Timestamp(PROFILE["window_end"])
        elif r["issue_type"] == "DQ_INVALID_ZIP":
            z = b.loc[b["party_uuid"] == k, "city_state_zip"].iloc[0].split(" ")[-1]
            assert not re.fullmatch(r"\d{5}", z) or z == "00000"
        elif r["issue_type"] == "DQ_DUPLICATE_KEY":
            assert (acc_a["ACCT_NO"] == k).sum() == 2
        elif r["issue_type"] == "DQ_ORPHAN_ACCOUNT":
            owner = acc_b.loc[acc_b["acct_ref"] == k, "party_uuid"].iloc[0]
            assert owner not in set(b["party_uuid"])


def test_control_totals_reconcile_to_the_files(read):
    c = read("core_a/control_totals.csv.gz").set_index("FILE_NM")
    assert int(c.at["transactions.csv", "REC_CNT"]) == len(read("core_a/transactions.csv.gz"))
    assert int(c.at["transactions.csv", "AMT_TOTAL_CENTS"]) == read("core_a/transactions.csv.gz")["AMT_CENTS"].astype(int).sum()
    assert int(c.at["accounts.csv", "AMT_TOTAL_CENTS"]) == read("core_a/accounts.csv.gz")["CUR_BAL_CENTS"].astype(int).sum()
    cb = read("core_b/control_totals.csv.gz").set_index("file_name")
    tb = read("core_b/txn.csv.gz")
    net = (np.where(tb["dr_cr"] == "C", 1, -1) * (tb["amount"].astype(float) * 100).round()).sum() / 100
    assert int(cb.at["txn.csv", "record_count"]) == len(tb)
    assert abs(float(cb.at["txn.csv", "amount_total"]) - net) < 0.005


# ---------- safety: synthetic only ----------

def test_no_ssn_shaped_values_anywhere(small_data):
    out, manifest = small_data
    ssn = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    for t in ALL_TABLES:
        with gzip.open(out / t.path, "rt") as f:
            assert not ssn.search(f.read()), t.name
    assert manifest["label"].startswith("SYNTHETIC")


# ---------- documents and answers ----------

def test_policy_pdf_has_citable_sections(small_data):
    _, manifest = small_data
    pages = manifest["policy_pdf"]["section_pages"]
    for key in ("4.2 Aggregation", "5.2 Red flags", "7.2 Deadline"):
        assert pages.get(key), key


def test_documents_cover_every_injected_customer(read):
    kyc = read("documents/kyc_summaries.csv.gz")
    g = read("ground_truth/injected_patterns.csv.gz")
    refs = set(kyc["customer_ref"])
    for _, p in g.iterrows():
        for r in p["customer_refs"].split(";"):
            assert r in refs, p["pattern_id"]
    notes = read("documents/investigator_notes.csv.gz")
    assert set(notes["alert_ref"]) == set(read("core_a/aml_alerts.csv.gz")["ALERT_ID"]) | set(read("core_b/case_alert.csv.gz")["case_ref"])


def test_golden_and_demo_answers_are_complete(small_data):
    out, _ = small_data
    gold = json.loads((out / "ground_truth" / "golden_answers.json").read_text())["questions"]
    demo = json.loads((out / "ground_truth" / "demo_answers.json").read_text())["questions"]
    assert len(gold) == 15 and len(demo) == 5
    d01 = demo[0]["answer"]
    assert d01["suspicious"] == PROFILE["injected"]["cross_core_structurers"]
    assert d01["explained_by_kyc"] == PROFILE["injected"]["cash_intensive_businesses"]


def test_golden_answers_recompute_from_the_files(read, small_data):
    """Independent path: recompute three answers from the CSVs, not the generator's frames."""
    out, _ = small_data
    gold = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "golden_answers.json").read_text())["questions"]}
    cash = _cash(read)
    aug = cash[(cash["date"] >= "2026-08-01") & (cash["date"] <= "2026-08-31")]
    assert abs(aug["usd"].sum() - gold["G07"]["cash_deposits_usd"]) < 0.01
    dormant = (read("core_a/accounts.csv.gz").drop_duplicates("ACCT_NO")["ACCT_STAT"] == "D").sum() \
        + (read("core_b/deposit_account.csv.gz")["acct_status"] == "DORMANT").sum()
    assert dormant == gold["G12"]["dormant_accounts"]
    assert gold["G01"]["core_a_records"] == len(read("core_a/customers.csv.gz"))
