"""Branches, deposit accounts and loans for each core."""
import numpy as np
import pandas as pd

from . import vocab

A_PRODUCTS = {"DDA": "DDA", "SAV": "SAV", "MMA": "MMA", "CD": "CD"}
B_PRODUCTS = {"DDA": "Everyday Checking", "SAV": "Statement Savings", "MMA": "Money Market",
              "CD": "Certificate of Deposit"}
B_BIZ_DDA = "Business Checking"

LOAN_TYPES_I = ["AUTO", "MORT", "HELOC", "PERS"]
LOAN_P_I = [0.44, 0.24, 0.11, 0.21]
LOAN_SPEC = {  # median original, sigma, term years, rate range
    "AUTO": (21000, 0.45, 5, (5.9, 9.4)), "MORT": (210000, 0.50, 30, (3.1, 7.4)),
    "HELOC": (45000, 0.60, 10, (7.0, 9.6)), "PERS": (9000, 0.60, 4, (9.0, 15.5)),
    "CRE": (700000, 0.80, 10, (5.2, 8.6)), "CI": (220000, 0.90, 5, (6.4, 9.6)),
}
B_LOAN_NAMES = {"AUTO": "Auto Loan", "MORT": "Residential Mortgage", "HELOC": "Home Equity Line",
                "PERS": "Personal Loan", "CRE": "Commercial Real Estate", "CI": "Commercial & Industrial"}
CRE_KINDS = [("OFF", "Office building", 0.30), ("RET", "Retail strip center", 0.22),
             ("MF", "Apartment building", 0.25), ("IND", "Warehouse / light industrial", 0.13),
             ("CON", "Construction - residential subdivision", 0.10)]


def branches(n_a, n_b):
    towns = vocab.TOWNS
    a = pd.DataFrame({
        "BR_CD": [f"A{i:02d}" for i in range(1, n_a + 1)],
        "BR_NM": [f"{towns[i % len(towns)][0]} {'Main' if i == 0 else 'Branch'}" for i in range(n_a)],
        "CITY": [towns[i % len(towns)][0] for i in range(n_a)],
        "ST": [towns[i % len(towns)][1] for i in range(n_a)],
    })
    names = ["Pellbrook Downtown", "Marrow Point", "Wrenfield", "Linden Crossing", "Finch Harbor",
             "Stillwater Junction", "Osprey Hollow", "Copper Ridge"][:n_b]
    b_towns = ["Pellbrook", "Marrow Point", "Wrenfield", "Linden Crossing", "Finch Harbor",
               "Stillwater Junction", "Osprey Hollow", "Copper Ridge"][:n_b]
    state = {t[0]: t[1] for t in towns}
    b = pd.DataFrame({
        "branch_name": names, "branch_city": b_towns,
        "branch_state": [state[t] for t in b_towns],
        "opened_year": [str(1968 + 7 * i) for i in range(n_b)],
    })
    return a, b


def build_accounts(rng, owners, n_target, core, as_of, window_start, branch_codes, prof_org):
    """owners: DataFrame with person_id, kind, cust_since. Returns an internal accounts frame."""
    n_own = len(owners)
    kind = owners["kind"].values
    base_prod = np.where(kind == "B", "DDA", np.where(rng.random(n_own) < 0.88, "DDA", "SAV"))
    n_extra = n_target - n_own
    w = np.where(kind == "B", 3.0, 1.0)
    extra_owner = rng.choice(n_own, n_extra, p=w / w.sum())
    ek = kind[extra_owner]
    p_i = rng.random(n_extra)
    extra_prod = np.where(ek == "B",
                          np.select([p_i < .4, p_i < .7, p_i < .9], ["MMA", "SAV", "CD"], "DDA"),
                          np.select([p_i < .45, p_i < .65, p_i < .85], ["SAV", "MMA", "CD"], "DDA"))
    owner_idx = np.concatenate([np.arange(n_own), extra_owner])
    prod = np.concatenate([base_prod, extra_prod])
    n = len(owner_idx)

    since = owners["cust_since"].values.astype("datetime64[D]")[owner_idx]
    asof = np.datetime64(as_of)
    span = ((asof - np.timedelta64(7, "D")) - since).astype(int)
    span = np.maximum(span, 1)
    is_base = np.arange(n) < n_own
    open_off = np.where(is_base, (rng.random(n) * 0.1 * span).astype(int), (rng.random(n) * span).astype(int))
    open_dt = since + open_off.astype("timedelta64[D]")

    # home branch per owner, account branch mostly the same
    home = rng.choice(branch_codes, n_own)
    br = np.where(rng.random(n) < 0.85, home[owner_idx], rng.choice(branch_codes, n))

    acc = pd.DataFrame({
        "core": core, "person_id": owners["person_id"].values[owner_idx], "kind": kind[owner_idx],
        "product": prod, "branch": br, "open_dt": open_dt, "close_dt": pd.NaT,
        "status": "A", "dormant_since": pd.NaT, "reactivated_on": pd.NaT, "is_base": is_base,
        "role": "",
    })
    acc["rate"] = np.select(
        [acc["product"] == "CD", acc["product"] == "MMA", acc["product"] == "SAV"],
        [rng.uniform(3.5, 4.8, n), rng.uniform(1.0, 3.4, n), rng.uniform(0.05, 0.5, n)],
        rng.uniform(0.0, 0.1, n)).round(2)

    # closed accounts (never the owner's base account)
    cand = np.where(~is_base)[0]
    n_closed = int(prof_org["closed_account_pct"] * n)
    closed = rng.choice(cand, min(n_closed, len(cand)), replace=False)
    lo = np.datetime64("2025-01-01")
    open_d = acc["open_dt"].values.astype("datetime64[D]")
    end = np.datetime64("2026-08-20")
    for i in closed:
        start = max(open_d[i] + np.timedelta64(30, "D"), lo)
        if start >= end:
            continue
        acc.at[i, "close_dt"] = start + np.timedelta64(int(rng.integers(0, (end - start).astype(int))), "D")
        acc.at[i, "status"] = "C"
    home_map = dict(zip(owners["person_id"].values, home))
    return acc, home_map


def mark_dormant(rng, acc, n, since_lo, since_hi, role, exclude=None, reactivate=None, core=None):
    """Flag n active, old, non-CD accounts as dormant. Optionally reactivate them."""
    ok = (acc["status"] == "A") & (acc["product"] != "CD") & (acc["role"] == "") \
        & (acc["open_dt"] < pd.Timestamp(since_lo) - pd.Timedelta(days=400))
    if exclude is not None:
        ok &= ~acc["person_id"].isin(exclude)
    if core is not None:
        ok &= acc["core"] == core
    idx = rng.choice(np.where(ok)[0], n, replace=False)
    lo, hi = np.datetime64(since_lo), np.datetime64(since_hi)
    for i in idx:
        acc.at[i, "dormant_since"] = lo + np.timedelta64(int(rng.integers(0, (hi - lo).astype(int))), "D")
        acc.at[i, "status"] = "D"
        acc.at[i, "role"] = role
        if reactivate is not None:
            r_lo, r_hi = np.datetime64(reactivate[0]), np.datetime64(reactivate[1])
            acc.at[i, "reactivated_on"] = r_lo + np.timedelta64(int(rng.integers(0, (r_hi - r_lo).astype(int) + 1)), "D")
            acc.at[i, "status"] = "A"
    return idx


def build_loans(rng, owners, n_target, core, as_of, branch_codes):
    kind = owners["kind"].values
    biz = np.where(kind == "B")[0]
    ind = np.where(kind == "I")[0]
    n_biz = int(len(biz) * 1.6)
    biz_owner = np.concatenate([biz, rng.choice(biz, n_biz - len(biz))])
    biz_type = np.where(rng.random(n_biz) < 0.56, "CRE", "CI")
    n_ind = n_target - n_biz
    ind_owner = rng.choice(ind, n_ind)
    ind_type = rng.choice(LOAN_TYPES_I, n_ind, p=LOAN_P_I)
    owner_idx = np.concatenate([biz_owner, ind_owner])
    ltype = np.concatenate([biz_type, ind_type])
    n = len(owner_idx)
    asof = np.datetime64(as_of)

    orig, cur, rate, orig_dt, mat_dt, coll, occ = [], [], [], [], [], [], []
    cre_codes = [c[0] for c in CRE_KINDS]
    cre_p = [c[2] for c in CRE_KINDS]
    for t in ltype:
        med, sig, term, (rlo, rhi) = LOAN_SPEC[t]
        o = round(float(rng.lognormal(np.log(med), sig)), -2)
        age_days = int(rng.uniform(0.02, 0.95) * min(term, 12) * 365)
        od = asof - np.timedelta64(age_days, "D")
        md = od + np.timedelta64(term * 365, "D")
        frac = max(0.05, 1 - age_days / (term * 365) * (1.0 if t not in ("HELOC", "CI") else 0.5))
        orig.append(o)
        cur.append(round(o * frac, 2))
        rate.append(round(float(rng.uniform(rlo, rhi)), 3))
        orig_dt.append(od)
        mat_dt.append(md)
        if t == "CRE":
            k = rng.choice(cre_codes, p=cre_p)
            coll.append("CRE-" + k)
            occ.append("Y" if (k in ("OFF", "RET", "IND") and rng.random() < 0.25) else "N")
        elif t == "MORT":
            coll.append("RES")
            occ.append("Y" if rng.random() < 0.92 else "N")
        elif t == "HELOC":
            coll.append("RES2")
            occ.append("Y")
        elif t == "AUTO":
            coll.append("VEH")
            occ.append("")
        elif t == "PERS":
            coll.append("UNS")
            occ.append("")
        else:
            coll.append("BUS-ASSETS")
            occ.append("")
    u = rng.random(n)
    dpd = np.select([u < 0.955, u < 0.98, u < 0.99, u < 0.995],
                    [0, rng.integers(1, 30, n), rng.integers(30, 60, n), rng.integers(60, 90, n)],
                    rng.integers(90, 240, n))
    return pd.DataFrame({
        "core": core, "person_id": owners["person_id"].values[owner_idx], "ltype": ltype,
        "branch": rng.choice(branch_codes, n), "orig_dt": orig_dt, "mat_dt": mat_dt,
        "orig_amt": orig, "cur_prin": cur, "rate": rate, "coll": coll, "owner_occ": occ, "dpd": dpd,
    })


def b_collateral_desc(code, rng):
    if code.startswith("CRE-"):
        k = code[4:]
        d = dict((c[0], c[1]) for c in CRE_KINDS)[k]
        if k == "MF":
            d += f" ({int(rng.integers(8, 60))} units)"
        return d
    return {"RES": "Primary residence", "RES2": "Second lien - primary residence",
            "VEH": "Vehicle", "UNS": "Unsecured", "BUS-ASSETS": "Business equipment and receivables"}[code]
