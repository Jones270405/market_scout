# market_scout_agent/agent.py
"""
Market Scout — Root Agent
ADK requires this file to expose a variable named exactly `root_agent`.
"""

import os
import sys
import json
from datetime import datetime, timedelta

_HERE         = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

from guardrails.callbacks import input_guardrail, output_guardrail
from web_retrieval_agent.agent import get_search_results
from content_extraction_agent.agent import extract_features
from temporal_validation_agent.agent import validate_by_timeframe
from feature_synthesis_agent.agent import generate_pdf, generate_briefing
from comparison_report_agent.agent import update_excel

def _out_dir() -> str:
    """Resolve output dir at call time so env var changes are always honoured."""
    d = os.environ.get("MARKET_SCOUT_OUTPUT_DIR", os.path.join(_PROJECT_ROOT, "outputs"))
    os.makedirs(d, exist_ok=True)
    return d

def _dashboard_file() -> str: return os.path.join(_out_dir(), "market_scout_dashboard.html")
def _history_file()   -> str: return os.path.join(_out_dir(), "market_scout_history.json")


# ─── History helpers ──────────────────────────────────────────────────────────

def _revalidate_history(history: list) -> list:
    """
    Re-run date validation on any feature that still has a raw Tavily date
    string (e.g. 'Thu, 02 May 2024 00:00:00 GMT') so old saved runs display
    correctly after the temporal-validation fix.
    """
    from temporal_validation_agent.agent import validate_by_timeframe
    for run in history:
        features = run.get("features", [])
        if features:
            run["features"] = validate_by_timeframe(features)
            # Recompute summary counts
            week  = sum(1 for f in features if f.get("status") == "WEEK")
            month = sum(1 for f in features if f.get("status") in ["WEEK", "MONTH"])
            year  = sum(1 for f in features if f.get("status") in ["WEEK", "MONTH", "YEAR"])
            unver = sum(1 for f in features if f.get("status") == "UNVERIFIED")
            run["summary"] = {
                "total": len(features),
                "week" : week,
                "month": month,
                "year" : year,
                "unver": unver,
            }
    return history


def load_history() -> list:
    if os.path.exists(_history_file()):
        try:
            with open(_history_file(), "r") as f:
                history = json.load(f)
            revalidated = _revalidate_history(history)
            # Save back so fixes persist across restarts
            save_history(revalidated)
            return revalidated
        except Exception:
            return []
    return []


def save_history(history: list) -> None:
    with open(_history_file(), "w") as f:
        json.dump(history, f, indent=2)


# ─── Dashboard builder ────────────────────────────────────────────────────────

def update_dashboard(all_runs: list) -> None:
    """Regenerates the persistent HTML dashboard from full run history."""
    version       = datetime.now().strftime("v%Y.%m.%d")
    timeline_html = ""

    status_colors = {
        "WEEK"      : "#C6EFCE",
        "MONTH"     : "#FFEB9C",
        "YEAR"      : "#DDEBF7",
        "UNVERIFIED": "#F2F2F2",
        "STALE"     : "#FFC7CE",
    }

    for run in reversed(all_runs):
        features  = run.get("features", [])
        company   = run.get("company", "")
        run_date  = run.get("run_date", "")
        week_cnt  = sum(1 for f in features if f.get("status") == "WEEK")
        month_cnt = sum(1 for f in features if f.get("status") in ["WEEK", "MONTH"])
        year_cnt  = sum(1 for f in features if f.get("status") in ["WEEK", "MONTH", "YEAR"])
        unver_cnt = sum(1 for f in features if f.get("status") == "UNVERIFIED")

        feature_rows = ""
        for f in features:
            bg   = status_colors.get(f.get("status", ""), "#FFFFFF")
            url  = f.get("url", "")
            link = f'<a href="{url}" target="_blank">View Source</a>' if url else "N/A"
            feature_rows += (
                f"<tr style='background:{bg}'>"
                f"<td>{f.get('feature','')}</td>"
                f"<td><span class='badge'>{f.get('category','')}</span></td>"
                f"<td>{f.get('date','unknown')}</td>"
                f"<td><strong>{f.get('status','')}</strong></td>"
                f"<td>{link}</td>"
                f"</tr>"
            )

        no_data = "<tr><td colspan='5' style='text-align:center;color:#888'>No features found</td></tr>"
        timeline_html += (
            f"<div class='run-card'>"
            f"<div class='run-header'>"
            f"<div><span class='company-tag'>{company}</span>"
            f"<span class='run-date'>&#128197; {run_date}</span></div>"
            f"<div class='run-stats'>"
            f"<span class='stat green'>7d: {week_cnt}</span>"
            f"<span class='stat orange'>30d: {month_cnt}</span>"
            f"<span class='stat blue'>365d: {year_cnt}</span>"
            f"<span class='stat grey'>Unverified: {unver_cnt}</span>"
            f"</div></div>"
            f"<table><tr><th>Feature</th><th>Category</th><th>Date</th><th>Status</th><th>Source</th></tr>"
            f"{feature_rows if feature_rows else no_data}"
            f"</table></div>"
        )

    total_runs     = len(all_runs)
    total_features = sum(len(r.get("features", [])) for r in all_runs)
    companies      = list(set(r.get("company", "") for r in all_runs))
    from datetime import timezone as _tz2
    _tz_off = int(os.environ.get("DISPLAY_TZ_OFFSET_HOURS", "5"))
    _tz_min = int(os.environ.get("DISPLAY_TZ_OFFSET_MINS", "30"))
    _tz_lbl = os.environ.get("DISPLAY_TZ_LABEL", "IST")
    _disp_tz = _tz2(timedelta(hours=_tz_off, minutes=_tz_min))
    now_str  = datetime.now(_tz2.utc).astimezone(_disp_tz).strftime(f"%B %d, %Y at %H:%M {_tz_lbl}")

    css = """<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#f0f4f8;color:#333}
.header{background:linear-gradient(135deg,#1F4E79,#2E86AB);color:white;padding:30px 40px}
.header h1{font-size:28px;margin-bottom:5px}
.header p{opacity:.8;font-size:14px}
.container{max-width:1400px;margin:30px auto;padding:0 20px}
.overview{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:30px}
.overview-card{background:white;border-radius:12px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.overview-card .number{font-size:36px;font-weight:bold;color:#1F4E79}
.overview-card .label{font-size:13px;color:#888;margin-top:5px}
.legend{background:white;border-radius:12px;padding:15px 25px;margin-bottom:25px;
box-shadow:0 2px 8px rgba(0,0,0,.08);display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.legend-item{display:flex;align-items:center;gap:8px;font-size:13px}
.legend-dot{width:14px;height:14px;border-radius:3px}
.run-card{background:white;border-radius:12px;padding:25px;margin-bottom:25px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.run-header{display:flex;justify-content:space-between;align-items:center;
margin-bottom:15px;padding-bottom:15px;border-bottom:2px solid #f0f0f0}
.company-tag{background:#1F4E79;color:white;padding:5px 15px;border-radius:20px;
font-weight:bold;font-size:16px;margin-right:10px}
.run-date{color:#888;font-size:14px}
.run-stats{display:flex;gap:10px}
.stat{padding:4px 12px;border-radius:20px;font-size:13px;font-weight:bold}
.stat.green{background:#C6EFCE;color:#2E7D32}
.stat.orange{background:#FFEB9C;color:#E65100}
.stat.blue{background:#DDEBF7;color:#1565C0}
.stat.grey{background:#F2F2F2;color:#666}
table{width:100%;border-collapse:collapse;font-size:14px}
th{background:#1F4E79;color:white;padding:10px 12px;text-align:left}
td{padding:10px 12px;border-bottom:1px solid #f0f0f0}
td a{color:#2E86AB;text-decoration:none}
td a:hover{text-decoration:underline}
.badge{background:#e8f0fe;color:#1F4E79;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:bold}
.version{text-align:right;font-size:12px;color:#aaa;margin-top:20px;margin-bottom:20px}
.section-title{font-size:20px;font-weight:bold;color:#1F4E79;margin-bottom:20px;
border-left:4px solid #2E86AB;padding-left:15px}
@media(max-width:768px){
.overview{grid-template-columns:1fr}
.run-header{flex-direction:column;gap:10px;align-items:flex-start}
.run-stats{flex-wrap:wrap}
.header{padding:20px}
}
</style>"""

    no_runs_msg = "<div style='text-align:center;padding:40px;color:#888'>No runs yet</div>"

    html = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>Market Scout Dashboard</title>
{css}
</head>
<body>
<div class='header'>
  <h1>Market Scout — Intelligence Dashboard</h1>
  <p>Live Competitive Intelligence | Last updated: {now_str} | {version}</p>
</div>
<div class='container'>
  <div class='overview' style='margin-top:25px'>
    <div class='overview-card'><div class='number'>{total_runs}</div><div class='label'>Total Runs</div></div>
    <div class='overview-card'><div class='number'>{total_features}</div><div class='label'>Total Features Tracked</div></div>
    <div class='overview-card'><div class='number'>{len(companies)}</div><div class='label'>Companies Tracked</div></div>
  </div>
  <div class='legend'>
    <strong>Status Legend:</strong>
    <div class='legend-item'><div class='legend-dot' style='background:#C6EFCE'></div>WEEK — Last 7 days</div>
    <div class='legend-item'><div class='legend-dot' style='background:#FFEB9C'></div>MONTH — Last 30 days</div>
    <div class='legend-item'><div class='legend-dot' style='background:#DDEBF7'></div>YEAR — Last 365 days</div>
    <div class='legend-item'><div class='legend-dot' style='background:#F2F2F2'></div>UNVERIFIED — Date unknown</div>
    <div class='legend-item'><div class='legend-dot' style='background:#FFC7CE'></div>STALE — Older than 1 year</div>
  </div>
  <div class='section-title'>Run History (Latest First)</div>
  {timeline_html if timeline_html else no_runs_msg}
  <div class='version'>Market Scout {version} | Google ADK + Groq LLaMA 3.3 | Chainlit UI</div>
</div>
</body>
</html>"""

    with open(_dashboard_file(), "w", encoding="utf-8") as fh:
        fh.write(html)


# ─── Main pipeline ────────────────────────────────────────────────────────────

def run_pipeline(query: str) -> dict:
    """
    Track competitor features and news for one or more companies.

    Args:
        query: A company name like 'Stripe', or multiple companies
               comma-separated like 'Stripe, PayPal'.

    Returns:
        A dictionary with company, run_date, version, summary counts,
        top_features list, file paths, and optional comparison table.
    """
    companies = [c.strip() for c in query.split(",") if c.strip()]
    history   = load_history()
    # Display time in configured timezone (default UTC+5:30 for IST)
    from datetime import timezone as _tz
    tz_offset = int(os.environ.get("DISPLAY_TZ_OFFSET_HOURS", "5"))
    tz_mins   = int(os.environ.get("DISPLAY_TZ_OFFSET_MINS", "30"))
    tz_label  = os.environ.get("DISPLAY_TZ_LABEL", "IST")
    display_tz = _tz(timedelta(hours=tz_offset, minutes=tz_mins))
    now        = datetime.now(_tz.utc).astimezone(display_tz)
    run_date   = now.strftime(f"%Y-%m-%d %H:%M {tz_label}")
    version    = now.strftime("v%Y.%m.%d")
    pdf_files = []
    new_runs  = []

    for company in companies:
        raw      = get_search_results(company)
        features = extract_features(raw)
        features = validate_by_timeframe(features)

        week  = sum(1 for f in features if f.get("status") == "WEEK")
        month = sum(1 for f in features if f.get("status") in ["WEEK", "MONTH"])
        year  = sum(1 for f in features if f.get("status") in ["WEEK", "MONTH", "YEAR"])
        unver = sum(1 for f in features if f.get("status") == "UNVERIFIED")

        pdf_path      = generate_pdf(company, features, run_date)
        briefing_path = generate_briefing(company, features, run_date)
        pdf_files.append(pdf_path)
        pdf_files.append(briefing_path)

        run_record = {
            "company" : company,
            "run_date": run_date,
            "features": features,
            "summary" : {
                "total": len(features),
                "week" : week,
                "month": month,
                "year" : year,
                "unver": unver,
            },
        }
        history.append(run_record)
        new_runs.append(run_record)

    save_history(history)
    update_dashboard(history)
    excel_path = update_excel(history)

    last_run      = new_runs[-1]
    last_company  = last_run["company"]
    last_features = last_run["features"]
    last_summary  = last_run["summary"]

    top_features = [
        {
            "feature" : f.get("feature", ""),
            "category": f.get("category", ""),
            "date"    : f.get("date", "unknown"),
            "status"  : f.get("status", ""),
            "url"     : f.get("url", ""),
        }
        for f in last_features
        if f.get("status") in ["WEEK", "MONTH", "YEAR", "UNVERIFIED"]
    ][:5]

    pdf_file   = next((p for p in pdf_files if str(p).endswith(".pdf")), None)
    brief_file = next((p for p in pdf_files if str(p).endswith("_briefing.txt")), None)

    # Build comparison table when multiple companies were requested
    comparison_table = ""
    if len(new_runs) > 1:
        from comparison_report_agent.agent import build_comparison_table
        comparison_table = build_comparison_table(new_runs)

    return {
        "company"         : last_company,
        "all_companies"   : [r["company"] for r in new_runs],
        "run_date"        : run_date,
        "version"         : version,
        "summary"         : last_summary,
        "top_features"    : top_features,
        "comparison_table": comparison_table,
        "files": {
            "dashboard": _dashboard_file(),
            "excel"    : str(excel_path),
            "pdf"      : str(pdf_file)   if pdf_file   else "Not generated",
            "briefing" : str(brief_file) if brief_file else "Not generated",
        },
    }


# ─── Tool + Root Agent ────────────────────────────────────────────────────────

pipeline_tool = FunctionTool(func=run_pipeline)

_INSTRUCTION = (
    "You are Market Scout, a Competitive Intelligence Assistant built on Google ADK.\n\n"

    "GREETING BEHAVIOUR:\n"
    "When the user sends their very first message, or says hello, hi, hey, greetings,\n"
    "good morning, good afternoon, good evening, or any casual greeting, you MUST respond\n"
    "with a warm welcome message in this exact format before doing anything else:\n\n"
    "---\n"
    "Welcome to Market Scout! Your AI-powered Competitive Intelligence Assistant.\n\n"
    "Here is what I can do for you:\n\n"
    "1. Track Competitor Features\n"
    "   Search the web for the latest product releases, API updates, integrations,\n"
    "   and announcements from any company you want to monitor.\n\n"
    "2. Validate Recency\n"
    "   Every result is date-stamped and classified by how recent it is:\n"
    "   - WEEK   : published in the last 7 days\n"
    "   - MONTH  : published in the last 30 days\n"
    "   - YEAR   : published in the last 365 days\n"
    "   - STALE  : older than 1 year\n"
    "   - UNVERIFIED : date could not be determined\n\n"
    "3. Generate Reports\n"
    "   After every run I automatically create:\n"
    "   - A live HTML Dashboard showing all your past runs\n"
    "   - A colour-coded Excel workbook with charts\n"
    "   - A formatted PDF report for the current run\n"
    "   - A plain-text briefing with full citations\n\n"
    "4. Compare Multiple Companies\n"
    "   Track two or more competitors in one go.\n\n"
    "To get started, just tell me a company name:\n"
    "   'Track Stripe'   or   'Tesla latest features'   or   'Compare PayPal and Stripe'\n"
    "---\n\n"

    "WHEN TO CALL run_pipeline:\n"
    "Call it whenever the user mentions a company name or asks to track, monitor,\n"
    "or get updates for any company. Do NOT call it for greetings.\n\n"

    "HOW TO CALL run_pipeline:\n"
    "Single company   : query='Stripe'\n"
    "Multiple companies: query='Stripe, PayPal'\n\n"

    "AFTER the tool returns, write a full markdown report using these exact fields:\n\n"
    "## Market Scout Report\n"
    "**Company:** [company]\n"
    "**Run Date:** [run_date] | **Version:** [version]\n\n"
    "---\n\n"
    "### Findings Summary\n"
    "| Timeframe | Count | Status |\n"
    "|-----------|-------|--------|\n"
    "| Total Features | [summary.total] | - |\n"
    "| Last 7 Days | [summary.week] | WEEK |\n"
    "| Last 30 Days | [summary.month] | MONTH |\n"
    "| Last 365 Days | [summary.year] | YEAR |\n"
    "| Unverified | [summary.unver] | Unknown Date |\n\n"
    "---\n\n"
    "### Top Features Found\n"
    "For each item in top_features write:\n"
    "**N. [feature name]**\n"
    "- Category: [category]\n"
    "- Date: [date]\n"
    "- Status: [status]\n"
    "- Source: [url]\n\n"
    "If top_features is empty write: No features found for this company.\n\n"
    "If comparison_table is non-empty, add:\n"
    "### Company Comparison\n"
    "[comparison_table]\n\n"
    "---\n\n"
    "### Reports Generated\n"
    "| File | Path |\n"
    "|------|------|\n"
    "| Dashboard (HTML) | [files.dashboard] |\n"
    "| Excel with Charts | [files.excel] |\n"
    "| PDF Report | [files.pdf] |\n"
    "| Text Briefing | [files.briefing] |\n\n"
    "---\n"
    "Powered by Google ADK, Groq LLaMA 3.3, and Tavily Search.\n\n"

    "STRICT RULES:\n"
    "- Always call run_pipeline first when given a company name.\n"
    "- Always write the full markdown report after the tool returns.\n"
    "- Never output a blank or raw-dict response.\n"
    "- Harmful requests: reply 'I can only help with competitor intelligence.'\n"
    "- Off-topic: reply 'I only track competitor updates.'\n"
)

root_agent = LlmAgent(
    name="market_scout_agent",
    model=LiteLlm(model="groq/llama-3.3-70b-versatile"),
    description=(
        "Market Scout — Competitive Intelligence System. "
        "Tracks competitor features with persistent dashboard, Excel, and PDF reports."
    ),
    instruction=_INSTRUCTION,
    tools=[pipeline_tool],
    before_model_callback=input_guardrail,
    after_model_callback=output_guardrail,
)