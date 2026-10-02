"""Presentation helpers for the Risk Copilot app: one stylesheet, and small HTML pieces (badges, chips, cards).

Pure presentation: nothing here queries data or changes a number. Colours carry meaning only:
  Core A and Core B each have one fixed colour; red / amber / green are used for risk and status.
"""
import html

import streamlit as st

NAVY = "#0f1b33"
INK = "#14213d"
MUTED = "#5b6b85"
ACCENT = "#2453c6"
LINE = "#dde4ef"
CORE_A = "#3b5bdb"      # Kestrel Valley (Core A)
CORE_B = "#0c8f7c"      # Pellbrook (Core B)
BOTH = "#14213d"        # combined across cores
RED, AMBER, GREEN, GREY = "#c92a2a", "#d9480f", "#2b8a3e", "#868e96"

CORE_NAME = {"core_a": "Core A · Kestrel Valley", "core_b": "Core B · Pellbrook", "core_c": "Core C"}
ORIGIN_NAME = {"RISK_ENGINE": "Risk engine", "LEGACY_CORE_A": "Legacy · Core A", "LEGACY_CORE_B": "Legacy · Core B"}
RULE_LABEL = {"XCORE_CASH_30D": "Cash split across cores", "CTR_AGGREGATION_MISSED": "Missed CTR aggregation",
              "NEAR_THRESHOLD_CASH": "Near-threshold cash", "RAPID_IN_OUT": "Rapid in and out",
              "DORMANT_REACTIVATION": "Dormant reactivation", "KYC_MISMATCH": "Cash above KYC profile",
              "KYC_INCONSISTENT_ACROSS_CORES": "KYC differs across cores",
              "KYC_CONSISTENT_CASH": "Cash in line with KYC (mitigating)"}
LINK_LABEL = {"TAX_TOKEN_EQUAL": "Tax ID token equal", "DOB_EQUAL": "Birth date equal", "SURNAME_MATCH": "Surname match",
              "GIVEN_NAME_EQUAL": "Given name equal", "GIVEN_NAME_NICKNAME": "Nickname of given name",
              "GIVEN_NAME_SIMILAR": "Given name similar", "ADDRESS_EQUAL": "Address equal", "PHONE_EQUAL": "Phone equal",
              "TAX_TOKEN_MISSING": "No tax token to compare"}

CSS = f"""
<style>
:root {{ --ink:{INK}; --muted:{MUTED}; --line:{LINE}; --accent:{ACCENT}; }}
html, body, [class*="css"] {{ font-feature-settings: "tnum" 1; }}
.block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1480px; }}
[data-testid="stAppDeployButton"], #MainMenu, footer {{ display: none !important; }}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}

/* sidebar */
[data-testid="stSidebar"] {{ border-right: 1px solid #0b1528; }}
[data-testid="stSidebar"] [data-testid="stRadio"] > label {{ display: none; }}
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 2px; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding: 9px 12px; border-radius: 8px; width: 100%;
    margin: 0; transition: background .15s; }}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: rgba(255,255,255,.06); }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{ background: rgba(92,132,255,.22);
    box-shadow: inset 3px 0 0 #7aa2ff; }}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {{ display: none; }}
[data-testid="stSidebar"] [role="radiogroup"] p {{ font-size: .95rem; font-weight: 500; }}
[data-testid="stSidebar"] input {{ background: #18284a !important; color: #fff !important; }}

/* cards: bordered Streamlit containers */
[data-testid="stVerticalBlockBorderWrapper"] {{ background: #fff; border-color: var(--line) !important;
    border-radius: 12px !important; }}
[data-testid="stMetric"] {{ padding: 2px 2px 0 2px; }}
[data-testid="stMetricLabel"] p {{ font-size: .7rem !important; text-transform: uppercase; letter-spacing: .04em;
    color: var(--muted) !important; font-weight: 700; white-space: normal !important; overflow: visible !important; }}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] div {{ overflow: visible !important; white-space: normal !important; }}
[class*="st-key-kpi_"] [data-testid="stCaptionContainer"] {{ min-height: 2.7em; }}
[class*="st-key-kpi_"] [data-testid="stMetricValue"] {{ font-size: 1.8rem !important; }}
.st-key-narrative h1 {{ font-size: 1.7rem !important; }}
.st-key-narrative h2 {{ font-size: 1.2rem !important; margin-top: .6rem; }}
.st-key-narrative {{ padding: 6px 18px; }}
[data-testid="stMetricValue"] {{ font-size: 2.0rem !important; font-weight: 650; color: var(--ink); }}

/* headings, tabs, buttons */
h1, h2, h3 {{ color: var(--ink); letter-spacing: -.01em; }}
[data-testid="stTabs"] button[role="tab"] p {{ font-size: .95rem; font-weight: 600; }}
.stButton > button, .stDownloadButton > button {{ border-radius: 8px; font-weight: 600; }}
.stButton > button[kind="primary"] {{ box-shadow: 0 1px 2px rgba(20,33,61,.18); }}
[data-testid="stExpander"] {{ background: #fff; border-radius: 10px; }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}

/* custom pieces */
.rc-top {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin: 0 0 18px 0; }}
.rc-title h1 {{ font-size: 1.85rem; margin: 0; padding: 0; line-height: 1.15; }}
.rc-title p {{ margin: 4px 0 0 0; color: var(--muted); font-size: .95rem; }}
.rc-meta {{ display:flex; flex-wrap:wrap; gap:6px; justify-content:flex-end; }}
.rc-pill {{ display:inline-flex; align-items:center; gap:6px; padding: 3px 10px; border-radius: 999px;
    font-size: .74rem; font-weight: 600; letter-spacing: .02em; border: 1px solid var(--line); background:#fff;
    color: var(--ink); white-space: nowrap; }}
.rc-pill.dot::before {{ content:""; width:7px; height:7px; border-radius:50%; background: currentColor; }}
.rc-pill.green {{ color:{GREEN}; background:#ebfbee; border-color:#c3e9cb; }}
.rc-pill.red {{ color:{RED}; background:#fff1f1; border-color:#ffd0d0; }}
.rc-pill.amber {{ color:{AMBER}; background:#fff4e6; border-color:#ffd8a8; }}
.rc-pill.blue {{ color:{ACCENT}; background:#edf2ff; border-color:#cdd9ff; }}
.rc-pill.navy {{ color:#fff; background:{NAVY}; border-color:{NAVY}; }}
.rc-pill.core-a {{ color:{CORE_A}; background:#eef1ff; border-color:#d0d8ff; }}
.rc-pill.core-b {{ color:{CORE_B}; background:#e6f7f3; border-color:#bfe9df; }}
.rc-chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
.rc-chip {{ padding: 3px 9px; border-radius: 6px; font-size: .78rem; background:#f1f4f9; color: var(--ink);
    border: 1px solid var(--line); }}
.rc-hero {{ background: linear-gradient(120deg, {NAVY} 0%, #1d3270 100%); color:#fff; border-radius: 14px;
    padding: 22px 26px; margin-bottom: 18px; display:flex; gap: 28px; align-items:center; }}
.rc-hero .lead {{ flex: 1.35; }}
.rc-hero .lead .eyebrow {{ font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; color:#9fb5ff; font-weight:700; }}
.rc-hero .lead h2 {{ color:#fff; font-size:1.35rem; line-height:1.35; margin:6px 0 6px 0; font-weight:600; }}
.rc-hero .lead p {{ color:#c9d4ee; margin:0; font-size:.92rem; }}
.rc-hero .stats {{ flex: 1.15; display:flex; gap: 10px; }}
.rc-hero .stat {{ flex:1; background: rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.12);
    border-radius: 10px; padding: 12px 14px; }}
.rc-hero .stat b {{ display:block; font-size: 1.9rem; line-height:1.1; color:#fff; }}
.rc-hero .stat span {{ font-size:.78rem; color:#c9d4ee; }}
.rc-section {{ display:flex; align-items:baseline; justify-content:space-between; margin: 22px 0 8px 0; }}
.rc-section h3 {{ font-size: 1.12rem; margin:0; padding:0; }}
.rc-section span {{ color: var(--muted); font-size: .84rem; }}
.rc-pipe {{ display:flex; align-items:stretch; gap: 0; margin: 4px 0 18px 0; }}
.rc-stage {{ flex:1; background:#fff; border:1px solid var(--line); border-radius: 12px; padding: 14px 16px; }}
.rc-stage .name {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.1em; font-weight:700; color: var(--muted); }}
.rc-stage .big {{ font-size: 1.55rem; font-weight: 650; color: var(--ink); margin: 4px 0 2px 0; }}
.rc-stage .sub {{ font-size: .8rem; color: var(--muted); }}
.rc-stage .ok {{ color:{GREEN}; font-weight:700; float:right; }}
.rc-arrow {{ display:flex; align-items:center; padding: 0 8px; color:#9aa7bd; font-size: 1.3rem; }}
.rc-rules {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }}
.rc-rule {{ background:#fff; border:1px solid var(--line); border-left: 4px solid {RED}; border-radius: 10px;
    padding: 12px 14px; }}
.rc-rule.mit {{ border-left-color: {GREEN}; }}
.rc-rule .hd {{ display:flex; justify-content:space-between; align-items:center; gap:8px; }}
.rc-rule .t {{ font-weight: 650; color: var(--ink); font-size: .95rem; }}
.rc-rule .w {{ font-weight: 700; font-size: .85rem; color:{RED}; }}
.rc-rule.mit .w {{ color:{GREEN}; }}
.rc-rule .code {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .7rem; color: var(--muted); }}
.rc-rule .ev {{ margin-top: 6px; font-size: .86rem; color: #2c3a55; line-height: 1.45; }}
.rc-profile {{ display:flex; gap: 22px; align-items:center; }}
.rc-profile .ids {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size:.78rem; color: var(--muted); }}
.rc-kv {{ display:flex; gap: 26px; flex-wrap: wrap; margin-top: 8px; }}
.rc-kv div span {{ display:block; font-size:.7rem; text-transform:uppercase; letter-spacing:.08em; color: var(--muted);
    font-weight:700; }}
.rc-kv div b {{ font-size: 1.25rem; color: var(--ink); }}
.rc-steps {{ display:flex; align-items:center; gap: 0; margin: 6px 0 14px 0; }}
.rc-step {{ display:flex; align-items:center; gap:8px; font-size:.86rem; font-weight:600; color:#9aa7bd; }}
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
.rc-doc {{ background:#fff; border:1px solid var(--line); border-radius: 12px; padding: 6px 30px 18px 30px; }}
.rc-legend {{ display:flex; gap:14px; font-size:.8rem; color: var(--muted); margin: 2px 0 6px 0; flex-wrap:wrap; }}
.rc-legend i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }}
.rc-brand {{ padding: 4px 2px 14px 2px; }}
.rc-brand .logo {{ display:flex; align-items:center; gap:10px; }}
.rc-brand .mark {{ width:34px; height:34px; border-radius:9px; background: linear-gradient(135deg,#4f7bff,#2453c6);
    display:flex; align-items:center; justify-content:center; color:#fff; font-weight:800; font-size:1rem; }}
.rc-brand .name {{ color:#fff; font-weight:700; font-size:1.05rem; line-height:1.1; }}
.rc-brand .sub {{ color:#9fb0d0; font-size:.74rem; }}
.rc-side-note {{ color:#9fb0d0; font-size:.78rem; line-height:1.45; }}
.rc-side-note b {{ color:#dce5f7; }}
.rc-trust {{ margin-top: 10px; padding: 10px 12px; border-radius: 10px; background: rgba(43,138,62,.14);
    border: 1px solid rgba(105,219,124,.28); color:#b2f2bb; font-size:.78rem; line-height:1.4; }}
.rc-trust b {{ color:#d3f9d8; }}
</style>
"""


def esc(x):
    return html.escape(str(x if x is not None else ""))


def inject_css():
    st.html(CSS)


def pill(text, kind="", dot=False):
    return f'<span class="rc-pill {kind}{" dot" if dot else ""}">{esc(text)}</span>'


def chips(items):
    return '<div class="rc-chips">' + "".join(f'<span class="rc-chip">{esc(i)}</span>' for i in items) + "</div>"


def page_header(title, subtitle, meta_html=""):
    st.html(f'<div class="rc-top"><div class="rc-title"><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>'
            f'<div class="rc-meta">{meta_html}</div></div>')


def section(title, note=""):
    st.html(f'<div class="rc-section"><h3>{esc(title)}</h3><span>{esc(note)}</span></div>')


def status_pill(status):
    s = str(status or "").upper()
    kind = {"APPROVED": "green", "MATCH": "green", "REJECTED": "red", "BREAK": "red", "DRAFT": "amber",
            "OPEN": "amber", "IN_PROGRESS": "blue", "CLOSED": ""}.get(s, "")
    return pill(s.replace("_", " ").title() if s not in ("MATCH", "BREAK") else s, kind, dot=True)


def score_ring(score, size=96):
    """Risk score as a ring; returned as an <img> (SVG data URI) so it renders the same everywhere."""
    import base64
    s = max(0.0, min(100.0, float(score or 0)))
    col = RED if s >= 70 else AMBER if s >= 40 else "#f08c00" if s >= 20 else GREEN
    r, c = 40, 2 * 3.14159 * 40
    svg = (f'<svg width="{size}" height="{size}" viewBox="0 0 100 100" aria-label="risk score {s:.0f} of 100">'
            f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="#edf0f5" stroke-width="10"/>'
            f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="{col}" stroke-width="10" stroke-linecap="round" '
            f'stroke-dasharray="{c * s / 100:.1f} {c:.1f}" transform="rotate(-90 50 50)"/>'
            f'<text x="50" y="49" text-anchor="middle" font-size="26" font-weight="700" fill="{INK}">{s:.0f}</text>'
            f'<text x="50" y="66" text-anchor="middle" font-size="10" fill="{MUTED}">of 100</text></svg>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg"' + svg[4:]).replace('aria-label', 'role="img" aria-label')
    return (f'<img alt="risk score {s:.0f} of 100" width="{size}" height="{size}" '
            f'src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"/>')


def rule_cards(signals):
    out = []
    for s in signals:
        mit = float(s["weight"]) < 0
        out.append(f'<div class="rc-rule{" mit" if mit else ""}"><div class="hd"><span class="t">'
                   f'{esc(RULE_LABEL.get(s["rule_code"], s["rule_code"]))}</span><span class="w">{float(s["weight"]):+.0f}'
                   f'</span></div><div class="code">{esc(s["rule_code"])}</div><div class="ev">{esc(s["evidence"])}</div></div>')
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
