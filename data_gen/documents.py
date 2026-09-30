"""KYC summaries and the fictional BSA/AML policy PDF."""
from pathlib import Path

import numpy as np
import pandas as pd

from . import vocab

SOURCES = ["Salary from employer", "Pension and Social Security", "Self-employment income",
           "Salary and spouse's income", "Hourly wages"]


def kyc_row(rng, kyc_id, core, ref, name, occupation, expected_cash, is_business, city, risk, conflict_note=""):
    review = np.datetime64("2024-06-01") + np.timedelta64(int(rng.integers(0, 730)), "D")
    rating = {"L": "Low", "M": "Medium", "H": "High", "2": "Low", "3": "Medium", "4": "High", "5": "High", "1": "Low"}[risk]
    if is_business:
        wires = int(rng.choice([0, 5000, 20000, 50000]))
        sof = "Business revenue"
        text = (f"{name} operates a {occupation.lower()} in {city}. Expected monthly cash deposits about "
                f"${expected_cash:,.0f}; expected monthly wires about ${wires:,.0f}. Beneficial ownership certified. "
                f"{'Cash-intensive business: CTR filings expected on large deposits. ' if expected_cash >= 30000 else ''}"
                f"Risk rating {rating}; last reviewed {review}.")
    else:
        wires = 0
        sof = SOURCES[int(rng.integers(0, len(SOURCES)))] if occupation != "Retired" else "Pension and Social Security"
        text = (f"{name}, occupation: {occupation}. Expected activity: payroll or benefit deposits, card spending and "
                f"bill payments. Expected monthly cash up to ${expected_cash:,.0f}; no wire activity expected. "
                f"Source of funds: {sof.lower()}. Risk rating {rating}; last reviewed {review}.{conflict_note}")
    return {"kyc_id": kyc_id, "core": core, "customer_ref": ref, "review_date": str(review),
            "risk_rating": rating, "occupation_or_business": occupation,
            "expected_monthly_cash_usd": f"{expected_cash:.0f}", "expected_monthly_wires_usd": f"{wires:.0f}",
            "source_of_funds": sof, "summary_text": text}


# ---------------- policy PDF ----------------

POLICY = [
    ("1. Purpose and scope", [
        "This policy sets out how Kestrel Valley Bank (the Bank) meets its obligations under the Bank Secrecy Act "
        "and related anti-money-laundering requirements. It applies to every account, product and channel of the Bank.",
        "Merger scope. On 30 June 2026 the Bank completed its acquisition of Pellbrook Savings Bank. Until core "
        "conversion is complete, customer accounts are held on two core systems: Core A (legacy Kestrel Valley) and "
        "Core B (legacy Pellbrook). Both cores belong to one legal entity. Every requirement in this policy applies "
        "across both cores as if they were a single system.",
    ]),
    ("2. Governance", [
        "The Board approves this policy at least annually. The BSA Officer is responsible for day-to-day compliance, "
        "reports to the Board Risk Committee quarterly and has authority to escalate any matter directly to the Board.",
        "Model and rule changes in transaction monitoring require BSA Officer approval and are logged with the date, "
        "the change and the rationale.",
    ]),
    ("3. Customer due diligence", [
        "3.1 Customer identification. Identity is verified at account opening under the Customer Identification Program.",
        "3.2 Customer risk profile. Each customer has a documented profile of expected activity, including expected "
        "monthly cash and wire activity, occupation or line of business, and source of funds.",
        "3.3 Enhanced due diligence. EDD applies to customers rated High risk, cash-intensive businesses, customers "
        "with a SAR filed in the last 24 months, and customers whose observed activity materially exceeds the expected "
        "activity in their profile.",
        "3.4 Profiles held on two cores. Where the same customer holds relationships on both cores, the investigator "
        "must compare both profiles. A material inconsistency between them (for example, a different occupation or "
        "source of funds) is itself a red flag and must be resolved before an alert is closed.",
    ]),
    ("4. Currency transaction reporting", [
        "4.1 Threshold. A Currency Transaction Report (CTR) is filed for each deposit, withdrawal, exchange or other "
        "payment or transfer involving more than $10,000 in currency.",
        "4.2 Aggregation. Multiple currency transactions by or on behalf of the same person on the same business day "
        "are treated as a single transaction when the Bank has knowledge of them and they total more than $10,000. "
        "Cash in and cash out are aggregated separately. Following the Pellbrook acquisition, currency transactions "
        "conducted on Core A and on Core B are known to the Bank and must be aggregated together. Until conversion, "
        "BSA Operations runs a daily cross-core cash aggregation report and files any CTR it identifies.",
        "4.3 Filing deadline. CTRs are filed electronically within 15 calendar days after the transaction.",
        "4.4 Exemptions. Exemptions are granted only through the documented exemption process and reviewed annually.",
    ]),
    ("5. Structuring", [
        "5.1 Definition. Structuring is breaking up currency transactions to evade a reporting or recordkeeping "
        "requirement. It is prohibited regardless of whether the underlying funds are legitimate.",
        "5.2 Red flags. Repeated cash deposits just below $10,000; deposits spread across branches, accounts or "
        "days; a customer asking about reporting thresholds; cash activity inconsistent with the customer profile; "
        "and cash split between Core A and Core B accounts of the same customer.",
        "5.3 Cross-core review. When a structuring alert is investigated, the investigator must review the "
        "customer's activity on both cores for the same period, using the unified customer view.",
        "5.4 Action. Suspected structuring is escalated for SAR consideration. Staff must never advise a customer "
        "how to avoid a report.",
    ]),
    ("6. Monitoring and alert handling", [
        "6.1 Triage. New alerts are triaged within 5 business days.",
        "6.2 Investigation. Investigations are completed within 30 calendar days of the alert date. Alerts open "
        "longer than 30 days are reported weekly to the BSA Officer as overdue.",
        "6.3 Documentation. Every closure records the facts reviewed, the rationale, the documents relied on and "
        "the investigator. A closure without a rationale is not permitted.",
        "6.4 Quality assurance. Ten percent of closed alerts are re-reviewed each month by a second investigator.",
        "6.5 Prioritisation. Alerts are worked in order of risk score. Scores must show the reasons that produced them.",
    ]),
    ("7. Suspicious Activity Reports", [
        "7.1 When to file. A SAR is considered for transactions that may involve money laundering, BSA violations "
        "(including structuring) or other suspicious activity, subject to the regulatory dollar thresholds.",
        "7.2 Deadline. A SAR is filed no later than 30 calendar days after initial detection of facts that may "
        "constitute a basis for filing. If no suspect is identified, filing may be delayed an additional 30 days to "
        "identify one, but never beyond 60 days after initial detection.",
        "7.3 Continuing activity. Continuing activity is reviewed at least every 90 days after a SAR is filed.",
        "7.4 Confidentiality. The existence of a SAR must never be disclosed to the subject.",
    ]),
    ("8. Dormant and inactive accounts", [
        "8.1 Definition. An account with no customer-initiated activity for 12 months is classified as dormant.",
        "8.2 Reactivation. Reactivation requires identity re-verification by the branch or contact centre.",
        "8.3 Monitoring. An inflow of $10,000 or more within 30 days of reactivation, followed by rapid withdrawal, "
        "is reviewed as potential account takeover or use of the account as a pass-through.",
    ]),
    ("9. Rapid movement of funds", [
        "When 90 percent or more of an inbound transfer of $25,000 or more leaves the account within 48 hours, with "
        "no documented business purpose, the activity is reviewed as possible pass-through or funnel activity. "
        "Investigators confirm the relationship between the customer, the originator and the beneficiaries.",
    ]),
    ("10. Recordkeeping, training and testing", [
        "10.1 Records. BSA records, including CTRs, SARs and supporting documentation, are kept for at least five years.",
        "10.2 Training. All customer-facing and operations staff complete BSA training annually; investigators "
        "complete advanced training.",
        "10.3 Independent testing. The BSA/AML program is independently tested at least every 12 to 18 months.",
    ]),
    ("Appendix A. Reporting obligations at a glance", [
        "CTR: cash over $10,000 per person per business day, aggregated across both cores; file within 15 days.",
        "SAR: within 30 days of initial detection (60 days if no suspect identified); review continuing activity every 90 days.",
        "Alert SLA: triage in 5 business days; resolve in 30 calendar days.",
        "Dormancy: 12 months without customer-initiated activity.",
    ]),
]


def write_policy_pdf(path: Path):
    """Write the fictional policy. Page footers carry page numbers for citation."""
    from reportlab import rl_config
    rl_config.invariant = 1  # reproducible bytes
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10.5, leading=14.5, spaceAfter=7)
    h1 = ParagraphStyle("h1", parent=styles["Heading2"], spaceBefore=10, spaceAfter=6)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(inch, 0.6 * inch, "Kestrel Valley Bank BSA/AML Program Policy v7.2 - FICTIONAL, SYNTHETIC DEMO DOCUMENT - not legal advice")
        canvas.drawRightString(LETTER[0] - inch, 0.6 * inch, f"Page {doc.page}")
        canvas.restoreState()

    story = [
        Paragraph("Kestrel Valley Bank", styles["Title"]),
        Paragraph("Bank Secrecy Act / Anti-Money Laundering Program Policy", styles["Heading1"]),
        Paragraph("Version 7.2 - effective 1 July 2026 - approved by the Board of Directors on 24 June 2026", body),
        Spacer(1, 12),
        Paragraph("<b>Synthetic document.</b> Kestrel Valley Bank and Pellbrook Savings Bank are fictional. This policy "
                  "was generated for a software demonstration. Regulatory references are summarised for illustration "
                  "only and are not legal advice.", body),
        Spacer(1, 18),
        Paragraph("<b>Contents</b>", body),
    ]
    for title, _ in POLICY:
        story.append(Paragraph(title, body))
    story.append(PageBreak())
    for i, (title, paras) in enumerate(POLICY):
        story.append(Paragraph(title, h1))
        for p in paras:
            story.append(Paragraph(p, body))
        if title.startswith(("3.", "5.", "7.", "9.")):
            story.append(PageBreak())
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=LETTER, title="Kestrel Valley Bank BSA/AML Policy (synthetic)",
                            author="Synthetic data generator", leftMargin=inch, rightMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def policy_page_index(path: Path, markers):
    """Return {marker: first page number containing it}, for citation answers and tests."""
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    texts = [" ".join((pg.extract_text() or "").split()) for pg in reader.pages]
    out = {}
    for m in markers:
        for n, t in enumerate(texts, start=1):
            if m in t:
                out[m] = n
                break
    return out, len(texts)
