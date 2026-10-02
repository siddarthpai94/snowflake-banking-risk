"""F8 smoke test: every screen of the Streamlit app renders without errors on a local DuckDB build, the
headline numbers match the ground truth, a KPI opens to its source rows, and the approval rules hold in the
UI (the author cannot approve)."""
import json
import os
import sys

import duckdb
import pytest

from conftest import REPO

st_testing = pytest.importorskip("streamlit.testing.v1")
sys.path.insert(0, str(REPO / "scripts"))
import local_duckdb as L  # noqa: E402


@pytest.fixture(scope="module")
def app(small_data, tmp_path_factory):
    out, _ = small_data
    db = tmp_path_factory.mktemp("app") / "app.duckdb"
    con = duckdb.connect(str(db))
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, out)
    for step in (L.run_silver, L.run_gold, L.run_semantic, L.run_search, L.run_agent, L.run_outputs):
        step(con)
    con.close()
    os.environ["RISK_COPILOT_BACKEND"] = f"duckdb:{db}"
    os.environ["RISK_COPILOT_MIMIC_SNOWFLAKE"] = "1"      # UPPER CASE column names, as Snowflake returns them
    at = st_testing.AppTest.from_file(str(REPO / "app" / "streamlit_app.py"), default_timeout=120).run()
    sign_in(at, "analyst")
    golden = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "golden_answers.json").read_text())["questions"]}
    demo = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "demo_answers.json").read_text())["questions"]}
    return at, golden, demo


PASSWORD = "Demo@2026"


def sign_in(at, username, password=PASSWORD):
    at.text_input[0].input(username)
    at.text_input[1].input(password)
    [b for b in at.button if b.label == "Sign in"][0].click().run()
    return at


def sign_out(at):
    at.button(key="sign_out").click().run()
    assert "auth" not in at.session_state
    return at


def fresh():
    return st_testing.AppTest.from_file(str(REPO / "app" / "streamlit_app.py"), default_timeout=120).run()


def test_sign_in_gate_wrong_password_and_lockout(app):
    at = fresh()
    assert not at.exception and not at.radio and not at.metric          # nothing behind the gate
    sign_in(at, "investigator", "wrong")
    assert "auth" not in at.session_state and any("do not match" in e.value for e in at.error)
    for _ in range(4):
        sign_in(at, "investigator", "wrong")
    assert any("Too many attempts" in w.value for w in at.warning)
    sign_in(at, "investigator")                                          # still locked, even with the right password
    assert "auth" not in at.session_state
    sign_in(fresh(), "investigator")                                     # a new browser session is locked too
    sys.path.insert(0, str(REPO / "app"))
    import auth
    assert auth.locked_for("investigator") > 0
    auth.clear_failures("investigator")


def test_sign_in_shows_profile_and_sign_out_returns_to_gate(app):
    at = sign_in(fresh(), "Investigator")                                # usernames are case-insensitive
    assert not at.exception and at.session_state["auth"]["name"] == "Daniel Ortiz"
    assert at.session_state["user"] == "Daniel Ortiz" and at.metric
    sign_out(at)
    assert not at.metric and [b for b in at.button if b.label == "Sign in"]


def test_overview_numbers(app):
    at, golden, _ = app
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["Alerts in August"] == f"{golden['G03']['alerts']:,}"
    assert m["False positives, Q2"] == f"{golden['G04']['false_positive_rate_pct']:.1f}%"


def test_kpi_opens_to_source_rows(app):
    at, golden, _ = app
    at.selectbox(key="kpi_pick").set_value("G03 Alerts in August").run()
    rows = at.dataframe[0].value
    assert len(rows) == golden["G03"]["alerts"]
    assert {"source_file", "source_row"} <= {c.lower() for c in rows.columns}


def test_every_screen_renders(app):
    at, *_ = app
    for page in ["Data integration health", "Alert queue & customer", "Ask & cases", "Executive overview"]:
        at.radio(key="page").set_value(page).run()
        assert not at.exception, (page, [e.value for e in at.exception])


def _draft_for(at, name):
    at.radio(key="page").set_value("Alert queue & customer").run()
    [t for t in at.text_input if t.label == "Find a customer by name"][0].input(name).run()
    assert any(name in h.proto.body for h in at.get("html"))           # the customer card
    draft = [b for b in at.button if b.label.startswith("Draft")][0]
    return draft


def test_roles_and_four_eyes_in_the_ui(app):
    at, _, demo = app
    name = demo["D05"]["name"]
    assert _draft_for(at, name).disabled                                 # an analyst cannot draft
    sign_out(at)
    sign_in(at, "investigator")
    _draft_for(at, name).click().run()
    assert at.session_state["page"] == "Ask & cases" and not at.exception
    assert [b for b in at.button if b.label == "Approve"][0].disabled    # an investigator cannot approve
    sign_out(at)
    sign_in(at, "approver")
    at.radio(key="page").set_value("Ask & cases").run()
    [b for b in at.button if b.label == "Approve"][0].click().run()
    assert any("Approved by Sarah Whitfield" in s.value for s in at.success), [s.value for s in at.success]
    # the approver drafts a case of their own and is blocked from approving it
    _draft_for(at, name).click().run()
    [b for b in at.button if b.label == "Approve"][0].click().run()
    assert any("cannot approve" in e.value for e in at.error)


def test_roles_enforced_server_side(app):
    from outputs import case_store as C
    with pytest.raises(C.ApprovalError):
        C.decide("00000000-0000-0000-0000-000000000000", "Someone", "APPROVED", None, role="Investigator")
    with pytest.raises(C.ApprovalError):
        C.draft_narrative("x", "Someone", None, role="Analyst")


def test_sign_out_forgets_the_previous_user(app):
    at = sign_in(fresh(), "investigator")
    at.radio(key="page").set_value("Ask & cases").run()
    at.session_state["verified_x"] = True
    sign_out(at)
    assert "verified_x" not in at.session_state
    sign_in(at, "analyst")
    assert at.session_state["page"] == "Executive overview"


def test_pdf_download_is_a_real_pdf_and_writes_no_stray_files(app):
    at, *_ = app
    before = set(p.name for p in REPO.iterdir())
    at.radio(key="page").set_value("Ask & cases").run()
    assert at.get("download_button")                      # the case PDF is offered
    after = set(p.name for p in REPO.iterdir())
    assert not {n for n in after - before if "BytesIO" in n}


def test_export_pdf_to_a_buffer():
    import io
    from outputs.export_pdf import export_pdf
    buf = io.BytesIO()
    export_pdf("# Title\n\nSome text with $1,000.\n", buf, status="DRAFT")
    assert buf.getvalue().startswith(b"%PDF") and len(buf.getvalue()) > 1000


def test_no_raw_codes_underscores_or_brackets_on_screen(app):
    """Visible prose has no snake_case codes, file names or [bracketed] tags (tables and code blocks aside)."""
    import re
    at, *_ = app
    bad = re.compile(r"[A-Za-z]_[A-Za-z]|\[[^\]]*\]|\.csv|\.py\b")
    for page in ["Executive overview", "Data integration health", "Alert queue & customer", "Ask & cases"]:
        at.radio(key="page").set_value(page).run()
        seen = [m.value for m in at.markdown] + [c.value for c in at.caption] + [h.value for h in at.subheader] \
            + [m.label for m in at.metric] + [b.label for b in at.button]
        clean = [re.sub(r"<[^>]+>|`[^`]*`|\]\([^)]*\)", "", str(t)) for t in seen]
        hits = [t[max(0, m.start() - 40):m.end() + 40] for t in clean for m in bad.finditer(t)]
        assert not hits, (page, hits[:8])


def test_password_hashing_and_user_file():
    sys.path.insert(0, str(REPO / "app"))
    import auth
    h = auth.hash_password("x")
    assert h.startswith("pbkdf2_sha256$") and auth._check("x", h) and not auth._check("y", h)
    users = auth.load_users()
    assert {"analyst", "investigator", "approver"} <= set(users)
    assert all("password" not in u and u["password_hash"].startswith("pbkdf2_sha256$") for u in users.values())
    assert auth.verify("approver", "Demo@2026", users)["role"] == "Approver"
    assert auth.verify("approver", "", users) is None and auth.verify("nobody", "Demo@2026", users) is None
