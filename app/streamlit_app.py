"""Sahasranshu Risk Copilot - Streamlit app (F8). No AI anywhere.

  streamlit run app/streamlit_app.py                                   # against Snowflake (connection "default")
  RISK_COPILOT_BACKEND=duckdb:<file> streamlit run app/streamlit_app.py  # offline, on a local DuckDB build

Four screens, as in the build plan:
  1. Executive overview        headline metrics, where the risk is, top of the queue
  2. Data integration health   load reconciliation, entity resolution, data-quality exceptions
  3. Alert queue & customer    ranked queue; one customer across both cores, with evidence rows
  4. Ask & cases               any question (routed by rules), case narratives with four-eyes approval
Every summary number opens to the rows behind it (source file and row) in three clicks or fewer.
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

from agent.answer import answer, customer_view, log_question  # noqa: E402
from agent.router import find_customers  # noqa: E402
from outputs import case_store as C  # noqa: E402
from outputs.export_pdf import export_pdf  # noqa: E402
from outputs.narrative import _commas  # noqa: E402
from semantic.catalog import by_id, headline, run_question  # noqa: E402

BLUE = "#2a78d6"   # single-series colour (reference palette slot 1)
RULE_LABEL = {"XCORE_CASH_30D": "Cash split across cores", "CTR_AGGREGATION_MISSED": "Missed CTR aggregation",
              "NEAR_THRESHOLD_CASH": "Near-threshold cash", "RAPID_IN_OUT": "Rapid in and out",
              "DORMANT_REACTIVATION": "Dormant reactivation", "KYC_MISMATCH": "Cash above KYC profile",
              "KYC_INCONSISTENT_ACROSS_CORES": "KYC differs across cores",
              "KYC_CONSISTENT_CASH": "Cash in line with KYC (mitigating)"}


def md_safe(text):
    """Markdown with dollar amounts shown as money, not as maths ('$' starts a formula in Streamlit)."""
    return _commas(str(text or "")).replace("$", "\\$")


def hbar(df, label, value, title):
    """Single-series horizontal bars, sorted by value, with hover tooltips."""
    return (alt.Chart(df).mark_bar(color=BLUE, cornerRadiusEnd=4, height=18)
            .encode(y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
                    x=alt.X(f"{value}:Q", title=title, axis=alt.Axis(grid=True, gridOpacity=0.3)),
                    tooltip=[alt.Tooltip(f"{label}:N", title="Rule"), alt.Tooltip(f"{value}:Q", title=title)])
            .properties(height=alt.Step(26)))
st.set_page_config(page_title="Risk Copilot", page_icon="🛡️", layout="wide")


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


def go(page, **state):
    st.session_state.update(state)
    st.session_state["nav_to"] = page          # applied before the navigation widget is drawn
    st.rerun()


def selected_row(event):
    rows = getattr(getattr(event, "selection", None), "rows", None) or []
    return rows[0] if rows else None


# ---------------------------------------------------------------- sidebar
PAGES = ["Executive overview", "Data integration health", "Alert queue & customer", "Ask & cases"]
st.session_state.setdefault("page", PAGES[0])
if "nav_to" in st.session_state:
    st.session_state["page"] = st.session_state.pop("nav_to")
with st.sidebar:
    st.title("🛡️ Risk Copilot")
    st.caption("Kestrel Valley Bank + Pellbrook Savings Bank. **Synthetic demo data.**")
    st.radio("Screen", PAGES, key="page")
    st.divider()
    st.text_input("You are", value=os.getenv("RISK_COPILOT_USER", "jehal"), key="user",
                  help="Recorded on every question, draft and approval. An author can never approve their own case.")
    st.caption(f"Data: {executor().backend.replace(str(Path.home()), '~')}")
    st.caption("No AI: answers come from reviewed SQL, transparent rules and reviewed templates.")


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


def overview():
    st.header("Executive overview")
    st.caption("As of 31 August 2026. Each figure is a reviewed question from the catalogue; open it to see the rows.")
    kpis = [("G02", "Unique customers", "unique_customers", "{:,.0f}"),
            ("G03", "Alerts in August", "alerts", "{:,.0f}"),
            ("G04", "False positives, Q2", "false_positive_rate_pct", "{:.1f}%"),
            ("G06", "Open > 30 days", "open_over_30_days", "{:,.0f}"),
            ("G09", "Loan-to-deposit", "loan_to_deposit_pct", "{:.1f}%"),
            ("G10", "CRE / capital", "cre_to_capital_pct", "{:.1f}%")]
    cols = st.columns(len(kpis))
    for col, (qid, label, field, fmt) in zip(cols, kpis):
        _, df = catalog_answer(qid)
        col.metric(label, fmt.format(float(df.iloc[0][field])))
    pick = st.selectbox("Show the rows behind", ["-"] + [f"{k[0]} {k[1]}" for k in kpis], key="kpi_pick")
    if pick != "-":
        qid = pick.split()[0]
        head, df = catalog_answer(qid)
        st.markdown(f"**{md_safe(head)}**  \n_{md_safe(by_id()[qid]['question'])}_")
        rows = q(EVIDENCE[qid])
        st.dataframe(rows, width="stretch", hide_index=True)
        with st.expander("SQL used"):
            st.code(by_id()[qid]["sql"], language="sql")

    st.subheader("Where the risk is")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Top of the work queue**: select a customer, then open their evidence.")
        top = q("SELECT queue_rank, display_name AS customer, origin, priority_score, reasons, party_id "
                "FROM GOLD.ALERT_QUEUE WHERE queue_rank <= 10 ORDER BY queue_rank")
        ev = st.dataframe(top.drop(columns=["party_id"]), width="stretch", hide_index=True,
                          on_select="rerun", selection_mode="single-row", key="ov_top")
        i = selected_row(ev)
        if i is not None and st.button(f"Open {top.iloc[i]['customer'].title()}", type="primary"):
            go("Alert queue & customer", party_id=top.iloc[i]["party_id"])
    with right:
        st.markdown("**Customers each risk rule fired for**")
        rules = q("SELECT rule_code, COUNT(*) AS customers FROM GOLD.RISK_SIGNAL GROUP BY rule_code ORDER BY customers DESC")
        rules.columns = [c.lower() for c in rules.columns]
        rules["rule"] = rules["rule_code"].map(RULE_LABEL).fillna(rules["rule_code"])
        st.altair_chart(hbar(rules, "rule", "customers", "customers"), width="stretch")
        mix = q("SELECT origin, COUNT(*) AS items FROM GOLD.ALERT_QUEUE GROUP BY origin ORDER BY items DESC")
        st.caption("Queue by origin: " + ", ".join(f"{r.origin} {int(r.items)}" for r in mix.itertuples()))


# ---------------------------------------------------------------- 2. data health
def data_health():
    st.header("Data integration health")
    st.subheader("1. Load reconciliation (Bronze vs each core's control totals)")
    rec = q_safe("SELECT * FROM BRONZE.V_LOAD_RECONCILIATION")
    if rec is not None:
        rec.columns = [c.lower() for c in rec.columns]
        ok = (rec["status"] == "MATCH").sum()
        st.metric("Files reconciled", f"{ok} of {len(rec)}", delta="all match" if ok == len(rec) else "BREAK",
                  delta_color="normal" if ok == len(rec) else "inverse")
        st.dataframe(rec, width="stretch", hide_index=True)

    st.subheader("2. Entity resolution across the cores")
    m = q("""SELECT (SELECT COUNT(*) FROM SILVER.AUTO_LINKS) AS auto_links,
                    (SELECT COUNT(*) FROM SILVER.MATCH_REVIEW_QUEUE) AS review_queue,
                    (SELECT COUNT(*) FROM GOLD.PARTY) AS resolved_customers,
                    (SELECT COUNT(*) FROM GOLD.PARTY WHERE cores = 2) AS in_both_cores""")
    m.columns = [c.lower() for c in m.columns]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Records linked automatically", f"{int(m.auto_links[0]):,}")
    c2.metric("Pairs waiting for review", f"{int(m.review_queue[0]):,}")
    c3.metric("Resolved customers", f"{int(m.resolved_customers[0]):,}")
    c4.metric("Customers in both cores", f"{int(m.in_both_cores[0]):,}")
    st.caption("Measured against ground truth: 0 false merges; 98.70% of true duplicates linked automatically, "
               "100% after the review queue.")
    with st.expander("Match review queue: uncertain pairs, never merged automatically"):
        st.dataframe(q("SELECT a_name, b_name, a_id, b_id, review_reason, reason_codes FROM SILVER.MATCH_REVIEW_QUEUE "
                       "ORDER BY review_reason, a_name"), width="stretch", hide_index=True)

    st.subheader("3. Data-quality exceptions")
    dq = q("SELECT rule_id, COUNT(*) AS records FROM SILVER.DQ_EXCEPTIONS GROUP BY rule_id ORDER BY records DESC")
    left, right = st.columns([2, 3])
    with left:
        dq.columns = [c.lower() for c in dq.columns]
        st.altair_chart(hbar(dq, "rule_id", "records", "records"), width="stretch")
    with right:
        rule = st.selectbox("Show the records for", dq["rule_id"].tolist(), key="dq_rule")
        st.dataframe(q(f"SELECT source_system, entity, record_key, field, observed_value, source_file, source_row "
                       f"FROM SILVER.DQ_EXCEPTIONS WHERE rule_id = '{rule}' ORDER BY source_system, source_row"),
                     width="stretch", hide_index=True, height=260)


# ---------------------------------------------------------------- 3. queue & customer
def queue_and_customer():
    st.header("Alert queue & customer view")
    f1, f2, f3 = st.columns([2, 2, 3])
    origins = f1.multiselect("Origin", ["RISK_ENGINE", "LEGACY_CORE_A", "LEGACY_CORE_B"],
                             default=["RISK_ENGINE", "LEGACY_CORE_A", "LEGACY_CORE_B"])
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
        ev = st.dataframe(queue.drop(columns=["party_id"]), width="stretch", hide_index=True, height=280,
                          on_select="rerun", selection_mode="single-row", key="queue_tbl")
        i = selected_row(ev)
        if i is not None and queue.iloc[i]["party_id"]:
            st.session_state["party_id"] = queue.iloc[i]["party_id"]

    pid = st.session_state.get("party_id")
    if not pid:
        st.info("Select a queue item or find a customer by name.")
        return
    st.divider()
    v = customer_view(pid, executor())
    prof = v["profile"].iloc[0]
    st.subheader(f"{prof.display_name.title()}")
    risk = numeric(v["risk"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cores", int(prof.cores))
    c2.metric("Risk score", f"{float(risk.risk_score[0]):.0f}" if len(risk) else "0")
    c3.metric("Queue rank", f"{int(risk.queue_rank[0])} of {int(risk.queue_size[0])}"
              if len(risk) and pd.notna(risk.queue_rank[0]) else "not queued")
    c4.metric("Legacy alerts", len(v["alerts"]))
    st.caption(f"Linked by: {prof.link_reasons or 'single record'}")
    if len(v["signals"]):
        st.markdown("**Why this customer is ranked here**")
        for s in numeric(v["signals"]).itertuples():
            st.markdown(f"- **{RULE_LABEL.get(s.rule_code, s.rule_code)}** ({s.weight:+.0f}): {md_safe(s.evidence_text)}")
    t1, t2, t3, t4 = st.tabs(["Accounts and cash", "KYC", "Alerts and notes", "Loans"])
    with t1:
        st.dataframe(numeric(v["accounts"]), width="stretch", hide_index=True)
        cash = q(f"SELECT posted_at, source_system, account_id, amount_usd, branch, ctr_filed, source_file, source_row "
                 f"FROM GOLD.TRANSACTION WHERE party_id = '{pid}' AND txn_type = 'CASH_DEPOSIT' "
                 f"AND posted_date > (SELECT MAX(posted_date) FROM GOLD.TRANSACTION) - 30 ORDER BY posted_at")
        st.markdown(f"**Cash deposits, last 30 days** ({len(cash)})")
        st.dataframe(cash, width="stretch", hide_index=True)
    with t2:
        st.dataframe(numeric(v["kyc"]), width="stretch", hide_index=True)
    with t3:
        st.dataframe(v["alerts"], width="stretch", hide_index=True)
        if v.get("notes") is not None and len(v["notes"]):
            st.dataframe(v["notes"][["citation", "snippet"]], width="stretch", hide_index=True)
        else:
            st.caption("No investigator notes for this customer.")
    with t4:
        st.dataframe(numeric(v["loans"]), width="stretch", hide_index=True)
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


def ask_and_cases():
    st.header("Ask & cases")
    banner = st.container()          # always present, so the tabs below keep their place (and their selected tab)
    if st.session_state.get("flash"):
        banner.success(st.session_state.pop("flash"))
    ask_tab, case_tab, log_tab = st.tabs(["Ask the copilot", "Case narratives", "Audit log"])
    with ask_tab:
        st.caption("Questions are routed by readable rules to a reviewed question, document search or the customer view.")
        ex_cols = st.columns(len(EXAMPLES))
        for i, (col, ex) in enumerate(zip(ex_cols, EXAMPLES)):
            if col.button(f"D0{i + 1}", help=ex, width="stretch"):
                st.session_state["question"] = ex
        text = st.text_input("Question", key="question", placeholder="e.g. How many alerts did we get last month?")
        if text:
            a = answer(text, executor())
            log_question(a, executor(), app_user=st.session_state["user"])
            st.markdown(f"`{a.route}` chosen by rule `{a.rule}`" + (f" · answered as **{a.answered_as}**" if a.answered_as else ""))
            st.info(md_safe(a.headline))
            if a.suggestions:
                cat = by_id()
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
    with case_tab:
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
        badge = {"APPROVED": "🟢 Approved", "REJECTED": "🔴 Rejected"}.get(status, "🟡 Draft, awaiting approval")
        st.markdown(f"**{badge}** · author **{out['author']}** · text fingerprint `{out['content_sha256'][:16]}…`")
        b1, b2, b3, b4 = st.columns([2, 2, 2, 3])
        comment = b4.text_input("Comment", key="case_comment")
        for col, label, decision in ((b1, "Approve", "APPROVED"), (b2, "Reject", "REJECTED")):
            if col.button(label, disabled=status != "DRAFT", width="stretch"):
                try:
                    C.decide(pick, st.session_state["user"], decision, executor(), comment)
                    go("Ask & cases", case_id=pick, flash=f"{decision.title()} by {st.session_state['user']}.")
                except C.ApprovalError as e:
                    st.error(str(e))
        if b3.button("Verify", width="stretch"):
            ok, info = C.reproduce(pick, executor())
            (st.success if ok else st.error)(("Reproduced byte for byte from the audit record. " if ok else "Mismatch. ")
                                              + str({k: v for k, v in info.items() if k.startswith(('re_', 'stored_t', 'stored_e'))}))
        buf = io.BytesIO()
        export_pdf(md, buf, status=status, footer=f"Output {pick} | status {status} | text SHA-256 "
                                                   f"{out['content_sha256'][:16]}... | synthetic data")
        st.download_button("Download PDF", buf.getvalue(), file_name=f"{out['subject'].replace(' ', '_').lower()}_{pick[:8]}.pdf",
                           mime="application/pdf")
        st.divider()
        st.markdown(md_safe(md))
    with log_tab:
        log = q_safe("SELECT logged_at, app_user, route, rule, question, headline FROM AUDIT.QUESTION_LOG "
                     "ORDER BY logged_at DESC LIMIT 50", cached=False)
        if log is not None:
            st.dataframe(log, width="stretch", hide_index=True)
        st.caption("Every question is logged with its route, rule and sources; every case keeps its evidence snapshot.")


{"Executive overview": overview, "Data integration health": data_health,
 "Alert queue & customer": queue_and_customer, "Ask & cases": ask_and_cases}[st.session_state["page"]]()
