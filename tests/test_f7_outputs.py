"""F7 acceptance without AI: the case narrative states the D05 facts, cites real policy pages, needs a
second person to approve it, and reproduces byte for byte from its audit record (build-plan bar).
"""
import json
import re
import sys

import duckdb
import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import local_duckdb as L  # noqa: E402
from outputs import case_store as C  # noqa: E402
from outputs.export_pdf import export_pdf  # noqa: E402
from outputs.narrative import gather_evidence, render_narrative  # noqa: E402


@pytest.fixture(scope="module")
def env(small_data):
    out, _ = small_data
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, out)
    L.run_silver(con)
    L.run_gold(con)
    L.run_search(con)
    L.run_outputs(con)
    execute = L.executor(con)
    demo = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "demo_answers.json").read_text())["questions"]}
    top = con.execute("SELECT party_id FROM gold.ALERT_QUEUE WHERE queue_rank = 1").fetchone()[0]
    return execute, con, demo, top


def test_narrative_states_the_d05_facts(env):
    execute, _, demo, top = env
    md = render_narrative(gather_evidence(top, execute), author="analyst_a")
    d05 = demo["D05"]
    assert md.startswith(f"# Case narrative: {d05['name']}")
    fact = d05["must_mention"][0]
    for amount in re.findall(r"\$[\d,]+\.\d\d", fact):                  # every dollar amount, to the cent
        assert amount in md, amount
    for n in re.findall(r"in (\d+) deposits", fact):
        assert f"in {n} deposits" in md
    for d in re.findall(r"\d{4}-\d{2}-\d{2}", fact):                     # CTR day and wire date
        assert d in md, d
    m = re.search(r"to (.+?) on \d{4}", fact)
    if m:
        assert m.group(1) in md                                          # wire counterparty
    assert "Each deposit was under $10,000" in md and "$30,000 legacy rule" in md
    assert "KYC expected cash" in md and "both cores" in md
    for code in d05["expected_reason_codes"]:
        assert code in md


def test_every_policy_citation_has_the_right_page(env):
    execute, con, _, top = env
    md = render_narrative(gather_evidence(top, execute))
    cites = set(re.findall(r"section (\d+\.\d+ [A-Za-z ]+?), page (\d+)", md))
    assert cites
    pages = dict(con.execute("SELECT section, page FROM search.POLICY_CHUNK").fetchall())
    for section, page in cites:
        assert pages[section.strip()] == int(page), section


def test_same_evidence_same_text(env):
    execute, _, _, top = env
    a = render_narrative(gather_evidence(top, execute), author="x")
    b = render_narrative(gather_evidence(top, execute), author="x")
    assert a == b


def test_four_eyes_approval_and_reproduction(env):
    execute, _, _, top = env
    oid, md = C.draft_narrative(top, "analyst_a", execute)
    assert C.status(oid, execute)["status"] == "DRAFT"
    assert "DRAFT" in C.final_text(oid, execute)[0]
    with pytest.raises(C.ApprovalError):
        C.decide(oid, " Analyst_A ", "APPROVED", execute)               # author cannot approve, any case/spacing
    st = C.decide(oid, "officer_b", "APPROVED", execute, "Escalate")
    assert st["status"] == "APPROVED" and st["approver"] == "officer_b"
    with pytest.raises(C.ApprovalError):
        C.decide(oid, "officer_c", "REJECTED", execute)                 # no second decision
    text, status = C.final_text(oid, execute)
    assert status == "APPROVED" and "APPROVED by officer_b" in text
    ok, info = C.reproduce(oid, execute)
    assert ok, info


def test_tampered_text_cannot_be_approved(env):
    execute, con, _, top = env
    oid, _ = C.draft_narrative(top, "analyst_a", execute)
    con.execute(f"UPDATE audit.CASE_OUTPUT SET content_md = content_md || ' edited' WHERE output_id = '{oid}'")
    with pytest.raises(C.ApprovalError):
        C.decide(oid, "officer_b", "APPROVED", execute)
    assert not C.reproduce(oid, execute)[0]


def test_bad_ids_are_rejected(env):
    execute, *_ = env
    with pytest.raises(ValueError):
        C.get_output("x' OR '1'='1", execute)


def test_pdf_export_marks_drafts(env, tmp_path):
    execute, _, _, top = env
    md = render_narrative(gather_evidence(top, execute))
    path = export_pdf(md, tmp_path / "case.pdf", status="DRAFT", footer="test")
    data = path.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 3000
    from pypdf import PdfReader
    text = " ".join(p.extract_text() for p in PdfReader(str(path)).pages)
    assert "DRAFT - NOT APPROVED" in text and "Case narrative" in text
