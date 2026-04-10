# app.py
"""
Market Scout — Gradio UI
Replaces Chainlit. Works reliably on Render free tier.
Run locally : python app.py
Deploy      : Render (see render.yaml)
"""

import os
import sys
import re
import asyncio
import threading
from pathlib import Path
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dotenv import load_dotenv
load_dotenv()

import gradio as gr
from market_scout_agent.agent import run_pipeline
from guardrails.callbacks import (
    HARMFUL_PATTERNS, INJECTION_PATTERNS, OUT_OF_SCOPE,
    MIN_QUERY_LEN, MAX_QUERY_LEN,
)

OUTPUT_DIR = os.environ.get(
    "MARKET_SCOUT_OUTPUT_DIR",
    os.path.join(_HERE, "outputs"),
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Company name extraction ──────────────────────────────────────────────────

_ACTION_PREFIXES = re.compile(
    r"^(track|monitor|research|analyse|analyze|check|find|get|show|give me|"
    r"look up|search for|tell me about|what about|latest features? (?:of|for)?|"
    r"(?:latest |recent )?(?:updates?|news|features?|releases?) (?:for|of|on|about)?)\s+",
    re.IGNORECASE,
)
_COMPARE_PATTERN = re.compile(r"^(?:compare|vs\.?|versus)\s+", re.IGNORECASE)
_AND_PATTERN     = re.compile(r"\s+(?:and|vs\.?|versus)\s+", re.IGNORECASE)

def _extract_companies(text: str) -> str:
    text = text.strip()
    for _ in range(3):
        new = _ACTION_PREFIXES.sub("", text).strip()
        new = _COMPARE_PATTERN.sub("", new).strip()
        if new == text:
            break
        text = new
    text = _AND_PATTERN.sub(", ", text)
    text = re.sub(
        r"\s+(?:latest|recent|new|updates?|features?|releases?|news|info|information)$",
        "", text, flags=re.IGNORECASE,
    ).strip()
    return text

# ─── Guardrail ────────────────────────────────────────────────────────────────

def _check_input(text: str) -> str | None:
    if len(text) < MIN_QUERY_LEN:
        return f"⚠️ Query too short (minimum {MIN_QUERY_LEN} characters)."
    if len(text) > MAX_QUERY_LEN:
        return f"⚠️ Query too long (maximum {MAX_QUERY_LEN} characters)."
    lower = text.lower()
    for p in HARMFUL_PATTERNS:
        if re.search(p, lower):
            return "🚫 Harmful intent detected. I can only help with competitor intelligence."
    for p in INJECTION_PATTERNS:
        if re.search(p, lower):
            return "🚫 Prompt injection attempt detected."
    for p in OUT_OF_SCOPE:
        if re.search(p, lower):
            return "ℹ️ I only track competitor updates. Try: 'Track Stripe'."
    return None

# ─── Main handler ─────────────────────────────────────────────────────────────

def handle_query(user_input: str):
    """
    Yields incremental status updates, then returns:
      (markdown_report, pdf_path, excel_path, briefing_path, dashboard_path)
    """
    text = user_input.strip()

    GREETING_TRIGGERS = {"hi","hello","hey","greetings","good morning",
                         "good afternoon","good evening","howdy","sup","yo"}
    if text.lower() in GREETING_TRIGGERS:
        yield (
            "👋 Hello! Type a company name to get started.\n\n"
            "Examples: `Stripe` · `Track Tesla` · `Compare PayPal and Stripe`",
            None, None, None, None
        )
        return

    block = _check_input(text)
    if block:
        yield (block, None, None, None, None)
        return

    query = _extract_companies(text)
    if not query:
        yield ("Please enter a company name. Example: `Stripe`", None, None, None, None)
        return

    yield (f"🔎 Searching for **{query}** — this may take 20–40 seconds…", None, None, None, None)

    try:
        result = run_pipeline(query)
    except Exception as exc:
        yield (
            f"❌ **Pipeline error:** `{str(exc)}`\n\n"
            "Check that **TAVILY_API_KEY** and **GROQ_API_KEY** are set in "
            "Render → Environment.",
            None, None, None, None
        )
        return

    summary          = result.get("summary", {})
    top_features     = result.get("top_features", [])
    files            = result.get("files", {})
    comparison_table = result.get("comparison_table", "")

    # ── Features section ──
    if top_features:
        features_md = ""
        for i, f in enumerate(top_features, 1):
            url_md = f"\n  - 🔗 [Source]({f['url']})" if f.get("url") else ""
            features_md += (
                f"**{i}. {f['feature']}**  \n"
                f"  `{f['category']}` · {f['date']} · **{f['status']}**"
                f"{url_md}\n\n"
            )
    else:
        features_md = (
            "> ⚠️ No features found. This usually means **TAVILY_API_KEY** "
            "is not set in Render → Environment → add it and redeploy.\n"
        )

    comparison_md = ""
    if comparison_table:
        comparison_md = f"\n### ⚖️ Company Comparison\n\n{comparison_table}\n"

    report = f"""## 📊 Market Scout Report
**Company:** {result['company']} &nbsp;|&nbsp; **Run Date:** {result['run_date']} &nbsp;|&nbsp; **Version:** {result['version']}

---

### 📈 Findings Summary

| Timeframe | Count | Status |
|:----------|------:|:-------|
| Total Features | {summary.get('total', 0)} | — |
| Last 7 Days | {summary.get('week', 0)} | 🟢 WEEK |
| Last 30 Days | {summary.get('month', 0)} | 🟡 MONTH |
| Last 365 Days | {summary.get('year', 0)} | 🔵 YEAR |
| Unverified | {summary.get('unver', 0)} | ⚪ Unknown |

---

### 🔑 Top Features

{features_md}{comparison_md}
---

*Powered by Google ADK · Groq LLaMA 3.3 · Tavily Search*
"""

    # Resolve file paths — return None if file doesn't exist (Gradio skips None)
    def _path(key):
        p = files.get(key, "")
        return p if p and Path(p).exists() else None

    yield (report, _path("pdf"), _path("excel"), _path("briefing"), _path("dashboard"))


# ─── Gradio UI ────────────────────────────────────────────────────────────────

EXAMPLES = [
    ["Stripe"],
    ["Track Tesla"],
    ["Compare PayPal and Stripe"],
    ["Nike latest features"],
    ["OpenAI"],
]

CSS = """
#header { text-align: center; padding: 20px 0 10px; }
#header h1 { font-size: 2rem; color: #1F4E79; }
#header p  { color: #666; font-size: 0.95rem; }
.report-box { font-size: 0.95rem; }
footer { display: none !important; }
"""

with gr.Blocks(
    title="Market Scout — Competitive Intelligence",
    theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
    css=CSS,
) as demo:

    gr.HTML("""
    <div id="header">
      <h1>🔍 Market Scout</h1>
      <p>AI-powered Competitive Intelligence &nbsp;·&nbsp;
         Google ADK &nbsp;·&nbsp; Groq LLaMA 3.3 &nbsp;·&nbsp; Tavily Search</p>
    </div>
    """)

    with gr.Row():
        with gr.Column(scale=3):
            user_input = gr.Textbox(
                label="Company or query",
                placeholder="e.g.  Stripe   |   Track Tesla   |   Compare PayPal and Stripe",
                lines=1,
                autofocus=True,
            )
            run_btn = gr.Button("🚀 Run Analysis", variant="primary", size="lg")

        with gr.Column(scale=1):
            gr.Markdown("""
**Quick examples:**
- `Stripe`
- `Track Tesla`
- `Compare PayPal and Stripe`
- `Nike latest features`
- `OpenAI, Anthropic`
            """)

    report_out = gr.Markdown(
        value="*Enter a company name above and click Run Analysis.*",
        label="Report",
        elem_classes=["report-box"],
    )

    gr.Markdown("### 📎 Download Reports")
    with gr.Row():
        pdf_out      = gr.File(label="📄 PDF Report",      visible=True, interactive=False)
        excel_out    = gr.File(label="📊 Excel Workbook",  visible=True, interactive=False)
        briefing_out = gr.File(label="📝 Text Briefing",   visible=True, interactive=False)
        dashboard_out= gr.File(label="🌐 HTML Dashboard",  visible=True, interactive=False)

    gr.Examples(
        examples=EXAMPLES,
        inputs=user_input,
        label="Example queries",
    )

    # Wire up button and Enter key
    run_btn.click(
        fn=handle_query,
        inputs=user_input,
        outputs=[report_out, pdf_out, excel_out, briefing_out, dashboard_out],
    )
    user_input.submit(
        fn=handle_query,
        inputs=user_input,
        outputs=[report_out, pdf_out, excel_out, briefing_out, dashboard_out],
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
    )