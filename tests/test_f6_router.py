"""F6 acceptance without AI: the rule-based router picks the right tool, says which rule fired, and the
five demo questions (D01-D05) are answered correctly three runs in a row (build-plan bar). Every question
is logged to AUDIT.QUESTION_LOG.
"""
import json
import sys

import duckdb
import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import local_duckdb as L  # noqa: E402
from agent.answer import answer, log_question  # noqa: E402
from agent.router import Router  # noqa: E402


@pytest.fixture(scope="module")
def env(small_data):
    out, _ = small_data
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, out)
    L.run_silver(con)
    L.run_gold(con)
    L.run_semantic(con)
    L.run_search(con)
    L.run_agent(con)
    demo = {q["id"]: q for q in json.loads((out / "ground_truth" / "demo_answers.json").read_text())["questions"]}
    return L.executor(con), con, demo


def _cases(name):
    return yaml.safe_load((REPO / "tests" / "data" / name).read_text())["cases"]


def _names_in_small(execute):
    df = execute("SELECT display_name FROM GOLD.PARTY")
    return set(df.iloc[:, 0])


@pytest.mark.parametrize("file", ["router_eval.yaml", "router_holdout.yaml"])
def test_router_routes(env, file):
    """Customer-name cases use demo-data names; on the small dataset only cases whose customer exists are
    checked for CUSTOMER/NARRATIVE (the rest must fall back safely, never to a wrong customer)."""
    execute, *_ = env
    names = _names_in_small(execute)
    r = Router(execute)
    wrong = []
    for c in _cases(file):
        got = r.route(c["q"])
        needs_name = c["route"] in ("CUSTOMER", "NARRATIVE") and c.get("target") not in (None, "TOP_OF_QUEUE")
        if needs_name and c["target"] not in names:
            if got.route in ("CUSTOMER", "NARRATIVE") and got.target != c["target"]:
                wrong.append((c["q"], got))              # a different customer would be a real error
            continue
        if got.route != c["route"] or (c.get("target") and got.target != c["target"]):
            wrong.append((c["q"], got.route, got.target, got.rule))
    assert not wrong, wrong


def test_every_route_records_its_rule(env):
    execute, *_ = env
    r = Router(execute)
    for c in _cases("router_eval.yaml"):
        assert r.route(c["q"]).rule


def _demo_answers(execute, demo):
    got = {}
    for qid in ["D01", "D02", "D03", "D04", "D05"]:
        a = answer(demo[qid]["question"], execute)
        got[qid] = a
    return got


def test_five_demo_questions_correct_three_runs_in_a_row(env):
    execute, _, demo = env
    runs = []
    for _ in range(3):
        a = _demo_answers(execute, demo)
        # D01: customers over $50k in 30 days, split by what KYC explains
        d01 = a["D01"].tables[0][1]
        assert a["D01"].route == "CATALOG" and len(d01) == demo["D01"]["answer"]["count"]
        assert (d01.kyc_verdict == "Not explained by KYC").sum() == demo["D01"]["answer"]["suspicious"]
        # D02: missed cross-core CTR aggregation days
        assert a["D02"].route == "CATALOG" and len(a["D02"].tables[0][1]) == demo["D02"]["answer"]["count"]
        # D03: queue led by the D05 customer
        assert a["D03"].tables[0][1].iloc[0]["customer"] == demo["D05"]["answer"]["name"].upper()
        # D04: policy citation
        exp = demo["D04"]["answer"]["expected_citation"]
        assert a["D04"].route == "SEARCH"
        assert f"section {exp['section']}" in a["D04"].citations[0] and f"page {exp['page']}" in a["D04"].citations[0]
        # D05: narrative request resolves to the highest-risk customer with the right evidence
        assert a["D05"].route == "NARRATIVE"
        assert demo["D05"]["answer"]["name"].upper() in a["D05"].headline
        assert a["D05"].text.startswith("# Case narrative: " + demo["D05"]["answer"]["name"])
        signals = dict(a["D05"].tables)["signals"]
        assert set(demo["D05"]["answer"]["expected_reason_codes"]) <= set(signals.rule_code)
        runs.append({k: v.headline for k, v in a.items()})
    assert runs[0] == runs[1] == runs[2]


def test_questions_are_logged(env):
    execute, con, demo = env
    before = con.execute("SELECT COUNT(*) FROM audit.QUESTION_LOG").fetchone()[0]
    a = answer("What does our BSA policy say about aggregating cash across the two cores?", execute)
    log_question(a, execute, app_user="test_user")
    row = con.execute("SELECT app_user, route, rule, citations FROM audit.QUESTION_LOG ORDER BY logged_at DESC LIMIT 1").fetchone()
    assert con.execute("SELECT COUNT(*) FROM audit.QUESTION_LOG").fetchone()[0] == before + 1
    assert row[0] == "test_user" and row[1] == "SEARCH" and row[2] == "policy_words" and "4.2 Aggregation" in row[3]


def test_unknown_question_asks_instead_of_guessing(env):
    execute, *_ = env
    a = answer("Can you order me a pizza?", execute)
    assert a.route == "CLARIFY" and not a.tables and "can't answer" in a.headline
    b = answer("Tell me about alerts", execute)            # related but vague: offer the closest questions
    assert b.route in ("CLARIFY", "CATALOG")
    if b.route == "CLARIFY":
        assert b.suggestions
