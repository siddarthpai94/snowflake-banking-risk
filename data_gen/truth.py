"""Ground truth: expected answers for the 15 golden questions and the 5 demo questions.

Answers are computed from the generator's internal frames using the metric
definitions in docs/spec.md. The system under test must reproduce them from
the loaded data; see tests/.
"""
import numpy as np
import pandas as pd

GOLDEN_QUESTIONS = [
    ("G01", "How many customer records does each core hold?"),
    ("G02", "How many unique customers do we have across both cores after matching?"),
    ("G03", "How many AML alerts were generated across both cores in August 2026?"),
    ("G04", "What was the false-positive rate for alerts closed in Q2 2026?"),
    ("G05", "Which three branches had the most alerts in the last 90 days, and how many each?"),
    ("G06", "How many alerts are still open more than 30 days after they were raised?"),
    ("G07", "What was the total value of cash deposits across both cores in August 2026?"),
    ("G08", "What was the total value of cash withdrawals, including ATM, across both cores in August 2026?"),
    ("G09", "What is the loan-to-deposit ratio as of 31 August 2026?"),
    ("G10", "What is non-owner-occupied CRE as a percentage of total risk-based capital?"),
    ("G11", "What are total deposit balances in each core?"),
    ("G12", "How many deposit accounts are dormant as of 31 August 2026?"),
    ("G13", "Who are the top five customers by cash deposited across both cores in the last 30 days?"),
    ("G14", "What was the average number of days to close alerts closed in Q2 2026?"),
    ("G15", "How many loans are 90 or more days past due, and what is their outstanding principal?"),
]

DEMO_QUESTIONS = [
    ("D01", "Which customers moved more than $50k in cash across both cores in 30 days, and what do their KYC files say?"),
    ("D02", "On which days did a customer's cash deposits across both cores exceed $10,000 with no CTR filed?"),
    ("D03", "Which alerts should my team work first today, and why?"),
    ("D04", "What does our BSA policy say about aggregating cash transactions across the two cores?"),
    ("D05", "Draft a case narrative for the highest-risk customer in the queue."),
]


def usd(cents):
    return round(float(cents) / 100.0, 2)


def compute(ctx):
    """ctx: dict of internal frames and settings built by generate.py."""
    tx, acc, loans, alerts = ctx["tx"], ctx["acc"], ctx["loans"], ctx["alerts"]
    cfg, as_of = ctx["cfg"], np.datetime64(ctx["as_of"])
    names = ctx["display_name"]          # person_id -> display name
    ans = {}

    ans["G01"] = {"core_a_records": ctx["n_records"]["core_a"], "core_b_records": ctx["n_records"]["core_b"],
                  "definition": "Rows in each core's customer file, individuals and businesses."}
    ans["G02"] = {"unique_customers": ctx["n_unique"],
                  "definition": "Distinct true persons and businesses across both cores (ground truth). "
                                "The system's answer depends on entity resolution; acceptance tolerance is 0.5%."}

    al = pd.DataFrame(alerts)
    al["date"] = pd.to_datetime(al["date"])
    al["close"] = pd.to_datetime(al["close"])
    ans["G03"] = {"alerts": int(((al["date"] >= "2026-08-01") & (al["date"] <= "2026-08-31")).sum()),
                  "definition": "Alerts with an alert date in August 2026, both cores."}
    q2 = al[(al["close"] >= "2026-04-01") & (al["close"] <= "2026-06-30")]
    fp = int((q2["dispo"] == "FP").sum())
    ans["G04"] = {"closed": int(len(q2)), "false_positives": fp,
                  "false_positive_rate_pct": round(100 * fp / len(q2), 1) if len(q2) else None,
                  "definition": "Alerts closed 1 Apr-30 Jun 2026 with disposition false positive (Core A FP, "
                                "Core B NOT_SUSPICIOUS), divided by all alerts closed in that period."}
    last90 = al[al["date"] > pd.Timestamp(as_of) - pd.Timedelta(days=90)].copy()
    last90["branch"] = acc["branch"].values[last90["acct_idx"].values]
    top = last90.groupby("branch").size().reset_index(name="alerts")
    top = top.sort_values(["alerts", "branch"], ascending=[False, True]).head(3)
    ans["G05"] = {"top3": [{"branch": b, "alerts": int(n)} for b, n in zip(top["branch"], top["alerts"])],
                  "definition": "Alerts dated in the 90 days to 31 Aug 2026, by branch of the alerted account "
                                "(Core A branch code or Core B branch name). Ties are listed alphabetically."}
    open_ = al[al["status"] != "CLOSED"]
    ans["G06"] = {"open_over_30_days": int((open_["date"] < pd.Timestamp(as_of) - pd.Timedelta(days=30)).sum()),
                  "open_total": int(len(open_)),
                  "definition": "Alerts not closed as of 31 Aug 2026 whose alert date is before 1 Aug 2026."}

    aug = tx[(tx["date"] >= np.datetime64("2026-08-01")) & (tx["date"] <= np.datetime64("2026-08-31"))]
    ans["G07"] = {"cash_deposits_usd": usd(aug.loc[aug["ttype"] == "CASH_DEP", "amount_c"].sum()),
                  "definition": "Sum of cash deposits posted 1-31 Aug 2026, both cores."}
    ans["G08"] = {"cash_withdrawals_usd": usd(aug.loc[aug["ttype"].isin(["CASH_WD", "ATM_WD"]), "amount_c"].sum()),
                  "definition": "Sum of teller cash withdrawals and ATM withdrawals posted 1-31 Aug 2026."}

    open_acc = acc[acc["status"] != "C"]
    dep = int(open_acc["balance_c"].sum())
    loan_c = int(round(loans["cur_prin"].sum() * 100))
    ans["G09"] = {"loans_usd": usd(loan_c), "deposits_usd": usd(dep),
                  "loan_to_deposit_pct": round(100 * loan_c / dep, 1),
                  "definition": "Outstanding loan principal divided by deposit balances of open and dormant accounts, both cores."}
    cre = loans[(loans["ltype"] == "CRE") & (loans["owner_occ"] != "Y")]
    cap = cfg["capital"]["total_risk_based_capital_usd"]
    ans["G10"] = {"non_owner_occupied_cre_usd": round(float(cre["cur_prin"].sum()), 2),
                  "total_risk_based_capital_usd": cap,
                  "cre_to_capital_pct": round(100 * float(cre["cur_prin"].sum()) / cap, 1),
                  "cre_share_of_loans_pct": round(100 * float(cre["cur_prin"].sum()) / float(loans["cur_prin"].sum()), 1),
                  "definition": "CRE loans not flagged owner-occupied (includes construction and multifamily), divided "
                                "by total risk-based capital from config/bank_demo.yaml."}
    by_core = open_acc.groupby("core")["balance_c"].sum()
    ans["G11"] = {"core_a_deposits_usd": usd(by_core.get("core_a", 0)),
                  "core_b_deposits_usd": usd(by_core.get("core_b", 0)),
                  "definition": "Balances of open and dormant deposit accounts at 31 Aug 2026."}
    ans["G12"] = {"dormant_accounts": int((acc["status"] == "D").sum()),
                  "definition": "Accounts in dormant status at 31 Aug 2026 (Core A ACCT_STAT D, Core B DORMANT). "
                                "Reactivated accounts are not dormant."}

    win_lo = as_of - np.timedelta64(cfg["thresholds"]["cross_core_cash_window_days"] - 1, "D")
    cash30 = tx[(tx["ttype"] == "CASH_DEP") & (tx["date"] >= win_lo) & (tx["date"] <= as_of)].copy()
    cash30["person_id"] = acc["person_id"].values[cash30["acct_idx"].values]
    cash30["core"] = acc["core"].values[cash30["acct_idx"].values]
    per = cash30.groupby("person_id")["amount_c"].sum().sort_values(ascending=False)
    ans["G13"] = {"window": f"{win_lo} to {as_of}",
                  "top5": [{"person_id": p, "name": names.get(p, p), "cash_deposits_usd": usd(v)}
                           for p, v in per.head(5).items()],
                  "definition": "Cash deposits per true person across both cores, 30 days to 31 Aug 2026."}
    q2c = q2.copy()
    ans["G14"] = {"avg_days_to_close": round(float((q2c["close"] - q2c["date"]).dt.days.mean()), 1),
                  "definition": "Mean of close date minus alert date for alerts closed 1 Apr-30 Jun 2026."}
    pd90 = loans[loans["dpd"] >= 90]
    ans["G15"] = {"loans_90_plus": int(len(pd90)), "principal_usd": round(float(pd90["cur_prin"].sum()), 2),
                  "definition": "Loans with days past due of 90 or more at 31 Aug 2026, both cores."}

    # ---------- demo answers ----------
    thr = cfg["thresholds"]["cross_core_cash_total_usd"] * 100
    by_core = cash30.groupby(["person_id", "core"])["amount_c"].sum().unstack(fill_value=0)
    by_core["total"] = by_core.sum(axis=1)
    hits = by_core[by_core["total"] > thr].sort_values("total", ascending=False)
    ptype = {p["person_id"]: p["pattern_type"] for p in ctx["patterns"]}
    kyc = ctx["kyc_by_person"]
    d1 = []
    for pid, r in hits.iterrows():
        d1.append({"person_id": pid, "name": names.get(pid, pid),
                   "core_a_cash_usd": usd(r.get("core_a", 0)), "core_b_cash_usd": usd(r.get("core_b", 0)),
                   "total_cash_usd": usd(r["total"]), "injected_pattern": ptype.get(pid, "none"),
                   "kyc": kyc.get(pid, [])})
    ans["D01"] = {"window": f"{win_lo} to {as_of}", "count": len(d1),
                  "suspicious": sum(1 for x in d1 if x["injected_pattern"] == "XCORE_STRUCTURING"),
                  "explained_by_kyc": sum(1 for x in d1 if x["injected_pattern"] == "CASH_INTENSIVE_LEGITIMATE"),
                  "customers": d1,
                  "expected_behaviour": "The answer lists every customer; the KYC files show the cash-intensive "
                                        "businesses expect this cash, while the structuring customers' profiles "
                                        "expect little or none."}

    cash = tx[tx["ttype"] == "CASH_DEP"].copy()
    cash["person_id"] = acc["person_id"].values[cash["acct_idx"].values]
    cash["core"] = acc["core"].values[cash["acct_idx"].values]
    day = cash.groupby(["person_id", "date", "core"]).agg(amt=("amount_c", "sum"), ctr=("ctr", "max")).reset_index()
    both = day.pivot_table(index=["person_id", "date"], columns="core", values=["amt", "ctr"], aggfunc="max")
    both.columns = [f"{a}_{b}" for a, b in both.columns]
    both = both.dropna(subset=["amt_core_a", "amt_core_b"])
    both["total"] = both["amt_core_a"] + both["amt_core_b"]
    missed = both[(both["total"] > 1_000_000) & (~both["ctr_core_a"].astype(bool))
                  & (~both["ctr_core_b"].astype(bool))]
    ans["D02"] = {"count": int(len(missed)), "days": [
        {"person_id": p, "name": names.get(p, p), "date": str(pd.Timestamp(d).date()),
         "core_a_cash_usd": usd(r["amt_core_a"]), "core_b_cash_usd": usd(r["amt_core_b"]),
         "total_usd": usd(r["total"])} for (p, d), r in missed.iterrows()],
        "definition": "Same person, same business day, cash deposits in both cores totalling over $10,000, "
                      "with no CTR flag in either core."}

    xcs = [p for p in ctx["patterns"] if p["pattern_type"] == "XCORE_STRUCTURING"]
    ans["D03"] = {"acceptance": "Every XCORE_STRUCTURING person must rank in the top 10% of the risk queue, "
                                "each with at least three reason codes from expected_reason_codes.",
                  "must_rank_top_10pct": [p["person_id"] for p in xcs]}
    ans["D04"] = {"expected_citation": {"document": "documents/bsa_aml_policy.pdf",
                                        "section": "4.2 Aggregation", "page": ctx["policy_pages"].get("4.2 Aggregation")},
                  "key_points": ["Same-person cash on the same business day totalling over $10,000 is one transaction.",
                                 "Cash in and cash out are aggregated separately.",
                                 "Core A and Core B transactions must be aggregated together after the acquisition.",
                                 "A daily cross-core aggregation report runs until conversion."]}
    top = max(xcs, key=lambda p: (len(p["expected_reason_codes"].split(";")), float(p["total_amount_usd"])))
    ans["D05"] = {"person_id": top["person_id"], "name": names.get(top["person_id"]),
                  "must_mention": [top["detail"], "KYC expected cash", "both cores"],
                  "pattern_id": top["pattern_id"],
                  "expected_reason_codes": top["expected_reason_codes"].split(";")}
    return ans
