from __future__ import annotations

from html import escape
from io import BytesIO

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def markdown_to_pdf(markdown: str, title: str) -> bytes:
    buffer = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ChineseBody",
        parent=styles["BodyText"],
        fontName="STSong-Light",
        fontSize=10.5,
        leading=17,
        spaceAfter=6,
    )
    heading = ParagraphStyle(
        "ChineseHeading",
        parent=body,
        fontSize=16,
        leading=23,
        spaceBefore=10,
        spaceAfter=8,
    )
    title_style = ParagraphStyle(
        "ChineseTitle",
        parent=heading,
        fontSize=20,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=16,
    )
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    story = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue
        if line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), title_style))
        elif line.startswith("## "):
            story.append(Paragraph(escape(line[3:]), heading))
        elif line.startswith("### "):
            story.append(Paragraph(escape(line[4:]), body))
        elif line.startswith("> "):
            story.append(Paragraph(f"<i>{escape(line[2:])}</i>", body))
        elif line.startswith("- "):
            story.append(Paragraph(f"• {escape(line[2:])}", body))
        else:
            story.append(Paragraph(escape(line), body))
    document.build(story)
    return buffer.getvalue()
