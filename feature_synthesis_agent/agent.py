# feature_synthesis_agent/agent.py
"""
Feature Synthesis Sub-Agent
Generates PDF reports and plain-text briefings from validated feature lists.
"""

import os
from datetime import datetime
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

def _out_dir():
    d = os.environ.get("MARKET_SCOUT_OUTPUT_DIR", os.path.join(os.getcwd(), "outputs"))
    os.makedirs(d, exist_ok=True)
    return d


def generate_pdf(company: str, features: list, run_date: str) -> str:
    """
    Generates a formatted PDF competitive intelligence report.
    Returns the PDF file path, or an error string if generation fails.
    """
    if not features:
        return f"PDF_SKIPPED — no features found for {company}."

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

        version  = datetime.now().strftime("v%Y.%m.%d")
        filename = f"{company}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join(_out_dir(), filename)

        doc    = SimpleDocTemplate(
            pdf_path, pagesize=letter,
            rightMargin=0.75 * inch, leftMargin=0.75 * inch,
            topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        )
        styles   = getSampleStyleSheet()
        elements = []

        title_style = ParagraphStyle(
            "CustomTitle", parent=styles["Title"],
            fontSize=22, textColor=colors.HexColor("#1F4E79"), spaceAfter=6,
        )
        elements.append(Paragraph(f"Market Scout — {company}", title_style))
        elements.append(Paragraph(
            f"Competitive Intelligence Report | {run_date} | {version}",
            styles["Normal"],
        ))
        elements.append(Spacer(1, 0.3 * inch))

        week  = sum(1 for f in features if f.get("status") == "WEEK")
        month = sum(1 for f in features if f.get("status") in ["WEEK", "MONTH"])
        year  = sum(1 for f in features if f.get("status") in ["WEEK", "MONTH", "YEAR"])
        unver = sum(1 for f in features if f.get("status") == "UNVERIFIED")

        summary_data = [
            ["Total Features", "Last 7 Days", "Last 30 Days", "Last 365 Days", "Unverified"],
            [str(len(features)), str(week), str(month), str(year), str(unver)],
        ]
        summary_table = Table(summary_data, colWidths=[1.3 * inch] * 5)
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 10),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#DDEBF7")),
            ("FONTNAME",   (0, 1), (-1, 1), "Helvetica-Bold"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWHEIGHT",  (0, 0), (-1, -1), 25),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.3 * inch))

        elements.append(Paragraph("Feature Details", styles["Heading2"]))
        elements.append(Spacer(1, 0.1 * inch))

        feat_data = [["Feature", "Category", "Date", "Status"]]
        for f in features:
            feat_data.append([
                Paragraph(f.get("feature", ""), styles["Normal"]),
                f.get("category", ""),
                f.get("date", "unknown"),
                f.get("status", ""),
            ])

        status_colors_pdf = {
            "WEEK"      : colors.HexColor("#C6EFCE"),
            "MONTH"     : colors.HexColor("#FFEB9C"),
            "YEAR"      : colors.HexColor("#DDEBF7"),
            "UNVERIFIED": colors.HexColor("#F2F2F2"),
            "STALE"     : colors.HexColor("#FFC7CE"),
        }

        feat_table = Table(feat_data, colWidths=[3.5 * inch, 1 * inch, 1 * inch, 1 * inch])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("ALIGN",      (1, 0), (-1, -1), "CENTER"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ]
        for i, f in enumerate(features, 1):
            bg = status_colors_pdf.get(f.get("status", ""), colors.white)
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))

        feat_table.setStyle(TableStyle(style_cmds))
        elements.append(feat_table)
        elements.append(Spacer(1, 0.3 * inch))

        elements.append(Paragraph("Sources", styles["Heading2"]))
        elements.append(Spacer(1, 0.1 * inch))
        for i, f in enumerate(features, 1):
            url = f.get("url", "")
            if url:
                elements.append(Paragraph(
                    f"{i}. {f.get('feature', '')} — {url}", styles["Normal"]
                ))
                elements.append(Spacer(1, 0.05 * inch))

        doc.build(elements)
        return pdf_path

    except ImportError:
        return "PDF_FAILED — run: pip install reportlab"
    except Exception as e:
        return f"PDF_FAILED — {str(e)}"


def generate_briefing(company: str, features: list, run_date: str) -> str:
    """
    Generates a plain-text competitor briefing with citations.
    Returns the file path of the saved briefing .txt file.
    """
    if not features:
        return f"BRIEFING_SKIPPED — no features found for {company}."

    week_features = [f for f in features if f.get("status") == "WEEK"]
    all_features  = [f for f in features if f.get("status") in ["WEEK", "MONTH", "YEAR", "UNVERIFIED"]]

    briefing = f"""
{'=' * 60}
COMPETITOR BRIEFING: {company.upper()}
Generated: {run_date}
Period: Last 7 Days
{'=' * 60}

EXECUTIVE SUMMARY
─────────────────
{company} has released {len(week_features)} new technical updates
in the last 7 days. {len(all_features)} total updates tracked
across the last 365 days.

NEW TECHNICAL FEATURES (Last 7 Days)
─────────────────────────────────────
"""
    if week_features:
        for i, f in enumerate(week_features, 1):
            briefing += f"""
{i}. {f.get('feature', '')}
   Category : {f.get('category', '')}
   Published: {f.get('date', 'unknown')}
   Summary  : {f.get('snippet', '')[:200]}
   Source   : {f.get('url', '')}
"""
    else:
        briefing += "\nNo verified features in last 7 days.\n"
        briefing += "Showing most recent updates:\n"
        for i, f in enumerate(all_features[:5], 1):
            briefing += f"""
{i}. {f.get('feature', '')}
   Category : {f.get('category', '')}
   Published: {f.get('date', 'unknown')}
   Summary  : {f.get('snippet', '')[:200]}
   Source   : {f.get('url', '')}
"""

    briefing += "\nALL CITATIONS\n─────────────\n"
    for i, f in enumerate(all_features, 1):
        briefing += f"{i}. {f.get('feature', '')} — {f.get('url', '')}\n"

    briefing += f"""
{'=' * 60}
Market Scout {datetime.now().strftime('v%Y.%m.%d')} |
Google ADK + Groq LLaMA 3.3 + Tavily Search
{'=' * 60}
"""

    filename      = f"{company}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_briefing.txt"
    briefing_path = os.path.join(_out_dir(), filename)
    with open(briefing_path, "w", encoding="utf-8") as bf:
        bf.write(briefing)

    return briefing_path


pdf_tool      = FunctionTool(func=generate_pdf)
briefing_tool = FunctionTool(func=generate_briefing)

feature_synthesis_agent = LlmAgent(
    name="feature_synthesis_agent",
    model=LiteLlm(model="groq/llama-3.1-8b-instant"),
    description="Generates PDF reports and plain-text briefings from validated feature lists.",
    instruction=(
        "You are a Feature Synthesis Agent. "
        "When given a company name, feature list, and run date: "
        "1. Call generate_pdf(company, features, run_date) to produce a PDF. "
        "2. Call generate_briefing(company, features, run_date) to produce a text briefing. "
        "Return both file paths exactly as received. Do not summarise or modify them."
    ),
    tools=[pdf_tool, briefing_tool],
)