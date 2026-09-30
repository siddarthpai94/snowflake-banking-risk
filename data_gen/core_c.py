"""Core C: a small third core with its own naming, formats and ID scheme.

Used only to prove the F9 onboarding skill works on a schema it has never seen.
Some Core C customers are the same people as Core A customers.
"""
import numpy as np
import pandas as pd

from . import people, vocab


def build(rng, prof, P, used, as_of, window_start):
    c = prof["core_c"]
    overlap_pool = P[(P["in_a"]) & (~P["in_b"]) & (~P["person_id"].isin(used))]
    ov = overlap_pool.iloc[rng.choice(len(overlap_pool), c["overlap_with_core_a"], replace=False)]
    new = people.build_individuals(rng, c["customers"] - len(ov), as_of)
    new["person_id"] = [f"PC{i:05d}" for i in range(1, len(new) + 1)]
    new["occupation"] = [vocab.OCCUPATIONS[i][0] for i in new.occ_idx]
    cols = ["person_id", "first", "last", "dob", "tin", "street_no", "street_word", "street_sfx",
            "town_idx", "zip_tail", "phone_tail", "area"]
    cust = pd.concat([ov[cols], new[cols]], ignore_index=True)
    cust = cust.iloc[rng.permutation(len(cust))].reset_index(drop=True)
    ids = people.unique_ids(rng, len(cust), 1_000_000, 2500)
    cust["custId"] = [f"C-{i:07d}" for i in ids]
    created = (np.datetime64("2010-01-01") + rng.integers(0, 5700, len(cust)).astype("timedelta64[D]"))

    def taxref(t):
        t = t.upper()
        return f"{t[0:4]}-{t[4:8]}-{t[8:12]}-{t[12:16]}"

    customers = pd.DataFrame({
        "custId": cust["custId"], "givenName": cust["first"], "familyName": cust["last"],
        "birthDate": pd.to_datetime(cust["dob"]).dt.strftime("%Y/%m/%d"),
        "taxRef": [taxref(t) for t in cust["tin"]],
        "addressLine": [f"{n} {w} {vocab.STREET_SUFFIX_LONG[s].upper()}" for n, w, s in
                        zip(cust["street_no"], cust["street_word"], cust["street_sfx"])],
        "cityName": [vocab.TOWNS[i][0] for i in cust["town_idx"]],
        "stateCode": [vocab.TOWNS[i][1] for i in cust["town_idx"]],
        "postalCode": [people.zip5(t, z) for t, z in zip(cust["town_idx"], cust["zip_tail"])],
        "mobile": [f"+1 {a} 555 {p:04d}" for a, p in zip(cust["area"], cust["phone_tail"])],
        "createdTs": ((created - np.datetime64("1970-01-01")).astype(int) * 86400).astype(str),
    })

    n_acc = c["accounts"]
    owner = np.concatenate([np.arange(len(cust)), rng.integers(0, len(cust), n_acc - len(cust))])
    atype = np.where(np.arange(n_acc) < len(cust), "CHK", np.where(rng.random(n_acc) < 0.7, "SVG", "CHK"))
    status = np.where(rng.random(n_acc) < 0.04, "2", np.where(rng.random(n_acc) < 0.05, "9", "1"))
    acc_ids = people.unique_ids(rng, n_acc, 50_000_000, 900)
    opened = np.datetime64("2012-01-01") + rng.integers(0, 5000, n_acc).astype("timedelta64[D]")
    accounts = pd.DataFrame({
        "accountId": [f"{i}" for i in acc_ids], "custId": cust["custId"].values[owner], "accountType": atype,
        "balanceAmt": [f"{v:.2f}" for v in np.where(status == "9", 0, rng.lognormal(np.log(5000), 1.1, n_acc))],
        "openedDate": pd.to_datetime(opened).strftime("%Y/%m/%d"), "statusCode": status,
    })

    active = np.where(status == "1")[0]
    days = (np.datetime64(as_of) - np.datetime64(window_start)).astype(int) + 1
    n_tx = rng.poisson(c["txns_per_account_month"] * days / 30, len(active))
    rep = np.repeat(active, n_tx)
    tcode = rng.choice(["CSHIN", "CSHOUT", "EFTIN", "EFTOUT", "POS"], len(rep), p=[.1, .1, .25, .2, .35])
    amt = rng.lognormal(np.log(120), 1.0, len(rep))
    sign = np.where(np.isin(tcode, ["CSHIN", "EFTIN"]), 1, -1)
    day = np.datetime64(window_start) + (rng.random(len(rep)) * days).astype(int).astype("timedelta64[D]")
    secs = ((day - np.datetime64("1970-01-01")).astype(int) * 86400 + rng.integers(13 * 3600, 23 * 3600, len(rep)))
    order = np.lexsort((secs,))
    post_ids = people.unique_ids(rng, len(rep), 900_000_000, 40)
    post_ids.sort()
    postings = pd.DataFrame({
        "postingId": [f"{i}" for i in post_ids],
        "accountId": accounts["accountId"].values[rep][order],
        "postedTs": secs[order].astype(str),
        "amt": [f"{v:.2f}" for v in (sign * amt)[order]],
        "typeCode": tcode[order],
        "channel": rng.choice(["branch", "atm", "web", "app", "card"], len(rep))[order],
    })
    person_map = pd.DataFrame({"person_id": cust["person_id"], "core": "core_c", "customer_ref": cust["custId"],
                               "record_role": np.where(cust["person_id"].str.startswith("PC"),
                                                       "core_c_only", "core_c_also_in_core_a")})
    return customers, accounts, postings, person_map
