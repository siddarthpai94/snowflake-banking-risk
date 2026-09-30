"""Export a case output (Markdown from outputs/narrative.py) to PDF. Unapproved outputs carry a DRAFT watermark.

Handles the small Markdown subset the narrative uses: # and ## headings, - bullets, **bold**, | tables |, ---.
"""
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _inline(text):
    t = escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)


def export_pdf(markdown, path, status="DRAFT", footer=""):
    styles = getSampleStyleSheet()
    body, small = styles["BodyText"], styles["BodyText"].clone("small", fontSize=7.5, leading=9)
    flow, table_rows = [], []

    def flush_table():
        if not table_rows:
            return
        data = [[Paragraph(_inline(c), small) for c in r] for r in table_rows if not re.fullmatch(r"[\s|:-]+", "|".join(r))]
        t = Table(data, repeatRows=1, colWidths=[30 * mm, 14 * mm, 20 * mm, 20 * mm, 32 * mm, 52 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        flow.append(t)
        flow.append(Spacer(1, 4))
        table_rows.clear()

    for line in markdown.splitlines():
        if line.startswith("|"):
            table_rows.append([c.strip() for c in line.strip().strip("|").split("|")])
            continue
        flush_table()
        if line.startswith("# "):
            flow.append(Paragraph(_inline(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            flow.append(Paragraph(_inline(line[3:]), styles["Heading2"]))
        elif line.startswith("- "):
            flow.append(Paragraph("&bull; " + _inline(line[2:]), body))
        elif line.strip() == "---":
            flow.append(Spacer(1, 6))
        elif line.strip():
            flow.append(Paragraph(_inline(line), body))
    flush_table()

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(15 * mm, 10 * mm, (footer or "")[:150])
        canvas.drawRightString(195 * mm, 10 * mm, f"Page {doc.page}")
        if status != "APPROVED":
            canvas.setFont("Helvetica-Bold", 46)
            canvas.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.15))
            canvas.translate(105 * mm, 150 * mm)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "DRAFT - NOT APPROVED")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=18 * mm, title="Case narrative", author="Risk Copilot")
    doc.build(flow, onFirstPage=decorate, onLaterPages=decorate)
    return path
