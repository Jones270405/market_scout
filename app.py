# app.py — Market Scout · Gradio 6.x compatible dark chat UI
import os, sys, re
from pathlib import Path

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

OUTPUT_DIR = os.environ.get("MARKET_SCOUT_OUTPUT_DIR", os.path.join(_HERE, "outputs"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────

_ACTION_PREFIXES = re.compile(
    r"^(track|monitor|research|analyse|analyze|check|find|get|show|give me|"
    r"look up|search for|tell me about|what about|latest features? (?:of|for)?|"
    r"(?:latest |recent )?(?:updates?|news|features?|releases?) (?:for|of|on|about)?)\s+",
    re.IGNORECASE,
)
_COMPARE_PATTERN = re.compile(r"^(?:compare|vs\.?|versus)\s+", re.IGNORECASE)
_AND_PATTERN     = re.compile(r"\s+(?:and|vs\.?|versus)\s+", re.IGNORECASE)

def _extract_companies(text):
    text = text.strip()
    for _ in range(3):
        new = _ACTION_PREFIXES.sub("", text).strip()
        new = _COMPARE_PATTERN.sub("", new).strip()
        if new == text: break
        text = new
    text = _AND_PATTERN.sub(", ", text)
    text = re.sub(
        r"\s+(?:latest|recent|new|updates?|features?|releases?|news|info|information)$",
        "", text, flags=re.IGNORECASE).strip()
    return text

def _check_input(text):
    if len(text) < MIN_QUERY_LEN: return f"⚠️ Query too short (min {MIN_QUERY_LEN} chars)."
    if len(text) > MAX_QUERY_LEN: return f"⚠️ Query too long (max {MAX_QUERY_LEN} chars)."
    lower = text.lower()
    for p in HARMFUL_PATTERNS:
        if re.search(p, lower): return "🚫 Harmful intent detected. I only help with competitor intelligence."
    for p in INJECTION_PATTERNS:
        if re.search(p, lower): return "🚫 Prompt injection detected."
    for p in OUT_OF_SCOPE:
        if re.search(p, lower): return "ℹ️ I only track competitor updates. Try: `Track Stripe`"
    return None

GREETINGS = {"hi","hello","hey","greetings","good morning","good afternoon","good evening","howdy","sup","yo"}

WELCOME_MSG = """👋 **Welcome to Market Scout — Competitive Intelligence Assistant!**

I help you track and analyse competitor product updates in real time.

**Here's what you can ask me:**

| Example Query | What happens |
|:---|:---|
| `Track Stripe` | Full intelligence run for Stripe |
| `What's new at Tesla?` | Latest feature updates for Tesla |
| `Compare Stripe and PayPal` | Side-by-side analysis of both |
| `Nike latest features` | Recent product moves by Nike |
| `OpenAI, Anthropic` | Track multiple companies at once |

After each run I generate a **PDF report**, **Excel workbook**, **text briefing**, and an **HTML dashboard** — all downloadable below the chat.

*Type a company name below or click an example to get started.*"""

# Gradio 6.x message format: list of dicts with role/content
def _bot_msg(content): return {"role": "assistant", "content": content}
def _user_msg(content): return {"role": "user",      "content": content}

INITIAL_HISTORY = [_bot_msg(WELCOME_MSG)]

# ─── Chat handler ─────────────────────────────────────────────────────────────

def respond(message, history):
    """Yields (history, files_dict) — Gradio 6.x dict message format."""
    text = message.strip()
    history = list(history) if history else []

    if text.lower() in GREETINGS:
        history.append(_user_msg(text))
        history.append(_bot_msg("👋 Hello! Type a company name to get started, e.g. `Track Stripe`."))
        yield history, {}, gr.update(value="")
        return

    block = _check_input(text)
    if block:
        history.append(_user_msg(text))
        history.append(_bot_msg(block))
        yield history, {}, gr.update(value="")
        return

    query = _extract_companies(text)
    if not query:
        history.append(_user_msg(text))
        history.append(_bot_msg("Please enter a company name. Example: `Stripe`"))
        yield history, {}, gr.update(value="")
        return

    # Show thinking message
    history.append(_user_msg(text))
    history.append(_bot_msg(f"🔎 Analysing **{query}** — please wait 20–40 seconds…"))
    yield history, {}, gr.update(value="")

    try:
        result = run_pipeline(query)
    except Exception as exc:
        history[-1] = _bot_msg(
            f"❌ **Pipeline error:** `{str(exc)}`\n\n"
            "Ensure **TAVILY_API_KEY** and **GROQ_API_KEY** are set in Render → Environment."
        )
        yield history, {}, gr.update(value="")
        return

    summary          = result.get("summary", {})
    top_features     = result.get("top_features", [])
    files            = result.get("files", {})
    comparison_table = result.get("comparison_table", "")

    status_icons = {"WEEK":"🟢","MONTH":"🟡","YEAR":"🔵","UNVERIFIED":"⚪","STALE":"🔴"}

    if top_features:
        features_md = ""
        for i, f in enumerate(top_features, 1):
            icon   = status_icons.get(f.get("status",""), "⚪")
            url_md = f" · [🔗 Source]({f['url']})" if f.get("url") else ""
            features_md += (
                f"**{i}. {f['feature']}**  \n"
                f"&nbsp;&nbsp;`{f.get('category','—')}` · "
                f"{f.get('date','unknown')} · "
                f"{icon} `{f.get('status','—')}`{url_md}\n\n"
            )
    else:
        features_md = "> ⚠️ No features found. Ensure **TAVILY_API_KEY** is set in Render → Environment.\n"

    comparison_md = f"\n### ⚖️ Comparison\n\n{comparison_table}\n" if comparison_table else ""

    response = f"""## 📊 {result['company']} — Intelligence Report
*{result['run_date']} · {result['version']}*

---

### 📈 Summary

| Timeframe | Count | Status |
|:---|---:|:---|
| **Total Features** | **{summary.get('total',0)}** | — |
| Last 7 Days | {summary.get('week',0)} | 🟢 WEEK |
| Last 30 Days | {summary.get('month',0)} | 🟡 MONTH |
| Last 365 Days | {summary.get('year',0)} | 🔵 YEAR |
| Unverified | {summary.get('unver',0)} | ⚪ |

---

### 🔑 Top Features

{features_md}{comparison_md}---

📁 **Reports ready — download below** 👇  
*Powered by Google ADK · Groq LLaMA 3.3 · Tavily Search*"""

    def _fp(key):
        p = files.get(key, "")
        return p if p and Path(p).exists() else None

    history[-1] = _bot_msg(response)
    yield history, {
        "pdf": _fp("pdf"), "excel": _fp("excel"),
        "briefing": _fp("briefing"), "dashboard": _fp("dashboard")
    }, gr.update(value="")


# ─── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; }

:root {
  --bg:         #1a1a2e;
  --bg-msg:     #16213e;
  --bg-input:   #0f0f23;
  --bg-header:  #12122a;
  --border:     #2a2a4a;
  --purple:     #9d4edd;
  --purple-dim: #7b2ff7;
  --text:       #e0e0ff;
  --text-dim:   #8888aa;
  --text-muted: #555577;
  --yellow:     #fbbf24;
  --radius:     12px;
}

html, body { background: var(--bg) !important; height: 100%; }

.gradio-container {
  background: var(--bg) !important;
  max-width: 100% !important;
  width: 100% !important;
  margin: 0 !important;
  padding: 0 !important;
  font-family: 'Inter', sans-serif !important;
  color: var(--text) !important;
}

footer, .footer, .built-with { display: none !important; }

/* Top bar */
#ms-topbar {
  background: var(--bg-header);
  border-bottom: 1px solid var(--border);
  padding: 14px 24px;
  display: flex; align-items: center; gap: 12px;
}
#ms-topbar .ms-logo {
  background: linear-gradient(135deg, #9d4edd, #e040fb);
  border-radius: 50%; width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; flex-shrink: 0;
  box-shadow: 0 0 12px rgba(157,78,237,0.5);
}
#ms-topbar .ms-title { font-size: 0.95rem; font-weight: 700; color: var(--text); }
#ms-topbar .ms-sub   { font-size: 0.75rem; color: var(--text-muted); margin-top: 1px; }
#ms-topbar .ms-badges { margin-left: auto; display: flex; gap: 6px; }
#ms-topbar .ms-badge {
  background: rgba(157,78,237,0.12); border: 1px solid rgba(157,78,237,0.3);
  color: #b388ff; padding: 3px 10px; border-radius: 20px;
  font-size: 0.7rem; font-weight: 500;
}

/* Chatbot */
#ms-chatbot {
  background: var(--bg) !important;
  border: none !important; border-radius: 0 !important;
  min-height: 460px;
}

/* User bubble */
.message.user .bubble-wrap {
  background: rgba(157,78,237,0.12) !important;
  border: 1px solid rgba(157,78,237,0.2) !important;
  border-radius: 18px 18px 4px 18px !important;
  color: var(--text) !important;
  max-width: 65% !important; margin-left: auto !important;
}

/* Bot bubble */
.message.bot .bubble-wrap {
  background: var(--bg-msg) !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px 18px 18px 18px !important;
  color: var(--text-dim) !important;
  max-width: 90% !important;
  font-size: 0.9rem !important; line-height: 1.75 !important;
}

/* Markdown in bot bubble */
.message.bot h2 { font-size:1.05rem !important; font-weight:700 !important; color:#c084fc !important; border:none !important; padding:0 !important; margin-bottom:4px !important; }
.message.bot h3 { font-size:0.88rem !important; font-weight:600 !important; color:#ddb8ff !important; margin:18px 0 8px !important; padding-left:10px !important; border-left:2px solid var(--purple) !important; }
.message.bot p  { color: var(--text-dim) !important; margin: 6px 0 !important; }
.message.bot strong { color: var(--text) !important; }
.message.bot em     { color: var(--text-muted) !important; font-size: 0.82rem !important; }
.message.bot hr     { border-color: var(--border) !important; margin: 12px 0 !important; }
.message.bot a      { color: #a78bfa !important; }
.message.bot a:hover { color: #c4b5fd !important; }
.message.bot code {
  background: rgba(157,78,237,0.18) !important; color: #c084fc !important;
  border: 1px solid rgba(157,78,237,0.25) !important; border-radius: 5px !important;
  padding: 1px 7px !important; font-family: 'JetBrains Mono', monospace !important; font-size: 0.82rem !important;
}
.message.bot blockquote {
  border-left: 3px solid var(--yellow) !important; background: rgba(251,191,36,0.07) !important;
  padding: 8px 14px !important; border-radius: 0 8px 8px 0 !important; margin: 8px 0 !important;
}
.message.bot blockquote p { color: var(--yellow) !important; }
.message.bot table { width:100% !important; border-collapse:collapse !important; margin:12px 0 !important; font-size:0.87rem !important; background:rgba(255,255,255,0.02) !important; }
.message.bot thead tr { background: rgba(157,78,237,0.12) !important; }
.message.bot th { color:var(--text-muted) !important; font-weight:500 !important; padding:9px 14px !important; text-align:left !important; border-bottom:1px solid var(--border) !important; font-size:0.78rem !important; }
.message.bot td { padding:9px 14px !important; border-bottom:1px solid var(--border) !important; color:var(--text-dim) !important; }
.message.bot td code { background:#2a2a3e !important; color:var(--text) !important; border:1px solid #3a3a5c !important; border-radius:5px !important; padding:3px 9px !important; font-family:'JetBrains Mono',monospace !important; font-size:0.8rem !important; font-weight:500 !important; }
.message.bot tbody tr:last-child td { border-bottom:none !important; }
.message.bot tbody tr:hover { background: rgba(157,78,237,0.05) !important; }

/* Input row */
#ms-input-area {
  background: var(--bg-header); border-top: 1px solid var(--border);
  padding: 12px 20px; display: flex; align-items: center; gap: 10px;
}
#ms-input-area textarea {
  background: var(--bg-input) !important; border: 1px solid var(--border) !important;
  border-radius: 10px !important; color: var(--text) !important;
  font-family: 'Inter', sans-serif !important; font-size: 0.93rem !important;
  padding: 11px 16px !important; resize: none !important;
  transition: border-color 0.2s, box-shadow 0.2s !important;
}
#ms-input-area textarea:focus {
  border-color: var(--purple) !important;
  box-shadow: 0 0 0 3px rgba(157,78,237,0.14) !important; outline: none !important;
}
#ms-input-area textarea::placeholder { color: var(--text-muted) !important; }

#ms-send-btn {
  background: linear-gradient(135deg, var(--purple), var(--purple-dim)) !important;
  border: none !important; border-radius: 10px !important;
  color: #fff !important; font-weight: 600 !important;
  font-size: 0.88rem !important; padding: 11px 22px !important;
  cursor: pointer !important; box-shadow: 0 3px 12px rgba(157,78,237,0.35) !important;
  transition: all 0.2s !important; white-space: nowrap !important; min-width: 90px !important;
}
#ms-send-btn:hover { filter: brightness(1.15) !important; transform: translateY(-1px) !important; }

/* Example chips */
#ms-chips-row {
  background: var(--bg-header); border-top: 1px solid var(--border);
  padding: 9px 20px 11px; display: flex; flex-wrap: wrap; align-items: center; gap: 7px;
}
#ms-chips-label { font-size:0.7rem; text-transform:uppercase; letter-spacing:1px; color:var(--text-muted); font-weight:600; margin-right:4px; }
.ms-chip button {
  background: #1e1e38 !important; border: 1px solid #333355 !important;
  border-radius: 20px !important; color: #a78bfa !important;
  font-family: 'JetBrains Mono', monospace !important; font-size: 0.76rem !important;
  padding: 4px 13px !important; cursor: pointer !important; transition: all 0.15s !important;
}
.ms-chip button:hover {
  background: rgba(157,78,237,0.15) !important; border-color: var(--purple) !important;
  color: #ddd6fe !important; transform: translateY(-1px) !important;
}

/* Download section */
#ms-dl-header {
  background: var(--bg-header); border-top: 1px solid var(--border);
  padding: 12px 24px 6px; font-size:0.7rem; text-transform:uppercase;
  letter-spacing:1px; color:var(--text-muted); font-weight:600;
}
#ms-dl-row { background: var(--bg-header); padding: 6px 20px 16px; }

/* File widgets */
.gr-file-preview, .file-preview {
  background: #1c1c34 !important; border: 1px solid var(--border) !important;
  border-radius: 9px !important; color: var(--text-dim) !important;
}

/* Labels */
label span, .label-wrap span {
  color: var(--text-muted) !important; font-size: 0.72rem !important;
  text-transform: uppercase !important; letter-spacing: 0.8px !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: #3a3a60; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--purple); }

/* Gradio overrides */
.gr-group, .gr-box { background: transparent !important; border: none !important; }
.gap-4 { gap: 0 !important; }
"""

EXAMPLES = [
    "Track Stripe",
    "What's new at Tesla?",
    "Compare Stripe and PayPal",
    "Nike latest features",
    "OpenAI, Anthropic",
]

# ─── Build UI ─────────────────────────────────────────────────────────────────

with gr.Blocks(title="Market Scout — Competitive Intelligence", fill_height=True) as demo:

    gr.HTML("""
    <div id="ms-topbar">
      <div class="ms-logo">◈</div>
      <div>
        <div class="ms-title">Market Scout</div>
        <div class="ms-sub">Competitive Intelligence Assistant</div>
      </div>
      <div class="ms-badges">
        <span class="ms-badge">Google ADK</span>
        <span class="ms-badge">Groq LLaMA 3.3</span>
        <span class="ms-badge">Tavily Search</span>
      </div>
    </div>
    """)

    # Gradio 6.x: type="messages" uses dict format
    chatbot = gr.Chatbot(
        value=INITIAL_HISTORY,
        elem_id="ms-chatbot",
        show_label=False,
        type="messages",
        height=500,
        scale=1,
        avatar_images=(
            None,
            "https://api.dicebear.com/7.x/bottts-neutral/svg?seed=ms&backgroundColor=7c3aed",
        ),
    )

    with gr.Row(elem_id="ms-input-area"):
        chat_input = gr.Textbox(
            placeholder="Type a company name…  e.g.  Stripe   ·   Compare PayPal and Stripe",
            show_label=False, lines=1, scale=5, autofocus=True, elem_id="ms-textbox",
        )
        send_btn = gr.Button("Send ➤", elem_id="ms-send-btn", scale=1, min_width=90, variant="primary")

    gr.HTML('<div id="ms-chips-row"><span id="ms-chips-label">Try:</span></div>')
    with gr.Row():
        chips = [gr.Button(ex, elem_classes=["ms-chip"], size="sm", min_width=0) for ex in EXAMPLES]

    gr.HTML('<div id="ms-dl-header">📎 Download Reports</div>')
    with gr.Row(elem_id="ms-dl-row"):
        pdf_out       = gr.File(label="📄 PDF Report",     interactive=False)
        excel_out     = gr.File(label="📊 Excel Workbook", interactive=False)
        briefing_out  = gr.File(label="📝 Text Briefing",  interactive=False)
        dashboard_out = gr.File(label="🌐 HTML Dashboard", interactive=False)

    # ── Event wiring ──────────────────────────────────────────────────────────

    def run(msg, history):
        last_h, last_f = [], {}
        for h, f, _ in respond(msg, history):
            last_h, last_f = h, f
            yield last_h, gr.update(value=""), None, None, None, None
        yield (
            last_h, gr.update(value=""),
            last_f.get("pdf"), last_f.get("excel"),
            last_f.get("briefing"), last_f.get("dashboard"),
        )

    outs = [chatbot, chat_input, pdf_out, excel_out, briefing_out, dashboard_out]
    send_btn.click(fn=run, inputs=[chat_input, chatbot], outputs=outs)
    chat_input.submit(fn=run, inputs=[chat_input, chatbot], outputs=outs)

    for chip, ex in zip(chips, EXAMPLES):
        chip.click(fn=lambda e=ex: gr.update(value=e), outputs=chat_input)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
        theme=gr.themes.Base(),
        css=CSS,
    )