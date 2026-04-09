# app.py
"""
Market Scout — Chainlit UI
Drop-in replacement for `adk web market_scout_agent`.
Run locally : chainlit run app.py
Deploy      : Render (see Procfile / render.yaml)
"""

import os
import sys
import asyncio
from pathlib import Path

# ── Resolve project root so sub-packages import cleanly ──
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import chainlit as cl
from dotenv import load_dotenv

load_dotenv()

from market_scout_agent.agent import run_pipeline
from guardrails.callbacks import (
    HARMFUL_PATTERNS,
    INJECTION_PATTERNS,
    OUT_OF_SCOPE,
    MIN_QUERY_LEN,
    MAX_QUERY_LEN,
)
import re

OUTPUT_DIR = os.environ.get(
    "MARKET_SCOUT_OUTPUT_DIR",
    os.path.join(_HERE, "outputs"),
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─── Guardrail check ──────────────────────────────────────────────────────────

def _check_input(text: str) -> str | None:
    """Returns an error string if the input should be blocked, else None."""
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


# ─── Greeting ─────────────────────────────────────────────────────────────────

WELCOME = """\
# 🔍 Welcome to Market Scout!
**Your AI-powered Competitive Intelligence Assistant.**

Here's what I can do:

| Capability | Description |
|---|---|
| 🏢 Track a company | Latest features, API updates, releases |
| 📅 Recency labels | WEEK / MONTH / YEAR / STALE / UNVERIFIED |
| 📊 Excel report | Colour-coded workbook with charts |
| 📄 PDF report | Per-run formatted PDF |
| 🌐 HTML dashboard | Persistent dashboard across all runs |
| ⚖️ Compare companies | Side-by-side summary table |

**To get started, just type a company name:**
- `Track Stripe`
- `Tesla latest features`
- `Compare PayPal and Stripe`
"""

GREETING_TRIGGERS = {
    "hi", "hello", "hey", "greetings", "good morning",
    "good afternoon", "good evening", "howdy", "sup", "yo",
}


def _is_greeting(text: str) -> bool:
    return text.strip().lower() in GREETING_TRIGGERS


# ─── Chainlit lifecycle ───────────────────────────────────────────────────────

@cl.on_chat_start
async def on_start():
    await cl.Message(content=WELCOME).send()


@cl.on_message
async def on_message(message: cl.Message):
    text = message.content.strip()

    if _is_greeting(text):
        await cl.Message(content=WELCOME).send()
        return

    block = _check_input(text)
    if block:
        await cl.Message(content=block).send()
        return

    async with cl.Step(name="Market Scout Pipeline", show_input=False) as step:
        step.output = "🔎 Searching the web and processing…"

        try:
            # asyncio.to_thread is safe in Python 3.9+ and works correctly
            # with Chainlit's ASGI context — avoids NoEventLoopError
            result = await asyncio.to_thread(run_pipeline, text)
        except Exception as exc:
            await cl.Message(
                content=f"❌ Pipeline error: {str(exc)}\n\nPlease check your API keys in the Render dashboard → Environment."
            ).send()
            return

    summary          = result.get("summary", {})
    top_features     = result.get("top_features", [])
    files            = result.get("files", {})
    comparison_table = result.get("comparison_table", "")

    if top_features:
        features_md = ""
        for i, f in enumerate(top_features, 1):
            url_line = f"  - Source: {f['url']}\n" if f.get("url") else ""
            features_md += (
                f"**{i}. {f['feature']}**\n"
                f"  - Category: `{f['category']}`  |  Date: {f['date']}  |  Status: `{f['status']}`\n"
                f"{url_line}\n"
            )
    else:
        features_md = "_No features found for this company._\n"

    comparison_md = ""
    if comparison_table:
        comparison_md = f"\n### ⚖️ Company Comparison\n\n{comparison_table}\n"

    report = f"""\
## 📊 Market Scout Report
**Company:** {result['company']}  
**Run Date:** {result['run_date']}  |  **Version:** {result['version']}

---

### Findings Summary

| Timeframe | Count | Status |
|-----------|------:|--------|
| Total Features | {summary.get('total', 0)} | — |
| Last 7 Days | {summary.get('week', 0)} | 🟢 WEEK |
| Last 30 Days | {summary.get('month', 0)} | 🟡 MONTH |
| Last 365 Days | {summary.get('year', 0)} | 🔵 YEAR |
| Unverified | {summary.get('unver', 0)} | ⚪ Unknown |

---

### 🔑 Top Features Found

{features_md}{comparison_md}
---

### 📁 Reports Generated

| File | Path |
|------|------|
| 🌐 Dashboard (HTML) | `{files.get('dashboard', 'N/A')}` |
| 📊 Excel with Charts | `{files.get('excel', 'N/A')}` |
| 📄 PDF Report | `{files.get('pdf', 'N/A')}` |
| 📝 Text Briefing | `{files.get('briefing', 'N/A')}` |

---
*Powered by Google ADK · Groq LLaMA 3.3 · Tavily Search*
"""

    await cl.Message(content=report).send()

    attachments = []
    for path_str in [
        files.get("pdf", ""),
        files.get("briefing", ""),
        files.get("excel", ""),
    ]:
        if path_str and Path(path_str).exists():
            attachments.append(
                cl.File(name=Path(path_str).name, path=path_str, display="inline")
            )

    if attachments:
        await cl.Message(
            content="📎 **Download your reports:**",
            elements=attachments,
        ).send()