"""F6 without AI: a rule-based router that sends each question to the right tool and says why.

Routes, checked in this order (the first rule that fires wins, and its name is recorded):
  NARRATIVE  "draft / write up / narrative / case summary" + a named customer or "highest-risk" -> F7 report
  CATALOG    data wording ("which customers", "how many", "$50k") + a confident catalogue match   -> F3 catalogue
  SEARCH     policy, procedure, notes or KYC-file wording                                     -> F5 search
  CUSTOMER   the question names a known customer (looked up in GOLD.PARTY)                     -> customer view
  CATALOG    the keyword matcher is confident about a reviewed question                        -> F3 catalogue
  CLARIFY    none of the above: show the closest catalogue questions and ask

`execute(sql) -> DataFrame` is the only database access, so the same router runs on Snowflake and DuckDB.
"""
import re
from dataclasses import dataclass, field

from semantic.matcher import Matcher

NARRATIVE_WORDS = re.compile(r"\b(draft|write[- ]?up|write|narrative|case summary|sar narrative|memo)\b", re.I)
TOP_OF_QUEUE = re.compile(r"\b(highest[- ]risk|top of the queue|riskiest|first in the queue|top customer)\b", re.I)
POLICY_WORDS = re.compile(r"\b(polic(y|ies)|procedures?|section|according to|what does .{0,40} (say|require)|"
                          r"require[sd]?|allowed|permitted|deadline for filing|bsa program|"
                          r"(what|which) (are|is) the (rules?|requirements?)|rules? (for|on|about))\b", re.I)
NOTE_WORDS = re.compile(r"\b(investigator notes?|notes?|case notes?)\b", re.I)
KYC_WORDS = re.compile(r"\b(kyc (files?|summar(y|ies)|profiles?|documents?)|search the kyc)\b", re.I)
DATA_WORDS = re.compile(r"(\bwhich customers\b|\bhow (many|much)\b|\btotal\b|\btop \w+|\bwho (are|deposited|moved)\b|"
                        r"\$\s?\d|\b\d+k\b|\bmoved\b|\bwhich days\b)", re.I)
SEARCH_VERBS = re.compile(r"\b(find|search|show me|look for|mention(s|ing)?)\b", re.I)
NAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]+")
NOT_NAMES = set("""the a an of in on at to for and or is are was were what which who how many much show tell me
about why ranked so high everything we know draft write up case narrative sar highest risk customer queue
alerts alert cash policy notes note kyc files search find customers our team work first today""".split())


@dataclass
class Route:
    route: str                     # CATALOG | SEARCH | CUSTOMER | NARRATIVE | CLARIFY
    target: str = ""               # question id, document type, customer name or TOP_OF_QUEUE
    rule: str = ""                 # which rule fired, for the audit log and the user
    party_id: str = ""
    suggestions: list = field(default_factory=list)


def find_customers(text, execute):
    """Look up 2-4 word spans of the question as customer names in GOLD.PARTY (exact, case-insensitive)."""
    words = [re.sub(r"'s$", "", w, flags=re.I) for w in NAME_TOKEN.findall(text)]   # "McDaniel's" -> "McDaniel"
    spans = set()
    for n in (2, 3, 4):
        for i in range(len(words) - n + 1):
            span = words[i:i + n]
            if all(w.lower() in NOT_NAMES for w in span):
                continue
            spans.add(" ".join(span).upper().replace("'", "''"))
    if not spans:
        return []
    in_list = ", ".join(f"'{s}'" for s in sorted(spans))
    df = execute(f"SELECT party_id, display_name, cores FROM GOLD.PARTY WHERE display_name IN ({in_list}) "
                 f"ORDER BY cores DESC, party_id")
    df.columns = [c.lower() for c in df.columns]
    return list(df.itertuples(index=False))


class Router:
    def __init__(self, execute, matcher=None):
        self.execute = execute
        self.matcher = matcher or Matcher()

    def route(self, text):
        text = (text or "").strip()
        if len(text) < 3:
            return Route("CLARIFY", rule="empty_or_too_short", suggestions=self.matcher.match("x")[1])

        customers = None

        def named():
            nonlocal customers
            if customers is None:
                customers = find_customers(text, self.execute)
            return customers

        # 1. narrative requests
        if NARRATIVE_WORDS.search(text):
            if TOP_OF_QUEUE.search(text):
                return Route("NARRATIVE", "TOP_OF_QUEUE", "narrative_words+top_of_queue")
            c = named()
            if c:
                return Route("NARRATIVE", c[0].display_name, "narrative_words+customer_name", c[0].party_id)

        # 2. a data question that also mentions documents ("...and what do their KYC files say?") is still
        #    a data question when a reviewed catalogue question matches it confidently
        if DATA_WORDS.search(text):
            best, top = self.matcher.match(text)
            if best:
                return Route("CATALOG", best, "data_words+catalog_match_confident", suggestions=top)

        # 3. document questions
        if KYC_WORDS.search(text):
            return Route("SEARCH", "KYC", "kyc_file_words")
        if NOTE_WORDS.search(text) and (SEARCH_VERBS.search(text) or "about" in text.lower()):
            return Route("SEARCH", "NOTE", "note_words+search_verb")
        if POLICY_WORDS.search(text):
            return Route("SEARCH", "POLICY", "policy_words")

        # 4. a named customer
        c = named()
        if c:
            return Route("CUSTOMER", c[0].display_name, "customer_name_found", c[0].party_id)

        # 5. reviewed catalogue question
        best, top = self.matcher.match(text)
        if best:
            return Route("CATALOG", best, "catalog_match_confident", suggestions=top)

        # 6. ask
        return Route("CLARIFY", rule="no_confident_route", suggestions=top)
