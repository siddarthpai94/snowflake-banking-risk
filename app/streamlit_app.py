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
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_executor, numeric  # noqa: E402
import auth  # noqa: E402
import charts  # noqa: E402
import ui  # noqa: E402
from ui import clean_text, esc, pill  # noqa: E402

from agent.answer import answer, customer_view, log_question  # noqa: E402
from agent.router import find_customers  # noqa: E402
from outputs import case_store as C  # noqa: E402
from outputs.export_pdf import export_pdf  # noqa: E402
from outputs.narrative import _commas  # noqa: E402
from semantic.catalog import by_id, headline, run_question  # noqa: E402

RULE_LABEL = ui.RULE_LABEL
AS_OF = "31 Aug 2026"
st.set_page_config(page_title="Risk Copilot", layout="wide")


def md_safe(text):
    """Display Markdown: plain English (no codes, underscores or brackets), and dollar amounts shown as money,
    not as maths ('$' starts a formula in Streamlit)."""
    return clean_text(_commas(str(text or ""))).replace("$", "\\$")


def money(x):
    return f"${float(x):,.0f}"


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
        st.info("This view is available on the Snowflake build only.")
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
    return (pill("Synthetic demo data", "amber", dot=True) + pill(f"Data: {backend_label()}", "accent", dot=True)
            + pill(f"As of {AS_OF}"))


QUEUE_COLUMNS = {
    "queue_rank": st.column_config.NumberColumn("#", width="small", format="%d"),
    "customer": st.column_config.TextColumn("Customer", width="medium"),
    "origin": st.column_config.TextColumn("Origin", width="medium"),
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
    if "customer" in out:
        out["customer"] = out["customer"].map(ui.title_name)
    out["reasons"] = out["reasons"].fillna("").map(
        lambda r: [ui.humanize_code(x.strip()) for x in str(r).split(";") if x.strip()])
    return out


_cards = __import__("itertools").count()


def card(parent=None):
    """A white bordered card. The key lets the stylesheet find it on every Streamlit version."""
    return (parent or st).container(border=True, key=f"card_{next(_cards)}")


# ---------------------------------------------------------------- sign in
def sign_in_page():
    ui.set_page("Sign in")
    users = auth.load_users()
    bank = (__import__("yaml").safe_load(auth.USERS_FILE.read_text()) or {}).get("bank", "")
    _, mid, _ = st.columns([1, 1.5, 1])
    with mid:
        with st.container(key="login_card"):
            st.html(f'<div class="rc-login-head">{ui.logo_svg(64)}<div class="n">Risk Copilot</div>'
                    f'<div class="s">Risk, fraud and regulatory intelligence{" for " + esc(bank) if bank else ""}</div></div>')
            with st.form("login", border=False):
                username = st.text_input("Username", placeholder="for example, investigator")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in", width="stretch")
            if submitted:
                wait = auth.locked_for(username)
                profile = None if wait > 0 else auth.verify(username, password, users)
                if wait > 0:
                    st.warning(f"Too many attempts. Try again in {int(wait) + 1} seconds.")
                elif profile:
                    auth.clear_failures(username)
                    st.session_state.update(auth=profile, user=profile["name"],
                                            signed_in_at=__import__("datetime").datetime.now().strftime("%d %b %Y, %H:%M"))
                    st.rerun()
                elif auth.record_failure(username):
                    st.warning(f"Too many attempts. Try again in {auth.LOCK_SECONDS} seconds.")
                else:
                    st.error("That username and password do not match. Please try again.")
            with st.expander("Demo sign-ins"):
                st.html("".join(f'<div style="display:flex;justify-content:space-between;font-size:.88rem;padding:3px 0">'
                                f'<span><b>{esc(u["username"])}</b> · {esc(u["name"])}</span><span>{esc(u["role"])}</span></div>'
                                for u in users.values())
                        + '<div class="rc-login-note">Password for every demo sign-in: Demo@2026</div>')
        st.html('<div class="rc-login-foot">Synthetic demo environment. Every person and bank shown is fictional.<br>'
                'Production sign-in uses the bank\'s single sign-on.</div>')


def sign_out():
    """Forget everything about the session (the sign-in lockout is kept server-side, per username)."""
    for k in list(st.session_state.keys()):
        if k != "page":                       # the navigation widget's own key; reset below instead of deleted
            del st.session_state[k]
    st.session_state["nav_to"] = "Executive overview"     # the next user starts on the first page


if "auth" not in st.session_state:
    sign_in_page()
    st.stop()

ME = st.session_state["auth"]
st.session_state["user"] = ME["name"]
CAN_DRAFT = ME["role"] in auth.CAN_DRAFT
CAN_APPROVE = ME["role"] in auth.CAN_APPROVE

# ---------------------------------------------------------------- navigation and top bar
PAGES = ["Executive overview", "Data integration health", "Alert queue & customer", "Ask & cases"]
NAV_ICON = {"Executive overview": ":material/dashboard:", "Data integration health": ":material/database:",
            "Alert queue & customer": ":material/person_search:", "Ask & cases": ":material/forum:"}
st.session_state.setdefault("page", PAGES[0])
if "nav_to" in st.session_state:
    st.session_state["page"] = st.session_state.pop("nav_to")
with st.sidebar:
    st.html(f'<div class="rc-brand">{ui.logo_svg(34)}<div><div class="n">Risk Copilot</div>'
            f'<div class="s">Financial crimes</div></div></div>')
    st.radio("Screen", PAGES, key="page", label_visibility="collapsed", format_func=lambda p: f"{NAV_ICON[p]}  {p}")
    st.divider()
    st.html('<div class="rc-side-card"><b>Synthetic demo</b>Kestrel Valley Bank and Pellbrook Savings Bank, '
            'one bank after the merger. Every person is fictional.</div>')
ui.set_page(st.session_state["page"])

trail, prof = st.columns([5, 1.4], vertical_alignment="center")
trail.html(ui.greeting_bar(ME["name"].split()[0]))
with prof.popover(f"{ME['initials']}  ·  {ME['name']}", width="stretch"):
    st.html(f'<div class="rc-profile-card"><div class="rc-avatar">{esc(ME["initials"])}</div><div>'
            f'<div class="n">{esc(ME["name"])}</div><div class="t">{esc(ME["title"])}</div></div></div>'
            f'<div class="rc-profile-meta">Role: <b>{esc(ME["role"])}</b><br>Username: {esc(ME["username"])}<br>'
            f'Signed in: {esc(st.session_state.get("signed_in_at", ""))}<br>'
            + ("Can draft and approve cases" if CAN_APPROVE else "Can draft cases" if CAN_DRAFT else "Can view and ask")
            + "</div>")
    if st.button("Sign out", key="sign_out", width="stretch"):
        sign_out()
        st.rerun()


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
KPI_ICON = {"G02": "users", "G03": "bell", "G04": "percent", "G06": "clock", "G09": "scale", "G10": "building"}
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
            f'<h2>{int(h.xcore)} customers moved over $50,000 in cash across both banks in 30 days.</h2>'
            f'<p>{"No legacy alert caught them." if int(h.xcore_no_alert) == int(h.xcore) else str(int(h.xcore_no_alert)) + " had no legacy alert."}</p></div>'
            f'<div class="stats"><div class="stat"><b>{int(h.xcore_no_alert)}</b><span>no alert</span></div>'
            f'<div class="stat"><b>{int(h.ctr_missed)}</b><span>missed CTRs</span></div>'
            f'<div class="stat"><b>{int(h.queue_size)}</b><span>in one queue</span></div></div></div>')

    cols = st.columns(len(KPIS))
    for col, (qid, label, field, fmt) in zip(cols, KPIS):
        _, df = catalog_answer(qid)
        with col.container(border=True, key=f"kpicard_{qid}"):
            st.html(f'<div class="rc-kpi-ic">{ui.icon(KPI_ICON[qid], ui.ACCENT, ui.ACCENT_SOFT, 38)}</div>')
            st.metric(label, fmt.format(float(df.iloc[0][field])))
            st.caption(md_safe(kpi_context(qid, df)))
            st.button("View rows", key=f"kpi_btn_{qid}", type="tertiary", on_click=_pick_kpi, args=(f"{qid} {label}",))
    pick = st.selectbox("Show the rows behind", ["-"] + [f"{k[0]} {k[1]}" for k in KPIS], key="kpi_pick",
                        format_func=lambda v: "Choose a number" if v == "-" else v.split(" ", 1)[1])
    if pick != "-":
        qid = pick.split()[0]
        head, df = catalog_answer(qid)
        with card():
            ui.card_title(clean_text(_commas(head)), "Reviewed question: " + clean_text(by_id()[qid]["question"]))
            rows = q(EVIDENCE[qid])
            ui.table(rows, height=300)
            with st.expander("SQL used"):
                st.code(by_id()[qid]["sql"], language="sql")

    ui.section("Where the risk is", f"one queue across both cores and the risk engine · {int(h.queue_size)} items")
    with card():
        ui.card_title("Top of the work queue", "Select a customer to open their evidence")
        top = q("SELECT queue_rank, display_name AS customer, origin, priority_score, reasons, party_id "
                "FROM GOLD.ALERT_QUEUE WHERE queue_rank <= 10 ORDER BY queue_rank")
        ev = st.dataframe(queue_frame(top).drop(columns=["party_id"]), width="stretch", hide_index=True,
                          column_config=QUEUE_COLUMNS, on_select="rerun", selection_mode="single-row", key="ov_top",
                          height=388)
        i = selected_row(ev)
        if i is not None and st.button(f"Open {ui.title_name(top.iloc[i]['customer'])}", type="primary"):
            go("Alert queue & customer", party_id=top.iloc[i]["party_id"])
    left, right = st.columns(2, gap="medium")
    with card(left):
        ui.card_title("How often each risk rule fires", "Customers flagged by each rule")
        rules = q("SELECT rule_code, COUNT(*) AS customers FROM GOLD.RISK_SIGNAL GROUP BY rule_code ORDER BY customers DESC")
        rules["rule"] = rules["rule_code"].map(ui.humanize_code)
        st.plotly_chart(charts.hbar(rules, "rule", "customers", "Customers"), width="stretch", config=charts.CONFIG)
        mix = q("SELECT origin, COUNT(*) AS items FROM GOLD.ALERT_QUEUE GROUP BY origin ORDER BY items DESC")
        mix["origin"] = mix["origin"].map(ui.ORIGIN_NAME).fillna(mix["origin"])
    with card(right):
        ui.card_title("Where the queue comes from", "Queue items by source")
        st.plotly_chart(charts.hbar(mix, "origin", "items", "Queue items"), width="stretch", config=charts.CONFIG)


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
        bronze = '<div class="name">Bronze · load</div><div class="big">–</div><div class="sub">checked on the Snowflake build</div>'
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

    ui.section("Load reconciliation", "Bronze row counts and amounts against each core's extract control totals")
    if rec is not None:
        recd = rec.copy()
        recd["status"] = recd["status"].map(lambda s: f"✓ {ui.humanize_code(s)}" if s == "MATCH" else f"✗ {ui.humanize_code(s)}")
        recd["core"] = recd["core"].map(ui.CORE_NAME).fillna(recd["core"])
        ui.table(recd, column_config={
            "amount_expected": st.column_config.NumberColumn("Amount expected", format="dollar"),
            "amount_loaded": st.column_config.NumberColumn("Amount loaded", format="dollar")})
    else:
        st.info("The load check runs on the Snowflake build; this offline copy has no extract control totals.")

    ui.section("Entity resolution across the cores", "Same customer, different IDs: matched by evidence, never by guess")
    c1, c2, c3, c4 = st.columns(4)
    for col, label, val in ((c1, "Records linked automatically", r.auto_links), (c2, "Pairs waiting for review", r.review_queue),
                            (c3, "Resolved customers", r.resolved_customers), (c4, "Customers in both cores", r.in_both_cores)):
        with col.container(border=True, key=f"kpi_er_{label[:12].replace(' ', '_')}"):
            st.metric(label, f"{int(val):,}")
    st.caption("Measured against ground truth: 0 false merges; 98.70% of true duplicates linked automatically, "
               "100% after the review queue.")
    with st.expander("Match review queue: uncertain pairs, never merged automatically"):
        ui.table(q("SELECT a_name, b_name, a_id, b_id, review_reason, reason_codes FROM SILVER.MATCH_REVIEW_QUEUE "
                   "ORDER BY review_reason, a_name"))

    ui.section("Data-quality exceptions", "Every record that breaks a rule, with its source file and row")
    dq = q("SELECT rule_id, COUNT(*) AS records FROM SILVER.DQ_EXCEPTIONS GROUP BY rule_id ORDER BY records DESC")
    left, right = st.columns([2, 3], gap="medium")
    with card(left):
        dqc = dq.copy()
        dqc["rule"] = dqc["rule_id"].map(ui.humanize_code)
        ui.card_title("Records flagged by each check")
        st.plotly_chart(charts.hbar(dqc, "rule", "records", "Records"), width="stretch", config=charts.CONFIG)
    with right:
        rule = st.selectbox("Show the records for", dq["rule_id"].tolist(), key="dq_rule", format_func=ui.humanize_code)
        ui.table(q(f"SELECT source_system, entity, record_key, field, observed_value, source_file, source_row "
                   f"FROM SILVER.DQ_EXCEPTIONS WHERE rule_id = '{rule}' ORDER BY source_system, source_row"), height=260)


# ---------------------------------------------------------------- 3. queue & customer
def queue_and_customer():
    ui.page_header("Alert queue & customer", "One ranked queue across both cores; every score shows its reasons and evidence",
                   meta())
    with card():
        f1, f2, f3 = st.columns([3, 2, 3])
        origins = f1.multiselect("Origin", ["RISK_ENGINE", "LEGACY_CORE_A", "LEGACY_CORE_B"],
                                 default=["RISK_ENGINE", "LEGACY_CORE_A", "LEGACY_CORE_B"],
                                 format_func=lambda o: ui.ORIGIN_NAME.get(o, o))
        min_score = f2.slider("Minimum priority", 0, 100, 0, step=5)
        name = f3.text_input("Find a customer by name", placeholder="for example, Deborah Sanford")
    if name:
        found = find_customers(name, executor())
        if found:
            st.session_state["party_id"] = found[0].party_id
        else:
            st.warning(f"No customer named {md_safe(name)}.")
    if origins:
        in_list = ", ".join(f"'{o}'" for o in origins)
        queue = q(f"SELECT queue_rank, display_name AS customer, origin, priority_score, engine_score, legacy_score, "
                  f"reasons, party_id FROM GOLD.ALERT_QUEUE WHERE origin IN ({in_list}) AND priority_score >= {int(min_score)} "
                  f"ORDER BY queue_rank LIMIT 200")
        st.caption(f"Showing {len(queue)} items, highest priority first. Select one to open the customer.")
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

    ui.section("Customer", "One real customer, resolved across both cores")
    with card():
        body, ring = st.columns([7, 1], vertical_alignment="center")
        ids = []
        if prof.core_a_key:
            ids.append(pill(f"Core A {prof.core_a_key}", "core-a"))
        if prof.core_b_key:
            ids.append(pill(f"Core B {str(prof.core_b_key)[:13]}…", "core-b"))
        kind = "Business" if prof.party_kind == "ORG" else "Person"
        cash_total = float(cash30["cash_usd"].astype(float).sum()) if len(cash30) else 0.0
        name = ui.title_name(prof.display_name)
        initials = "".join(w[0] for w in name.split()[:2]).upper()
        body.html(ui.profile_header(
            name, initials, "".join(ids) + pill(kind) + pill("In both cores" if int(prof.cores) == 2 else "In one core", "accent"),
            f'<div class="rc-kv"><div><span>Queue rank</span><b>{esc(rank)}</b></div>'
            f'<div><span>Legacy alerts</span><b>{len(v["alerts"])}</b></div>'
            f'<div><span>Cash in, 30 days</span><b>{money(cash_total)}</b></div>'
            f'<div><span>City</span><b>{esc(str(prof.city or "").title())}, {esc(prof.state or "")}</b></div></div>'))
        ring.html(ui.score_ring(score, 104))
        links = [ui.humanize_code(x) for x in str(prof.link_reasons or "").split(";") if x]
        st.html('<div class="rc-label">Linked across cores by</div>'
                + (ui.chips(links) if links else ui.chips(["Single record in one core"])))

    if len(v["signals"]):
        sig = numeric(v["signals"])
        ui.section("Why this customer is ranked here", f"Score {score:.0f} is the sum of the rule weights, capped at 100")
        st.html(ui.rule_cards([{"rule_code": s.rule_code, "weight": s.weight, "evidence": _commas(s.evidence_text)}
                               for s in sig.itertuples()]))

    cash = q(f"SELECT posted_at, source_system, account_id, amount_usd, branch, ctr_filed, source_file, source_row "
             f"FROM GOLD.TRANSACTION WHERE party_id = '{pid}' AND txn_type = 'CASH_DEPOSIT' "
             f"AND posted_date > (SELECT MAX(posted_date) FROM GOLD.TRANSACTION) - 30 ORDER BY posted_at")
    if len(cash) and cash["source_system"].nunique() >= 1:
        d = cash.assign(amount_usd=cash["amount_usd"].astype(float))
        per = d.groupby("source_system")["amount_usd"].sum()
        a_usd, b_usd = float(per.get("core_a", 0)), float(per.get("core_b", 0))
        title = (f"Each bank saw under {money(thresholds().get('thresholds.legacy_per_core_cash_30d_usd', 30000))}. "
                 f"Together: {money(a_usd + b_usd)}." if a_usd and b_usd else f"Cash deposits: {money(a_usd + b_usd)} in 30 days")
        ui.section("Cash across both cores, last 30 days", "What each legacy system saw against what the bank really holds")
        with card():
            st.html(f'<div style="font-size:1.15rem;font-weight:650;color:{ui.INK}">{esc(title)}</div>'
                    f'<div style="color:{ui.MUTED};font-size:.88rem;margin:2px 0 4px 0">Core A {money(a_usd)} + Core B '
                    f'{money(b_usd)} in {len(d)} deposits, the largest {money(d.amount_usd.max())}.</div>')
            c1, c2 = st.columns(2, gap="large")
            th = thresholds()
            c1.plotly_chart(charts.daily_cash(cash, th.get("thresholds.ctr_cash_threshold_usd", 10000.0)),
                            width="stretch", config=charts.CONFIG)
            c2.plotly_chart(charts.running_cash(cash, th.get("thresholds.legacy_per_core_cash_30d_usd", 30000.0),
                                                th.get("thresholds.cross_core_cash_total_usd", 50000.0)),
                            width="stretch", config=charts.CONFIG)

    t1, t2, t3, t4 = st.tabs(["Accounts and cash", "KYC", "Alerts and notes", "Loans"])
    with t1:
        accts = numeric(v["accounts"])
        st.html(ui.account_cards(accts))
        if len(cash):
            ui.card_title(f"Cash deposits, last 30 days", f"{len(cash)} deposits, newest first")
            st.html(ui.statement(cash))
        with st.expander("Full records with source file and row"):
            ui.table(accts)
            ui.table(cash)
    with t2:
        ui.table(numeric(v["kyc"]))
    with t3:
        ui.table(v["alerts"])
        if v.get("notes") is not None and len(v["notes"]):
            ui.table(v["notes"][["citation", "snippet"]])
        else:
            st.caption("No investigator notes for this customer.")
    with t4:
        ui.table(numeric(v["loans"]))
    if st.button("Draft a case narrative for this customer", type="primary", disabled=not CAN_DRAFT,
                 help=None if CAN_DRAFT else "Investigators and approvers can draft cases"):
        try:
            oid, _ = C.draft_narrative(pid, st.session_state["user"], executor(), role=ME["role"])
        except C.ApprovalError as e:
            st.error(clean_text(str(e)).capitalize())
        else:
            go("Ask & cases", case_id=oid, flash=f"Draft saved. Someone other than {st.session_state['user']} must approve it.")
    if not CAN_DRAFT:
        st.caption("Your role can view and ask. Investigators and approvers can draft cases.")


# ---------------------------------------------------------------- 4. ask & cases
EXAMPLES = ["Which customers moved more than $50k in cash across both cores in 30 days, and what do their KYC files say?",
            "On which days did a customer's cash deposits across both cores exceed $10,000 with no CTR filed?",
            "Which alerts should my team work first today, and why?",
            "What does our BSA policy say about aggregating cash transactions across the two cores?",
            "Draft a case narrative for the highest-risk customer in the queue."]
EXAMPLE_LABELS = ["Cross-core cash", "Missed CTRs", "Work first", "Policy", "Draft top case"]
ROUTE_KIND = {"CATALOG": "accent", "SEARCH": "accent", "CUSTOMER": "accent", "NARRATIVE": "accent", "CLARIFY": "amber"}


def rule_words(rule):
    """data_words+catalog_match_confident -> data words, confident catalogue match."""
    parts = [p.replace("_", " ") for p in str(rule or "").split("+") if p]
    return ", ".join(parts).replace("catalog", "catalogue")


def ask_tab_body():
    with card():
        ui.card_title("Ask in plain English", "Readable rules route each question to a reviewed SQL question, document "
                      "search, the customer view or a case narrative. If no rule is sure, it says so.")
        ex_cols = st.container(key="examples").columns(len(EXAMPLES))
        for col, ex, label in zip(ex_cols, EXAMPLES, EXAMPLE_LABELS):
            if col.button(label, help=ex, width="stretch"):
                st.session_state["question"] = ex
        text = st.text_input("Question", key="question", placeholder="for example, How many alerts did we get last month?")
    if not text:
        return
    a = answer(text, executor())
    if st.session_state.get("last_logged") != (ME["username"], text):     # one audit row per question, not per rerun
        log_question(a, executor(), app_user=st.session_state["user"])
        st.session_state["last_logged"] = (ME["username"], text)
    with card():
        answered_as = clean_text(re.sub(r"\s*\([^)]*\.py\)", "", str(a.answered_as or "")))[:90]
        st.html(f'<div class="rc-meta" style="justify-content:flex-start;margin-bottom:10px">'
                f'{pill("Answered by: " + ui.ROUTE_NAME.get(a.route, ui.humanize_code(a.route)), ROUTE_KIND.get(a.route, ""), dot=True)}'
                f'{pill("Rule: " + rule_words(a.rule))}'
                + (pill("Answered as " + answered_as) if answered_as else "") + "</div>"
                f'<div class="rc-answer">{esc(clean_text(_commas(a.headline)))}</div>')
        if a.suggestions:
            cat = by_id()
            ui.card_title("Did you mean one of these reviewed questions?")
            for qid, _ in a.suggestions:
                st.markdown(f"- {md_safe(cat[qid]['question'])}")
        if a.text:
            text_shown = re.sub(r"\s*To save it for approval:.*?(?=\n|$)", "", str(a.text))
            st.markdown(md_safe(text_shown))
            if a.route == "NARRATIVE" and CAN_DRAFT and getattr(a, "party_id", None):
                if st.button("Save this draft for approval", type="primary", key="save_preview"):
                    try:
                        oid, _ = C.draft_narrative(a.party_id, st.session_state["user"], executor(), role=ME["role"])
                    except C.ApprovalError as e:
                        st.error(clean_text(str(e)).capitalize())
                        return
                    go("Ask & cases", case_id=oid, flash=f"Draft saved. Someone other than {st.session_state['user']} "
                                                         f"must approve it.")
        else:
            for title, df in a.tables:
                ui.card_title(clean_text(title))
                ui.table(numeric(df))
        if a.citations:
            with st.expander(f"Sources: {len(a.citations)}"):
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
                        format_func=lambda i: (lambda r: f"{ui.title_name(r.subject)} · {ui.humanize_code(r.status)} · "
                                                         f"by {r.author} · {clean_text(str(r.created_at)[:16])}")(
                            outs[outs.output_id == i].iloc[0]))
    md, status = C.final_text(pick, executor())
    out = C.get_output(pick, executor())
    row = outs[outs.output_id == pick].iloc[0]
    with card():
        head = st.empty()                 # filled after the buttons, so a Verify click shows at once
        b1, b2, b3, b4, b5 = st.columns([2, 2, 2, 2, 3], vertical_alignment="bottom")
        comment = b5.text_input("Comment", key="case_comment", placeholder="Optional, saved with the decision")
        for col, label, decision in ((b1, "Approve", "APPROVED"), (b2, "Reject", "REJECTED")):
            if col.button(label, disabled=status != "DRAFT" or not CAN_APPROVE, width="stretch",
                          type="primary" if label == "Approve" else "secondary",
                          help=None if CAN_APPROVE else "Only approvers can approve or reject"):
                try:
                    C.decide(pick, st.session_state["user"], decision, executor(), comment, role=ME["role"])
                    go("Ask & cases", case_id=pick, flash=f"{decision.title()} by {st.session_state['user']}.")
                except C.ApprovalError as e:
                    msg = str(e)
                    if "cannot approve" in msg:
                        msg = f"{st.session_state['user']} wrote this case and cannot approve it. A second person must."
                    st.error(clean_text(msg))
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
        b4.download_button("Download PDF", buf.getvalue(), file_name=f"{out['subject'].replace(' ', '-').lower()}-{pick[:8]}.pdf",
                           mime="application/pdf", width="stretch")
        verified = st.session_state.get(f"verified_{pick}")
        steps = [("Drafted", "done"),
                 ("Approved by a second person", "done" if status == "APPROVED" else "bad" if status == "REJECTED" else "now"),
                 ("Verified against the audit record", "done" if verified else "todo")]
        head.html(ui.stepper(steps)
                + f'<div class="rc-kv"><div><span>Status</span><b>{ui.status_pill(status)}</b></div>'
                f'<div><span>Author</span><b>{esc(out["author"])}</b></div>'
                f'<div><span>Approver</span><b>{esc(row.get("approver") if pd.notna(row.get("approver")) else "–")}</b></div>'
                f'<div><span>Case reference</span><b class="rc-mono" style="font-size:.95rem">{esc(pick[:8])}</b></div>'
                f'<div><span>Text fingerprint, SHA-256</span><b class="rc-mono" style="font-size:.95rem">'
                f'{esc(out["content_sha256"][:16])}…</b></div></div>')
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
            log = log.copy()
            log["route"] = log["route"].map(lambda r: ui.ROUTE_NAME.get(r, ui.humanize_code(r)))
            log["rule"] = log["rule"].map(rule_words)
            ui.table(log, column_config={"question": st.column_config.TextColumn("Question", width="large"),
                                         "headline": st.column_config.TextColumn("Answer", width="large")})
        st.caption("Every question is logged with its route, rule and sources; every case keeps its evidence snapshot.")


{"Executive overview": overview, "Data integration health": data_health,
 "Alert queue & customer": queue_and_customer, "Ask & cases": ask_and_cases}[st.session_state["page"]]()
