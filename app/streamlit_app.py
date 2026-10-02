"""Sahasranshu Risk Copilot - Streamlit app (F8). No AI anywhere.

  streamlit run app/streamlit_app.py                                   # against Snowflake (connection "default")
  RISK_COPILOT_BACKEND=duckdb:<file> streamlit run app/streamlit_app.py  # offline, on a local DuckDB build

Four screens, as in the build plan:
  1. Executive overview        headline metrics, where the risk is, top of the queue
  2. Data integration health   load reconciliation, entity resolution, data-quality exceptions
  3. Alert queue & customer    ranked queue; one customer across both cores, with evidence rows
  4. Ask & cases               any question (routed by rules), case narratives with four-eyes approval
Every summary number opens to the rows behind it (source file and row) in three clicks or fewer.
Presentation lives in app/ui.py; this file only arranges the screens.
"""
import io
import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_executor, numeric  # noqa: E402
import ui  # noqa: E402
from ui import esc, pill  # noqa: E402

from agent.answer import answer, customer_view, log_question  # noqa: E402
from agent.router import find_customers  # noqa: E402
from outputs import case_store as C  # noqa: E402
from outputs.export_pdf import export_pdf  # noqa: E402
from outputs.narrative import _commas  # noqa: E402
from semantic.catalog import by_id, headline, run_question  # noqa: E402

RULE_LABEL = ui.RULE_LABEL
AS_OF = "31 Aug 2026"
st.set_page_config(page_title="Risk Copilot", page_icon="🛡️", layout="wide")
ui.inject_css()


def md_safe(text):
    """Markdown with dollar amounts shown as money, not as maths ('$' starts a formula in Streamlit)."""
    return _commas(str(text or "")).replace("$", "\\$")


def money(x):
    return f"${float(x):,.0f}"


def style(chart):
    return (chart.configure_view(strokeWidth=0)
            .configure_axis(labelColor=ui.MUTED, titleColor=ui.MUTED, gridColor="#edf0f5", domainColor="#c9d2e0",
                            labelFontSize=11, titleFontSize=11, titleFontWeight=600)
            .configure_legend(labelColor=ui.INK, titleColor=ui.MUTED, orient="top"))


def hbar(df, label, value, title, color=ui.ACCENT):
    """Single-series horizontal bars, sorted by value, with hover tooltips."""
    base = alt.Chart(df).encode(y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260, ticks=False)),
                                x=alt.X(f"{value}:Q", title=title, axis=alt.Axis(grid=True)),
                                tooltip=[alt.Tooltip(f"{label}:N", title="Item"), alt.Tooltip(f"{value}:Q", title=title)])
    bars = base.mark_bar(color=color, cornerRadiusEnd=4, height=16)
    text = base.mark_text(align="left", dx=4, color=ui.INK, fontSize=11).encode(text=f"{value}:Q")
    return style((bars + text).properties(height=alt.Step(26)))


# ---------------------------------------------------------------- data access
@st.cache_resource(show_spinner="Connecting to the data...")
def executor():
    return get_executor()


@st.cache_data(ttl=600, show_spinner=False)
def q(sql):
    return numeric(executor()(sql))


def q_safe(sql, cached=True):
    try:
        return q(sql) if cached else numeric(executor()(sql))
    except Exception as e:                       # a table this backend does not have
        st.info(f"Not available on this backend ({type(e).__name__}).")
        return None


@st.cache_data(ttl=600, show_spinner=False)
def catalog_answer(qid):
    item = by_id()[qid]
    df = run_question(item, executor())
    return headline(item, df), numeric(df)


@st.cache_data(ttl=600, show_spinner=False)
def thresholds():
    t = q("SELECT name, num_value FROM GOLD.CONFIG_PARAM WHERE num_value IS NOT NULL")
    return dict(zip(t["name"], t["num_value"].astype(float)))


def go(page, **state):
    st.session_state.update(state)
    st.session_state["nav_to"] = page          # applied before the navigation widget is drawn
    st.rerun()


def selected_row(event):
    rows = getattr(getattr(event, "selection", None), "rows", None) or []
    return rows[0] if rows else None


def backend_label():
    b = executor().backend
    return "Snowflake" if b.startswith("Snowflake") or "Streamlit in Snowflake" in b else "Offline copy"


def meta():
    return (pill("Synthetic demo data", "amber", dot=True) + pill(f"Data: {backend_label()}", "blue", dot=True)
            + pill(f"As of {AS_OF}") + pill(f"User: {st.session_state.get('user', '')}", "navy"))


QUEUE_COLUMNS = {
    "queue_rank": st.column_config.NumberColumn("#", width="small", format="%d"),
    "customer": st.column_config.TextColumn("Customer", width="medium"),
    "origin": st.column_config.TextColumn("Origin", width="small"),
    "priority_score": st.column_config.ProgressColumn("Priority", min_value=0, max_value=100, format="%.0f", width="small"),
    "engine_score": st.column_config.NumberColumn("Engine", format="%.0f", width="small"),
    "legacy_score": st.column_config.TextColumn("Legacy", width="small"),
    "reasons": st.column_config.ListColumn("Why", width="large"),
}


def queue_frame(df):
    out = df.copy()
    for c in ("priority_score", "engine_score", "legacy_score"):
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    if "legacy_score" in out:
        out["legacy_score"] = out["legacy_score"].map(lambda v: "–" if pd.isna(v) else f"{v:.0f}")
    out["origin"] = out["origin"].map(ui.ORIGIN_NAME).fillna(out["origin"])
    out["reasons"] = out["reasons"].fillna("").map(
        lambda r: [RULE_LABEL.get(x.strip(), x.strip().replace("LEGACY_", "Legacy: ").replace("_", " ").title())
                   for x in str(r).split(";") if x.strip()])
    return out


# ---------------------------------------------------------------- sidebar
PAGES = ["Executive overview", "Data integration health", "Alert queue & customer", "Ask & cases"]
st.session_state.setdefault("page", PAGES[0])
if "nav_to" in st.session_state:
    st.session_state["page"] = st.session_state.pop("nav_to")
with st.sidebar:
    st.html('<div class="rc-brand"><div class="logo"><div class="mark">RC</div><div><div class="name">Risk Copilot</div>'
            '<div class="sub">Risk, fraud &amp; regulatory intelligence</div></div></div></div>')
    st.radio("Screen", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    st.text_input("You are", value=os.getenv("RISK_COPILOT_USER", "jehal"), key="user",
                  help="Recorded on every question, draft and approval. An author can never approve their own case.")
    st.html(f'<div class="rc-side-note"><b>Kestrel Valley Bank</b> (Core A) + <b>Pellbrook Savings Bank</b> (Core B). '
            f'Synthetic demo data; every person is fictional.<br><br>Data: {esc(executor().backend.replace(str(Path.home()), "~"))}</div>'
            '<div class="rc-trust"><b>No AI.</b> Every answer comes from reviewed SQL, transparent rules and reviewed '
            'templates, so the same question always gets the same answer.</div>')


# ---------------------------------------------------------------- 1. overview
EVIDENCE = {   # KPI -> the rows behind it
    "G03": "SELECT alert_id, source_system, scenario, alert_date, branch, status, source_file, source_row "
           "FROM SEMANTIC.V_ALERT WHERE alert_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31' ORDER BY alert_date",
    "G04": "SELECT alert_id, source_system, scenario, closed_on, disposition, source_file, source_row "
           "FROM SEMANTIC.V_ALERT WHERE closed_on BETWEEN DATE '2026-04-01' AND DATE '2026-06-30' ORDER BY closed_on",
    "G06": "SELECT alert_id, source_system, scenario, alert_date, status, owner, source_file, source_row "
           "FROM SEMANTIC.V_ALERT WHERE is_open AND alert_date < DATE '2026-08-01' ORDER BY alert_date",
    "G09": "SELECT loan_id, source_system, loan_type, principal_usd, source_file, source_row FROM SEMANTIC.V_LOAN "
           "ORDER BY principal_usd DESC LIMIT 500",
    "G10": "SELECT loan_id, source_system, cre_category, principal_usd, source_file, source_row FROM SEMANTIC.V_LOAN "
           "WHERE is_non_owner_occupied_cre ORDER BY principal_usd DESC",
    "G02": "SELECT party_id, display_name, cores, core_a_key, core_b_key, link_reasons FROM GOLD.PARTY "
           "WHERE cores = 2 ORDER BY display_name LIMIT 500",
}
KPIS = [("G02", "Unique customers", "unique_customers", "{:,.0f}"),
        ("G03", "Alerts in August", "alerts", "{:,.0f}"),
        ("G04", "False positives, Q2", "false_positive_rate_pct", "{:.1f}%"),
        ("G06", "Open > 30 days", "open_over_30_days", "{:,.0f}"),
        ("G09", "Loan-to-deposit", "loan_to_deposit_pct", "{:.1f}%"),
        ("G10", "CRE / capital", "cre_to_capital_pct", "{:.1f}%")]


def kpi_context(qid, df):
    r = df.iloc[0]
    return {"G02": lambda: f"{int(r.customers_in_both_cores):,} bank with both cores",
            "G03": lambda: f"Core A {int(r.core_a_alerts)} · Core B {int(r.core_b_alerts)}",
            "G04": lambda: f"{int(r.false_positives):,} of {int(r.closed):,} closed Apr-Jun",
            "G06": lambda: f"of {int(r.open_total):,} open; SLA is 30 days",
            "G09": lambda: "loans vs deposits, both cores",
            "G10": lambda: "non-owner-occupied CRE vs capital"}[qid]()


def _pick_kpi(value):
    st.session_state["kpi_pick"] = value


def overview():
    ui.page_header("Executive overview", "One bank, two core systems: where the risk is and how much of it the legacy systems missed",
                   meta())
    h = q("""SELECT (SELECT COUNT(DISTINCT party_id) FROM GOLD.RISK_SIGNAL WHERE rule_code = 'XCORE_CASH_30D') AS xcore,
                    (SELECT COUNT(DISTINCT s.party_id) FROM GOLD.RISK_SIGNAL s WHERE s.rule_code = 'XCORE_CASH_30D'
                        AND NOT EXISTS (SELECT 1 FROM GOLD.ALERT a WHERE a.party_id = s.party_id)) AS xcore_no_alert,
                    (SELECT COUNT(DISTINCT party_id) FROM GOLD.RISK_SIGNAL WHERE rule_code = 'CTR_AGGREGATION_MISSED') AS ctr_missed,
                    (SELECT COUNT(*) FROM GOLD.ALERT_QUEUE) AS queue_size""").iloc[0]
    st.html(f'<div class="rc-hero"><div class="lead"><div class="eyebrow">What the merger hid</div>'
            f'<h2>{int(h.xcore)} customers moved over $50,000 in cash across the two banks in 30 days. '
            f'{"None" if int(h.xcore_no_alert) == int(h.xcore) else int(h.xcore) - int(h.xcore_no_alert)} of them had '
            f'a legacy alert in either core.</h2><p>Each core saw only its own half of the cash, so every deposit and every '
            f'monthly total stayed under its own threshold. Joined in Snowflake, the pattern is plain.</p></div>'
            f'<div class="stats"><div class="stat"><b>{int(h.xcore_no_alert)}</b><span>missed by both legacy systems</span></div>'
            f'<div class="stat"><b>{int(h.ctr_missed)}</b><span>with a missed CTR across cores</span></div>'
            f'<div class="stat"><b>{int(h.queue_size)}</b><span>items in one ranked queue</span></div></div></div>')

    cols = st.columns(len(KPIS))
    for col, (qid, label, field, fmt) in zip(cols, KPIS):
        _, df = catalog_answer(qid)
        with col.container(border=True, key=f"kpi_{qid}"):
            st.metric(label, fmt.format(float(df.iloc[0][field])))
            st.caption(md_safe(kpi_context(qid, df)))
            st.button("View rows", key=f"kpi_btn_{qid}", type="tertiary", on_click=_pick_kpi, args=(f"{qid} {label}",))
    pick = st.selectbox("Show the rows behind", ["-"] + [f"{k[0]} {k[1]}" for k in KPIS], key="kpi_pick")
    if pick != "-":
        qid = pick.split()[0]
        head, df = catalog_answer(qid)
        with st.container(border=True):
            st.html(f'<div style="font-weight:650;font-size:1.02rem">{esc(_commas(head))}</div>'
                    f'<div style="color:{ui.MUTED};font-size:.88rem;margin-top:2px">Reviewed question {esc(qid)}: '
                    f'{esc(by_id()[qid]["question"])}</div>')
            rows = q(EVIDENCE[qid])
            st.dataframe(rows, width="stretch", hide_index=True, height=300)
            with st.expander("SQL used"):
                st.code(by_id()[qid]["sql"], language="sql")

    ui.section("Where the risk is", f"one queue across both cores and the risk engine · {int(h.queue_size)} items")
    left, right = st.columns([3, 2], gap="medium")
    with left.container(border=True):
        st.markdown("**Top of the work queue**: select a customer to open their evidence")
        top = q("SELECT queue_rank, display_name AS customer, origin, priority_score, reasons, party_id "
                "FROM GOLD.ALERT_QUEUE WHERE queue_rank <= 10 ORDER BY queue_rank")
        ev = st.dataframe(queue_frame(top).drop(columns=["party_id"]), width="stretch", hide_index=True,
                          column_config=QUEUE_COLUMNS, on_select="rerun", selection_mode="single-row", key="ov_top",
                          height=388)
        i = selected_row(ev)
        if i is not None and st.button(f"Open {top.iloc[i]['customer'].title()}", type="primary"):
            go("Alert queue & customer", party_id=top.iloc[i]["party_id"])
    with right.container(border=True):
        st.markdown("**How often each risk rule fires** (customers)")
        rules = q("SELECT rule_code, COUNT(*) AS customers FROM GOLD.RISK_SIGNAL GROUP BY rule_code ORDER BY customers DESC")
        rules["rule"] = rules["rule_code"].map(RULE_LABEL).fillna(rules["rule_code"])
        st.altair_chart(hbar(rules, "rule", "customers", "customers"), width="stretch")
        mix = q("SELECT origin, COUNT(*) AS items FROM GOLD.ALERT_QUEUE GROUP BY origin ORDER BY items DESC")
        mix["origin"] = mix["origin"].map(ui.ORIGIN_NAME).fillna(mix["origin"])
        mix["bar"] = "Queue"
        st.markdown("**Where the queue comes from**")
        st.altair_chart(style(alt.Chart(mix).mark_bar(height=26).encode(
            x=alt.X("items:Q", stack="normalize", title=None, axis=alt.Axis(format="%", grid=False)),
            y=alt.Y("bar:N", title=None, axis=None),
            color=alt.Color("origin:N", title=None, scale=alt.Scale(
                domain=list(ui.ORIGIN_NAME.values()), range=[ui.ACCENT, ui.CORE_A, ui.CORE_B])),
            tooltip=["origin:N", "items:Q"]).properties(height=60)), width="stretch")


# ---------------------------------------------------------------- 2. data health
def data_health():
    ui.page_header("Data integration health", "Can the numbers be trusted? Every file reconciled, every customer matched with "
                   "evidence, every bad record flagged", meta())
    m = q("""SELECT (SELECT COUNT(*) FROM SILVER.AUTO_LINKS) AS auto_links,
                    (SELECT COUNT(*) FROM SILVER.MATCH_REVIEW_QUEUE) AS review_queue,
                    (SELECT COUNT(*) FROM GOLD.PARTY) AS resolved_customers,
                    (SELECT COUNT(*) FROM GOLD.PARTY WHERE cores = 2) AS in_both_cores,
                    (SELECT COUNT(*) FROM SILVER.DQ_EXCEPTIONS) AS dq_records,
                    (SELECT COUNT(*) FROM SILVER.CUSTOMER_STD) AS customer_records""")
    rec = None
    try:
        rec = q("SELECT * FROM BRONZE.V_LOAD_RECONCILIATION")
    except Exception:
        pass
    r = m.iloc[0]
    if rec is not None:
        ok, n = int((rec["status"] == "MATCH").sum()), len(rec)
        rows = int(rec["rows_loaded"].fillna(0).sum())
        bronze = (f'<div class="name">Bronze · load</div><div class="big">{ok} of {n} files'
                  f'<span class="ok">{"&#10003;" if ok == n else "&#9888;"}</span></div>'
                  f'<div class="sub">{rows:,} rows match control totals</div>')
    else:
        bronze = '<div class="name">Bronze · load</div><div class="big">-</div><div class="sub">reconciliation view not on this backend</div>'
    st.html('<div class="rc-pipe">'
            f'<div class="rc-stage">{bronze}</div><div class="rc-arrow">&#8594;</div>'
            f'<div class="rc-stage"><div class="name">Silver · match</div><div class="big">{int(r.auto_links):,} linked'
            f'<span class="ok">&#10003;</span></div><div class="sub">0 false merges · {int(r.review_queue)} pairs for a person</div></div>'
            f'<div class="rc-arrow">&#8594;</div>'
            f'<div class="rc-stage"><div class="name">Gold · one bank</div><div class="big">{int(r.resolved_customers):,}'
            f'<span class="ok">&#10003;</span></div><div class="sub">customers from {int(r.customer_records):,} records</div></div>'
            f'<div class="rc-arrow">&#8594;</div>'
            f'<div class="rc-stage"><div class="name">Quality</div><div class="big">{int(r.dq_records):,} flagged</div>'
            f'<div class="sub">bad records listed, never dropped</div></div></div>')

    ui.section("1. Load reconciliation", "Bronze row counts and amounts vs each core's extract control totals")
    if rec is not None:
        recd = rec.copy()
        recd["status"] = recd["status"].map(lambda s: f"✓ {s}" if s == "MATCH" else f"✗ {s}")
        recd["core"] = recd["core"].map(ui.CORE_NAME).fillna(recd["core"])
        st.dataframe(recd, width="stretch", hide_index=True, column_config={
            "amount_expected": st.column_config.NumberColumn("amount expected", format="dollar"),
            "amount_loaded": st.column_config.NumberColumn("amount loaded", format="dollar"),
            "rows_expected": st.column_config.NumberColumn("rows expected", format="localized"),
            "rows_loaded": st.column_config.NumberColumn("rows loaded", format="localized")})
    else:
        st.info("Not available on this backend (CatalogException).")

    ui.section("2. Entity resolution across the cores", "same customer, different IDs: matched by evidence, never by guess")
    c1, c2, c3, c4 = st.columns(4)
    for col, label, val in ((c1, "Records linked automatically", r.auto_links), (c2, "Pairs waiting for review", r.review_queue),
                            (c3, "Resolved customers", r.resolved_customers), (c4, "Customers in both cores", r.in_both_cores)):
        with col.container(border=True):
            st.metric(label, f"{int(val):,}")
    st.caption("Measured against ground truth: 0 false merges; 98.70% of true duplicates linked automatically, "
               "100% after the review queue.")
    with st.expander("Match review queue: uncertain pairs, never merged automatically"):
        st.dataframe(q("SELECT a_name, b_name, a_id, b_id, review_reason, reason_codes FROM SILVER.MATCH_REVIEW_QUEUE "
                       "ORDER BY review_reason, a_name"), width="stretch", hide_index=True)

    ui.section("3. Data-quality exceptions", "every record that breaks a rule, with its source file and row")
    dq = q("SELECT rule_id, COUNT(*) AS records FROM SILVER.DQ_EXCEPTIONS GROUP BY rule_id ORDER BY records DESC")
    left, right = st.columns([2, 3], gap="medium")
    with left.container(border=True):
        dqc = dq.copy()
        dqc["rule"] = dqc["rule_id"].str.replace("DQ_", "").str.replace("_", " ").str.capitalize()
        st.altair_chart(hbar(dqc, "rule", "records", "records", color=ui.AMBER), width="stretch")
    with right:
        rule = st.selectbox("Show the records for", dq["rule_id"].tolist(), key="dq_rule")
        st.dataframe(q(f"SELECT source_system, entity, record_key, field, observed_value, source_file, source_row "
                       f"FROM SILVER.DQ_EXCEPTIONS WHERE rule_id = '{rule}' ORDER BY source_system, source_row"),
                     width="stretch", hide_index=True, height=260)


# ---------------------------------------------------------------- 3. queue & customer
def cash_story(cash, t):
    """The signature visual: daily cash by core against the CTR line, and running totals against each core's rule."""
    ctr = t.get("thresholds.ctr_cash_threshold_usd", 10000.0)
    per_core = t.get("thresholds.legacy_per_core_cash_30d_usd", 30000.0)
    xcore = t.get("thresholds.cross_core_cash_total_usd", 50000.0)
    d = cash.copy()
    d["day"] = pd.to_datetime(d["posted_at"]).dt.normalize()
    d["core"] = d["source_system"].map({"core_a": "Core A", "core_b": "Core B"})
    d["amount_usd"] = d["amount_usd"].astype(float)
    domain, rng = ["Core A", "Core B"], [ui.CORE_A, ui.CORE_B]
    daily = d.groupby(["day", "core"], as_index=False)["amount_usd"].sum()
    totals = d.groupby("day").agg(total=("amount_usd", "sum"), cores=("source_system", "nunique"),
                                  ctr=("ctr_filed", lambda s: bool(pd.Series(s).astype(bool).any()))).reset_index()
    missed = totals[(totals.cores >= 2) & (totals.total > ctr) & (~totals.ctr)]
    x = alt.X("day:T", title=None, axis=alt.Axis(format="%d %b", labelAngle=0, grid=False))
    bars = alt.Chart(daily).mark_bar(width=14, cornerRadiusEnd=2).encode(
        x=x, y=alt.Y("sum(amount_usd):Q", title="cash deposited that day ($)", axis=alt.Axis(format="$,.0f")),
        color=alt.Color("core:N", title=None, scale=alt.Scale(domain=domain, range=rng)),
        tooltip=[alt.Tooltip("day:T", format="%d %b %Y"), "core:N", alt.Tooltip("amount_usd:Q", format="$,.2f")])
    rule_ctr = alt.Chart(pd.DataFrame({"y": [ctr]})).mark_rule(color=ui.RED, strokeDash=[5, 4], size=1.5).encode(y="y:Q")
    lab_ctr = alt.Chart(pd.DataFrame({"y": [ctr], "t": [f"CTR threshold {money(ctr)} per person per day"]})).mark_text(
        align="right", dy=-7, x="width", color=ui.RED, fontSize=11, fontWeight=600).encode(y="y:Q", text="t:N")
    layers = [bars, rule_ctr, lab_ctr]
    if len(missed):
        layers.append(alt.Chart(missed).mark_text(dy=-10, color=ui.RED, fontWeight=700, fontSize=11).encode(
            x="day:T", y="total:Q", text=alt.value("No CTR filed")))
    daily_chart = alt.layer(*layers).properties(height=280)

    d = d.sort_values("posted_at")
    run = []
    for core, g in d.groupby("core"):
        g = g.groupby("day", as_index=False)["amount_usd"].sum()
        g["running"] = g["amount_usd"].cumsum()
        g["line"] = core
        run.append(g[["day", "running", "line"]])
    allg = d.groupby("day", as_index=False)["amount_usd"].sum()
    allg["running"] = allg["amount_usd"].cumsum()
    allg["line"] = "Both cores"
    run = pd.concat(run + [allg[["day", "running", "line"]]])
    lines = alt.Chart(run).mark_line(interpolate="step-after", strokeWidth=3, point=alt.OverlayMarkDef(size=36)).encode(
        x=x, y=alt.Y("running:Q", title="running total of cash ($)", axis=alt.Axis(format="$,.0f"),
                     scale=alt.Scale(domain=[0, max(float(run.running.max()), xcore) * 1.12])),
        color=alt.Color("line:N", title=None, scale=alt.Scale(domain=domain + ["Both cores"], range=rng + [ui.BOTH])),
        tooltip=[alt.Tooltip("day:T", format="%d %b %Y"), "line:N", alt.Tooltip("running:Q", format="$,.2f")])
    refs = pd.DataFrame({"y": [per_core, xcore], "t": [f"Each core's legacy alert rule {money(per_core)} in 30 days",
                                                         f"Cross-core rule {money(xcore)} in 30 days"],
                         "c": [ui.GREY, ui.RED]})
    ref_rules = alt.Chart(refs).mark_rule(strokeDash=[5, 4], size=1.5).encode(y="y:Q", color=alt.Color("c:N", scale=None))
    ref_text = alt.Chart(refs).mark_text(align="right", dy=-7, x="width", fontSize=11, fontWeight=600).encode(
        y="y:Q", text="t:N", color=alt.Color("c:N", scale=None))
    run_chart = alt.layer(lines, ref_rules, ref_text).properties(height=280)
    return daily_chart, run_chart, d


def queue_and_customer():
    ui.page_header("Alert queue & customer", "One ranked queue across both cores; every score shows its reasons and evidence",
                   meta())
    with st.container(border=True):
        f1, f2, f3 = st.columns([2, 2, 3])
        origins = f1.multiselect("Origin", ["RISK_ENGINE", "LEGACY_CORE_A", "LEGACY_CORE_B"],
                                 default=["RISK_ENGINE", "LEGACY_CORE_A", "LEGACY_CORE_B"],
                                 format_func=lambda o: ui.ORIGIN_NAME.get(o, o))
        min_score = f2.slider("Minimum priority", 0, 100, 0, step=5)
        name = f3.text_input("Find a customer by name", placeholder="e.g. Deborah Sanford")
    if name:
        found = find_customers(name, executor())
        if found:
            st.session_state["party_id"] = found[0].party_id
        else:
            st.warning(f"No customer named {name!r}.")
    if origins:
        in_list = ", ".join(f"'{o}'" for o in origins)
        queue = q(f"SELECT queue_rank, display_name AS customer, origin, priority_score, engine_score, legacy_score, "
                  f"reasons, party_id FROM GOLD.ALERT_QUEUE WHERE origin IN ({in_list}) AND priority_score >= {int(min_score)} "
                  f"ORDER BY queue_rank LIMIT 200")
        st.caption(f"{len(queue)} items shown (first 200). Select one to open the customer.")
        ev = st.dataframe(queue_frame(queue).drop(columns=["party_id"]), width="stretch", hide_index=True, height=300,
                          column_config=QUEUE_COLUMNS, on_select="rerun", selection_mode="single-row", key="queue_tbl")
        i = selected_row(ev)
        if i is not None and queue.iloc[i]["party_id"]:
            st.session_state["party_id"] = queue.iloc[i]["party_id"]

    pid = st.session_state.get("party_id")
    if not pid:
        st.info("Select a queue item or find a customer by name.")
        return
    v = customer_view(pid, executor())
    prof = v["profile"].iloc[0]
    risk = numeric(v["risk"])
    cash30 = numeric(v["cash_30d"])
    score = float(risk.risk_score[0]) if len(risk) else 0.0
    ranked = len(risk) and pd.notna(risk.queue_rank[0])
    rank = f"{int(risk.queue_rank[0])} of {int(risk.queue_size[0])}" if ranked else "not queued"

    ui.section("Customer", "one real customer, resolved across both cores")
    with st.container(border=True):
        ring, body = st.columns([1, 7], vertical_alignment="center")
        ring.html(ui.score_ring(score, 104))
        with body:
            st.subheader(f"{prof.display_name.title()}")
            ids = []
            if prof.core_a_key:
                ids.append(pill(f"Core A {prof.core_a_key}", "core-a"))
            if prof.core_b_key:
                ids.append(pill(f"Core B {str(prof.core_b_key)[:13]}…", "core-b"))
            kind = "Business" if prof.party_kind == "ORG" else "Person"
            cash_total = float(cash30["cash_usd"].astype(float).sum()) if len(cash30) else 0.0
            st.html(f'<div class="rc-meta" style="justify-content:flex-start">{"".join(ids)}{pill(kind)}'
                    f'{pill(f"{int(prof.cores)} core(s)", "blue")}</div>'
                    f'<div class="rc-kv"><div><span>Queue rank</span><b>{esc(rank)}</b></div>'
                    f'<div><span>Risk score</span><b>{score:.0f}</b></div>'
                    f'<div><span>Legacy alerts</span><b>{len(v["alerts"])}</b></div>'
                    f'<div><span>Cash in, 30 days</span><b>{money(cash_total)}</b></div>'
                    f'<div><span>City</span><b>{esc(str(prof.city or "").title())}, {esc(prof.state or "")}</b></div></div>')
        links = [ui.LINK_LABEL.get(x, x.replace("_", " ").title()) for x in str(prof.link_reasons or "").split(";") if x]
        st.html('<div style="margin-top:10px;font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;'
                f'color:{ui.MUTED};font-weight:700;margin-bottom:6px">Linked across cores by</div>'
                + (ui.chips(links) if links else ui.chips(["Single record in one core"])))

    if len(v["signals"]):
        sig = numeric(v["signals"])
        ui.section("Why this customer is ranked here", f"score {score:.0f} = the sum of the rule weights (kept within 0-100)")
        st.html(ui.rule_cards([{"rule_code": s.rule_code, "weight": s.weight, "evidence": _commas(s.evidence_text)}
                               for s in sig.itertuples()]))

    cash = q(f"SELECT posted_at, source_system, account_id, amount_usd, branch, ctr_filed, source_file, source_row "
             f"FROM GOLD.TRANSACTION WHERE party_id = '{pid}' AND txn_type = 'CASH_DEPOSIT' "
             f"AND posted_date > (SELECT MAX(posted_date) FROM GOLD.TRANSACTION) - 30 ORDER BY posted_at")
    if len(cash) and cash["source_system"].nunique() >= 1:
        daily_chart, run_chart, d = cash_story(cash, thresholds())
        per = d.groupby("source_system")["amount_usd"].sum()
        a_usd, b_usd = float(per.get("core_a", 0)), float(per.get("core_b", 0))
        title = (f"Each bank saw under {money(thresholds().get('thresholds.legacy_per_core_cash_30d_usd', 30000))}. "
                 f"Together: {money(a_usd + b_usd)}." if a_usd and b_usd else f"Cash deposits: {money(a_usd + b_usd)} in 30 days")
        ui.section("Cash across both cores, last 30 days", "what each legacy system saw vs what the bank really holds")
        with st.container(border=True):
            st.html(f'<div style="font-size:1.15rem;font-weight:650;color:{ui.INK}">{esc(title)}</div>'
                    f'<div style="color:{ui.MUTED};font-size:.88rem;margin:2px 0 4px 0">Core A {money(a_usd)} + Core B '
                    f'{money(b_usd)} in {len(d)} deposits, the largest {money(d.amount_usd.max())}.</div>')
            c1, c2 = st.columns(2, gap="large")
            c1.altair_chart(style(daily_chart), width="stretch")
            c2.altair_chart(style(run_chart), width="stretch")

    t1, t2, t3, t4 = st.tabs(["Accounts and cash", "KYC", "Alerts and notes", "Loans"])
    money_cols = {c: st.column_config.NumberColumn(c.replace("_", " "), format="dollar")
                  for c in ("balance_usd", "amount_usd", "expected_monthly_cash_usd", "principal_usd")}
    with t1:
        st.dataframe(numeric(v["accounts"]), width="stretch", hide_index=True, column_config=money_cols)
        st.markdown(f"**Cash deposits, last 30 days** ({len(cash)})")
        st.dataframe(cash, width="stretch", hide_index=True, column_config=money_cols)
    with t2:
        st.dataframe(numeric(v["kyc"]), width="stretch", hide_index=True, column_config=money_cols)
    with t3:
        st.dataframe(v["alerts"], width="stretch", hide_index=True)
        if v.get("notes") is not None and len(v["notes"]):
            st.dataframe(v["notes"][["citation", "snippet"]], width="stretch", hide_index=True)
        else:
            st.caption("No investigator notes for this customer.")
    with t4:
        st.dataframe(numeric(v["loans"]), width="stretch", hide_index=True, column_config=money_cols)
    if st.button("Draft a case narrative for this customer", type="primary"):
        oid, _ = C.draft_narrative(pid, st.session_state["user"], executor())
        go("Ask & cases", case_id=oid, flash=f"Draft {oid[:8]} saved. Someone other than "
                                               f"{st.session_state['user']} must approve it.")


# ---------------------------------------------------------------- 4. ask & cases
EXAMPLES = ["Which customers moved more than $50k in cash across both cores in 30 days, and what do their KYC files say?",
            "On which days did a customer's cash deposits across both cores exceed $10,000 with no CTR filed?",
            "Which alerts should my team work first today, and why?",
            "What does our BSA policy say about aggregating cash transactions across the two cores?",
            "Draft a case narrative for the highest-risk customer in the queue."]
EXAMPLE_LABELS = ["D01 · Cross-core cash", "D02 · Missed CTRs", "D03 · Work first",
                  "D04 · Policy", "D05 · Draft top case"]
ROUTE_KIND = {"CATALOG": "blue", "SEARCH": "core-b", "CUSTOMER": "core-a", "NARRATIVE": "amber", "CLARIFY": ""}


def ask_tab_body():
    with st.container(border=True):
        st.html(f'<div style="font-weight:650;font-size:1.05rem">Ask in plain English</div><div style="color:{ui.MUTED};'
                'font-size:.88rem;margin:2px 0 8px 0">Readable rules route each question to a reviewed SQL question, '
                'document search, the customer view or a case narrative. If no rule is sure, it says so.</div>')
        ex_cols = st.columns(len(EXAMPLES))
        for col, ex, label in zip(ex_cols, EXAMPLES, EXAMPLE_LABELS):
            if col.button(label, help=ex, width="stretch"):
                st.session_state["question"] = ex
        text = st.text_input("Question", key="question", placeholder="e.g. How many alerts did we get last month?")
    if not text:
        return
    a = answer(text, executor())
    log_question(a, executor(), app_user=st.session_state["user"])
    with st.container(border=True):
        st.html(f'<div class="rc-meta" style="justify-content:flex-start;margin-bottom:10px">'
                f'{pill("Route: " + a.route, ROUTE_KIND.get(a.route, ""), dot=True)}{pill("Rule: " + str(a.rule))}'
                + (pill("Answered as " + str(a.answered_as)[:90]) if a.answered_as else "") + "</div>"
                f'<div style="font-size:1.12rem;font-weight:650;line-height:1.45;color:{ui.INK};border-left:4px solid '
                f'{ui.ACCENT};padding:6px 0 6px 14px;background:#f5f8ff;border-radius:0 8px 8px 0">{esc(_commas(a.headline))}</div>')
        if a.suggestions:
            cat = by_id()
            st.markdown("**Did you mean one of these reviewed questions?**")
            for qid, _ in a.suggestions:
                st.markdown(f"- {md_safe(cat[qid]['question'])}")
        if a.text:
            st.markdown(md_safe(a.text))
        else:
            for title, df in a.tables:
                st.markdown(f"**{title}**")
                st.dataframe(numeric(df), width="stretch", hide_index=True)
        if a.citations:
            with st.expander(f"Sources ({len(a.citations)})"):
                for c in a.citations:
                    st.markdown(f"- {md_safe(c)}")


def case_tab_body():
    outs = C.list_outputs(executor(), limit=50)
    if not len(outs):
        st.info("No case narratives yet. Draft one from a customer, or ask for one.")
        return
    ids = outs["output_id"].tolist()
    default = ids.index(st.session_state["case_id"]) if st.session_state.get("case_id") in ids else 0
    pick = st.selectbox("Case", ids, index=default,
                        format_func=lambda i: (lambda r: f"{r.subject.title()} · {r.status} · by {r.author} · {str(r.created_at)[:16]}")(
                            outs[outs.output_id == i].iloc[0]))
    md, status = C.final_text(pick, executor())
    out = C.get_output(pick, executor())
    row = outs[outs.output_id == pick].iloc[0]
    with st.container(border=True):
        head = st.empty()                 # filled after the buttons, so a Verify click shows at once
        b1, b2, b3, b4, b5 = st.columns([2, 2, 2, 2, 3], vertical_alignment="bottom")
        comment = b5.text_input("Comment", key="case_comment", placeholder="optional, saved with the decision")
        for col, label, decision in ((b1, "Approve", "APPROVED"), (b2, "Reject", "REJECTED")):
            if col.button(label, disabled=status != "DRAFT", width="stretch",
                          type="primary" if label == "Approve" else "secondary"):
                try:
                    C.decide(pick, st.session_state["user"], decision, executor(), comment)
                    go("Ask & cases", case_id=pick, flash=f"{decision.title()} by {st.session_state['user']}.")
                except C.ApprovalError as e:
                    st.error(str(e))
        if b3.button("Verify", width="stretch"):
            ok, info = C.reproduce(pick, executor())
            st.session_state[f"verified_{pick}"] = ok
            checks = {"re_rendered_text_matches_fingerprint": "re-rendered text",
                      "stored_text_matches_fingerprint": "stored text", "stored_evidence_matches_fingerprint": "stored evidence"}
            detail = ", ".join(f"{name} {'✓' if info.get(k) else '✗'}" for k, name in checks.items())
            (st.success if ok else st.error)(("Reproduced byte for byte from the audit record: " if ok
                                              else "Mismatch with the audit record: ") + detail)
        buf = io.BytesIO()
        export_pdf(md, buf, status=status, footer=f"Output {pick} | status {status} | text SHA-256 "
                                                   f"{out['content_sha256'][:16]}... | synthetic data")
        b4.download_button("Download PDF", buf.getvalue(), file_name=f"{out['subject'].replace(' ', '_').lower()}_{pick[:8]}.pdf",
                           mime="application/pdf", width="stretch")
        verified = st.session_state.get(f"verified_{pick}")
        steps = [("Drafted", "done"),
                 ("Approved by a second person", "done" if status == "APPROVED" else "bad" if status == "REJECTED" else "now"),
                 ("Verified against the audit record", "done" if verified else "todo")]
        head.html(ui.stepper(steps)
                + f'<div class="rc-kv"><div><span>Status</span><b>{ui.status_pill(status)}</b></div>'
                f'<div><span>Author</span><b>{esc(out["author"])}</b></div>'
                f'<div><span>Approver</span><b>{esc(row.get("approver") if pd.notna(row.get("approver")) else "-")}</b></div>'
                f'<div><span>Output</span><b style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.95rem">'
                f'{esc(pick[:8])}</b></div>'
                f'<div><span>Text fingerprint (SHA-256)</span><b style="font-family:ui-monospace,Menlo,Consolas,monospace;'
                f'font-size:.95rem">{esc(out["content_sha256"][:16])}…</b></div></div>')
    with st.container(border=True, key="narrative"):
        st.markdown(md_safe(md))


def ask_and_cases():
    ui.page_header("Ask & cases", "Questions answered from reviewed SQL and cited documents; cases with four-eyes approval",
                   meta())
    banner = st.container()          # always present, so the tabs below keep their place (and their selected tab)
    if st.session_state.get("flash"):
        banner.success(st.session_state.pop("flash"))
    ask_tab, case_tab, log_tab = st.tabs(["Ask the copilot", "Case narratives", "Audit log"])
    with ask_tab:
        ask_tab_body()
    with case_tab:
        case_tab_body()
    with log_tab:
        log = q_safe("SELECT logged_at, app_user, route, rule, question, headline FROM AUDIT.QUESTION_LOG "
                     "ORDER BY logged_at DESC LIMIT 50", cached=False)
        if log is not None:
            st.dataframe(log, width="stretch", hide_index=True, column_config={
                "logged_at": st.column_config.DatetimeColumn("logged at", format="D MMM YYYY, HH:mm:ss"),
                "question": st.column_config.TextColumn("question", width="large"),
                "headline": st.column_config.TextColumn("headline", width="large")})
        st.caption("Every question is logged with its route, rule and sources; every case keeps its evidence snapshot.")


{"Executive overview": overview, "Data integration health": data_health,
 "Alert queue & customer": queue_and_customer, "Ask & cases": ask_and_cases}[st.session_state["page"]]()
