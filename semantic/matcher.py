"""Match a typed question to the catalogue with keyword scoring. No AI, no network.

Each catalogue question contributes its text and its keyword list. A typed question is normalised
(lower case, simple stemming, synonyms), and scored by the rarity-weighted overlap of its words with
each question, plus a bonus for multi-word keyword phrases found verbatim. The caller shows the best
match when it is confident, and otherwise asks the user to pick from the top suggestions.

  python -m semantic.matcher "how many alerts did we get last month"
"""
import math
import re
import sys
from collections import Counter

from semantic.catalog import load_catalog

STOP = set("""a an the of in on at to for and or is are was were be been do does did we our us you your i me my
what which who whom how many much there this that these those with by from as it its any all have has had
can could would should please show tell give list me across per get got count number over past two
hold our their right now today""".split())

SYNONYMS = {
    "aml": "alert", "case": "alert", "cases": "alert", "alerts": "alert",
    "fp": "false_positive", "false-positive": "false_positive", "falsepositive": "false_positive",
    "ctr": "ctr", "ctrs": "ctr", "sar": "sar",
    "atm": "atm", "withdrawal": "withdraw", "withdrawals": "withdraw", "withdrawn": "withdraw",
    "deposit": "deposit", "deposits": "deposit", "deposited": "deposit",
    "dormant": "dormant", "inactive": "dormant",
    "delinquent": "past_due", "overdue": "past_due", "nonperforming": "past_due",
    "cre": "cre", "ltd": "ltd", "kyc": "kyc",
    "customers": "customer", "clients": "customer", "client": "customer", "members": "customer",
    "member": "customer", "people": "customer", "persons": "customer",
    "branches": "branch", "q2": "q2", "august": "august", "aug": "august",
    "prioritise": "priority", "prioritize": "priority", "triage": "priority", "first": "priority",
    "riskiest": "risk", "risky": "risk", "highest": "top", "biggest": "top", "largest": "top", "most": "top",
    "10k": "10000", "10,000": "10000", "$10,000": "10000", "50k": "50000", "$50k": "50000", "50,000": "50000",
    "$50,000": "50000", "unique": "unique", "distinct": "unique", "deduplicated": "unique",
    "concentration": "cre", "commercial": "cre",
}
PHRASES = {  # multi-word cues, normalised to one token before scoring
    "false positives": "false_positive", "false positive": "false_positive", "last quarter": "q2", "past due": "past_due", "days past due": "past_due",
    "loan to deposit": "ltd", "loan-to-deposit": "ltd", "commercial real estate": "cre",
    "currency transaction report": "ctr", "owner occupied": "owner_occupied", "non owner occupied": "owner_occupied",
    "non-owner-occupied": "owner_occupied", "cash in": "deposit", "cash out": "withdraw",
    "last month": "august", "second quarter": "q2", "work first": "priority", "time to close": "close",
    "both cores": "both_cores", "two cores": "both_cores", "both systems": "both_cores",
    "core a and core b": "each_core", "core a": "each_core", "core b": "each_core", "each core": "each_core", "per core": "each_core", "by core": "each_core",
    "30 days": "30_days", "last 30 days": "30_days", "90 days": "90_days", "last 90 days": "90_days",
    "entity resolution": "unique", "after matching": "unique", "still open": "open",
}


def _stem(w):
    if len(w) > 4 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def normalise(text):
    t = " " + re.sub(r"[?!.;:()\"]|'s\b", " ", text.lower().replace("’", "'")) + " "
    t = re.sub(r"\s+", " ", t)
    for ph in sorted(PHRASES, key=len, reverse=True):
        t = t.replace(" " + ph + " ", " " + PHRASES[ph] + " ")
    words = re.findall(r"[\w$,\-]+", t)
    out = []
    for w in words:
        w = w.strip(",-")
        if not w or w in STOP:
            continue
        w = SYNONYMS.get(w, w)
        if w in STOP:
            continue
        out.append(w if "_" in w or w.isdigit() else _stem(w))
    return out


class Matcher:
    def __init__(self, catalog=None):
        self.catalog = catalog or load_catalog()
        self.docs = {}
        for q in self.catalog:
            text = q["question"] + " " + " ".join(str(k) for k in q.get("keywords", []))
            self.docs[q["id"]] = Counter(normalise(text))
        df = Counter()
        for c in self.docs.values():
            df.update(set(c))
        n = len(self.docs)
        self.idf = {w: math.log((n + 1) / (d + 0.5)) for w, d in df.items()}

    def score(self, text):
        words = set(normalise(text))
        if not words:
            return None
        out = []
        for qid, doc in self.docs.items():
            matched = [w for w in words if w in doc]
            hit = sum(self.idf.get(w, 0) for w in matched)
            miss = sum(self.idf.get(w, 1.0) for w in words if w not in doc)
            out.append((qid, round(hit - 0.25 * miss, 3), len(matched)))
        out.sort(key=lambda x: -x[1])
        return [(q, sc) for q, sc, _ in out], {q: n for q, _, n in out}

    def match(self, text, min_score=2.0, min_margin=0.5):
        """Return (best_id or None, ranked suggestions). None means: ask the user to pick."""
        scored = self.score(text)
        if not scored:
            return None, []
        ranked, n_matched = scored
        best, second = ranked[0], ranked[1] if len(ranked) > 1 else (None, -99)
        confident = (best[1] >= min_score and best[1] - second[1] >= min_margin
                     and n_matched[best[0]] >= 2)          # one shared word is never enough
        return (best[0] if confident else None), ranked[:3]


if __name__ == "__main__":
    m = Matcher()
    q = " ".join(sys.argv[1:]) or "how many alerts did we get last month"
    best, top = m.match(q)
    cat = {c["id"]: c["question"] for c in m.catalog}
    print(f"{q!r} -> {best or 'no confident match'}")
    for qid, s in top:
        print(f"  {qid} {s:6.2f}  {cat[qid]}")
