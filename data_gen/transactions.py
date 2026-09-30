"""Organic transaction generation, legacy CTR flags, balances and per-core rendering.

Internal frame columns (one row per posted transaction):
  acct_idx, date (datetime64[D]), secs (seconds after midnight, local),
  ttype, amount_c (positive cents), channel, branch, ctr (bool),
  cpty, cpty_bank, pattern_id
"""
import numpy as np
import pandas as pd

from . import vocab

CREDIT = {"CASH_DEP", "ACH_CR", "WIRE_IN", "XFER_IN", "INT"}
CASH_IN = {"CASH_DEP"}
CASH_OUT = {"CASH_WD", "ATM_WD"}

RATES = {  # expected transactions per 30 days
    ("I", "DDA"): 6.0, ("I", "SAV"): 1.5, ("I", "MMA"): 1.0,
    ("B", "DDA"): 25.0, ("B", "SAV"): 1.5, ("B", "MMA"): 2.0,
}
MIX = {
    ("I", "DDA"): {"CARD": .42, "ATM_WD": .10, "CASH_DEP": .05, "ACH_CR": .12, "ACH_DR": .15,
                   "CHECK": .06, "XFER_OUT": .05, "XFER_IN": .05},
    ("I", "SAV"): {"XFER_IN": .45, "XFER_OUT": .30, "CASH_DEP": .10, "CASH_WD": .10, "INT": .05},
    ("I", "MMA"): {"XFER_IN": .40, "XFER_OUT": .30, "CHECK": .10, "WIRE_IN": .05, "WIRE_OUT": .05, "INT": .10},
    ("B", "DDA"): {"CARD": .15, "CASH_DEP": .08, "ACH_CR": .25, "ACH_DR": .25, "CHECK": .12,
                   "WIRE_IN": .04, "WIRE_OUT": .04, "XFER_IN": .035, "XFER_OUT": .035},
    ("B", "SAV"): {"XFER_IN": .45, "XFER_OUT": .35, "WIRE_IN": .05, "WIRE_OUT": .05, "INT": .10},
    ("B", "MMA"): {"XFER_IN": .45, "XFER_OUT": .35, "WIRE_IN": .05, "WIRE_OUT": .05, "INT": .10},
}
AMT = {  # (median $, sigma, cap $)
    ("I", "CARD"): (35, .9, 2000), ("I", "ATM_WD"): (80, .6, 800), ("I", "CASH_DEP"): (250, .9, 3000),
    ("I", "CASH_WD"): (300, .9, 3000), ("I", "ACH_CR"): (1800, .45, 9000), ("I", "ACH_DR"): (150, 1.0, 5000),
    ("I", "CHECK"): (180, 1.1, 8000), ("I", "XFER_IN"): (400, 1.0, 15000), ("I", "XFER_OUT"): (400, 1.0, 15000),
    ("I", "WIRE_IN"): (6000, 1.0, 60000), ("I", "WIRE_OUT"): (6000, 1.0, 60000), ("I", "INT"): (3, 1.0, 400),
    ("B", "CARD"): (180, 1.0, 9000), ("B", "CASH_DEP"): (900, .8, 8000), ("B", "ACH_CR"): (3500, 1.0, 90000),
    ("B", "ACH_DR"): (2000, 1.1, 90000), ("B", "CHECK"): (2500, 1.0, 60000), ("B", "WIRE_IN"): (25000, 1.0, 400000),
    ("B", "WIRE_OUT"): (25000, 1.0, 400000), ("B", "XFER_IN"): (5000, 1.0, 100000),
    ("B", "XFER_OUT"): (5000, 1.0, 100000), ("B", "INT"): (40, 1.0, 3000),
}
CHANNEL = {"CASH_DEP": [("BRANCH", .85), ("ATM", .15)], "CASH_WD": [("BRANCH", 1.0)],
           "ATM_WD": [("ATM", 1.0)], "ACH_CR": [("SYSTEM", 1.0)], "ACH_DR": [("SYSTEM", 1.0)],
           "WIRE_IN": [("BRANCH", .4), ("ONLINE", .6)], "WIRE_OUT": [("BRANCH", .4), ("ONLINE", .6)],
           "CHECK": [("SYSTEM", 1.0)], "CARD": [("SYSTEM", 1.0)], "XFER_IN": [("ONLINE", .5), ("MOBILE", .5)],
           "XFER_OUT": [("ONLINE", .5), ("MOBILE", .5)], "INT": [("SYSTEM", 1.0)]}
HOURS = {"BRANCH": (9 * 3600, 17 * 3600), "ATM": (6 * 3600, 23 * 3600), "ONLINE": (0, 86399),
         "MOBILE": (0, 86399), "SYSTEM": (2 * 3600, 7 * 3600)}

A_TXN_CODE = {"CASH_DEP": "CDEP", "CASH_WD": "CWDR", "ATM_WD": "ATMW", "ACH_CR": "ACHC", "ACH_DR": "ACHD",
              "WIRE_IN": "WIRI", "WIRE_OUT": "WIRO", "CHECK": "CHKP", "CARD": "CARD", "XFER_IN": "XFRI",
              "XFER_OUT": "XFRO", "INT": "INTC"}
B_TXN_DESC = {"CASH_DEP": "Cash Deposit", "CASH_WD": "Cash Withdrawal", "ATM_WD": "ATM Withdrawal",
              "ACH_CR": "ACH Credit", "ACH_DR": "ACH Debit", "WIRE_IN": "Incoming Wire",
              "WIRE_OUT": "Outgoing Wire", "CHECK": "Check Paid", "CARD": "Debit Card Purchase",
              "XFER_IN": "Transfer In", "XFER_OUT": "Transfer Out", "INT": "Interest Credit"}
A_CHANNEL = {"BRANCH": "BR", "ATM": "ATM", "ONLINE": "OLB", "MOBILE": "MOB", "SYSTEM": "SYS"}
B_CHANNEL = {"BRANCH": "Teller", "ATM": "ATM", "ONLINE": "Online Banking", "MOBILE": "Mobile App",
             "SYSTEM": "System"}


def organic(rng, acc, window_start, window_end):
    """Organic activity for every account active in the window."""
    ws, we = np.datetime64(window_start), np.datetime64(window_end)
    start = np.maximum(acc["open_dt"].values.astype("datetime64[D]"), ws)
    end = np.full(len(acc), we)
    closed = acc["close_dt"].notna().values
    end[closed] = np.minimum(acc["close_dt"].values[closed].astype("datetime64[D]") - np.timedelta64(1, "D"), we)
    react = acc["reactivated_on"].notna().values
    start[react] = np.maximum(start[react], acc["reactivated_on"].values[react].astype("datetime64[D]"))
    dormant = (acc["status"].values == "D")
    skip = dormant | (acc["product"].values == "CD") | acc["role"].isin(["inj_dormant"]).values
    days = (end - start).astype(int) + 1
    days[skip | (days <= 0)] = 0

    frames = []
    for (kind, prod), rate in RATES.items():
        m = (acc["kind"].values == kind) & (acc["product"].values == prod) & (days > 0)
        idx = np.where(m)[0]
        if len(idx) == 0:
            continue
        lam = np.full(len(idx), rate / 30.0)
        lam[react[idx]] = 1.0 / 30.0  # legitimately reactivated accounts stay quiet
        n = rng.poisson(lam * days[idx])
        rep = np.repeat(idx, n)
        if len(rep) == 0:
            continue
        off = (rng.random(len(rep)) * days[rep]).astype(int)
        date = start[rep] + off.astype("timedelta64[D]")
        mix = MIX[(kind, prod)]
        ttype = rng.choice(list(mix), len(rep), p=np.array(list(mix.values())) / sum(mix.values()))
        amt = np.zeros(len(rep))
        for t in mix:
            tm = ttype == t
            med, sig, cap = AMT[(kind, t)]
            amt[tm] = np.minimum(rng.lognormal(np.log(med), sig, tm.sum()), cap)
        atm = ttype == "ATM_WD"
        amt[atm] = rng.choice([20, 40, 60, 80, 100, 140, 200, 300, 400, 500], atm.sum())
        amt = np.maximum(amt, 1.0)
        frames.append(pd.DataFrame({"acct_idx": rep, "date": date, "ttype": ttype,
                                    "amount_c": np.round(amt * 100).astype(np.int64)}))
    tx = pd.concat(frames, ignore_index=True)
    tx["pattern_id"] = ""
    return tx


def assign_channels(rng, tx, acc, branch_pool):
    """Fill channel, time, branch and counterparties for rows missing them."""
    n = len(tx)
    need = tx["channel"].isna() if "channel" in tx else pd.Series(True, index=tx.index)
    if "channel" not in tx:
        for c in ["channel", "branch", "cpty", "cpty_bank"]:
            tx[c] = None
        tx["secs"] = -1
        tx["ctr"] = False
    idx = np.where(need.values)[0]
    tt = tx["ttype"].values[idx]
    ch = np.empty(len(idx), dtype=object)
    for t, opts in CHANNEL.items():
        m = tt == t
        if m.any():
            ch[m] = rng.choice([o[0] for o in opts], m.sum(), p=[o[1] for o in opts])
    secs = np.zeros(len(idx), dtype=np.int64)
    for c, (lo, hi) in HOURS.items():
        m = ch == c
        secs[m] = rng.integers(lo, hi, m.sum())
    secs[tt == "INT"] = 300
    tx.loc[tx.index[idx], "channel"] = ch
    tx.loc[tx.index[idx], "secs"] = secs

    acct_branch = acc["branch"].values[tx["acct_idx"].values[idx]]
    core = acc["core"].values[tx["acct_idx"].values[idx]]
    other = np.array([rng.choice(branch_pool[c]) for c in core], dtype=object)
    br = np.where(rng.random(len(idx)) < 0.75, acct_branch, other)
    br = np.where(ch == "BRANCH", br, "")
    tx.loc[tx.index[idx], "branch"] = br

    cp = np.full(len(idx), "", dtype=object)
    cb = np.full(len(idx), "", dtype=object)
    named = np.isin(tt, ["ACH_CR", "ACH_DR", "CHECK", "CARD"])
    cp[named] = rng.choice(vocab.COUNTERPARTIES, named.sum())
    wire = np.isin(tt, ["WIRE_IN", "WIRE_OUT"])
    cp[wire] = rng.choice(vocab.COUNTERPARTIES + [f"{s} Holdings" for s in ("Birch", "Summit", "Alder")], wire.sum())
    cb[wire] = rng.choice(vocab.EXTERNAL_BANKS, wire.sum())
    tx.loc[tx.index[idx], "cpty"] = cp
    tx.loc[tx.index[idx], "cpty_bank"] = cb
    return tx


def legacy_ctr_flags(tx, acc):
    """Each legacy core files a CTR when one person's cash in, or cash out, exceeds
    $10,000 in a business day *within that core*. Nothing aggregates across cores."""
    t = tx.copy()
    t["core"] = acc["core"].values[t["acct_idx"].values]
    t["person_id"] = acc["person_id"].values[t["acct_idx"].values]
    t["dir"] = np.where(t["ttype"].isin(CASH_IN), "in", np.where(t["ttype"].isin(CASH_OUT), "out", ""))
    cash = t[t["dir"] != ""]
    g = cash.groupby(["core", "person_id", "date", "dir"])["amount_c"].transform("sum")
    flag_idx = cash.index[g.values > 1_000_000]
    tx["ctr"] = False
    tx.loc[flag_idx, "ctr"] = True
    return tx


def balances(rng, tx, acc):
    """Current balance = opening + net activity; opening is big enough that the
    running balance never goes negative."""
    sign = np.where(tx["ttype"].isin(CREDIT), 1, -1)
    t = pd.DataFrame({"acct_idx": tx["acct_idx"].values, "date": tx["date"].values,
                      "secs": tx["secs"].values, "signed": sign * tx["amount_c"].values})
    t = t.sort_values(["acct_idx", "date", "secs"], kind="mergesort")
    t["run"] = t.groupby("acct_idx")["signed"].cumsum()
    mins = t.groupby("acct_idx")["run"].min()
    net = t.groupby("acct_idx")["signed"].sum()
    n = len(acc)
    med = {"DDA": 4000, "SAV": 8000, "MMA": 60000, "CD": 40000}
    base = np.array([rng.lognormal(np.log(med[p] * (8 if k == "B" else 1)), 1.0)
                     for p, k in zip(acc["product"].values, acc["kind"].values)])
    opening = np.round(base * 100).astype(np.int64)
    min_run = np.zeros(n, dtype=np.int64)
    min_run[mins.index.values] = mins.values
    opening = np.maximum(opening, -min_run + 5_000)
    netv = np.zeros(n, dtype=np.int64)
    netv[net.index.values] = net.values
    bal = opening + netv
    bal[acc["status"].values == "C"] = 0
    return bal


def b_offset(dates):
    """US Eastern offset: EDT from 2026-03-08 to 2026-11-01."""
    d = pd.to_datetime(dates)
    edt = (d >= "2026-03-08") & (d < "2026-11-01")
    return np.where(edt, "-04:00", "-05:00")
