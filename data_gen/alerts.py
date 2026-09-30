"""Legacy transaction-monitoring alerts for both cores, and investigator notes."""
import numpy as np
import pandas as pd

A_RULE = {"LARGE_CASH": "LCT01", "STRUCT": "STR02", "VELOCITY": "VEL03", "HRJ_WIRE": "WIR04",
          "RAPID": "RMV05", "DORMANT": "DRM06"}
B_SCENARIO = {"LARGE_CASH": "Large Cash Activity", "STRUCT": "Possible Structuring",
              "VELOCITY": "High Velocity", "HRJ_WIRE": "High Risk Geography Wire",
              "RAPID": "Rapid Movement of Funds", "DORMANT": "Dormant Account Activity"}
RULE_DESC = {"LARGE_CASH": "large cash activity", "STRUCT": "possible structuring",
             "VELOCITY": "high transaction velocity", "HRJ_WIRE": "wire involving a high-risk jurisdiction",
             "RAPID": "rapid movement of funds", "DORMANT": "dormant account activity"}
A_INVESTIGATORS = ["kalvarez", "mchen", "rokafor", "spatel", "tbrooks", "lnguyen"]
B_ANALYSTS = ["Dana Whitfield", "Omar Haddad", "Grace Liu", "Victor Ramos", "Nina Kowalski"]
ORGANIC_RULES = ["LARGE_CASH", "VELOCITY", "HRJ_WIRE", "STRUCT", "RAPID", "DORMANT"]
ORGANIC_P = [0.30, 0.25, 0.12, 0.10, 0.13, 0.10]


def organic_alerts(rng, acc, people_kind, people_risk, used, n_by_core, window_start, window_end):
    specs = []
    ws, we = np.datetime64(window_start), np.datetime64(window_end)
    days = (we - ws).astype(int)
    for core, n in n_by_core.items():
        a = acc[(acc["core"] == core) & (acc["status"] != "C") & (acc["product"] != "CD")
                & (~acc["person_id"].isin(used))]
        a = a.drop_duplicates("person_id")
        w = np.where(a["kind"] == "B", 4.0, 1.0) * np.where(a["person_id"].map(people_risk) == "H", 3.0, 1.0)
        pick = rng.choice(len(a), n, replace=True, p=w / w.sum())
        rules = rng.choice(ORGANIC_RULES, n, p=ORGANIC_P)
        for k, r in zip(pick, rules):
            specs.append({"core": core, "person_id": a["person_id"].iloc[k], "acct_idx": int(a.index[k]),
                          "rule": r, "date": ws + np.timedelta64(int(rng.integers(0, days + 1)), "D"),
                          "state": "AGE_BASED", "pattern_id": ""})
    return specs


def finalize(rng, specs, as_of):
    """Status, disposition, close date, score and owner for every alert."""
    asof = np.datetime64(as_of)
    out = []
    for s in specs:
        s = dict(s)
        age = int((asof - s["date"]).astype(int))
        state = s["state"]
        score = int(rng.integers(40, 96))
        if state == "OPEN":
            status, dispo, close = ("WIP" if rng.random() < 0.4 else "OPEN"), "", None
            score = int(rng.integers(78, 94))
        elif state == "CLOSED_FP_EXPLAINED":
            status, dispo = "CLOSED", "FP"
            close = s["date"] + np.timedelta64(int(rng.integers(4, 20)), "D")
        else:
            closed = age > 45 or rng.random() < 0.45
            if closed:
                u = rng.random()
                dispo = "FP" if u < 0.88 else ("NSR" if u < 0.96 else "SAR")
                dur = max(1, min(int(rng.lognormal(np.log(14), 0.6)), max(age, 1)))
                close = s["date"] + np.timedelta64(dur, "D")
                status = "CLOSED"
            else:
                status, dispo, close = ("WIP" if rng.random() < 0.45 else "OPEN"), "", None
        s.update(status=status, dispo=dispo, close=close, score=score)
        if s["core"] == "core_a":
            s["owner"] = A_INVESTIGATORS[int(rng.integers(0, len(A_INVESTIGATORS)))]
        else:
            s["owner"] = B_ANALYSTS[int(rng.integers(0, len(B_ANALYSTS)))]
        out.append(s)
    out.sort(key=lambda x: (x["core"], x["date"], x["person_id"]))
    return out


def facts_for(tx_by_acct, acct_idx, date):
    """Summarise the account's last 30 days of activity up to the alert date."""
    t = tx_by_acct.get(acct_idx)
    if t is None:
        return dict(n_cash=0, cash=0.0, n_near=0, wi=0.0, wo=0.0, max_item=0.0)
    lo = date - np.timedelta64(30, "D")
    w = t[(t["date"] > lo) & (t["date"] <= date)]
    cash = w[w["ttype"] == "CASH_DEP"]["amount_c"] / 100
    return dict(n_cash=int(len(cash)), cash=float(cash.sum()),
                n_near=int(((cash >= 7000) & (cash < 10000)).sum()),
                wi=float(w[w["ttype"] == "WIRE_IN"]["amount_c"].sum() / 100),
                wo=float(w[w["ttype"] == "WIRE_OUT"]["amount_c"].sum() / 100),
                max_item=float(w["amount_c"].max() / 100) if len(w) else 0.0)


def ts(date, rng, lo_h=9, hi_h=17):
    secs = int(rng.integers(lo_h * 3600, hi_h * 3600))
    return f"{pd.Timestamp(date).date()}T{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"


def notes_for(rng, alert, ref, cust_ref, f, profile, pattern):
    """Investigator notes for one alert. profile: dict with occupation, expected_cash, name."""
    notes = []
    d0 = alert["date"] + np.timedelta64(int(rng.integers(0, 3)), "D")
    who = alert["owner"]
    rd = RULE_DESC[alert["rule"]]
    ptype = pattern.get("pattern_type", "") if pattern else ""
    occ = profile.get("occupation", "not recorded")
    exp = profile.get("expected_cash", 0)

    if ptype == "SINGLE_CORE_STRUCTURING":
        triage = (f"Alert {ref} ({rd}). {f['n_near']} cash deposits between $7,000 and $10,000 in the last 30 days, "
                  f"${f['cash']:,.0f} in total, each below the $10,000 CTR threshold and made at different branches. "
                  f"KYC lists occupation '{occ}' with expected monthly cash of about ${exp:,.0f}. Pattern is consistent "
                  f"with possible structuring. Requested deposit slips and teller video.")
    elif ptype == "CASH_INTENSIVE_LEGITIMATE":
        triage = (f"Alert {ref} ({rd}). ${f['cash']:,.0f} in cash deposits over 30 days. Customer operates a "
                  f"{occ.lower()}; KYC expects about ${exp:,.0f} per month in cash. Deposits follow the usual weekly "
                  f"pattern and CTRs were filed for deposits over $10,000.")
    elif ptype == "RAPID_IN_OUT":
        triage = (f"Alert {ref} ({rd}). Inbound ${f['wi']:,.0f} followed by outbound ${f['wo']:,.0f} within about two "
                  f"days to unrelated third parties. Customer occupation '{occ}'; no wire activity expected in KYC. "
                  f"Contacting customer for the purpose of the transfers.")
    elif ptype == "DORMANT_REACTIVATION":
        triage = (f"Alert {ref} ({rd}). Account had been dormant for over a year and was reactivated with a large "
                  f"inbound transfer, then emptied through cash withdrawals and an outgoing wire within days. "
                  f"Identity re-verification not on file. Contacting customer.")
    else:
        triage = rng.choice([
            (f"Alert {ref} ({rd}) triaged. Last 30 days: {f['n_cash']} cash deposits totalling ${f['cash']:,.0f}; "
             f"wires in ${f['wi']:,.0f}; wires out ${f['wo']:,.0f}. KYC occupation '{occ}'. Requesting statements."),
            (f"Initial review of alert {ref}. Largest item in the review window ${f['max_item']:,.0f}. "
             f"Comparing with the prior six months and the KYC profile ('{occ}')."),
            (f"Alert {ref} opened for {rd}. Pulled 30-day activity and customer profile; occupation '{occ}', "
             f"expected monthly cash about ${exp:,.0f}. Review in progress."),
        ])
    notes.append((ts(d0, rng), who, triage))

    if alert["status"] == "CLOSED":
        c = alert["close"]
        if ptype == "CASH_INTENSIVE_LEGITIMATE":
            txt = ("Activity consistent with the business type and KYC profile; CTRs on file for large deposits. "
                   "No indicators of structuring. Closed as false positive.")
        elif ptype == "RAPID_IN_OUT":
            txt = ("Customer stated the funds related to a real estate closing and sent a settlement statement. "
                   "Closed as not suspicious.")
        elif alert["dispo"] == "FP":
            txt = rng.choice([
                "Activity consistent with stated occupation and prior six-month history. No indicators of structuring or third-party funding. Closed as false positive.",
                "Items are documented transfers between the customer's own accounts plus routine payroll and bill payments. Closed, not suspicious.",
                "Cash deposits match seasonal receipts noted in the KYC file. Closed as false positive.",
                "Wire relates to a documented property purchase; settlement statement on file. Closed as false positive.",
            ])
        elif alert["dispo"] == "NSR":
            txt = rng.choice([
                "Reviewed source-of-funds documents (vehicle sale). Explanation reasonable and documented. No SAR warranted.",
                "Customer provided inheritance paperwork covering the large deposits. Closed after review, no SAR.",
                "Tax refund and bonus explain the spike. Closed after review, no SAR.",
            ])
        else:
            txt = (f"Activity lacks an apparent business or lawful purpose: ${f['cash']:,.0f} cash and "
                   f"${f['wo']:,.0f} wires out in 30 days. Escalated to the BSA Officer. SAR filed "
                   f"{pd.Timestamp(c).date()}. Relationship placed on enhanced monitoring.")
        notes.append((ts(c, rng), who, txt))
    elif alert["status"] == "WIP":
        d1 = min(alert["date"] + np.timedelta64(int(rng.integers(3, 12)), "D"), np.datetime64("2026-08-31"))
        notes.append((ts(d1, rng), who, rng.choice([
            "Awaiting customer response to request for information.",
            "Documents requested from the branch; follow-up scheduled.",
            "Reviewed statements; need source-of-funds evidence before closing.",
        ])))
    return notes
