"""Turn a routed question into an answer: headline, tables, citations and the rule that chose the route.

No AI. Every number comes from reviewed SQL; every document quote comes with its citation.
Every question is written to AUDIT.QUESTION_LOG with its route and rule (log_question).
"""
import getpass
import os
import re
import uuid
from dataclasses import dataclass, field

from agent.router import Route, Router
from search.search import search
from semantic.catalog import by_id, headline, run_question


@dataclass
class Answer:
    question: str
    route: str
    rule: str
    headline: str
    answered_as: str = ""                          # the reviewed question or tool actually used
    tables: list = field(default_factory=list)     # [(title, DataFrame)]
    citations: list = field(default_factory=list)  # ["BSA/AML Policy v7.2, section 4.2 ..., page 3", ...]
    suggestions: list = field(default_factory=list)
    party_id: str = ""
    text: str = ""                                 # a full document (narrative preview), when there is one


def _q(execute, sql):
    df = execute(sql)
    df.columns = [c.lower() for c in df.columns]
    return df


def _money(x):
    try:
        return f"${float(x):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


def customer_view(party_id, execute):
    """All the evidence about one resolved customer, from Gold, the risk engine and document search."""
    if not re.fullmatch(r"PTY_[0-9a-f]{8,32}", party_id or ""):
        raise ValueError("bad party id")
    p = f"'{party_id}'"
    tables = {
        "profile": _q(execute, f"""SELECT p.display_name, p.party_kind, p.birth_date, p.city, p.state, p.cores,
                   p.core_a_key, p.core_b_key, p.link_reasons FROM GOLD.PARTY p WHERE p.party_id = {p}"""),
        "risk": _q(execute, f"""SELECT s.risk_score, s.raw_score, s.top_reasons, s.mitigating,
                   q.queue_rank, q.queue_size, q.origin
                   FROM GOLD.RISK_SCORE s LEFT JOIN GOLD.ALERT_QUEUE q ON q.party_id = s.party_id
                   WHERE s.party_id = {p} ORDER BY q.queue_rank LIMIT 1"""),
        "signals": _q(execute, f"""SELECT rule_code, weight, evidence_text FROM GOLD.RISK_SIGNAL
                   WHERE party_id = {p} ORDER BY weight DESC, rule_code"""),
        "accounts": _q(execute, f"""SELECT source_system, product_type, status, branch, balance_usd, account_id,
                   source_file, source_row FROM GOLD.ACCOUNT WHERE party_id = {p} ORDER BY source_system, account_id"""),
        "loans": _q(execute, f"""SELECT source_system, loan_type, principal_usd, days_past_due, loan_id
                   FROM GOLD.LOAN WHERE party_id = {p} ORDER BY source_system, loan_id"""),
        "kyc": _q(execute, f"""SELECT source_system, occupation, expected_monthly_cash_usd, risk_rating, review_date
                   FROM GOLD.KYC_PROFILE WHERE party_id = {p} ORDER BY source_system"""),
        "alerts": _q(execute, f"""SELECT alert_id, scenario, alert_date, status, disposition FROM GOLD.ALERT
                   WHERE party_id = {p} ORDER BY alert_date DESC"""),
        "cash_30d": _q(execute, f"""SELECT source_system, COUNT(*) AS deposits, ROUND(SUM(amount_usd), 2) AS cash_usd
                   FROM GOLD.TRANSACTION WHERE party_id = {p} AND txn_type = 'CASH_DEPOSIT'
                   AND posted_date > (SELECT MAX(posted_date) FROM GOLD.TRANSACTION) - 30
                   GROUP BY source_system ORDER BY source_system"""),
    }
    _, notes = search("alert review cash wire KYC SAR", execute, k=5, doc_types=["NOTE"], party_id=party_id)
    tables["notes"] = notes if notes is not None else None
    return tables


def _customer_headline(v):
    prof = v["profile"].iloc[0]
    parts = [f"{prof.display_name}: customer in {int(prof.cores)} core(s)"]
    if len(v["risk"]):
        r = v["risk"].iloc[0]
        rank = f", queue rank {int(r.queue_rank)} of {int(r.queue_size)}" if r.queue_rank == r.queue_rank and r.queue_rank is not None else ""
        parts.append(f"risk score {float(r.risk_score):.0f}{rank} ({r.top_reasons or 'no risk-raising rules'})")
    else:
        parts.append("no risk rules fired")
    open_alerts = int((v["alerts"]["status"] != "CLOSED").sum()) if len(v["alerts"]) else 0
    parts.append(f"{len(v['alerts'])} legacy alert(s), {open_alerts} open")
    if len(v["cash_30d"]):
        parts.append(f"cash in last 30 days {_money(v['cash_30d']['cash_usd'].astype(float).sum())}")
    return "; ".join(parts) + "."


def answer(question, execute, router=None):
    router = router or Router(execute)
    r: Route = router.route(question)

    if r.route == "CATALOG":
        q = by_id()[r.target]
        df = run_question(q, execute)
        return Answer(question, r.route, r.rule, headline(q, df), f"{q['id']}: {q['question']}",
                      [(q["id"], df)], [f"Definition: {q.get('definition', '')} (SEMANTIC.METRIC_DEFINITION)"])

    if r.route == "SEARCH":
        ts, hits = search(question, execute, k=5, doc_types=[r.target])
        if hits is None or not len(hits):
            return Answer(question, r.route, r.rule, f"No {r.target.lower()} documents matched {ts}.",
                          f"document search ({r.target})")
        top = hits.iloc[0]
        return Answer(question, r.route, r.rule, f"{top.snippet} [{top.citation}]", f"document search ({r.target})",
                      [("matches", hits[["citation", "snippet", "score"]])], list(hits["citation"]))

    if r.route in ("CUSTOMER", "NARRATIVE"):
        party_id = r.party_id
        if r.target == "TOP_OF_QUEUE":
            top = _q(execute, "SELECT party_id FROM GOLD.ALERT_QUEUE WHERE queue_rank = 1")
            party_id = top.iloc[0]["party_id"]
        v = customer_view(party_id, execute)
        tables = [(k, df) for k, df in v.items() if df is not None and len(df)]
        cites = [f"{row.source_file} row {row.source_row}" for row in v["accounts"].itertuples()]
        if v.get("notes") is not None and len(v["notes"]):
            cites += list(v["notes"]["citation"])
        head = _customer_headline(v)
        if r.route == "NARRATIVE":
            from outputs.narrative import gather_evidence, render_narrative
            md = render_narrative(gather_evidence(party_id, execute), status="PREVIEW - not saved")
            name = v["profile"].iloc[0]["display_name"]
            return Answer(question, r.route, r.rule,
                          f"Draft case narrative for {name} (preview, not saved). To save it for approval: "
                          f"python scripts/case.py draft --customer \"{name.title()}\" --author <you>",
                          "case narrative template (outputs/narrative.py)", tables, cites, party_id=party_id, text=md)
        return Answer(question, r.route, r.rule, head, "customer view (Gold, risk engine, notes)", tables, cites,
                      party_id=party_id)

    related = [(qid, sc) for qid, sc in (r.suggestions or []) if sc > 0]
    if not related:
        return Answer(question, r.route, r.rule, "I can't answer that from the bank's data or documents. "
                      "See what I can answer with: python scripts/ask.py --list")
    return Answer(question, r.route, r.rule, "I'm not sure which question you mean. Closest reviewed questions:",
                  "", suggestions=related)


def log_question(a: Answer, execute, app_user=None):
    """Write one row to AUDIT.QUESTION_LOG. Returns the log id."""
    def q(s):
        return str(s or "").replace("'", "''")[:4000]
    log_id = str(uuid.uuid4())
    user = app_user or os.getenv("RISK_COPILOT_USER") or getpass.getuser()
    rows = sum(len(df) for _, df in a.tables)
    execute(f"""INSERT INTO AUDIT.QUESTION_LOG (log_id, logged_at, app_user, question, route, rule, answered_as,
                headline, row_count, citations, party_id)
                SELECT '{log_id}', CURRENT_TIMESTAMP, '{q(user)}', '{q(a.question)}', '{q(a.route)}', '{q(a.rule)}',
                       '{q(a.answered_as)}', '{q(a.headline)}', {rows}, '{q(" | ".join(a.citations[:20]))}',
                       '{q(a.party_id)}'""")
    return log_id
