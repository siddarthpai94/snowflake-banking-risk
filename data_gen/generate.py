"""F1: synthetic two-core bank generator.

Usage:
  python -m data_gen.generate --profile data_gen/profiles/demo.yaml --out data/out/demo
  python -m data_gen.generate --profile data_gen/profiles/small.yaml --out data/out/small

Same profile + same seed => byte-identical output (checked by tests and by
the SHA-256 list in manifest.json). ALL DATA IS SYNTHETIC.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import alerts as AL
from . import banking, core_c, documents, injections, people, transactions as TX, truth, vocab
from .writers import write_table, sha256_file

GENERATOR_VERSION = "1.0.0"
REPO = Path(__file__).resolve().parent.parent


def split2(n, share_a):
    a = int(round(n * share_a))
    return a, n - a


def run(profile_path, out_dir, seed=None, quiet=False):
    t0 = time.time()
    log = (lambda *a: None) if quiet else (lambda *a: print(f"[{time.time() - t0:6.1f}s]", *a, flush=True))
    prof = yaml.safe_load(Path(profile_path).read_text())
    seed = int(seed if seed is not None else prof["seed"])
    cfg = yaml.safe_load((REPO / "config" / "bank_demo.yaml").read_text())
    as_of, ws = prof["window_end"], prof["window_start"]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rngs = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(9)]
    r_people, r_acc, r_inj, r_tx, r_alert, r_doc, r_c, r_ids, r_dq = rngs

    # ---------------- people ----------------
    P, ba, bb, look = people.build_people(r_people, prof, as_of)
    log(f"people: {len(P):,} individuals, {len(ba) + len(bb):,} businesses")

    def owners(ind, biz):
        return pd.concat([ind[["person_id", "kind", "cust_since"]], biz[["person_id", "kind", "cust_since"]]],
                         ignore_index=True)

    own_a, own_b = owners(P[P.in_a], ba), owners(P[P.in_b], bb)
    br_a, br_b = banking.branches(prof["core_a"]["branches"], prof["core_b"]["branches"])
    acc_a, home_a = banking.build_accounts(r_acc, own_a, prof["core_a"]["accounts"], "core_a", as_of, ws,
                                           br_a["BR_CD"].values, prof["organic"])
    acc_b, home_b = banking.build_accounts(r_acc, own_b, prof["core_b"]["accounts"], "core_b", as_of, ws,
                                           br_b["branch_name"].values, prof["organic"])
    acc = pd.concat([acc_a, acc_b], ignore_index=True)
    loans = pd.concat([banking.build_loans(r_acc, own_a, prof["core_a"]["loans"], "core_a", as_of, br_a["BR_CD"].values),
                       banking.build_loans(r_acc, own_b, prof["core_b"]["loans"], "core_b", as_of, br_b["branch_name"].values)],
                      ignore_index=True)
    log(f"accounts {len(acc):,}, loans {len(loans):,}")

    # ---------------- injections ----------------
    pool = {"core_a": list(br_a["BR_CD"]), "core_b": list(br_b["branch_name"])}
    inj = injections.Injector(r_inj, acc, None, pool, cfg)
    inj.used |= set(look["x"]) | set(look["y"])
    ij = prof["injected"]
    tier_a = list(P.loc[P.tier == "A", "person_id"])
    xcs = inj.cross_core_structuring(tier_a, ij["cross_core_structurers"], ij["missed_ctr_aggregation_people"],
                                     ij["kyc_conflict_people"])
    a_only = list(P.loc[P.in_a & ~P.in_b, "person_id"])
    b_only = list(P.loc[~P.in_a & P.in_b, "person_id"])
    pools = {"core_a": a_only, "core_b": b_only}
    inj.single_core_structuring(pools, split2(ij["single_core_structurers"], 2 / 3))
    inj.cash_intensive({"core_a": ba, "core_b": bb}, split2(ij["cash_intensive_businesses"], 0.6))
    inj.rapid_in_out(pools, split2(ij["rapid_in_out"], 2 / 3), ij["rapid_in_out_with_alert"])
    na, nb = split2(ij["dormant_reactivation"], 0.65)
    d_idx = list(banking.mark_dormant(r_acc, acc, na, "2024-06-01", "2025-06-30", "inj_dormant", inj.used,
                                      ("2026-08-01", "2026-08-20"), "core_a"))
    d_idx += list(banking.mark_dormant(r_acc, acc, nb, "2024-06-01", "2025-06-30", "inj_dormant", inj.used,
                                       ("2026-08-01", "2026-08-20"), "core_b"))
    inj.dormant_reactivation(d_idx, ij["dormant_reactivation_with_alert"])
    org = prof["organic"]
    la, lb = split2(org["legit_reactivations"], 0.6)
    legit = list(banking.mark_dormant(r_acc, acc, la, "2024-01-01", "2025-06-30", "legit_react", inj.used,
                                      ("2026-04-01", "2026-08-20"), "core_a"))
    legit += list(banking.mark_dormant(r_acc, acc, lb, "2024-01-01", "2025-06-30", "legit_react", inj.used,
                                       ("2026-04-01", "2026-08-20"), "core_b"))
    for i in legit:  # a small, explainable deposit reactivates the account
        d = np.datetime64(pd.Timestamp(acc.at[i, "reactivated_on"]).date())
        inj.row(i, d, int(r_inj.integers(9 * 3600, 20 * 3600)), "XFER_IN",
                int(r_inj.integers(50, 2500)) * 100, "ONLINE")
    banking.mark_dormant(r_acc, acc, org["dormant_accounts_a"], "2024-03-01", "2026-02-27", "dormant", inj.used, None, "core_a")
    banking.mark_dormant(r_acc, acc, org["dormant_accounts_b"], "2024-03-01", "2026-02-27", "dormant", inj.used, None, "core_b")
    log(f"injected {len(inj.patterns)} patterns, {len(inj.rows):,} injected transactions")

    # ---------------- transactions ----------------
    tx = TX.organic(r_tx, acc, ws, as_of)
    roles = acc["role"].values[tx["acct_idx"].values]
    quiet_cash = np.isin(roles, ["inj_xcore", "inj_single", "inj_cashbiz"]) & tx["ttype"].isin(["CASH_DEP", "CASH_WD", "ATM_WD"]).values
    tx = tx[~quiet_cash].reset_index(drop=True)
    tx = TX.assign_channels(r_tx, tx, acc, pool)
    tx = pd.concat([tx, pd.DataFrame(inj.rows)], ignore_index=True)
    tx = TX.legacy_ctr_flags(tx, acc)
    tx = tx.sort_values(["date", "secs", "acct_idx"], kind="mergesort").reset_index(drop=True)
    acc["balance_c"] = TX.balances(r_tx, tx, acc)
    log(f"transactions {len(tx):,}")

    # ---------------- ids ----------------
    ind_a, ind_b = P[P.in_a], P[P.in_b]
    a_person_ids = list(ind_a["person_id"]) + list(ba["person_id"])
    b_person_ids = list(ind_b["person_id"]) + list(bb["person_id"])
    a_ids = dict(zip(a_person_ids, people.unique_ids(r_ids, len(a_person_ids), 100_000_000, 15000)))
    b_ids = dict(zip(b_person_ids, people.uuids(r_ids, len(b_person_ids))))
    is_a = (acc["core"] == "core_a").values
    acct_key = np.empty(len(acc), dtype=object)
    acct_key[is_a] = [str(x) for x in people.unique_ids(r_ids, int(is_a.sum()), 1_200_000_000, 90_000)]
    acct_key[~is_a] = [f"PB-{x:08d}" for x in people.unique_ids(r_ids, int((~is_a).sum()), 10_000_000, 1500)]
    acc["acct_key"] = acct_key
    cust_ref = lambda core, pid: str(a_ids[pid]) if core == "core_a" else b_ids[pid]

    # ---------------- Core A files ----------------
    cust_a = people.render_core_a_customers(r_people, P, ba, a_ids)
    cust_a["HOME_BR_CD"] = [home_a[p] for p in a_person_ids]
    cust_b = people.render_core_b_party(r_people, P, bb, b_ids)
    cust_b["home_branch"] = [home_b[p] for p in b_person_ids]

    # data-quality injections (on records not used by any pattern)
    dq = prof["dq_issues"]
    gt_dq = []
    exclude = inj.used | set(P.loc[P.in_a & P.in_b, "person_id"])
    a_ok = [i for i, p in enumerate(a_person_ids) if p.startswith("P") and p not in exclude]
    pick = r_dq.choice(a_ok, dq["core_a_missing_dob"] + dq["core_a_future_dob"], replace=False)
    for k, i in enumerate(pick):
        if k < dq["core_a_missing_dob"]:
            cust_a.at[i, "BIRTH_DT"] = "00000000"
            gt_dq.append(("DQ_MISSING_DOB", "core_a", "CORE_A_CUSTOMERS", cust_a.at[i, "CIF_NO"], "BIRTH_DT"))
        else:
            cust_a.at[i, "BIRTH_DT"] = f"20{int(r_dq.integers(27, 31))}{int(r_dq.integers(1, 13)):02d}{int(r_dq.integers(1, 28)):02d}"
            gt_dq.append(("DQ_FUTURE_DOB", "core_a", "CORE_A_CUSTOMERS", cust_a.at[i, "CIF_NO"], "BIRTH_DT"))
    b_ok = [i for i, p in enumerate(b_person_ids) if p.startswith("P") and p not in exclude]
    for i in r_dq.choice(b_ok, dq["core_b_invalid_zip"], replace=False):
        csz = cust_b.at[i, "city_state_zip"]
        bad = csz[:-5] + (csz[-5:-1] if r_dq.random() < 0.6 else "00000")
        cust_b.at[i, "city_state_zip"] = bad
        gt_dq.append(("DQ_INVALID_ZIP", "core_b", "CORE_B_PARTY", cust_b.at[i, "party_uuid"], "city_state_zip"))

    acct_a = acc[is_a]
    acc_rows_a = pd.DataFrame({
        "ACCT_NO": acct_a["acct_key"].values, "CIF_NO": [str(a_ids[p]) for p in acct_a["person_id"]],
        "PROD_CD": acct_a["product"].values, "BR_CD": acct_a["branch"].values,
        "OPEN_DT": pd.to_datetime(acct_a["open_dt"]).dt.strftime("%Y%m%d").values,
        "CLOSE_DT": pd.to_datetime(acct_a["close_dt"]).dt.strftime("%Y%m%d").fillna("").values,
        "ACCT_STAT": acct_a["status"].values,
        "DORM_FLAG_DT": pd.to_datetime(acct_a["dormant_since"]).dt.strftime("%Y%m%d").fillna("").values,
        "REACT_DT": pd.to_datetime(acct_a["reactivated_on"]).dt.strftime("%Y%m%d").fillna("").values,
        "CUR_BAL_CENTS": acct_a["balance_c"].astype(str).values,
        "INT_RATE_PCT": [f"{v:.2f}" for v in acct_a["rate"]],
    })
    dup_rows = r_dq.choice(np.where(acct_a["role"].values == "")[0], dq["core_a_duplicate_acct_no"], replace=False)
    for i in dup_rows:
        gt_dq.append(("DQ_DUPLICATE_KEY", "core_a", "CORE_A_ACCOUNTS", acc_rows_a.at[i, "ACCT_NO"], "ACCT_NO"))
    acc_rows_a = pd.concat([acc_rows_a, acc_rows_a.iloc[np.sort(dup_rows)]], ignore_index=True)

    loans_a = loans[loans["core"] == "core_a"].reset_index(drop=True)
    loan_ids = people.unique_ids(r_ids, len(loans_a), 300_000_000, 30_000)
    loans_a_rows = pd.DataFrame({
        "LOAN_NO": [f"L{x:09d}" for x in loan_ids], "CIF_NO": [str(a_ids[p]) for p in loans_a["person_id"]],
        "LOAN_TYP": loans_a["ltype"].values, "BR_CD": loans_a["branch"].values,
        "ORIG_DT": pd.to_datetime(loans_a["orig_dt"]).dt.strftime("%Y%m%d").values,
        "MAT_DT": pd.to_datetime(loans_a["mat_dt"]).dt.strftime("%Y%m%d").values,
        "ORIG_AMT_CENTS": [str(int(round(v * 100))) for v in loans_a["orig_amt"]],
        "CUR_PRIN_CENTS": [str(int(round(v * 100))) for v in loans_a["cur_prin"]],
        "INT_RATE_PCT": [f"{v:.3f}" for v in loans_a["rate"]], "COLL_TYP": loans_a["coll"].values,
        "OWNER_OCC_FLG": loans_a["owner_occ"].values, "DPD": loans_a["dpd"].astype(str).values,
    })

    ta = tx[acc["core"].values[tx["acct_idx"].values] == "core_a"]
    sign_a = np.where(ta["ttype"].isin(TX.CREDIT), 1, -1)
    secs = ta["secs"].values.astype(int)
    txn_a = pd.DataFrame({
        "TXN_ID": [f"{30_000_000_000_000 + i:014d}" for i in range(len(ta))],
        "ACCT_NO": acc["acct_key"].values[ta["acct_idx"].values],
        "POST_DT": pd.to_datetime(ta["date"]).dt.strftime("%Y%m%d").values,
        "POST_TM": [f"{s // 3600:02d}{s % 3600 // 60:02d}{s % 60:02d}" for s in secs],
        "TXN_CD": ta["ttype"].map(TX.A_TXN_CODE).values,
        "AMT_CENTS": (sign_a * ta["amount_c"].values).astype(str),
        "CHNL_CD": ta["channel"].map(TX.A_CHANNEL).values, "BR_CD": ta["branch"].fillna("").values,
        "CTR_FLG": np.where(ta["ctr"].values, "Y", "N"),
        "CPTY_NM": ta["cpty"].fillna("").values, "CPTY_BANK": ta["cpty_bank"].fillna("").values,
    })
    log("rendered Core A")

    # ---------------- Core B files ----------------
    acct_b = acc[~is_a]
    status_b = {"A": "OPEN", "D": "DORMANT", "C": "CLOSED"}
    acc_rows_b = pd.DataFrame({
        "acct_ref": acct_b["acct_key"].values, "party_uuid": [b_ids[p] for p in acct_b["person_id"]],
        "product_name": [banking.B_BIZ_DDA if (k == "B" and p == "DDA") else banking.B_PRODUCTS[p]
                         for k, p in zip(acct_b["kind"], acct_b["product"])],
        "branch_name": acct_b["branch"].values,
        "opened_on": pd.to_datetime(acct_b["open_dt"]).dt.strftime("%Y-%m-%d").values,
        "closed_on": pd.to_datetime(acct_b["close_dt"]).dt.strftime("%Y-%m-%d").fillna("").values,
        "acct_status": acct_b["status"].map(status_b).values,
        "dormant_since": pd.to_datetime(acct_b["dormant_since"]).dt.strftime("%Y-%m-%d").fillna("").values,
        "reactivated_on": pd.to_datetime(acct_b["reactivated_on"]).dt.strftime("%Y-%m-%d").fillna("").values,
        "ledger_balance": [f"{v / 100:.2f}" for v in acct_b["balance_c"]],
        "rate_pct": [f"{v:.2f}" for v in acct_b["rate"]],
    })
    orphan = r_dq.choice(np.where(acct_b["role"].values == "")[0], dq["core_b_orphan_account"], replace=False)
    ghost = people.uuids(r_dq, len(orphan))
    for i, g in zip(orphan, ghost):
        acc_rows_b.at[i, "party_uuid"] = g
        gt_dq.append(("DQ_ORPHAN_ACCOUNT", "core_b", "CORE_B_DEPOSIT_ACCOUNT", acc_rows_b.at[i, "acct_ref"], "party_uuid"))

    loans_b = loans[loans["core"] == "core_b"].reset_index(drop=True)
    seq = people.unique_ids(r_ids, len(loans_b), 100_000, 40)
    loans_b_rows = pd.DataFrame({
        "note_number": [f"LN-{pd.Timestamp(d).year}-{s:06d}" for d, s in zip(loans_b["orig_dt"], seq)],
        "party_uuid": [b_ids[p] for p in loans_b["person_id"]],
        "product_name": loans_b["ltype"].map(banking.B_LOAN_NAMES).values,
        "branch_name": loans_b["branch"].values,
        "booked_on": pd.to_datetime(loans_b["orig_dt"]).dt.strftime("%Y-%m-%d").values,
        "maturity_on": pd.to_datetime(loans_b["mat_dt"]).dt.strftime("%Y-%m-%d").values,
        "original_amount": [f"{v:.2f}" for v in loans_b["orig_amt"]],
        "principal_outstanding": [f"{v:.2f}" for v in loans_b["cur_prin"]],
        "interest_rate_pct": [f"{v:.3f}" for v in loans_b["rate"]],
        "collateral_desc": [banking.b_collateral_desc(c, r_ids) for c in loans_b["coll"]],
        "owner_occupied": ["true" if o == "Y" else "false" for o in loans_b["owner_occ"]],
        "days_delinquent": loans_b["dpd"].astype(str).values,
    })

    tb = tx[acc["core"].values[tx["acct_idx"].values] == "core_b"]
    secs = tb["secs"].values.astype(int)
    hhmmss = [f"T{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}" for s in secs]
    dstr = pd.to_datetime(tb["date"]).dt.strftime("%Y-%m-%d").values
    txn_b = pd.DataFrame({
        "txn_uuid": people.uuids(r_ids, len(tb)),
        "acct_ref": acc["acct_key"].values[tb["acct_idx"].values],
        "txn_timestamp": [d + h + o for d, h, o in zip(dstr, hhmmss, TX.b_offset(tb["date"].values))],
        "amount": [f"{v / 100:.2f}" for v in tb["amount_c"].values],
        "dr_cr": np.where(tb["ttype"].isin(TX.CREDIT), "C", "D"),
        "txn_type_desc": tb["ttype"].map(TX.B_TXN_DESC).values,
        "channel_desc": tb["channel"].map(TX.B_CHANNEL).values,
        "branch_name": tb["branch"].fillna("").values,
        "ctr_filed": np.where(tb["ctr"].values, "true", "false"),
        "counterparty": tb["cpty"].fillna("").values,
        "counterparty_institution": tb["cpty_bank"].fillna("").values,
    })
    log("rendered Core B")

    # ---------------- alerts, notes, KYC ----------------
    risk = dict(zip(P["person_id"], P["risk_a"]))
    specs = AL.organic_alerts(r_alert, acc, None, risk, inj.used,
                              {"core_a": org["alerts_a"], "core_b": org["alerts_b"]}, ws, as_of)
    specs += inj.alerts
    al = AL.finalize(r_alert, specs, as_of)
    a_seq, b_seq = 700_001, 1
    for s in al:
        if s["core"] == "core_a":
            s["ref"] = str(a_seq)
            a_seq += int(r_alert.integers(1, 4))
        else:
            s["ref"] = f"AL-2026-{b_seq:06d}"
            b_seq += int(r_alert.integers(1, 3))
    pat_by_id = {p["pattern_id"]: p for p in inj.patterns}
    for s in al:
        if s["pattern_id"]:
            refs = pat_by_id[s["pattern_id"]]["legacy_alerts"]
            if "pending" in refs:
                refs.remove("pending")
            refs.append(f"{s['core']}:{s['ref']}")

    alerts_a = pd.DataFrame([{
        "ALERT_ID": s["ref"], "CIF_NO": str(a_ids[s["person_id"]]), "ACCT_NO": acc.at[s["acct_idx"], "acct_key"],
        "RULE_CD": AL.A_RULE[s["rule"]], "ALERT_DT": pd.Timestamp(s["date"]).strftime("%Y%m%d"),
        "ALERT_SCORE": str(s["score"]), "ALERT_STAT": s["status"], "DISPO_CD": s["dispo"],
        "CLOSE_DT": pd.Timestamp(s["close"]).strftime("%Y%m%d") if s["close"] is not None else "",
        "ASSIGNED_TO": s["owner"], "BR_CD": acc.at[s["acct_idx"], "branch"],
    } for s in al if s["core"] == "core_a"])
    outcome_b = {"FP": "NOT_SUSPICIOUS", "NSR": "NO_SAR_AFTER_REVIEW", "SAR": "SAR_FILED", "": ""}
    state_b = {"OPEN": "NEW", "WIP": "IN_REVIEW", "CLOSED": "CLOSED"}
    alerts_b = pd.DataFrame([{
        "case_ref": s["ref"], "party_uuid": b_ids[s["person_id"]], "acct_ref": acc.at[s["acct_idx"], "acct_key"],
        "scenario_name": AL.B_SCENARIO[s["rule"]],
        "created_at": AL.ts(s["date"], r_alert, 1, 6),
        "priority": "P1" if s["score"] >= 85 else ("P2" if s["score"] >= 65 else "P3"),
        "state": "ESCALATED" if (s["status"] == "WIP" and s["score"] >= 85) else state_b[s["status"]],
        "outcome": outcome_b[s["dispo"]],
        "closed_at": AL.ts(s["close"], r_alert) if s["close"] is not None else "",
        "analyst": s["owner"],
    } for s in al if s["core"] == "core_b"])
    log(f"alerts: {len(alerts_a):,} Core A, {len(alerts_b):,} Core B")

    # profiles used by notes and KYC
    biz_all = pd.concat([ba, bb], ignore_index=True).set_index("person_id")
    Pi = P.set_index("person_id")
    conflict_people = {p["person_id"] for p in inj.patterns if p.get("kyc_conflict")}
    for pid in sorted(conflict_people):
        cur = Pi.at[pid, "occupation"]
        alt = [o for o, _ in vocab.OCCUPATIONS if o != cur and o != "Retired"]
        Pi.at[pid, "b_occupation"] = alt[int(r_doc.integers(0, len(alt)))]
    P["b_occupation"] = Pi["b_occupation"].values
    cust_b["employer_or_industry"] = [Pi.at[p, "b_occupation"] if p in Pi.index else vocab.BUSINESS_TYPES[biz_all.at[p, "biz_type_idx"]][0]
                                      for p in b_person_ids]
    # keep business names consistent with any retyping done by the cash-intensive injector
    for df, ids_, col_name, col_occ, upper in ((cust_a, a_person_ids, "BUS_NM", "OCCUP_DESC", False),
                                               (cust_b, b_person_ids, "full_name", "employer_or_industry", True)):
        for i, p in enumerate(ids_):
            if p.startswith("B"):
                nm = biz_all.at[p, "biz_name"]
                df.at[i, col_name] = nm.upper() if upper else nm
                df.at[i, col_occ] = vocab.BUSINESS_TYPES[biz_all.at[p, "biz_type_idx"]][0]
    ctype = {p["person_id"]: p for p in inj.patterns if p["pattern_type"] == "CASH_INTENSIVE_LEGITIMATE"}
    for i, p in enumerate(a_person_ids):
        if p in ctype:
            cust_a.at[i, "RISK_RTG"] = "M"

    def profile(core, pid):
        if pid.startswith("B"):
            b = biz_all.loc[pid]
            exp = ctype[pid]["expected_cash"] if pid in ctype else b["expected_cash"]
            return {"occupation": vocab.BUSINESS_TYPES[b["biz_type_idx"]][0], "expected_cash": float(exp),
                    "name": b["biz_name"], "business": True, "town": vocab.TOWNS[b["town_idx"]][0]}
        r = Pi.loc[pid]
        occ = r["occupation"] if core == "core_a" else r["b_occupation"]
        exp = dict(vocab.OCCUPATIONS)[occ]
        return {"occupation": occ, "expected_cash": float(exp), "business": False,
                "name": f"{r['first']} {r['last']}", "town": vocab.TOWNS[r["town_idx"]][0]}

    alerted_accts = sorted({s["acct_idx"] for s in al})
    sub = tx[tx["acct_idx"].isin(alerted_accts)][["acct_idx", "date", "ttype", "amount_c"]]
    tx_by_acct = {k: g for k, g in sub.groupby("acct_idx")}
    notes = []
    for s in al:
        pr = profile(s["core"], s["person_id"])
        pat = pat_by_id.get(s["pattern_id"]) if s["pattern_id"] else None
        f = AL.facts_for(tx_by_acct, s["acct_idx"], s["date"])
        for t_, who, text in AL.notes_for(r_alert, s, s["ref"], cust_ref(s["core"], s["person_id"]), f, pr, pat):
            notes.append({"note_id": f"N{len(notes) + 1:06d}", "core": s["core"], "alert_ref": s["ref"],
                          "customer_ref": cust_ref(s["core"], s["person_id"]), "author": who,
                          "created_at": t_, "note_text": str(text)})

    # KYC: alerted customers, every injected customer, and a random sample
    kyc_keys = {(s["core"], s["person_id"]) for s in al}
    for p in inj.patterns:
        for c in p["cores"].split(";"):
            kyc_keys.add((c, p["person_id"]))
    everyone = [("core_a", p) for p in a_person_ids] + [("core_b", p) for p in b_person_ids]
    for k in r_doc.choice(len(everyone), org["random_kyc_summaries"], replace=False):
        kyc_keys.add(everyone[k])
    kyc_rows, kyc_by_person = [], {}
    risk_lookup = {("core_a", p): r for p, r in zip(a_person_ids, cust_a["RISK_RTG"])}
    risk_lookup.update({("core_b", p): r for p, r in zip(b_person_ids, cust_b["kyc_risk"])})
    for n, (core, pid) in enumerate(sorted(kyc_keys), start=1):
        pr = profile(core, pid)
        row = documents.kyc_row(r_doc, f"KYC{n:06d}", core, cust_ref(core, pid), pr["name"], pr["occupation"],
                                pr["expected_cash"], pr["business"], pr["town"], risk_lookup[(core, pid)])
        kyc_rows.append(row)
        kyc_by_person.setdefault(pid, []).append({"core": core, "occupation": row["occupation_or_business"],
                                                  "expected_monthly_cash_usd": row["expected_monthly_cash_usd"]})
    log(f"notes {len(notes):,}, KYC summaries {len(kyc_rows):,}")

    policy_path = out / "documents" / "bsa_aml_policy.pdf"
    documents.write_policy_pdf(policy_path)
    markers = ["4.2 Aggregation", "5.2 Red flags", "5.3 Cross-core review", "6.2 Investigation", "7.2 Deadline",
               "8.3 Monitoring", "3.4 Profiles held on two cores"]
    policy_pages, n_pages = documents.policy_page_index(policy_path, markers)

    # ---------------- Core C ----------------
    c_cust, c_acc, c_post, c_map = core_c.build(r_c, prof, P, inj.used, as_of, ws)

    # ---------------- control totals ----------------
    ctl_a = pd.DataFrame([
        {"FILE_NM": "customers.csv", "REC_CNT": str(len(cust_a)), "AMT_TOTAL_CENTS": "", "AS_OF_DT": as_of.replace("-", "")},
        {"FILE_NM": "accounts.csv", "REC_CNT": str(len(acc_rows_a)),
         "AMT_TOTAL_CENTS": str(acc_rows_a["CUR_BAL_CENTS"].astype(np.int64).sum()), "AS_OF_DT": as_of.replace("-", "")},
        {"FILE_NM": "loans.csv", "REC_CNT": str(len(loans_a_rows)),
         "AMT_TOTAL_CENTS": str(loans_a_rows["CUR_PRIN_CENTS"].astype(np.int64).sum()), "AS_OF_DT": as_of.replace("-", "")},
        {"FILE_NM": "transactions.csv", "REC_CNT": str(len(txn_a)),
         "AMT_TOTAL_CENTS": str(txn_a["AMT_CENTS"].astype(np.int64).sum()), "AS_OF_DT": as_of.replace("-", "")},
        {"FILE_NM": "aml_alerts.csv", "REC_CNT": str(len(alerts_a)), "AMT_TOTAL_CENTS": "", "AS_OF_DT": as_of.replace("-", "")},
    ])
    bal_b = sum(int(round(float(v) * 100)) for v in acc_rows_b["ledger_balance"])
    prin_b = sum(int(round(float(v) * 100)) for v in loans_b_rows["principal_outstanding"])
    net_b = int((np.where(tb["ttype"].isin(TX.CREDIT), 1, -1) * tb["amount_c"].values).sum())
    ctl_b = pd.DataFrame([
        {"file_name": "party.csv", "record_count": str(len(cust_b)), "amount_total": "", "as_of": as_of},
        {"file_name": "deposit_account.csv", "record_count": str(len(acc_rows_b)), "amount_total": f"{bal_b / 100:.2f}", "as_of": as_of},
        {"file_name": "loan.csv", "record_count": str(len(loans_b_rows)), "amount_total": f"{prin_b / 100:.2f}", "as_of": as_of},
        {"file_name": "txn.csv", "record_count": str(len(txn_b)), "amount_total": f"{net_b / 100:.2f}", "as_of": as_of},
        {"file_name": "case_alert.csv", "record_count": str(len(alerts_b)), "amount_total": "", "as_of": as_of},
    ])

    # ---------------- ground truth ----------------
    pm = [{"person_id": p, "core": "core_a", "customer_ref": str(a_ids[p]),
           "record_role": "duplicate_in_both_cores" if (p.startswith("P") and Pi.at[p, "in_b"]) else "core_a_only"}
          for p in a_person_ids]
    pm += [{"person_id": p, "core": "core_b", "customer_ref": b_ids[p],
            "record_role": "duplicate_in_both_cores" if (p.startswith("P") and Pi.at[p, "in_a"]) else "core_b_only"}
           for p in b_person_ids]
    pm_df = pd.concat([pd.DataFrame(pm), c_map], ignore_index=True)
    dups = P[P.in_a & P.in_b]
    dup_df = pd.DataFrame({"person_id": dups["person_id"], "core_a_cif": [str(a_ids[p]) for p in dups["person_id"]],
                           "core_b_party_uuid": [b_ids[p] for p in dups["person_id"]], "tier": dups["tier"],
                           "variation": dups["variation"]})
    look_df = pd.DataFrame({
        "pair_id": [f"LA{i:04d}" for i in range(1, len(look) + 1)], "lookalike_type": look["type"],
        "core_a_cif": [str(a_ids[x]) for x in look["x"]], "core_b_party_uuid": [b_ids[y] for y in look["y"]],
        "person_id_a": look["x"], "person_id_b": look["y"],
        "core_b_token_missing": ["true" if v else "false" for v in look["b_token_missing"]],
    })
    pat_rows = []
    for p in inj.patterns:
        cores = p["cores"].split(";")
        pat_rows.append({
            "pattern_id": p["pattern_id"], "pattern_type": p["pattern_type"], "person_id": p["person_id"],
            "cores": p["cores"], "customer_refs": ";".join(cust_ref(c, p["person_id"]) for c in cores),
            "account_refs": ";".join(acc.at[i, "acct_key"] for i in p["acct_idx"]),
            "window_start": p["window_start"], "window_end": p["window_end"],
            "total_amount_usd": p["total_amount_usd"], "expected_reason_codes": p["expected_reason_codes"],
            "legacy_alert_refs": ";".join(p["legacy_alerts"]), "detail": p["detail"],
        })
    dq_df = pd.DataFrame([{"issue_id": f"DQ{i:05d}", "issue_type": t, "core": c, "table_name": tn,
                           "record_key": k, "field": f} for i, (t, c, tn, k, f) in enumerate(gt_dq, start=1)])

    # ---------------- write ----------------
    written = []
    for name, data in [
        ("CORE_A_CUSTOMERS", cust_a), ("CORE_A_ACCOUNTS", acc_rows_a), ("CORE_A_LOANS", loans_a_rows),
        ("CORE_A_TXNS", txn_a), ("CORE_A_AML_ALERTS", alerts_a), ("CORE_A_BRANCHES", br_a),
        ("CORE_A_CONTROL_TOTALS", ctl_a),
        ("CORE_B_PARTY", cust_b), ("CORE_B_DEPOSIT_ACCOUNT", acc_rows_b), ("CORE_B_LOAN", loans_b_rows),
        ("CORE_B_TXN", txn_b), ("CORE_B_CASE_ALERT", alerts_b), ("CORE_B_BRANCH", br_b),
        ("CORE_B_CONTROL_TOTALS", ctl_b),
        ("CORE_C_CUSTOMERS", c_cust), ("CORE_C_ACCOUNTS", c_acc), ("CORE_C_POSTINGS", c_post),
        ("DOC_INVESTIGATOR_NOTES", notes), ("DOC_KYC_SUMMARIES", kyc_rows),
        ("GT_PERSON_MAP", pm_df), ("GT_DUPLICATE_LINKS", dup_df), ("GT_LOOKALIKE_PAIRS", look_df),
        ("GT_INJECTED_PATTERNS", pat_rows), ("GT_DQ_ISSUES", dq_df),
    ]:
        written.append(write_table(out, name, data))
    log("wrote CSV files")

    names = {}
    for p, r in zip(P["person_id"], zip(P["first"], P["last"])):
        names[p] = f"{r[0]} {r[1]}"
    for p, n in zip(biz_all.index, biz_all["biz_name"]):
        names[p] = n
    ctx = {"tx": tx, "acc": acc, "loans": loans, "alerts": al, "cfg": cfg, "as_of": as_of,
           "display_name": names, "patterns": inj.patterns, "kyc_by_person": kyc_by_person,
           "policy_pages": policy_pages,
           "n_records": {"core_a": len(cust_a), "core_b": len(cust_b)},
           "n_unique": int(len(P) + len(ba) + len(bb))}
    answers = truth.compute(ctx)
    for pid_list in (answers["D01"]["customers"], answers["D02"]["days"]):
        for x in pid_list:
            x["customer_refs"] = [cust_ref(c, x["person_id"]) for c in ("core_a", "core_b")
                                  if (c == "core_a" and x["person_id"] in a_ids) or (c == "core_b" and x["person_id"] in b_ids)]
    gt_dir = out / "ground_truth"
    (gt_dir / "golden_answers.json").write_text(json.dumps(
        {"questions": [{"id": i, "question": q, "answer": answers[i]} for i, q in truth.GOLDEN_QUESTIONS]},
        indent=2, default=str) + "\n")
    (gt_dir / "demo_answers.json").write_text(json.dumps(
        {"questions": [{"id": i, "question": q, "answer": answers[i]} for i, q in truth.DEMO_QUESTIONS]},
        indent=2, default=str) + "\n")

    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "manifest.json")
    manifest = {
        "label": "SYNTHETIC DATA - fictional institutions and people - not for production use",
        "generator_version": GENERATOR_VERSION, "profile": Path(profile_path).name, "seed": seed,
        "window": {"start": ws, "end": as_of},
        "tables": {w["table"]: {"path": w["path"], "rows": w["rows"]} for w in written},
        "policy_pdf": {"path": "documents/bsa_aml_policy.pdf", "pages": n_pages, "section_pages": policy_pages},
        "injection_summary": pd.Series([p["pattern_type"] for p in inj.patterns]).value_counts().sort_index().to_dict(),
        "dq_summary": dq_df["issue_type"].value_counts().sort_index().to_dict(),
        "duplicates": dup_df["tier"].value_counts().sort_index().to_dict(),
        "lookalike_pairs": int(len(look_df)),
        "sha256": {str(p.relative_to(out)): sha256_file(p) for p in files},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    log(f"done: {len(files)} files in {out}")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default=str(REPO / "data_gen" / "profiles" / "demo.yaml"))
    ap.add_argument("--out", default=str(REPO / "data" / "out" / "demo"))
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    run(a.profile, a.out, a.seed)


if __name__ == "__main__":
    main()
