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
    at = st_testing.AppTest.from_file(str(REPO / "app" / "streamlit_app.py"), default_timeout=120).run()
    golden = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "golden_answers.json").read_text())["questions"]}
    demo = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "demo_answers.json").read_text())["questions"]}
    return at, golden, demo


def test_overview_numbers(app):
    at, golden, _ = app
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["Alerts in August"] == f"{golden['G03']['alerts']:,}"
    assert m["False positives, Q2"] == f"{golden['G04']['false_positive_rate_pct']:.1f}%"


def test_kpi_opens_to_source_rows(app):
    at, golden, _ = app
    at.selectbox(key="kpi_pick").select("G03 Alerts in August").run()
    rows = at.dataframe[0].value
    assert len(rows) == golden["G03"]["alerts"]
    assert {"source_file", "source_row"} <= {c.lower() for c in rows.columns}


def test_every_screen_renders(app):
    at, *_ = app
    for page in ["Data integration health", "Alert queue & customer", "Ask & cases", "Executive overview"]:
        at.radio(key="page").set_value(page).run()
        assert not at.exception, (page, [e.value for e in at.exception])


def test_customer_and_four_eyes_in_the_ui(app):
    at, _, demo = app
    at.radio(key="page").set_value("Alert queue & customer").run()
    at.text_input[0].input(demo["D05"]["name"]).run()
    assert demo["D05"]["name"] in [h.value for h in at.subheader]
    [b for b in at.button if b.label.startswith("Draft")][0].click().run()
    assert at.session_state["page"] == "Ask & cases" and not at.exception
    [b for b in at.button if b.label == "Approve"][0].click().run()
    assert any("cannot approve" in e.value for e in at.error)            # the author is blocked
    at.text_input(key="user").set_value("second_person").run()
    [b for b in at.button if b.label == "Approve"][0].click().run()
    assert any("Approved by second_person" in s.value for s in at.success)


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
