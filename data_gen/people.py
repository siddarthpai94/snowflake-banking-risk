"""True people and businesses, and how each core records them.

A person exists once in reality (person_id). Each core renders its own
customer record in its own format. Duplicates are the same person in both
cores; look-alikes are different people who resemble each other.
"""
import numpy as np
import pandas as pd

from . import vocab

SURNAMES = list(dict.fromkeys(vocab.SURNAMES))
NICK_KEYS = sorted(vocab.NICKNAMES)
AREA_CODES = {"OH": ["330", "440", "216", "419"], "PA": ["412", "724", "814"], "WV": ["304", "681"]}


def _hex_tokens(rng, n, width=16):
    """Unique hex tokens (synthetic stand-ins for tokenised SSN/EIN)."""
    out, seen = [], set()
    while len(out) < n:
        for v in rng.integers(0, 2**63 - 1, size=(n - len(out)) * 2, dtype=np.int64):
            tok = f"{int(v):016x}"[:width]
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
                if len(out) == n:
                    break
    return out


def unique_ids(rng, n, start, max_gap):
    """Unique increasing integers with random gaps, then shuffled."""
    ids = start + np.cumsum(rng.integers(1, max_gap, size=n))
    rng.shuffle(ids)
    return ids


def uuids(rng, n):
    raw = rng.integers(0, 256, size=(n, 16), dtype=np.uint8)
    raw[:, 6] = (raw[:, 6] & 0x0F) | 0x40
    raw[:, 8] = (raw[:, 8] & 0x3F) | 0x80
    h = raw.tobytes().hex()
    return [f"{h[i:i+8]}-{h[i+8:i+12]}-{h[i+12:i+16]}-{h[i+16:i+20]}-{h[i+20:i+32]}"
            for i in range(0, 32 * n, 32)]


def _dob(rng, n, as_of):
    # adult ages 18-92, mode around 45
    age_days = (np.clip(rng.normal(46, 15, n), 18.2, 92) * 365.25).astype(int)
    return (np.datetime64(as_of) - age_days.astype("timedelta64[D]"))


def build_individuals(rng, n, as_of):
    gender = rng.integers(0, 2, n)
    first = np.where(gender == 0,
                     rng.choice(vocab.FIRST_MALE, n),
                     rng.choice(vocab.FIRST_FEMALE, n))
    last = rng.choice(SURNAMES, n)
    mid = np.array(list("ABCDEFGHIJKLMNOPRSTW"))[rng.integers(0, 20, n)]
    mid = np.where(rng.random(n) < 0.15, "", mid)
    town_idx = rng.integers(0, len(vocab.TOWNS), n)
    df = pd.DataFrame({
        "gender": gender, "first": first, "middle": mid, "last": last, "suffix": "",
        "dob": _dob(rng, n, as_of),
        "tin": _hex_tokens(rng, n),
        "street_no": rng.integers(10, 9990, n),
        "street_word": rng.choice(vocab.STREET_WORDS, n),
        "street_sfx": rng.choice(vocab.STREET_SUFFIX, n),
        "town_idx": town_idx,
        "zip_tail": rng.integers(0, 3, n) * 17 + 1,
        "phone_tail": rng.integers(0, 10000, n),
        "email_n": rng.integers(1, 99, n),
        "occ_idx": rng.integers(0, len(vocab.OCCUPATIONS), n),
        "kind": "I",
    })
    df["area"] = [AREA_CODES[vocab.TOWNS[t][1]][p % len(AREA_CODES[vocab.TOWNS[t][1]])]
                  for t, p in zip(df.town_idx, df.phone_tail)]
    return df


def build_businesses(rng, n):
    idx = rng.integers(0, len(vocab.BUSINESS_TYPES), n)
    owner = rng.choice(SURNAMES, n)
    town_idx = rng.integers(0, len(vocab.TOWNS), n)
    names = [f"{o} {vocab.BUSINESS_TYPES[i][0]} {vocab.BUSINESS_TYPES[i][1]}" for o, i in zip(owner, idx)]
    df = pd.DataFrame({
        "biz_name": names, "biz_type_idx": idx,
        "tin": _hex_tokens(rng, n),
        "street_no": rng.integers(10, 9990, n),
        "street_word": rng.choice(vocab.STREET_WORDS, n),
        "street_sfx": rng.choice(vocab.STREET_SUFFIX, n),
        "town_idx": town_idx, "zip_tail": rng.integers(0, 3, n) * 17 + 1,
        "phone_tail": rng.integers(0, 10000, n), "kind": "B",
    })
    df["area"] = [AREA_CODES[vocab.TOWNS[t][1]][0] for t in df.town_idx]
    df["cash_intensive"] = [vocab.BUSINESS_TYPES[i][3] for i in idx]
    df["expected_cash"] = [vocab.BUSINESS_TYPES[i][2] for i in idx]
    return df


def typo(rng, s):
    """One realistic keying error: substitution, deletion or transposition."""
    if len(s) < 4:
        return s + "e"
    i = int(rng.integers(1, len(s) - 1))
    kind = int(rng.integers(0, 3))
    if kind == 0:
        c = "aeiou"[int(rng.integers(0, 5))] if s[i] not in "aeiou" else "rnstl"[int(rng.integers(0, 5))]
        return s[:i] + c + s[i + 1:]
    if kind == 1:
        return s[:i] + s[i + 1:]
    return s[:i - 1] + s[i] + s[i - 1] + s[i + 1:]


def build_people(rng, prof, as_of):
    """Return (individuals, businesses_a, businesses_b, links, lookalikes).

    individuals: one row per true person with in_a / in_b flags, duplicate tier,
    and Core B variation fields.
    """
    dup = prof["duplicates"]
    n_dup = dup["tier_a_clean"] + dup["tier_b_variant"] + dup["tier_c_hard"]
    la = prof["lookalikes"]
    n_look = la["jr_sr_same_address"] + la["twins"] + la["same_name_same_dob"]
    a_only = prof["core_a"]["individuals"] - n_dup
    b_only = prof["core_b"]["individuals"] - n_dup
    n_random = n_dup + a_only + (b_only - n_look)

    P = build_individuals(rng, n_random, as_of)
    P["in_a"] = False
    P["in_b"] = False
    P["tier"] = ""
    P["variation"] = ""
    P.loc[: n_dup - 1, ["in_a", "in_b"]] = True
    P.loc[n_dup: n_dup + a_only - 1, "in_a"] = True
    P.loc[n_dup + a_only:, "in_b"] = True
    tiers = (["A"] * dup["tier_a_clean"] + ["B"] * dup["tier_b_variant"] + ["C"] * dup["tier_c_hard"])
    P.loc[: n_dup - 1, "tier"] = tiers

    # Core B rendering fields default to the true values
    for col in ["first", "middle", "last", "street_no", "street_word", "street_sfx", "town_idx",
                "zip_tail", "phone_tail", "area", "email_n"]:
        P["b_" + col] = P[col]
    P["b_tin_missing"] = False
    P["b_suffix"] = ""

    # Tier A: formatting-only differences, plus common benign drift
    ia = np.arange(0, dup["tier_a_clean"])
    drop_mid = ia[rng.random(len(ia)) < 0.35]
    P.loc[drop_mid, "b_middle"] = ""
    new_email = ia[rng.random(len(ia)) < 0.30]
    P.loc[new_email, "b_email_n"] = rng.integers(100, 199, len(new_email))
    P.loc[ia, "variation"] = "format_only"

    # Tier B and C: a real variation; C also loses the tax-id token in Core B
    def vary(i):
        r = rng.random()
        first = P.at[i, "first"]
        if r < 0.40 and first in vocab.NICKNAMES:
            P.at[i, "b_first"] = rng.choice(vocab.NICKNAMES[first])
            return "nickname"
        if r < 0.70:
            P.at[i, "b_last"] = typo(rng, P.at[i, "last"])
            return "surname_typo"
        P.at[i, "b_street_no"] = int(rng.integers(10, 9990))
        P.at[i, "b_street_word"] = rng.choice(vocab.STREET_WORDS)
        P.at[i, "b_town_idx"] = int(rng.integers(0, len(vocab.TOWNS)))
        P.at[i, "b_phone_tail"] = int(rng.integers(0, 10000))
        return "moved_address"

    for i in range(dup["tier_a_clean"], n_dup):
        P.at[i, "variation"] = vary(i)
    ic = np.arange(dup["tier_a_clean"] + dup["tier_b_variant"], n_dup)
    P.loc[ic, "b_tin_missing"] = True
    P.loc[ic, "variation"] = P.loc[ic, "variation"] + "+token_missing"

    # Look-alikes: pick A-only people (X) and build a distinct B-only person (Y) from each
    a_only_idx = np.arange(n_dup, n_dup + a_only)
    xs = rng.choice(a_only_idx, n_look, replace=False)
    types = (["JR_SR"] * la["jr_sr_same_address"] + ["TWINS"] * la["twins"]
             + ["SAME_NAME_DOB"] * la["same_name_same_dob"])
    Y = build_individuals(rng, n_look, as_of)
    Y["in_a"] = False
    Y["in_b"] = True
    Y["tier"] = ""
    Y["variation"] = ""
    for j, (x, t) in enumerate(zip(xs, types)):
        Y.at[j, "last"] = P.at[x, "last"]
        if t == "JR_SR":
            Y.at[j, "first"] = P.at[x, "first"]
            Y.at[j, "gender"] = P.at[x, "gender"]
            P.at[x, "suffix"] = "SR"
            Y.at[j, "suffix"] = "JR"
            # father is 24-34 years older than son; keep son adult
            gap = int(rng.integers(24, 35)) * 365
            son = P.at[x, "dob"] + np.timedelta64(gap, "D")
            if son > np.datetime64(as_of) - np.timedelta64(19 * 365, "D"):
                P.at[x, "dob"] = P.at[x, "dob"] - np.timedelta64(gap, "D")
                son = P.at[x, "dob"] + np.timedelta64(gap, "D")
            Y.at[j, "dob"] = son
            for c in ["street_no", "street_word", "street_sfx", "town_idx", "zip_tail"]:
                Y.at[j, c] = P.at[x, c]
        elif t == "TWINS":
            Y.at[j, "dob"] = P.at[x, "dob"]
            for c in ["street_no", "street_word", "street_sfx", "town_idx", "zip_tail"]:
                Y.at[j, c] = P.at[x, c]
            # different first name, sometimes sharing an initial
            pool = vocab.FIRST_MALE if Y.at[j, "gender"] == 0 else vocab.FIRST_FEMALE
            f = rng.choice(pool)
            while f == P.at[x, "first"]:
                f = rng.choice(pool)
            Y.at[j, "first"] = f
        else:
            Y.at[j, "first"] = P.at[x, "first"]
            Y.at[j, "gender"] = P.at[x, "gender"]
            Y.at[j, "dob"] = P.at[x, "dob"]
    for col in ["first", "middle", "last", "street_no", "street_word", "street_sfx", "town_idx",
                "zip_tail", "phone_tail", "area", "email_n"]:
        Y["b_" + col] = Y[col]
    Y["b_suffix"] = Y["suffix"]
    # Junior's record in Core B often omits the suffix
    jr = np.array([t == "JR_SR" for t in types])
    omit = jr & (rng.random(n_look) < 0.5)
    Y.loc[omit, "b_suffix"] = ""
    missing = rng.choice(n_look, la["core_b_token_missing"], replace=False)
    Y["b_tin_missing"] = False
    Y.loc[missing, "b_tin_missing"] = True

    P = pd.concat([P, Y], ignore_index=True)
    P["person_id"] = [f"P{i:06d}" for i in range(1, len(P) + 1)]
    look = pd.DataFrame({
        "x": P.loc[xs, "person_id"].values,
        "y": P["person_id"].iloc[len(P) - n_look:].values,
        "type": types,
        "b_token_missing": Y["b_tin_missing"].values,
    })

    ba = build_businesses(rng, prof["core_a"]["businesses"])
    bb = build_businesses(rng, prof["core_b"]["businesses"])
    ba["person_id"] = [f"B{i:05d}" for i in range(1, len(ba) + 1)]
    bb["person_id"] = [f"B{i:05d}" for i in range(len(ba) + 1, len(ba) + len(bb) + 1)]
    ba["in_a"], ba["in_b"] = True, False
    bb["in_a"], bb["in_b"] = False, True

    # relationship start and occupation-driven expected cash
    for df in (P, ba, bb):
        years = np.clip(rng.exponential(9, len(df)), 0.2, 35)
        df["cust_since"] = np.datetime64(as_of) - (years * 365.25).astype(int).astype("timedelta64[D]")
    P["expected_cash"] = [vocab.OCCUPATIONS[i][1] for i in P.occ_idx]
    P["occupation"] = [vocab.OCCUPATIONS[i][0] for i in P.occ_idx]
    P["b_occupation"] = P["occupation"]
    P["risk_a"] = np.where(rng.random(len(P)) < 0.03, "H", np.where(rng.random(len(P)) < 0.15, "M", "L"))
    P["risk_b"] = np.where(P["risk_a"] == "H", "4", np.where(P["risk_a"] == "M", "3", "2"))
    return P, ba, bb, look


# ---------- rendering ----------

def fmt_ymd(d):
    return pd.Series(d).dt.strftime("%Y%m%d").values


def town(i):
    return vocab.TOWNS[int(i)]


def zip5(town_idx, tail):
    return f"{town(town_idx)[2]}{int(tail):02d}"


def render_core_a_customers(rng, P, ba, a_ids):
    """Core A customer rows. a_ids maps person_id -> CIF_NO."""
    Pa = P[P.in_a]
    rows = []
    for r in Pa.itertuples(index=False):
        t = town(r.town_idx)
        rows.append({
            "CIF_NO": str(a_ids[r.person_id]), "CUST_TYPE": "I",
            "FIRST_NM": r.first, "MID_INIT": r.middle, "LAST_NM": r.last, "SFX": r.suffix,
            "BUS_NM": "", "BIRTH_DT": pd.Timestamp(r.dob).strftime("%Y%m%d"),
            "TAX_ID_TKN": r.tin.upper(),
            "ADDR_LN1": f"{r.street_no} {r.street_word} {r.street_sfx}",
            "CITY": t[0], "ST": t[1], "ZIP5": zip5(r.town_idx, r.zip_tail),
            "PHONE_NO": f"{r.area}555{r.phone_tail:04d}",
            "EMAIL_ADDR": f"{r.first.lower()}.{r.last.lower()}{r.email_n}@example.com",
            "CUST_SINCE_DT": pd.Timestamp(r.cust_since).strftime("%Y%m%d"),
            "RISK_RTG": r.risk_a, "OCCUP_DESC": r.occupation, "HOME_BR_CD": "",
        })
    for r in ba.itertuples(index=False):
        t = town(r.town_idx)
        rows.append({
            "CIF_NO": str(a_ids[r.person_id]), "CUST_TYPE": "B",
            "FIRST_NM": "", "MID_INIT": "", "LAST_NM": "", "SFX": "",
            "BUS_NM": r.biz_name, "BIRTH_DT": "00000000", "TAX_ID_TKN": r.tin.upper(),
            "ADDR_LN1": f"{r.street_no} {r.street_word} {r.street_sfx}",
            "CITY": t[0], "ST": t[1], "ZIP5": zip5(r.town_idx, r.zip_tail),
            "PHONE_NO": f"{r.area}555{r.phone_tail:04d}",
            "EMAIL_ADDR": f"office{r.phone_tail % 97}@example.org",
            "CUST_SINCE_DT": pd.Timestamp(r.cust_since).strftime("%Y%m%d"),
            "RISK_RTG": "M" if r.cash_intensive else "L",
            "OCCUP_DESC": vocab.BUSINESS_TYPES[r.biz_type_idx][0], "HOME_BR_CD": "",
        })
    return pd.DataFrame(rows)


def render_core_b_party(rng, P, bb, b_ids):
    """Core B party rows. b_ids maps person_id -> party_uuid."""
    Pb = P[P.in_b]
    rows = []
    for r in Pb.itertuples(index=False):
        t = town(r.b_town_idx)
        name = f"{r.b_last.upper()}, {r.b_first.upper()}" + (f" {r.b_middle}" if r.b_middle else "")
        if r.b_suffix:
            name += f" {r.b_suffix}"
        sfx_long = vocab.STREET_SUFFIX_LONG[r.b_street_sfx]
        rows.append({
            "party_uuid": b_ids[r.person_id], "party_kind": "PERSON", "full_name": name,
            "dob": pd.Timestamp(r.dob).strftime("%m/%d/%Y"),
            "ssn_token": "" if r.b_tin_missing else "tkn_" + r.tin.lower(),
            "street": f"{r.b_street_no} {r.b_street_word} {sfx_long}",
            "city_state_zip": f"{t[0]}, {t[1]} {zip5(r.b_town_idx, r.b_zip_tail)}",
            "phone_num": f"({r.b_area}) 555-{r.b_phone_tail:04d}",
            "email_addr": f"{r.b_first.lower()}{r.b_last.lower()[:1]}{r.b_email_n}@example.net",
            "relationship_start": pd.Timestamp(r.cust_since).strftime("%Y-%m-%d"),
            "kyc_risk": r.risk_b, "employer_or_industry": r.b_occupation, "home_branch": "",
        })
    for r in bb.itertuples(index=False):
        t = town(r.town_idx)
        rows.append({
            "party_uuid": b_ids[r.person_id], "party_kind": "ORG", "full_name": r.biz_name.upper(),
            "dob": "", "ssn_token": "tkn_" + r.tin.lower(),
            "street": f"{r.street_no} {r.street_word} {vocab.STREET_SUFFIX_LONG[r.street_sfx]}",
            "city_state_zip": f"{t[0]}, {t[1]} {zip5(r.town_idx, r.zip_tail)}",
            "phone_num": f"({r.area}) 555-{r.phone_tail:04d}",
            "email_addr": f"accounts{r.phone_tail % 89}@example.org",
            "relationship_start": pd.Timestamp(r.cust_since).strftime("%Y-%m-%d"),
            "kyc_risk": "3" if r.cash_intensive else "2",
            "employer_or_industry": vocab.BUSINESS_TYPES[r.biz_type_idx][0], "home_branch": "",
        })
    return pd.DataFrame(rows)
