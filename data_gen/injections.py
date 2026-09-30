"""Injected risk patterns. Every injection writes a ground-truth row.

Each injector returns transaction rows (fully specified: channel, time, branch,
counterparty) plus ground-truth pattern records and legacy-alert specs.
"""
import math

import numpy as np
import pandas as pd

from . import vocab


def business_days(start, end):
    d = pd.bdate_range(start, end)
    return [np.datetime64(x.date()) for x in d]


class Injector:
    def __init__(self, rng, acc, persons, branch_pool, cfg):
        self.rng = rng
        self.acc = acc
        self.persons = persons          # DataFrame indexed by person_id (individuals and businesses)
        self.branch_pool = branch_pool  # core -> list of branch codes/names
        self.cfg = cfg
        self.rows = []
        self.patterns = []
        self.alerts = []                # legacy alert specs
        self.used = set()
        self._n = 0

    # ---------- helpers ----------
    def base_dda(self, person_id, core):
        if not hasattr(self, "_dda"):
            a = self.acc
            m = (a["product"] == "DDA") & (a["status"] == "A") & a["close_dt"].isna()
            sub = a[m]
            self._dda = {}
            for i, p, c in zip(sub.index, sub["person_id"], sub["core"]):
                self._dda.setdefault((p, c), int(i))
        i = self._dda.get((person_id, core))
        if i is None or self.acc.at[i, "role"] != "":
            return None
        return i

    def eligible(self, pool, cores):
        """People from pool who have an active, unused DDA in every listed core."""
        out = []
        for pid in pool:
            if pid in self.used:
                continue
            accts = [self.base_dda(pid, c) for c in cores]
            if all(x is not None for x in accts):
                out.append((pid, accts))
        return out

    def pid(self, prefix):
        self._n += 1
        return f"{prefix}-{self._n:04d}"

    def row(self, acct_idx, date, secs, ttype, cents, channel, branch="", cpty="", cpty_bank="", pattern=""):
        self.rows.append({"acct_idx": acct_idx, "date": np.datetime64(date, "D"), "secs": int(secs),
                          "ttype": ttype, "amount_c": int(cents), "channel": channel, "branch": branch,
                          "cpty": cpty, "cpty_bank": cpty_bank, "pattern_id": pattern, "ctr": False})

    def split(self, total, lo=7000, hi=9900, step=10):
        k = math.ceil(total / 9700)
        for _ in range(500):
            w = 1 + self.rng.uniform(-0.09, 0.09, k)
            amts = np.round(total * w / w.sum() / step) * step
            amts[-1] = round(total - amts[:-1].sum(), 2)
            if (amts >= lo).all() and (amts < hi).all():
                return [float(a) for a in amts]
        raise RuntimeError(f"cannot split {total}")

    def mark(self, acct_idx, role):
        self.acc.at[acct_idx, "role"] = role

    # ---------- patterns ----------
    def cross_core_structuring(self, tier_a_people, n, n_missed_ctr, n_kyc_conflict):
        rng = self.rng
        cands = self.eligible(tier_a_people, ["core_a", "core_b"])
        chosen = [cands[i] for i in rng.choice(len(cands), n, replace=False)]
        days = business_days("2026-08-03", "2026-08-28")
        out = []
        for j, (pid, (ia, ib)) in enumerate(chosen):
            self.used.add(pid)
            self.mark(ia, "inj_xcore")
            self.mark(ib, "inj_xcore")
            pat = self.pid("XCS")
            total = round(float(rng.uniform(51000, 58500)), -1)
            a_tot = round(float(rng.uniform(max(total - 29500, 21500), 29500)), -1)
            b_tot = total - a_tot
            a_amts, b_amts = self.split(a_tot), self.split(b_tot)
            missed = j < n_missed_ctr
            pick = list(rng.choice(len(days), len(a_amts) + len(b_amts) - (1 if missed else 0), replace=False))
            a_days = [days[i] for i in pick[:len(a_amts)]]
            b_days = [days[i] for i in pick[len(a_amts):]]
            if missed:
                b_days = [a_days[0]] + b_days       # same business day in both cores
            missed_day = str(a_days[0]) if missed else ""
            for amt, d in zip(a_amts, a_days):
                self.row(ia, d, rng.integers(9 * 3600 + 1800, 16 * 3600 + 1800), "CASH_DEP", amt * 100,
                         "BRANCH", rng.choice(self.branch_pool["core_a"]), pattern=pat)
            for amt, d in zip(b_amts, b_days):
                self.row(ib, d, rng.integers(9 * 3600 + 1800, 16 * 3600 + 1800), "CASH_DEP", amt * 100,
                         "BRANCH", rng.choice(self.branch_pool["core_b"]), pattern=pat)
            wire = ""
            if j % 5 < 3:  # 60% move most of it out by wire
                last = max(a_days + b_days)
                wd = min(np.datetime64(last) + np.timedelta64(int(rng.integers(1, 4)), "D"), np.datetime64("2026-08-31"))
                amt = round(total * float(rng.uniform(0.6, 0.85)), 2)
                cp = rng.choice(vocab.SHELL_COUNTERPARTIES)
                self.row(ia, wd, rng.integers(10 * 3600, 15 * 3600), "WIRE_OUT", amt * 100, "ONLINE",
                         cpty=cp, cpty_bank=rng.choice(vocab.EXTERNAL_BANKS), pattern=pat)
                wire = f"; wire out ${amt:,.2f} to {cp} on {wd}"
            codes = ["XCORE_CASH_30D", "NEAR_THRESHOLD_CASH", "KYC_MISMATCH"]
            if missed:
                codes.append("CTR_AGGREGATION_MISSED")
            conflict = j >= n - n_kyc_conflict
            if conflict:
                codes.append("KYC_INCONSISTENT_ACROSS_CORES")
            out.append(pid)
            self.patterns.append({
                "pattern_id": pat, "pattern_type": "XCORE_STRUCTURING", "person_id": pid,
                "cores": "core_a;core_b", "acct_idx": [ia, ib],
                "window_start": str(min(a_days + b_days)), "window_end": str(max(a_days + b_days)),
                "total_amount_usd": f"{total:.2f}", "expected_reason_codes": ";".join(codes),
                "legacy_alerts": [],
                "detail": (f"Core A ${a_tot:,.2f} in {len(a_amts)} deposits; Core B ${b_tot:,.2f} in "
                           f"{len(b_amts)} deposits; each deposit under $10,000; each core under its "
                           f"$30,000 legacy rule" + (f"; same-day cross-core cash on {missed_day} with no CTR" if missed else "")
                           + wire),
                "missed_ctr_day": missed_day, "kyc_conflict": conflict,
            })
        return out

    def single_core_structuring(self, pools, counts):
        rng = self.rng
        days = business_days("2026-07-27", "2026-08-24")
        for core, pool, n in [("core_a", pools["core_a"], counts[0]), ("core_b", pools["core_b"], counts[1])]:
            cands = self.eligible(pool, [core])
            for i in rng.choice(len(cands), n, replace=False):
                pid, (ia,) = cands[i]
                self.used.add(pid)
                self.mark(ia, "inj_single")
                pat = self.pid("SCS")
                total = round(float(rng.uniform(34000, 46000)), -1)
                amts = self.split(total)
                ds = sorted(days[k] for k in rng.choice(len(days), len(amts), replace=False))
                for amt, d in zip(amts, ds):
                    self.row(ia, d, rng.integers(9 * 3600 + 1800, 16 * 3600 + 1800), "CASH_DEP", amt * 100,
                             "BRANCH", rng.choice(self.branch_pool[core]), pattern=pat)
                ad = min(np.datetime64(ds[-1]) + np.timedelta64(int(rng.integers(1, 5)), "D"), np.datetime64("2026-08-29"))
                self.alerts.append({"core": core, "person_id": pid, "acct_idx": ia, "rule": "STRUCT",
                                    "date": ad, "state": "OPEN", "pattern_id": pat})
                self.patterns.append({
                    "pattern_id": pat, "pattern_type": "SINGLE_CORE_STRUCTURING", "person_id": pid,
                    "cores": core, "acct_idx": [ia], "window_start": str(ds[0]), "window_end": str(ds[-1]),
                    "total_amount_usd": f"{total:.2f}",
                    "expected_reason_codes": "NEAR_THRESHOLD_CASH;KYC_MISMATCH", "legacy_alerts": ["pending"],
                    "detail": f"{len(amts)} cash deposits between $7,000 and $9,900 totalling ${total:,.2f} in one core; legacy alert open",
                })

    def cash_intensive(self, biz_frames, counts):
        """Legitimate cash-heavy businesses. High cash, but KYC explains it."""
        rng = self.rng
        cash_types = [i for i, b in enumerate(vocab.BUSINESS_TYPES) if b[3]]
        weeks = pd.date_range("2026-03-02", "2026-08-31", freq="W-MON")
        for core, bdf, n in [("core_a", biz_frames["core_a"], counts[0]), ("core_b", biz_frames["core_b"], counts[1])]:
            cands = self.eligible(list(bdf["person_id"]), [core])
            for i in rng.choice(len(cands), n, replace=False):
                pid, (ia,) = cands[i]
                self.used.add(pid)
                self.mark(ia, "inj_cashbiz")
                r = bdf.index[bdf["person_id"] == pid][0]
                t = int(rng.choice(cash_types))
                owner = bdf.at[r, "biz_name"].split(" ")[0]
                bdf.at[r, "biz_type_idx"] = t
                bdf.at[r, "biz_name"] = f"{owner} {vocab.BUSINESS_TYPES[t][0]} {vocab.BUSINESS_TYPES[t][1]}"
                bdf.at[r, "cash_intensive"] = True
                expected = round(float(rng.uniform(65000, 95000)), -3)
                bdf.at[r, "expected_cash"] = expected
                pat = self.pid("CIB")
                total = 0.0
                for wk in weeks:
                    weekly = expected * float(rng.uniform(0.85, 1.15)) / 4.33
                    for off, share in ((0, 0.6), (3, 0.4)):
                        d = np.datetime64((wk + pd.Timedelta(days=off)).date())
                        if d > np.datetime64("2026-08-31"):
                            continue
                        amt = round(weekly * share * float(rng.uniform(0.9, 1.1)), 2)
                        total += amt
                        self.row(ia, d, rng.integers(9 * 3600, 11 * 3600), "CASH_DEP", amt * 100, "BRANCH",
                                 self.acc.at[ia, "branch"], pattern=pat)
                n_alerts = 1 + int(rng.random() < 0.5)
                for k in range(n_alerts):
                    ad = np.datetime64("2026-03-20") + np.timedelta64(int(rng.integers(0, 110)), "D")
                    self.alerts.append({"core": core, "person_id": pid, "acct_idx": ia, "rule": "LARGE_CASH",
                                        "date": ad, "state": "CLOSED_FP_EXPLAINED", "pattern_id": pat})
                self.patterns.append({
                    "pattern_id": pat, "pattern_type": "CASH_INTENSIVE_LEGITIMATE", "person_id": pid,
                    "cores": core, "acct_idx": [ia], "window_start": "2026-03-02", "window_end": "2026-08-31",
                    "total_amount_usd": f"{total:.2f}", "expected_reason_codes": "EXPECTED_LOW_RISK_KYC_CONSISTENT",
                    "legacy_alerts": ["pending"],
                    "detail": f"{vocab.BUSINESS_TYPES[t][0]}; expected monthly cash ${expected:,.0f}; CTRs filed on deposits over $10,000",
                    "expected_cash": expected,
                })

    def rapid_in_out(self, pools, counts, n_with_alert):
        rng = self.rng
        days = business_days("2026-03-16", "2026-08-24")
        k = 0
        for core, pool, n in [("core_a", pools["core_a"], counts[0]), ("core_b", pools["core_b"], counts[1])]:
            cands = self.eligible(pool, [core])
            for i in rng.choice(len(cands), n, replace=False):
                pid, (ia,) = cands[i]
                self.used.add(pid)
                self.mark(ia, "inj_rapid")
                pat = self.pid("RIO")
                d = days[int(rng.integers(0, len(days)))]
                t0 = int(rng.integers(10 * 3600, 15 * 3600))
                inflow = round(float(rng.uniform(40000, 150000)), 0)
                in_type = "WIRE_IN" if rng.random() < 0.6 else "ACH_CR"
                src = rng.choice(vocab.SHELL_COUNTERPARTIES)
                self.row(ia, d, t0, in_type, inflow * 100, "SYSTEM" if in_type == "ACH_CR" else "ONLINE",
                         cpty=src, cpty_bank=rng.choice(vocab.EXTERNAL_BANKS), pattern=pat)
                m = int(rng.integers(2, 5))
                out_total = round(inflow * float(rng.uniform(0.90, 0.98)), 2)
                w = rng.dirichlet(np.ones(m) * 3)
                outs = np.round(out_total * w, 2)
                outs[-1] = round(out_total - outs[:-1].sum(), 2)
                offs = np.sort(rng.uniform(0.5, 46, m)) * 3600
                last = d
                for amt, o in zip(outs, offs):
                    ts = t0 + int(o)
                    od = np.datetime64(d) + np.timedelta64(ts // 86400, "D")
                    last = max(last, od)
                    typ = "WIRE_OUT" if rng.random() < 0.7 else "ACH_DR"
                    dest = rng.choice([s for s in vocab.SHELL_COUNTERPARTIES if s != src])
                    self.row(ia, od, ts % 86400, typ, amt * 100, "ONLINE" if typ == "WIRE_OUT" else "SYSTEM",
                             cpty=dest, cpty_bank=rng.choice(vocab.EXTERNAL_BANKS), pattern=pat)
                alert = k < n_with_alert
                if alert:
                    self.alerts.append({"core": core, "person_id": pid, "acct_idx": ia, "rule": "RAPID",
                                        "date": np.datetime64(d) + np.timedelta64(int(rng.integers(1, 4)), "D"),
                                        "state": "AGE_BASED", "pattern_id": pat})
                k += 1
                self.patterns.append({
                    "pattern_id": pat, "pattern_type": "RAPID_IN_OUT", "person_id": pid, "cores": core,
                    "acct_idx": [ia], "window_start": str(d), "window_end": str(last),
                    "total_amount_usd": f"{inflow:.2f}", "expected_reason_codes": "RAPID_IN_OUT",
                    "legacy_alerts": ["pending"] if alert else [],
                    "detail": f"{in_type} ${inflow:,.0f} from {src}; {m} outflows totalling ${out_total:,.2f} "
                              f"({out_total / inflow:.0%}) within 48 hours",
                })

    def dormant_reactivation(self, acct_idx_list, n_with_alert):
        rng = self.rng
        for k, ia in enumerate(acct_idx_list):
            a = self.acc
            core = a.at[ia, "core"]
            pid = a.at[ia, "person_id"]
            self.used.add(pid)
            pat = self.pid("DRA")
            r = a.at[ia, "reactivated_on"]
            d = np.datetime64(pd.Timestamp(r).date())
            inflow = round(float(rng.uniform(15000, 60000)), 0)
            typ = "WIRE_IN" if rng.random() < 0.5 else "ACH_CR"
            src = rng.choice(vocab.SHELL_COUNTERPARTIES)
            self.row(ia, d, rng.integers(9 * 3600, 16 * 3600), typ, inflow * 100,
                     "ONLINE" if typ == "WIRE_IN" else "SYSTEM", cpty=src,
                     cpty_bank=rng.choice(vocab.EXTERNAL_BANKS), pattern=pat)
            out_total = round(inflow * float(rng.uniform(0.85, 1.0)), 2)
            n_cash = int(rng.integers(1, 3))
            cash = [round(float(rng.uniform(3000, 9500)), -1) for _ in range(n_cash)]
            if sum(cash) > out_total * 0.8:
                cash = [round(out_total * 0.3, -1)]
            wire = round(out_total - sum(cash), 2)
            offs = sorted(int(x) for x in rng.integers(1, 10, len(cash) + 1))
            for c, o in zip(cash, offs):
                self.row(ia, min(d + np.timedelta64(o, "D"), np.datetime64("2026-08-31")),
                         rng.integers(9 * 3600, 16 * 3600), "CASH_WD", c * 100, "BRANCH",
                         rng.choice(self.branch_pool[core]), pattern=pat)
            dest = rng.choice([s for s in vocab.SHELL_COUNTERPARTIES if s != src])
            last = min(d + np.timedelta64(offs[-1], "D"), np.datetime64("2026-08-31"))
            self.row(ia, last, rng.integers(10 * 3600, 15 * 3600), "WIRE_OUT", wire * 100, "ONLINE",
                     cpty=dest, cpty_bank=rng.choice(vocab.EXTERNAL_BANKS), pattern=pat)
            alert = k < n_with_alert
            if alert:
                self.alerts.append({"core": core, "person_id": pid, "acct_idx": ia, "rule": "DORMANT",
                                    "date": min(d + np.timedelta64(int(rng.integers(2, 6)), "D"), np.datetime64("2026-08-30")),
                                    "state": "OPEN", "pattern_id": pat})
            ds = pd.Timestamp(a.at[ia, "dormant_since"]).date()
            self.patterns.append({
                "pattern_id": pat, "pattern_type": "DORMANT_REACTIVATION", "person_id": pid, "cores": core,
                "acct_idx": [ia], "window_start": str(d), "window_end": str(last),
                "total_amount_usd": f"{inflow:.2f}", "expected_reason_codes": "DORMANT_REACTIVATION",
                "legacy_alerts": ["pending"] if alert else [],
                "detail": f"Dormant since {ds}; {typ} ${inflow:,.0f} from {src} on reactivation, "
                          f"then ${out_total:,.2f} out ({len(cash)} cash withdrawals and a wire) within 10 days",
            })
