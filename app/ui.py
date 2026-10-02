"""Presentation for the Risk Copilot app: one stylesheet, one font (Inter), a colour per page, standard charts and
tables, and a display layer that turns database names and codes into plain English.

Pure presentation: nothing here queries data or changes a stored number or record. Colours carry meaning:
  each page has its own accent; Core A and Core B each keep one fixed colour; red / amber / green mean status only.
"""
import html
import math
import re
from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st

FONT = "Inter"
NAVY = "#0f1b33"
INK = "#14213d"
MUTED = "#5b6b85"
LINE = "#dde4ef"
PAGE_BG = "#f4f6fa"
CORE_A = "#3b5bdb"      # Kestrel Valley (Core A)
CORE_B = "#0d9488"      # Pellbrook (Core B)
BOTH = "#14213d"        # combined across cores
RED, AMBER, GREEN, GREY = "#b91c1c", "#b45309", "#15803d", "#868e96"

# Each page keeps the same layout and components; only its accent changes.
PAGE_THEME = {
    "Sign in": ("#1e3a8a", "#e8eefc"),
    "Executive overview": ("#1d4ed8", "#e8efff"),
    "Data integration health": ("#0f766e", "#e2f3f1"),
    "Alert queue & customer": ("#c2410c", "#fff0e6"),
    "Ask & cases": ("#6d28d9", "#f1eafe"),
}
ACCENT = PAGE_THEME["Executive overview"][0]       # default, replaced per page by set_page()

CORE_NAME = {"core_a": "Core A · Kestrel Valley", "core_b": "Core B · Pellbrook", "core_c": "Core C"}
CORE_SHORT = {"core_a": "Core A", "core_b": "Core B", "core_c": "Core C"}
ORIGIN_NAME = {"RISK_ENGINE": "Risk engine", "LEGACY_CORE_A": "Legacy · Core A", "LEGACY_CORE_B": "Legacy · Core B"}
RULE_LABEL = {"XCORE_CASH_30D": "Cash split across cores", "CTR_AGGREGATION_MISSED": "Missed CTR aggregation",
              "NEAR_THRESHOLD_CASH": "Near-threshold cash", "RAPID_IN_OUT": "Rapid in and out",
              "DORMANT_REACTIVATION": "Dormant reactivation", "KYC_MISMATCH": "Cash above KYC profile",
              "KYC_INCONSISTENT_ACROSS_CORES": "KYC differs across cores",
              "KYC_CONSISTENT_CASH": "Cash in line with KYC, mitigating"}
LINK_LABEL = {"TAX_TOKEN_EQUAL": "Tax ID token equal", "DOB_EQUAL": "Birth date equal", "SURNAME_MATCH": "Surname match",
              "GIVEN_NAME_EQUAL": "Given name equal", "GIVEN_NAME_NICKNAME": "Nickname of given name",
              "GIVEN_NAME_SIMILAR": "Given name similar", "ADDRESS_EQUAL": "Address equal", "PHONE_EQUAL": "Phone equal",
              "TAX_TOKEN_MISSING": "No tax token to compare"}
ROUTE_NAME = {"CATALOG": "Reviewed question", "SEARCH": "Document search", "CUSTOMER": "Customer view",
              "NARRATIVE": "Case narrative", "CLARIFY": "Needs a clearer question"}

# Words that stay in capitals: standard banking and technical abbreviations.
ACRONYMS = {"CTR", "KYC", "BSA", "AML", "SAR", "CRE", "SLA", "USD", "ID", "PDF", "SQL", "DOB", "OFAC", "EDD", "CDD",
            "LLC", "INC", "LP", "LLP", "ACH", "ATM", "Q1", "Q2", "Q3", "Q4", "SHA", "UTC", "US", "FinCEN"}

COLUMN_LABEL = {
    "queue_rank": "#", "customer": "Customer", "display_name": "Customer", "origin": "Origin",
    "priority_score": "Priority", "engine_score": "Engine score", "legacy_score": "Legacy score", "reasons": "Why",
    "alert_id": "Alert", "source_system": "Core", "scenario": "Scenario", "alert_date": "Alert date", "branch": "Branch",
    "status": "Status", "source_file": "Source file", "source_row": "Row", "closed_on": "Closed on",
    "disposition": "Disposition", "owner": "Owner", "loan_id": "Loan", "loan_type": "Loan type",
    "principal_usd": "Principal", "cre_category": "CRE category", "party_id": "Customer key", "cores": "Cores",
    "core_a_key": "Core A key", "core_b_key": "Core B key", "link_reasons": "Linked by", "a_name": "Name in Core A",
    "b_name": "Name in Core B", "a_id": "Core A key", "b_id": "Core B key", "review_reason": "Why it needs review",
    "reason_codes": "Evidence", "entity": "Record type", "record_key": "Record", "field": "Field",
    "observed_value": "Value found", "rule_id": "Check", "records": "Records", "product_type": "Product",
    "balance_usd": "Balance", "account_id": "Account", "posted_at": "Posted", "amount_usd": "Amount",
    "ctr_filed": "CTR filed", "occupation": "Occupation", "expected_monthly_cash_usd": "Expected monthly cash",
    "risk_rating": "Risk rating", "review_date": "Reviewed", "days_past_due": "Days past due", "deposits": "Deposits",
    "cash_usd": "Cash", "core_a_usd": "Core A cash", "core_b_usd": "Core B cash", "total_cash_usd": "Total cash",
    "kyc_says": "What KYC says", "business_day": "Business day", "total_usd": "Total", "logged_at": "Logged",
    "app_user": "User", "route": "Answered by", "rule": "Rule", "question": "Question", "headline": "Answer",
    "citation": "Source", "snippet": "Note", "core": "Core", "file": "File", "rows_expected": "Rows expected",
    "rows_loaded": "Rows loaded", "amount_expected": "Amount expected", "amount_loaded": "Amount loaded",
    "party_kind": "Type", "birth_date": "Birth date", "city": "City", "state": "State", "txn_type": "Transaction",
}
VALUE_LABEL = {"core_a": "Core A", "core_b": "Core B", "core_c": "Core C", "ORG": "Business",
               "PERSON": "Person", "MATCH": "Match", "BREAK": "Break", **ORIGIN_NAME, **RULE_LABEL, **LINK_LABEL}
NAME_COLUMNS = {"customer", "display_name", "a_name", "b_name", "subject"}


# ---------------------------------------------------------------- plain-English text
def _cap_word(w):
    core = w.strip(".,;:")
    if core.upper() in ACRONYMS or not core.isalpha():
        return w
    return w[:1] + w[1:].lower() if w.isupper() else w


def title_name(s):
    """DEBORAH SANFORD -> Deborah Sanford; keeps Mc/Mac and hyphenated parts readable."""
    s = str(s or "")
    if not s.isupper():
        return s
    out = s.title()
    out = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), out)
    out = re.sub(r"\b(Llc|Inc|Lp|Llp)\b", lambda m: m.group(1).upper(), out)
    return out


def humanize_code(code):
    """A database code -> words: CASH_DEPOSIT -> Cash deposit; known codes use their reviewed label."""
    c = str(code or "").strip()
    if c in VALUE_LABEL:
        return VALUE_LABEL[c]
    if c.startswith("DQ_"):
        c = c[3:]
    if c.startswith("LEGACY_"):
        return "Legacy: " + humanize_code(c[7:]).lower()
    words = [w for w in re.split(r"[_\s]+", c) if w]
    if not words:
        return ""
    out = " ".join(w if w.upper() in ACRONYMS else w.lower() for w in words)
    return out[:1].upper() + out[1:]


_FILE = re.compile(r"\b(core_[a-z]|documents)/([A-Za-z0-9_]+)\.(?:csv|parquet|json|pdf)(?:\.gz)?")
_PAIR = re.compile(r"\b(core_[a-z]):")
_CODE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_DT = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?)?\b")
_PLURAL = re.compile(r"\b(\d+) ([a-z]+(?: [a-z]+)?)\(s\)")
_CAPS_RUN = re.compile(r"\b[A-Z][A-Z'\-]+(?:\s+[A-Z][A-Z'\-]+)+\b")


def file_label(core, stem):
    who = CORE_SHORT.get(core, "Documents" if core == "documents" else core)
    return f"{who} {stem.replace('_', ' ')} file"


def fmt_date(y, m, d, hh=None, mm=None):
    try:
        dt = datetime(int(y), int(m), int(d), int(hh or 0), int(mm or 0))
    except ValueError:
        return f"{y}-{m}-{d}"
    day = f"{dt.day} {dt.strftime('%b %Y')}"
    return f"{day}, {dt.strftime('%H:%M')}" if hh is not None else day


def clean_text(s):
    """Display text without underscores, brackets, codes or shouting capitals. Display only: stored records,
    fingerprints and exported documents are never changed by this."""
    t = str(s if s is not None else "")
    links = []                                    # Markdown links pass through untouched
    t = re.sub(r"\[[^\[\]]+\]\([^()\s]+\)", lambda m: links.append(m.group(0)) or f"\x00{len(links) - 1}\x00", t)
    t = re.sub(r"\((-?\$[\d,]+(?:\.\d+)?)\)", r"-\1", t)      # accounting negative ($1,200.50) -> -$1,200.50
    t = _FILE.sub(lambda m: file_label(m.group(1), m.group(2)), t)
    t = re.sub(r"\b[\w/]+/(\w+)\.py\b", lambda m: f"the {m.group(1).replace('_', ' ')} builder", t)
    t = _PAIR.sub(lambda m: CORE_SHORT.get(m.group(1), m.group(1)) + " ", t)
    t = re.sub(r"\bcore_([a-z])\b", lambda m: f"Core {m.group(1).upper()}", t)
    t = _CODE.sub(lambda m: humanize_code(m.group(0)), t)
    t = _PLURAL.sub(lambda m: f"{m.group(1)} {m.group(2)}" + ("" if m.group(1) == "1" else "s"), t)
    t = re.sub(r"\(s\)", "s", t)
    t = _DT.sub(lambda m: fmt_date(*m.groups()), t)
    t = re.sub(r"\s*\[([^\[\]]+)\]", lambda m: f" Source: {m.group(1).strip()}.", t)
    t = re.sub(r"\s*\(([^()]+)\)", lambda m: f", {m.group(1).strip()}", t)
    t = re.sub(r"\s*\(\)", "", t)
    t = t.replace("_", " ")
    t = re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], t)
    t = _CAPS_RUN.sub(lambda m: m.group(0) if all(w.upper() in ACRONYMS for w in m.group(0).split())
                      else title_name(m.group(0)), t)
    t = re.sub(r"\b([A-Z]{4,})\b", lambda m: m.group(1) if m.group(1) in ACRONYMS else m.group(1).title(), t)
    t = re.sub(r"\.\s*\.", ".", t).replace(",,", ",").replace(", ,", ",").replace(" ,", ",")
    return t


def label_for(col):
    c = str(col)
    lc = c.lower()
    if lc in COLUMN_LABEL:
        return COLUMN_LABEL[lc]
    words = [w for w in lc.replace("_usd", "").split("_") if w]
    out = " ".join(w.upper() if w.upper() in ACRONYMS else w for w in words)
    return out[:1].upper() + out[1:]


def _clean_value(col, v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return v
    if isinstance(v, (bool,)):
        return "Yes" if v else "No"
    if isinstance(v, (pd.Timestamp, datetime)):
        return fmt_date(v.year, f"{v.month:02d}", f"{v.day:02d}", f"{v.hour:02d}", f"{v.minute:02d}") \
            if (v.hour or v.minute) else fmt_date(v.year, f"{v.month:02d}", f"{v.day:02d}")
    if isinstance(v, date):
        return fmt_date(v.year, f"{v.month:02d}", f"{v.day:02d}")
    if not isinstance(v, str):
        return v
    lc = str(col).lower()
    if lc in NAME_COLUMNS:
        return title_name(v)
    if v in VALUE_LABEL:
        return VALUE_LABEL[v]
    if lc in ("reasons", "link_reasons", "reason_codes", "top_reasons") or (";" in v and _CODE.search(v)):
        return ", ".join(humanize_code(x.strip()) for x in re.split(r"[;,]", v) if x.strip())
    if re.fullmatch(r"[A-Z][A-Z0-9]*(?:[_ ][A-Z0-9]+)*", v) and v not in ACRONYMS and len(v) > 2:
        return humanize_code(v)
    return clean_text(v)


def present(df, money=None):
    """(display frame, column config): plain-English headers and values, money as dollars, dates readable.
    Keeps the original column names underneath, so code and tests still address them."""
    if df is None:
        return df, {}
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == bool:
            out[c] = out[c].map(lambda b: "Yes" if b else "No")
        elif str(out[c].dtype).startswith("datetime"):
            out[c] = out[c].map(lambda v: _clean_value(c, v))
        elif out[c].dtype == object:
            out[c] = out[c].map(lambda v, c=c: _clean_value(c, v))
    cfg = {}
    money = set(money or []) | {c for c in out.columns if str(c).lower().endswith("_usd")}
    for c in out.columns:
        lab = label_for(c)
        if c in money and pd.api.types.is_numeric_dtype(out[c]):
            cfg[c] = st.column_config.NumberColumn(lab, format="dollar")
        elif pd.api.types.is_integer_dtype(out[c]) and str(c).lower() not in ("source_row", "queue_rank"):
            cfg[c] = st.column_config.NumberColumn(lab, format="localized")
        elif pd.api.types.is_float_dtype(out[c]):
            cfg[c] = st.column_config.NumberColumn(lab, format="localized")
        else:
            cfg[c] = st.column_config.Column(lab)
    return out, cfg


def table(df, key=None, height=None, column_config=None, **kw):
    """The one way the app shows a table."""
    shown, cfg = present(df)
    cfg.update(column_config or {})
    return st.dataframe(shown, width="stretch", hide_index=True, column_config=cfg, key=key,
                        **({"height": height} if height else {}), **kw)


# ---------------------------------------------------------------- charts: one style for every chart
def chart_style(chart):
    return (chart.configure(font=FONT)
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor="#edf0f5", domainColor="#c9d2e0",
                            labelFontSize=12, titleFontSize=12, titleFontWeight=600, labelFont=FONT, titleFont=FONT,
                            tickColor="#c9d2e0")
            .configure_legend(labelColor=INK, titleColor=MUTED, orient="top", labelFontSize=12, labelFont=FONT,
                              symbolType="square", titleFont=FONT)
            .configure_text(font=FONT, fontSize=12)
            .configure_title(font=FONT, fontSize=13, color=INK, anchor="start"))


def hbar(df, label, value, axis_title, color=None, value_format=",.0f"):
    """Ranking: one series of horizontal bars, sorted, with value labels and tooltips."""
    color = color or ACCENT
    base = alt.Chart(df).encode(
        y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=280, ticks=False)),
        x=alt.X(f"{value}:Q", title=axis_title, axis=alt.Axis(grid=True, format=value_format, tickCount=5),
                scale=alt.Scale(domain=[0, float(df[value].max() or 1) * 1.18], nice=False)),
        tooltip=[alt.Tooltip(f"{label}:N", title="Item"), alt.Tooltip(f"{value}:Q", title=axis_title, format=value_format)])
    bars = base.mark_bar(color=color, cornerRadiusEnd=3, height=18)
    text = base.mark_text(align="left", dx=5, color=INK, fontSize=12).encode(text=alt.Text(f"{value}:Q", format=value_format))
    return chart_style((bars + text).properties(height=alt.Step(30)))


# ---------------------------------------------------------------- stylesheet
def _css(accent, soft):
    return f"""
<style>
:root {{ --ink:{INK}; --muted:{MUTED}; --line:{LINE}; --accent:{accent}; --accent-soft:{soft}; --navy:{NAVY}; }}
html, body, [class*="css"], .stApp, button, input, textarea, select, .stMarkdown, [data-testid="stHtml"] {{
    font-family: "{FONT}", system-ui, -apple-system, "Segoe UI", sans-serif !important; }}
body {{ font-feature-settings: "cv11" 1; }}
[data-testid="stMetricValue"], .rc-mono, .rc-kv b {{ font-variant-numeric: tabular-nums; }}
.stButton > button p, .stDownloadButton > button p, [data-testid="stFormSubmitButton"] > button p,
[data-testid="stPopover"] button p {{ font-size: .9rem !important; font-weight: 500; }}
.stApp {{ background: {PAGE_BG}; }}
.block-container {{ padding-top: .9rem; padding-bottom: 3rem; max-width: 1480px; }}
[data-testid="stAppDeployButton"], #MainMenu, footer {{ display: none !important; }}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}

/* type scale: title 1.7 / section 1.1 / body .95 / label .82 / caption .8 rem, sentence case everywhere */
h1, h2, h3 {{ color: var(--ink); letter-spacing: -.01em; }}
[data-testid="stCaptionContainer"], .stCaption {{ font-size: .82rem !important; color: var(--muted) !important; }}

/* sidebar navigation */
[data-testid="stSidebar"] {{ border-right: 1px solid #0b1528; }}
[data-testid="stSidebar"] [data-testid="stRadio"] > label {{ display: none; }}
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 2px; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding: 10px 12px; border-radius: 8px; width: 100%;
    margin: 0; transition: background .15s; }}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: rgba(255,255,255,.06); }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{ background: rgba(255,255,255,.10);
    box-shadow: inset 3px 0 0 {accent}; }}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child:not(:has([data-testid="stMarkdownContainer"])),
[data-testid="stSidebar"] [role="radiogroup"] label > div > div:first-child:not([data-testid]) {{ display: none; }}
[data-testid="stSidebar"] [role="radiogroup"] > div, [data-testid="stSidebar"] [role="radiogroup"] label {{ width: 100%; box-sizing: border-box; }}
[data-testid="stSidebar"] [role="radiogroup"] label[data-selected="true"] {{ background: rgba(255,255,255,.10);
    box-shadow: inset 3px 0 0 {accent}; }}
[data-testid="stSidebar"] [role="radiogroup"] p {{ font-size: .95rem; font-weight: 500; }}
.rc-wordmark {{ padding: 6px 4px 18px 4px; }}
.rc-wordmark .n {{ color:#fff; font-weight:700; font-size:1.08rem; letter-spacing:-.01em; }}
.rc-wordmark .s {{ color:#9fb0d0; font-size:.8rem; margin-top:2px; }}
.rc-side-foot {{ color:#9fb0d0; font-size:.8rem; line-height:1.5; margin-top: 8px; }}

/* top bar: page trail on the left, profile on the right */
.rc-trail {{ font-size:.85rem; color: var(--muted); padding-top: 9px; }}
.rc-trail b {{ color: var(--ink); font-weight:600; }}
[data-testid="stPopover"] > div > button, [data-testid="stPopoverButton"] {{ border-radius: 999px !important;
    border: 1px solid var(--line) !important; background: #fff !important; font-weight: 600 !important; }}
.rc-avatar {{ width:40px; height:40px; border-radius:50%; background: var(--navy); color:#fff; display:flex;
    align-items:center; justify-content:center; font-weight:700; font-size:.95rem; }}
.rc-profile-card {{ display:flex; gap:12px; align-items:center; margin-bottom: 8px; }}
.rc-profile-card .n {{ font-weight:700; color: var(--ink); }}
.rc-profile-card .t {{ color: var(--muted); font-size:.85rem; }}
.rc-profile-meta {{ font-size:.82rem; color: var(--muted); line-height:1.6; margin: 6px 0 10px 0; }}

/* page header with the page's accent */
.rc-top {{ display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin: 6px 0 18px 0;
    padding-bottom: 14px; border-bottom: 3px solid var(--accent); }}
.rc-title h1 {{ font-size: 1.7rem; font-weight: 700; margin: 0; padding: 0; line-height: 1.15; }}
.rc-title p {{ margin: 6px 0 0 0; color: var(--muted); font-size: .95rem; }}
.rc-meta {{ display:flex; flex-wrap:wrap; gap:6px; justify-content:flex-end; }}

/* cards */
[data-testid="stVerticalBlockBorderWrapper"] {{ background: #fff; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: 0 1px 2px rgba(15,27,51,.04); }}
[class*="st-key-kpicard_"] {{ border-top: 3px solid var(--accent) !important; }}
[data-testid="stMetricLabel"] p {{ font-size: .82rem !important; color: var(--muted) !important; font-weight: 600;
    white-space: normal !important; overflow: visible !important; }}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] div {{ overflow: visible !important; white-space: normal !important; }}
[data-testid="stMetricValue"] {{ font-size: 1.7rem !important; font-weight: 700; color: var(--ink); }}
[class*="st-key-kpicard_"] [data-testid="stMetricLabel"] {{ min-height: 2.5em; align-items: flex-start; }}
[class*="st-key-kpicard_"] [data-testid="stCaptionContainer"] {{ min-height: 5.4em; }}
.st-key-narrative h1 {{ font-size: 1.5rem !important; }}
.st-key-narrative h2 {{ font-size: 1.1rem !important; margin-top: .6rem; }}
.st-key-narrative {{ padding: 6px 18px; }}

/* accent on controls */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{ border-radius: 8px;
    font-weight: 600; }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button {{ background: var(--accent) !important; border-color: var(--accent) !important;
    color: #fff !important; }}
.stButton > button[kind="tertiary"] {{ color: var(--accent) !important; padding-left: 0; }}
[data-testid="stTabs"] [role="tab"] p {{ font-size: .95rem; font-weight: 600; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {{ color: var(--accent); }}
[data-baseweb="tab-highlight"], [data-testid="stTabs"] .react-aria-SelectionIndicator {{ background-color: var(--accent) !important; border-color: var(--accent) !important; }}
[data-baseweb="tag"] {{ background-color: var(--accent) !important; }}
[data-testid="stSlider"] [role="slider"] {{ background-color: var(--accent) !important; }}
[data-testid="stExpander"] {{ background: #fff; border-radius: 10px; }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}

/* pills and chips */
.rc-pill {{ display:inline-flex; align-items:center; gap:6px; padding: 3px 10px; border-radius: 999px;
    font-size: .78rem; font-weight: 600; border: 1px solid var(--line); background:#fff; color: var(--ink); white-space: nowrap; }}
.rc-pill.dot::before {{ content:""; width:7px; height:7px; border-radius:50%; background: currentColor; }}
.rc-pill.green {{ color:{GREEN}; background:#ecfdf3; border-color:#bbe5c8; }}
.rc-pill.red {{ color:{RED}; background:#fef2f2; border-color:#f6caca; }}
.rc-pill.amber {{ color:{AMBER}; background:#fff7ed; border-color:#f9d6a8; }}
.rc-pill.blue, .rc-pill.accent {{ color: var(--accent); background: var(--accent-soft); border-color: transparent; }}
.rc-pill.navy {{ color:#fff; background:{NAVY}; border-color:{NAVY}; }}
.rc-pill.core-a {{ color:{CORE_A}; background:#eef1ff; border-color:#d0d8ff; }}
.rc-pill.core-b {{ color:{CORE_B}; background:#e6f6f4; border-color:#bfe6e0; }}
.rc-chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
.rc-chip {{ padding: 3px 9px; border-radius: 6px; font-size: .82rem; background:#f1f4f9; color: var(--ink);
    border: 1px solid var(--line); }}

/* hero band */
.rc-hero {{ background: linear-gradient(120deg, {NAVY} 0%, #1b2d5c 100%); color:#fff; border-radius: 14px;
    padding: 22px 26px; margin-bottom: 18px; display:flex; gap: 28px; align-items:center; border-left: 5px solid var(--accent); }}
.rc-hero .lead {{ flex: 1.35; }}
.rc-hero .lead .eyebrow {{ font-size:.85rem; color:#b9c8f0; font-weight:600; }}
.rc-hero .lead h2 {{ color:#fff; font-size:1.3rem; line-height:1.4; margin:6px 0 6px 0; font-weight:600; }}
.rc-hero .lead p {{ color:#c9d4ee; margin:0; font-size:.92rem; }}
.rc-hero .stats {{ flex: 1.15; display:flex; gap: 10px; }}
.rc-hero .stat {{ flex:1; background: rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.12);
    border-radius: 10px; padding: 12px 14px; }}
.rc-hero .stat b {{ display:block; font-size: 1.8rem; line-height:1.1; color:#fff; }}
.rc-hero .stat span {{ font-size:.8rem; color:#c9d4ee; }}

.rc-section {{ display:flex; align-items:baseline; justify-content:space-between; margin: 24px 0 10px 0; }}
.rc-section h3 {{ font-size: 1.1rem; font-weight: 650; margin:0; padding:0; }}
.rc-section span {{ color: var(--muted); font-size: .85rem; }}
.rc-card-title {{ font-weight: 650; font-size: 1rem; color: var(--ink); margin-bottom: 2px; }}
.rc-card-sub {{ color: var(--muted); font-size: .85rem; margin-bottom: 8px; }}

.rc-pipe {{ display:flex; align-items:stretch; gap: 0; margin: 4px 0 18px 0; }}
.rc-stage {{ flex:1; background:#fff; border:1px solid var(--line); border-top: 3px solid var(--accent);
    border-radius: 12px; padding: 14px 16px; }}
.rc-stage .name {{ font-size:.85rem; font-weight:600; color: var(--muted); }}
.rc-stage .big {{ font-size: 1.5rem; font-weight: 700; color: var(--ink); margin: 4px 0 2px 0; }}
.rc-stage .sub {{ font-size: .82rem; color: var(--muted); }}
.rc-stage .ok {{ color:{GREEN}; font-weight:700; float:right; }}
.rc-arrow {{ display:flex; align-items:center; padding: 0 8px; color:#9aa7bd; font-size: 1.3rem; }}

.rc-rules {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }}
.rc-rule {{ background:#fff; border:1px solid var(--line); border-left: 4px solid {RED}; border-radius: 10px; padding: 12px 14px; }}
.rc-rule.mit {{ border-left-color: {GREEN}; }}
.rc-rule .hd {{ display:flex; justify-content:space-between; align-items:center; gap:8px; }}
.rc-rule .t {{ font-weight: 650; color: var(--ink); font-size: .95rem; }}
.rc-rule .w {{ font-weight: 700; font-size: .85rem; color:{RED}; }}
.rc-rule.mit .w {{ color:{GREEN}; }}
.rc-rule .ev {{ margin-top: 6px; font-size: .88rem; color: #2c3a55; line-height: 1.5; }}
.rc-kv {{ display:flex; gap: 28px; flex-wrap: wrap; margin-top: 8px; }}
.rc-kv div span {{ display:block; font-size:.82rem; color: var(--muted); font-weight:600; }}
.rc-kv div b {{ font-size: 1.2rem; color: var(--ink); }}
.rc-label {{ font-size:.82rem; color: var(--muted); font-weight:600; margin: 10px 0 6px 0; }}
.rc-steps {{ display:flex; align-items:center; gap: 0; margin: 6px 0 14px 0; }}
.rc-step {{ display:flex; align-items:center; gap:8px; font-size:.88rem; font-weight:600; color:#9aa7bd; }}
.rc-step .n {{ width: 24px; height: 24px; border-radius: 50%; border: 2px solid #c5cfdf; display:flex;
    align-items:center; justify-content:center; font-size:.75rem; background:#fff; }}
.rc-step.done {{ color: var(--ink); }}
.rc-step.done .n {{ background:{GREEN}; border-color:{GREEN}; color:#fff; }}
.rc-step.now .n {{ border-color:{AMBER}; color:{AMBER}; }}
.rc-step.now {{ color:{AMBER}; }}
.rc-step.bad .n {{ background:{RED}; border-color:{RED}; color:#fff; }}
.rc-step.bad {{ color:{RED}; }}
.rc-bar {{ width: 56px; height: 2px; background:#d5dce8; margin: 0 10px; }}
.rc-bar.done {{ background:{GREEN}; }}
.rc-legend {{ display:flex; gap:14px; font-size:.82rem; color: var(--muted); margin: 2px 0 6px 0; flex-wrap:wrap; }}
.rc-legend i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }}
.rc-answer {{ font-size:1.08rem; font-weight:600; line-height:1.5; color: var(--ink); border-left:4px solid var(--accent);
    padding:8px 0 8px 14px; background: var(--accent-soft); border-radius:0 8px 8px 0; }}
.rc-mono {{ font-variant-numeric: tabular-nums; letter-spacing: .01em; }}
</style>
"""


LOGIN_CSS = f"""
<style>
.stApp {{ background: radial-gradient(1200px 600px at 20% 0%, #1e3a8a 0%, {NAVY} 55%, #0a1326 100%) !important; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{ display:none !important; }}
.block-container {{ max-width: 1100px; padding-top: 7vh; }}
.st-key-login_card {{ background:#fff !important; border-radius: 16px !important; padding: 30px 32px 22px 32px !important;
    box-shadow: 0 24px 60px rgba(4,10,25,.45) !important; border: none !important; }}
.rc-login-head {{ text-align:center; margin-bottom: 14px; }}
.rc-login-head .n {{ font-size:1.35rem; font-weight:700; color:{INK}; margin-top: 12px; letter-spacing:-.01em; }}
.rc-login-head .s {{ color:{MUTED}; font-size:.92rem; margin-top: 4px; }}
.rc-login-foot {{ text-align:center; color:#b9c6e4; font-size:.82rem; margin-top: 16px; line-height:1.6; }}
.rc-login-note {{ color:{MUTED}; font-size:.8rem; text-align:center; margin-top: 6px; }}
</style>
"""


def logo_svg(size=56):
    """The Sahasranshu mark: a shield with a rising sun (sahasranshu: the sun of a thousand rays). Original artwork."""
    rays = "".join(
        f'<line x1="32" y1="36" x2="{32 + 15 * math.cos(a):.1f}" y2="{36 - 15 * math.sin(a):.1f}" '
        f'stroke="#f5b942" stroke-width="2.2" stroke-linecap="round"/>'
        for a in [3.14159 * k / 8 for k in range(1, 8)])
    import base64
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 64 64">'
            f'<path d="M32 4 L55 12 V30 C55 45 45 55 32 60 C19 55 9 45 9 30 V12 Z" fill="{NAVY}"/>'
            f'<path d="M32 4 L55 12 V30 C55 45 45 55 32 60 Z" fill="#1e3a8a"/>'
            f'{rays}<circle cx="32" cy="36" r="7.5" fill="#f5b942"/>'
            f'<rect x="16" y="36" width="32" height="2.6" rx="1.3" fill="#ffffff"/></svg>')
    # an <img> data URI: st.html strips inline <svg> elements
    return (f'<img alt="Sahasranshu logo" width="{size}" height="{size}" '
            f'src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"/>')


def esc(x):
    return html.escape(str(x if x is not None else ""))


def set_page(page):
    """Apply the stylesheet with this page's accent; charts read ui.ACCENT."""
    global ACCENT
    accent, soft = PAGE_THEME.get(page, PAGE_THEME["Executive overview"])
    ACCENT = accent
    st.html(_css(accent, soft))
    if page == "Sign in":
        st.html(LOGIN_CSS)


def pill(text, kind="", dot=False):
    return f'<span class="rc-pill {kind}{" dot" if dot else ""}">{esc(text)}</span>'


def chips(items):
    return '<div class="rc-chips">' + "".join(f'<span class="rc-chip">{esc(i)}</span>' for i in items) + "</div>"


def page_header(title, subtitle, meta_html=""):
    st.html(f'<div class="rc-top"><div class="rc-title"><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>'
            f'<div class="rc-meta">{meta_html}</div></div>')


def section(title, note=""):
    st.html(f'<div class="rc-section"><h3>{esc(title)}</h3><span>{esc(note)}</span></div>')


def card_title(title, sub=""):
    st.html(f'<div class="rc-card-title">{esc(title)}</div>' + (f'<div class="rc-card-sub">{esc(sub)}</div>' if sub else ""))


def status_pill(status):
    s = str(status or "").upper()
    kind = {"APPROVED": "green", "MATCH": "green", "REJECTED": "red", "BREAK": "red", "DRAFT": "amber",
            "OPEN": "amber", "IN_PROGRESS": "accent", "CLOSED": "", "PREVIEW": "accent"}.get(s, "")
    return pill(humanize_code(s), kind, dot=True)


def score_ring(score, size=96):
    """Risk score as a ring; returned as an <img> (SVG data URI) so it renders the same everywhere."""
    import base64
    s = max(0.0, min(100.0, float(score or 0)))
    col = RED if s >= 70 else AMBER if s >= 40 else "#ca8a04" if s >= 20 else GREEN
    r, c = 40, 2 * 3.14159 * 40
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 100 100" role="img" '
           f'aria-label="risk score {s:.0f} of 100">'
           f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="#edf0f5" stroke-width="10"/>'
           f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="{col}" stroke-width="10" stroke-linecap="round" '
           f'stroke-dasharray="{c * s / 100:.1f} {c:.1f}" transform="rotate(-90 50 50)"/>'
           f'<text x="50" y="49" text-anchor="middle" font-family="{FONT}, sans-serif" font-size="26" font-weight="700" '
           f'fill="{INK}">{s:.0f}</text>'
           f'<text x="50" y="66" text-anchor="middle" font-family="{FONT}, sans-serif" font-size="10" fill="{MUTED}">of 100</text></svg>')
    return (f'<img alt="risk score {s:.0f} of 100" width="{size}" height="{size}" '
            f'src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"/>')


def rule_cards(signals):
    out = []
    for s in signals:
        mit = float(s["weight"]) < 0
        out.append(f'<div class="rc-rule{" mit" if mit else ""}"><div class="hd"><span class="t">'
                   f'{esc(RULE_LABEL.get(s["rule_code"], humanize_code(s["rule_code"])))}</span>'
                   f'<span class="w">{float(s["weight"]):+.0f}</span></div>'
                   f'<div class="ev">{esc(clean_text(s["evidence"]))}</div></div>')
    return '<div class="rc-rules">' + "".join(out) + "</div>"


def stepper(steps):
    """steps: list of (label, state) with state in done | now | bad | todo."""
    parts = []
    for i, (label, state) in enumerate(steps):
        if i:
            parts.append(f'<div class="rc-bar{" done" if steps[i - 1][1] == "done" and state in ("done", "now") else ""}"></div>')
        mark = "&#10003;" if state == "done" else "&#10005;" if state == "bad" else str(i + 1)
        parts.append(f'<div class="rc-step {state}"><span class="n">{mark}</span>{esc(label)}</div>')
    return '<div class="rc-steps">' + "".join(parts) + "</div>"


def legend(items):
    return '<div class="rc-legend">' + "".join(f'<span><i style="background:{c}"></i>{esc(t)}</span>' for t, c in items) + "</div>"
