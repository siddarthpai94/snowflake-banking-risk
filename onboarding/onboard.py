"""Onboard a new core system from its extract files: profile, map to the canonical model, generate SQL. No AI.

  python -m onboarding.onboard --core core_c --files data/out/demo/core_c --out build/onboard/core_c

Steps
  1. Profile every column of every file: formats (dates, epoch seconds, ISO timestamps, money, cents, IDs,
     UUIDs, tax tokens, phones, ZIPs, states, emails, names, small code sets) from a sample of rows.
  2. Decide what each file holds (customers, accounts, transactions, loans, alerts) from its name and columns.
  3. Map each canonical field to the best column by name (abbreviations expanded) AND by content; a column
     whose content does not fit a field is never chosen. Links between files are found by value overlap.
  4. Translate code values (CHK, SVG, EFTIN, ...) with a reviewed vocabulary; anything unknown is listed
     for a person to review instead of guessed.
  5. Write: mapping.yaml (same format as config/mappings/core_*.yaml, plus confidence and a review list),
     10_bronze.sql (tables + COPY), 20_canonical.sql (canonical views), 30_dq_tests.sql (checks).
"""
import argparse
import csv
import gzip
import io
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

SAMPLE_ROWS = 3000

# ------------------------------------------------------------------ 1. profiling
DATE_FORMATS = [("YYYYMMDD", r"\d{8}", "%Y%m%d"), ("YYYY-MM-DD", r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
                ("YYYY/MM/DD", r"\d{4}/\d{2}/\d{2}", "%Y/%m/%d"), ("MM/DD/YYYY", r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y")]
US_STATES = set("""AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY
NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC""".split())


def _valid_date(v, fmt):
    try:
        d = datetime.strptime(v, fmt)
        return 1900 <= d.year <= 2100
    except ValueError:
        return False


def detect_kinds(values):
    """Return {kind: share of non-empty values that fit} for the kinds this column could be."""
    vals = [v.strip() for v in values if v is not None and v.strip() != ""]
    if not vals:
        return {"empty": 1.0}, {}
    n = len(vals)
    share = lambda pred: sum(1 for v in vals if pred(v)) / n     # noqa: E731
    kinds, extra = {}, {}
    for label, rx, fmt in DATE_FORMATS:
        s = share(lambda v: re.fullmatch(rx, v) and _valid_date(v, fmt))
        if s >= 0.95:
            kinds["date"] = s
            extra["date_format"] = label
            break
    s = share(lambda v: re.fullmatch(r"\d{10}", v) and 946684800 <= int(v) <= 2208988800)
    if s >= 0.95:
        kinds["epoch_seconds"] = s
    s = share(lambda v: re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*", v))
    if s >= 0.95:
        kinds["iso_timestamp"] = s
    s = share(lambda v: re.fullmatch(r"\d{6}", v) and int(v[:2]) < 24 and int(v[2:4]) < 60)
    if s >= 0.95:
        kinds["hhmmss"] = s
    if share(lambda v: re.fullmatch(r"-?\d+\.\d{2}", v)) >= 0.95:
        kinds["money"] = 1.0
        extra["has_negative"] = any(v.startswith("-") for v in vals)
    if share(lambda v: re.fullmatch(r"-?\d+(\.\d+)?", v)) >= 0.98:
        kinds["number"] = 1.0
        extra["has_negative"] = extra.get("has_negative") or any(v.startswith("-") for v in vals)
    if share(lambda v: re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", v.lower())) >= 0.95:
        kinds["uuid"] = 1.0
    # tax token: 16 hex digits once any prefix ("tkn_") and separators are removed, and not plain digits
    def tokenish(v):
        core = re.sub(r"[^0-9a-f]", "", re.sub(r"^[a-z]+_", "", v.lower()))
        return len(core) == 16 and not v.isdigit()
    if share(tokenish) >= 0.95:
        kinds["tax_token"] = 1.0
    if share(lambda v: len(re.sub(r"\D", "", v)) in (10, 11) and not re.fullmatch(r"\d{8}", v)
             and re.search(r"[\s()+\-]|^\d{10}$", v)) >= 0.95:
        kinds["phone"] = 1.0
    if share(lambda v: re.fullmatch(r"\d{5}", v)) >= 0.95:
        kinds["zip5"] = 1.0
    if share(lambda v: v.upper() in US_STATES and len(v) == 2) >= 0.95:
        kinds["state"] = 1.0
    if share(lambda v: re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", v.lower())) >= 0.95:
        kinds["email"] = 1.0
    if share(lambda v: re.fullmatch(r"[A-Za-z .'\-]+, [A-Za-z .'\-]+( .+)?", v)) >= 0.6:
        kinds["name_last_first"] = 1.0
    if share(lambda v: re.fullmatch(r".+, [A-Z]{2} \d{5}", v)) >= 0.95:
        kinds["city_state_zip"] = 1.0
    if share(lambda v: re.fullmatch(r"[A-Za-z][A-Za-z'\-]+( [A-Za-z][A-Za-z'\-]+)?", v)) >= 0.9:
        kinds["word"] = 1.0
    if share(lambda v: re.fullmatch(r"\d+ .+", v)) >= 0.9:
        kinds["street"] = 1.0
    distinct = Counter(vals)
    extra["distinct"] = len(distinct)
    extra["unique_ratio"] = len(distinct) / n
    if len(distinct) <= 25 and n >= 20:
        kinds["code"] = 1.0
        extra["codes"] = sorted(distinct)
    if extra["unique_ratio"] >= 0.98 and len(distinct) >= 20:
        kinds["id"] = 1.0
        extra["id_pattern"] = _id_pattern(list(distinct)[:200])
    return kinds, extra


def _id_pattern(samples):
    shapes = Counter(re.sub(r"[0-9]", "9", re.sub(r"[a-f]", "x", s.lower())) for s in samples)
    return shapes.most_common(1)[0][0]


FULL_VALUES_CAP = 250_000      # keep every distinct value of a column up to this many (for key links)


def read_sample(path, n=SAMPLE_ROWS):
    """One pass over the whole file: a reproducible random sample of rows (reservoir), and for each column
    its complete set of distinct values while that stays under FULL_VALUES_CAP."""
    import random
    rnd = random.Random(0)
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows, full = [], [set() for _ in header]
        total = 0
        for r in reader:
            total += 1
            if len(rows) < n:
                rows.append(r)
            else:
                j = rnd.randrange(total)
                if j < n:
                    rows[j] = r
            for i, v in enumerate(r):
                s = full[i]
                if s is not None:
                    v = v.strip()
                    if v:
                        s.add(v)
                        if len(s) > FULL_VALUES_CAP:
                            full[i] = None
    return header, rows, full, total


def profile_file(path):
    header, rows, full, total = read_sample(path)
    cols = {}
    for j, name in enumerate(header):
        values = [r[j] if j < len(r) else "" for r in rows]
        kinds, extra = detect_kinds(values)
        if full[j] is not None and len(full[j]) <= 25 and "code" in kinds:
            extra["codes"] = sorted(full[j])               # every code in the file, not just the sample
        nonempty = [v for v in values if v.strip()]
        cols[name] = {"kinds": kinds, **extra, "null_share": round(1 - len(nonempty) / max(len(values), 1), 3),
                      "samples": nonempty[:3], "values": set(v.strip() for v in nonempty), "all_values": full[j]}
    return {"file": path.name, "header": header, "columns": cols, "rows_sampled": len(rows), "rows_total": total}


# ------------------------------------------------------------------ 2-3. canonical model and matching
ABBREV = {"nm": "name", "dt": "date", "tkn": "token", "cd": "code", "bal": "balance", "amt": "amount",
          "acct": "account", "cust": "customer", "cif": "customer", "txn": "transaction", "addr": "address",
          "st": "state", "br": "branch", "ts": "timestamp", "tm": "time", "no": "number", "num": "number",
          "prin": "principal", "orig": "original", "mat": "maturity", "stat": "status", "typ": "type",
          "prod": "product", "dob": "birth", "ssn": "tax", "zip5": "zip", "sfx": "suffix", "mid": "middle",
          "init": "initial", "occup": "occupation", "rtg": "rating", "chnl": "channel", "cpty": "counterparty",
          "id": "id", "ref": "reference", "desc": "description", "flg": "flag", "dpd": "days_past_due",
          "dorm": "dormant", "react": "reactivated", "int": "interest", "pct": "percent", "tel": "phone"}
SYNONYM = {"family": "last", "surname": "last", "given": "first", "forename": "first", "postal": "zip",
           "postcode": "zip", "mobile": "phone", "cell": "phone", "posted": "post", "posting": "transaction",
           "ledger": "balance", "opened": "open", "created": "open", "party": "customer", "client": "customer",
           "member": "customer", "birthdate": "birth", "taxref": "tax", "town": "city", "employer": "occupation",
           "industry": "occupation", "booked": "original", "delinquent": "days_past_due", "note": "loan",
           "case": "alert", "scenario": "alert", "kind": "type", "dr": "direction", "cr": "direction"}


def name_tokens(col):
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", col)            # camelCase -> camel Case
    parts = re.split(r"[\s_\-]+", parts.lower())
    out = set()
    for p in parts:
        if not p:
            continue
        p = ABBREV.get(p, p)
        p = SYNONYM.get(p, p)
        out.update(p.split("_") if p != "days_past_due" else [p])
    return out


# field -> (name tokens that suggest it, kinds allowed, how to build the expression)
FIELDS = {
    "customer": {
        "key": ({"customer", "id", "number", "uuid"}, {"id", "uuid"}),
        "party_kind": ({"customer", "type"}, {"code"}),
        "first_name": ({"first", "name"}, {"word"}),
        "last_name": ({"last", "name"}, {"word"}),
        "full_name": ({"full", "name"}, {"name_last_first"}),
        "birth_date": ({"birth", "date"}, {"date"}),
        "tax_token": ({"tax", "token", "id", "reference"}, {"tax_token"}),
        "street": ({"address", "street", "line"}, {"street"}),
        "city": ({"city"}, {"word"}),
        "state": ({"state"}, {"state"}),
        "zip": ({"zip"}, {"zip5"}),
        "city_state_zip": ({"city", "state", "zip"}, {"city_state_zip"}),
        "phone": ({"phone"}, {"phone"}),
        "email": ({"email"}, {"email"}),
        "customer_since": ({"open", "since", "start", "relationship"}, {"date", "epoch_seconds"}),
    },
    "account": {
        "key": ({"account", "id", "number", "reference"}, {"id"}),
        "customer_key": ({"customer", "id", "uuid"}, {"id", "uuid", "code", "number"}),
        "product_type": ({"product", "type", "account"}, {"code"}),
        "opened_on": ({"open", "date"}, {"date"}),
        "status": ({"status"}, {"code"}),
        "balance_usd": ({"balance", "amount", "current"}, {"money", "number"}),
    },
    "transaction": {
        "key": ({"transaction", "id", "uuid"}, {"id", "uuid"}),
        "account_key": ({"account", "id", "number", "reference"}, {"id", "number", "code"}),
        "posted_at": ({"post", "timestamp", "date"}, {"epoch_seconds", "iso_timestamp", "date"}),
        "posted_time": ({"post", "time"}, {"hhmmss"}),
        "txn_type": ({"type", "code", "transaction", "description"}, {"code"}),
        "amount": ({"amount"}, {"money", "number"}),
        "direction": ({"direction"}, {"code"}),
        "channel": ({"channel"}, {"code"}),
    },
}

SPECIFIC_KINDS = {"date", "epoch_seconds", "iso_timestamp", "tax_token", "phone", "zip5", "state", "email",
                  "money", "uuid", "name_last_first", "city_state_zip", "street", "hhmmss"}

FILE_HINTS = {"customer": {"customer", "customers", "party", "client", "member", "cif"},
              "account": {"account", "accounts", "deposit", "acct"},
              "transaction": {"transaction", "transactions", "txn", "txns", "posting", "postings"},
              "loan": {"loan", "loans", "note"}, "alert": {"alert", "alerts", "case"}}

VOCAB = {
    "party_kind": {"I": "PERSON", "IND": "PERSON", "PERSON": "PERSON", "INDIVIDUAL": "PERSON", "P": "PERSON",
                   "B": "ORG", "BUS": "ORG", "ORG": "ORG", "BUSINESS": "ORG", "O": "ORG"},
    "product_type": {"CHK": "CHECKING", "DDA": "CHECKING", "CHECKING": "CHECKING", "EVERYDAY CHECKING": "CHECKING",
                     "BUSINESS CHECKING": "CHECKING", "SAV": "SAVINGS", "SVG": "SAVINGS", "SAVINGS": "SAVINGS",
                     "STATEMENT SAVINGS": "SAVINGS", "MMA": "MONEY_MARKET", "MONEY MARKET": "MONEY_MARKET",
                     "CD": "CERTIFICATE", "CERTIFICATE OF DEPOSIT": "CERTIFICATE"},
    "status": {"A": "OPEN", "OPEN": "OPEN", "ACTIVE": "OPEN", "D": "DORMANT", "DORMANT": "DORMANT",
               "C": "CLOSED", "CLOSED": "CLOSED"},
    "txn_type": {"CDEP": "CASH_DEPOSIT", "CSHIN": "CASH_DEPOSIT", "CASH DEPOSIT": "CASH_DEPOSIT",
                 "CWDR": "CASH_WITHDRAWAL", "CSHOUT": "CASH_WITHDRAWAL", "CASH WITHDRAWAL": "CASH_WITHDRAWAL",
                 "ATMW": "ATM_WITHDRAWAL", "ATM WITHDRAWAL": "ATM_WITHDRAWAL",
                 "ACHC": "ACH_CREDIT", "EFTIN": "ACH_CREDIT", "ACH CREDIT": "ACH_CREDIT",
                 "ACHD": "ACH_DEBIT", "EFTOUT": "ACH_DEBIT", "ACH DEBIT": "ACH_DEBIT",
                 "WIRI": "WIRE_IN", "INCOMING WIRE": "WIRE_IN", "WIRO": "WIRE_OUT", "OUTGOING WIRE": "WIRE_OUT",
                 "CHKP": "CHECK_PAID", "CHECK PAID": "CHECK_PAID", "CARD": "CARD_PURCHASE", "POS": "CARD_PURCHASE",
                 "DEBIT CARD PURCHASE": "CARD_PURCHASE", "XFRI": "TRANSFER_IN", "TRANSFER IN": "TRANSFER_IN",
                 "XFRO": "TRANSFER_OUT", "TRANSFER OUT": "TRANSFER_OUT", "INTC": "INTEREST",
                 "INTEREST CREDIT": "INTEREST"},
    "channel": {"BR": "BRANCH", "BRANCH": "BRANCH", "TELLER": "BRANCH", "ATM": "ATM", "OLB": "ONLINE",
                "WEB": "ONLINE", "ONLINE": "ONLINE", "ONLINE BANKING": "ONLINE", "MOB": "MOBILE", "APP": "MOBILE",
                "MOBILE": "MOBILE", "MOBILE APP": "MOBILE", "SYS": "SYSTEM", "SYSTEM": "SYSTEM"},
}


def classify_file(prof):
    stem = set(re.split(r"[\s_\-.]+", prof["file"].lower().replace(".csv", "").replace(".gz", "")))
    scores = {}
    for ent, hints in FILE_HINTS.items():
        s = 3 * len(stem & hints)
        if ent in FIELDS:
            s += sum(1 for f, (toks, kinds) in FIELDS[ent].items() if f != "key" and any(
                (name_tokens(c) & toks) and (kinds & set(p["kinds"])) for c, p in prof["columns"].items()))
        scores[ent] = s
    best = max(scores, key=scores.get)
    return best, scores


def _score(col, prof_col, toks, kinds):
    if not (kinds & set(prof_col["kinds"])):
        return 0.0
    ct = name_tokens(col)
    overlap = len(ct & toks)
    return overlap + 0.25 * (overlap / max(len(ct), 1))


def map_entity(entity, prof):
    """Pick one column per canonical field. Returns {field: (column, score)}."""
    chosen, used = {}, set()
    # key first: most unique id-like column whose name fits, preferring the first column
    cands = []
    for i, (c, p) in enumerate(prof["columns"].items()):
        toks, kinds = FIELDS[entity]["key"]
        s = _score(c, p, toks, kinds)
        if s > 0:
            cands.append((s + (0.5 if i == 0 else 0), c))
    if cands:
        s, c = max(cands)
        chosen["key"] = (c, round(s, 2))
        used.add(c)
    for field, (toks, kinds) in FIELDS[entity].items():
        if field == "key":
            continue
        best = max(((_score(c, p, toks, kinds), c) for c, p in prof["columns"].items() if c not in used),
                   default=(0, None))
        if best[0] >= 1:
            chosen[field] = (best[1], round(best[0], 2))
            used.add(best[1])
    return chosen


def link_by_values(child_prof, child_col_candidates, parent_prof, parent_key):
    """Choose the child column whose values overlap most with the parent's key values."""
    parent_vals = parent_prof["columns"][parent_key]["all_values"] or parent_prof["columns"][parent_key]["values"]
    best = (0.0, None)
    for c in child_col_candidates:
        vals = child_prof["columns"][c]["values"]
        if vals:
            ov = len(vals & parent_vals) / len(vals)
            best = max(best, (ov, c))
    return best


# ------------------------------------------------------------------ 4. expressions
def q(col):
    return '"' + col.replace('"', '""') + '"'


def date_expr(col, prof_col):
    if "date" in prof_col["kinds"]:
        return f"TRY_TO_DATE({q(col)}, '{prof_col['date_format']}')"
    if "epoch_seconds" in prof_col["kinds"]:
        return f"TO_DATE(TO_TIMESTAMP_NTZ(TRY_TO_NUMBER({q(col)})))"
    return f"TRY_TO_DATE({q(col)})"


def decode_expr(col, field, prof_col, review):
    vocab = VOCAB.get(field, {})
    pairs, unknown = [], []
    for v in prof_col.get("codes", []):
        target = vocab.get(v.upper().strip())
        if target:
            pairs.append((v, target))
        else:
            unknown.append(v)
    if unknown:
        review.append({"field": field, "column": col, "issue": "code values not in the reviewed vocabulary",
                       "values": unknown, "action": "add them to VOCAB or to the mapping by hand"})
    if not pairs:
        return None
    args = ", ".join(f"'{a}', '{b}'" for a, b in pairs)
    return f"DECODE({q(col)}, {args})"


def build_mapping(core, files):
    profiles = {p.name: profile_file(p) for p in files}
    by_entity, review, notes = {}, [], []
    # assign file -> entity best score first (never first come), one file per entity, minimum score 3
    pairs = []
    for name, prof in profiles.items():
        _, scores = classify_file(prof)
        pairs += [(sc, name, ent, scores) for ent, sc in scores.items()]
    taken_files = set()
    for sc, name, ent, scores in sorted(pairs, key=lambda x: (-x[0], x[1], x[2])):
        if sc < 3 or name in taken_files or ent in by_entity:
            continue
        by_entity[ent] = (name, profiles[name], scores)
        taken_files.add(name)
    for name in profiles:
        if name not in taken_files:
            notes.append(f"{name}: not mapped (reference or out-of-scope file)")
    for ent in ("loan", "alert"):
        if ent in by_entity:
            notes.append(f"{by_entity[ent][0]}: recognised as {ent}s; mapping {ent}s is not automated yet (map by hand, "
                         f"see config/mappings/core_a.yaml)")
    mapping = {"source_system": core, "label": f"{core} (onboarded by onboarding)",
               "generated_by": "onboarding/onboard.py (rules, no AI)"}
    confidence = {}
    for ent in ("customer", "account", "transaction"):
        if ent not in by_entity:
            continue
        fname, prof, _ = by_entity[ent]
        chosen = map_entity(ent, prof)
        cols = prof["columns"]
        fields = {}
        # links between files by value overlap (more reliable than names)
        if ent == "account" and "customer" in by_entity and "key" in dict(map_entity("customer", by_entity["customer"][1])):
            parent = by_entity["customer"][1]
            pkey = map_entity("customer", parent)["key"][0]
            ov, c = link_by_values(prof, [x for x in cols if x != chosen.get("key", (None,))[0]], parent, pkey)
            if c and ov >= 0.9:
                chosen["customer_key"] = (c, round(1 + ov, 2))
                notes.append(f"account.customer_key = {c}: {ov:.0%} of its values are {pkey} values in {parent['file']}")
        if ent == "transaction" and "account" in by_entity:
            parent = by_entity["account"][1]
            pkey = map_entity("account", parent)["key"][0]
            ov, c = link_by_values(prof, [x for x in cols if x != chosen.get("key", (None,))[0]], parent, pkey)
            if c and ov >= 0.9:
                chosen["account_key"] = (c, round(1 + ov, 2))
                notes.append(f"transaction.account_key = {c}: {ov:.0%} of its values are {pkey} values in {parent['file']}")
        for field, (col, score) in chosen.items():
            pc = cols[col]
            if field == "key":
                continue
            if field in ("birth_date", "opened_on", "customer_since"):
                expr = date_expr(col, pc)
            elif field == "tax_token":
                expr = f"NULLIF(LOWER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM({q(col)}), '^[A-Za-z]+_', ''), '[^0-9A-Fa-f]', '')), '')"
            elif field == "phone":
                expr = f"RIGHT(REGEXP_REPLACE({q(col)}, '[^0-9]', ''), 10)"
            elif field in ("first_name", "last_name", "city", "street"):
                expr = f"UPPER(TRIM({q(col)}))"
            elif field == "state":
                expr = f"UPPER(TRIM({q(col)}))"
            elif field == "email":
                expr = f"LOWER(TRIM({q(col)}))"
            elif field == "full_name":
                expr = None
                fields["last_name"] = f"UPPER(TRIM(SPLIT_PART({q(col)}, ',', 1)))"
                fields["first_name"] = f"UPPER(SPLIT_PART(TRIM(SPLIT_PART({q(col)}, ',', 2)), ' ', 1))"
            elif field == "city_state_zip":
                expr = None
                fields["city"] = f"UPPER(TRIM(SPLIT_PART({q(col)}, ',', 1)))"
                fields["state"] = f"UPPER(SPLIT_PART(TRIM(SPLIT_PART({q(col)}, ',', 2)), ' ', 1))"
                fields["zip"] = f"SPLIT_PART(TRIM(SPLIT_PART({q(col)}, ',', 2)), ' ', 2)"
            elif field in ("party_kind", "product_type", "status", "txn_type", "channel"):
                expr = decode_expr(col, field, pc, review)
            elif field in ("balance_usd", "amount"):
                cents = "cents" in col.lower()
                base = f"TO_NUMBER({q(col)}, 38, 2)" + (" / 100" if cents else "")
                expr = base
                if field == "amount":
                    if pc.get("has_negative"):
                        fields["amount_signed_usd"] = base
                    elif "direction" in chosen:
                        d = chosen["direction"][0]
                        fields["amount_signed_usd"] = f"IFF({q(d)} = 'C', 1, -1) * {base}"
                    else:
                        review.append({"field": "amount_signed_usd", "column": col,
                                       "issue": "amounts are never negative and no debit/credit column was found"})
                    expr = None
            elif field == "posted_at":
                if "epoch_seconds" in pc["kinds"]:
                    expr = f"TO_TIMESTAMP_NTZ(TRY_TO_NUMBER({q(col)}))"
                elif "iso_timestamp" in pc["kinds"]:
                    expr = f"TRY_TO_TIMESTAMP_NTZ(LEFT({q(col)}, 19))"
                elif "posted_time" in chosen:
                    t = chosen["posted_time"][0]
                    expr = f"TRY_TO_TIMESTAMP({q(col)} || {q(t)}, 'YYYYMMDDHH24MISS')"
                else:
                    expr = f"CAST({date_expr(col, pc)} AS TIMESTAMP_NTZ)"
                    review.append({"field": "posted_at", "column": col, "issue": "date only, no time of day"})
            elif field in ("posted_time", "direction"):
                expr = None
            else:
                expr = q(col)
            if expr:
                fields[field] = expr
            specific = bool(set(pc["kinds"]) & SPECIFIC_KINDS & FIELDS[ent][field][1]) if field in FIELDS[ent] else True
            level = "high" if score >= 2 or (score >= 1 and specific) else "medium" if score >= 1 else "low"
            confidence[f"{ent}.{field}"] = {"column": col, "score": score, "level": level,
                                            "evidence": "name and content" if specific else "name, content fits"}
        for req in [f for f in FIELDS[ent] if f not in chosen and f not in ("full_name", "city_state_zip",
                                                                            "posted_time", "direction")]:
            if not (req in ("first_name", "last_name") and "full_name" in chosen) and \
               not (req in ("city", "state", "zip") and "city_state_zip" in chosen):
                review.append({"field": f"{ent}.{req}", "issue": "no column found"})
        if ent == "customer" and "party_kind" in fields:
            kind = fields["party_kind"]
            for f in ("first_name", "last_name"):
                if f in fields:
                    fields[f] = f"IFF({kind} = 'ORG', NULL, {fields[f]})"
            notes.append("customer: first and last name are left empty for organisations (party_kind = 'ORG')")
        mapping[ent] = {"source_file": fname, "bronze_table": f"BRONZE.{core.upper()}_{Path(fname).name.split('.')[0].upper()}",
                        "key": chosen.get("key", ("?",))[0], "fields": fields}
    mapping["confidence"] = confidence
    mapping["links"] = notes
    mapping["review"] = review
    return mapping, profiles


# ------------------------------------------------------------------ 5. SQL
HEADER = "-- GENERATED by onboarding/onboard.py (rules, no AI). Review mapping.yaml first.\n" \
         "USE ROLE RISK_ADMIN;\nUSE WAREHOUSE RISK_WH;\nUSE DATABASE RISK_COPILOT;\n\n"


def bronze_sql(core, mapping, profiles, stage_dir):
    out = [HEADER]
    for ent in ("customer", "account", "transaction"):
        if ent not in mapping:
            continue
        m = mapping[ent]
        prof = profiles[m["source_file"]]
        cols = ",\n".join(f"    {q(c)} VARCHAR" for c in prof["header"])
        out.append(f"CREATE OR REPLACE TABLE RISK_COPILOT.{m['bronze_table']} (\n{cols},\n"
                   f"    _SOURCE_FILE VARCHAR, _SOURCE_ROW NUMBER, _LOADED_AT TIMESTAMP_LTZ\n);\n")
        sel = ", ".join(f"${i + 1}" for i in range(len(prof["header"])))
        names = ", ".join(q(c) for c in prof["header"])
        out.append(f"COPY INTO RISK_COPILOT.{m['bronze_table']} ({names}, _SOURCE_FILE, _SOURCE_ROW, _LOADED_AT)\n"
                   f"  FROM (SELECT {sel}, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, CURRENT_TIMESTAMP()\n"
                   f"        FROM @RISK_COPILOT.BRONZE.RAW_STAGE/{stage_dir}/{m['source_file']})\n"
                   f"  FILE_FORMAT = (FORMAT_NAME = 'RISK_COPILOT.BRONZE.FF_CSV_GZ')\n"
                   f"  ON_ERROR = ABORT_STATEMENT FORCE = TRUE;\n")
    return "\n".join(out)


def canonical_sql(core, mapping):
    out = [HEADER]
    names = {"customer": "CUSTOMER", "account": "ACCOUNT", "transaction": "TRANSACTION"}
    for ent, view in names.items():
        if ent not in mapping:
            continue
        m = mapping[ent]
        sel = [f"'{core}:' || {q(m['key'])} AS record_id", f"'{core}' AS source_system", f"{q(m['key'])} AS source_key"]
        for f, e in m["fields"].items():
            if f.endswith("_key"):
                e = f"'{core}:' || {e}"
            sel.append(f"{e} AS {f}")
        sel += ["_SOURCE_FILE AS source_file", "_SOURCE_ROW AS source_row"]
        body = ",\n       ".join(sel)
        out.append(f"CREATE OR REPLACE VIEW SILVER.{core.upper()}_{view} AS\nSELECT {body}\n  FROM {m['bronze_table']};\n")
    return "\n".join(out)


def dq_sql(core, mapping):
    """Data-quality tests on the generated canonical views. Problems are reported, never silently fixed."""
    checks = []
    for ent in ("customer", "account", "transaction"):
        if ent not in mapping:
            continue
        v = f"SILVER.{core.upper()}_{ent.upper()}"
        bt = mapping[ent]["bronze_table"]
        checks.append(f"SELECT '{ent}' AS entity, 'rows' AS check_name, COUNT(*) AS failures, 'information' AS rule FROM {v}")
        checks.append(f"SELECT '{ent}', 'key is null', COUNT(*), 'must be 0' FROM {v} WHERE source_key IS NULL")
        checks.append(f"SELECT '{ent}', 'duplicate keys', COUNT(*) - COUNT(DISTINCT source_key), 'must be 0' FROM {v}")
        fields = mapping[ent]["fields"]
        for f in fields:
            if f in ("birth_date", "opened_on", "customer_since", "posted_at", "product_type", "status", "txn_type",
                     "channel", "amount_signed_usd", "balance_usd", "party_kind"):
                conf = mapping["confidence"].get(f"{ent}.{f}") or mapping["confidence"].get(f"{ent}.amount") or {}
                src = conf.get("column")
                cond = f"v.{f} IS NULL" + (f" AND b.{q(src)} IS NOT NULL" if src else "")
                if f == "birth_date" and "party_kind" in fields:
                    cond += " AND v.party_kind IS DISTINCT FROM 'ORG'"          # organisations have no birth date
                checks.append(f"SELECT '{ent}', '{f} not parsed or not mapped', COUNT(*), 'must be 0' "
                              f"FROM {v} v JOIN {bt} b ON b._SOURCE_ROW = v.source_row WHERE {cond}")
        if "birth_date" in fields:
            checks.append(f"SELECT '{ent}', 'birth_date in the future or before 1900', COUNT(*), 'report' FROM {v} v "
                          f"WHERE v.birth_date > CURRENT_DATE OR v.birth_date < DATE '1900-01-01'")
        if "zip" in fields:
            checks.append(f"SELECT '{ent}', 'zip not 5 digits or 00000', COUNT(*), 'report' FROM {v} v "
                          f"WHERE v.zip IS NOT NULL AND (NOT REGEXP_LIKE(v.zip, '[0-9]{{5}}') OR v.zip = '00000')")
        if "tax_token" in fields:
            checks.append(f"SELECT '{ent}', 'tax token not 16 hex characters', COUNT(*), 'report' FROM {v} v "
                          f"WHERE v.tax_token IS NOT NULL AND NOT REGEXP_LIKE(v.tax_token, '[0-9a-f]{{16}}')")
        if "phone" in fields:
            checks.append(f"SELECT '{ent}', 'phone not 10 digits', COUNT(*), 'report' FROM {v} v "
                          f"WHERE v.phone IS NOT NULL AND NOT REGEXP_LIKE(v.phone, '[0-9]{{10}}')")
    if "account" in mapping and "customer" in mapping and "customer_key" in mapping["account"]["fields"]:
        checks.append(f"SELECT 'account', 'orphan accounts (no customer)', COUNT(*), 'report' FROM SILVER.{core.upper()}_ACCOUNT a "
                      f"LEFT JOIN SILVER.{core.upper()}_CUSTOMER c ON c.record_id = a.customer_key WHERE c.record_id IS NULL")
    if "transaction" in mapping and "account" in mapping and "account_key" in mapping["transaction"]["fields"]:
        checks.append(f"SELECT 'transaction', 'orphan transactions (no account)', COUNT(*), 'report' "
                      f"FROM SILVER.{core.upper()}_TRANSACTION t LEFT JOIN SILVER.{core.upper()}_ACCOUNT a "
                      f"ON a.record_id = t.account_key WHERE a.record_id IS NULL")
    return HEADER + "\nUNION ALL\n".join(checks) + "\nORDER BY 1, 2;\n"


def write_outputs(core, mapping, profiles, out_dir, stage_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mapping.yaml").write_text(
        f"# {core} -> canonical model. GENERATED by onboarding (rules, no AI).\n"
        f"# A person must review the 'review' list and any 'low' confidence field before loading.\n"
        + yaml.safe_dump(mapping, sort_keys=False, width=140, allow_unicode=True))
    (out_dir / "10_bronze.sql").write_text(bronze_sql(core, mapping, profiles, stage_dir))
    (out_dir / "20_canonical.sql").write_text(canonical_sql(core, mapping))
    (out_dir / "30_dq_tests.sql").write_text(dq_sql(core, mapping))
    prof_lines = []
    for name, p in profiles.items():
        prof_lines.append(f"## {name} ({p['rows_total']:,} rows; {p['rows_sampled']:,} sampled)")
        for c, pc in p["columns"].items():
            kinds = ", ".join(k for k in pc["kinds"])
            fmt = f" [{pc['date_format']}]" if "date_format" in pc else ""
            prof_lines.append(f"- {c}: {kinds}{fmt}; e.g. {', '.join(pc['samples'][:2])}")
    (out_dir / "profile.md").write_text("\n".join(prof_lines) + "\n")
    return out_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True, help="source system name, e.g. core_c")
    ap.add_argument("--files", required=True, help="folder with the core's extract files (.csv or .csv.gz)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--stage-dir", default=None, help="folder in @BRONZE.RAW_STAGE (default: the core name)")
    a = ap.parse_args()
    files = sorted(p for p in Path(a.files).iterdir() if p.name.endswith((".csv", ".csv.gz")) and "control" not in p.name)
    mapping, profiles = build_mapping(a.core, files)
    out = write_outputs(a.core, mapping, profiles, a.out or f"build/onboard/{a.core}", a.stage_dir or a.core)
    print(f"Wrote {out}/mapping.yaml, 10_bronze.sql, 20_canonical.sql, 30_dq_tests.sql, profile.md")
    for ent in ("customer", "account", "transaction"):
        if ent in mapping:
            print(f"  {ent:12s} <- {mapping[ent]['source_file']} (key {mapping[ent]['key']}), {len(mapping[ent]['fields'])} fields")
    print(f"  links: {'; '.join(mapping['links']) or 'none'}")
    print(f"  items for review: {len(mapping['review'])}")
    for r in mapping["review"]:
        print(f"    - {r}")


if __name__ == "__main__":
    main()
