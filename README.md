# Market Scout — Competitive Intelligence Agent

Tracks competitor product features, API updates, and releases using
**Google ADK + Groq LLaMA 3.3 + Tavily Search + Chainlit UI**.

## Project Structure

```
market_scout/
├── app.py                       ← Chainlit entry point (replaces `adk web`)
├── chainlit.md                  ← Sidebar content shown in Chainlit UI
├── Procfile                     ← Render / Heroku start command
├── render.yaml                  ← Render infrastructure-as-code
├── requirements.txt
├── .env.example                 ← Copy to .env and add your keys
├── .gitignore
├── outputs/                     ← Generated at runtime (PDFs, Excel, HTML, JSON)
│
├── market_scout_agent/          ← Root agent (entry point for ADK)
│   ├── __init__.py
│   └── agent.py                 ← root_agent + run_pipeline live here
│
├── web_retrieval_agent/         ← Tavily web search
│   ├── __init__.py
│   └── agent.py
│
├── content_extraction_agent/    ← Parse & deduplicate results
│   ├── __init__.py
│   └── agent.py
│
├── temporal_validation_agent/   ← Date validation & recency status
│   ├── __init__.py
│   └── agent.py
│
├── feature_synthesis_agent/     ← PDF + briefing generation
│   ├── __init__.py
│   └── agent.py
│
├── comparison_report_agent/     ← Excel + comparison tables
│   ├── __init__.py
│   └── agent.py
│
└── guardrails/
    ├── __init__.py
    └── callbacks.py             ← Input/output guardrail hooks
```

---

## Quick Start (Local)

### 1. Clone and install
```bash
git clone https://github.com/YOUR_USERNAME/market-scout.git
cd market-scout
pip install -r requirements.txt
```

### 2. Set up environment variables
```bash
cp .env.example .env
# Edit .env — add TAVILY_API_KEY and GROQ_API_KEY
```

Get your keys:
- Tavily : https://app.tavily.com
- Groq   : https://console.groq.com

### 3. Run with Chainlit UI
```bash
chainlit run app.py
```
Open **http://localhost:8000** in your browser.

### 4. (Optional) Run with ADK CLI
```bash
adk run market_scout_agent
```

---

## Deploy to Render (Public URL, Any Device)

### Option A — render.yaml (recommended)

1. Push this repo to GitHub.
2. Go to https://dashboard.render.com → **New → Blueprint**.
3. Connect your GitHub repo — Render auto-reads `render.yaml`.
4. In the Render dashboard, open the service → **Environment** tab.
   Add two secrets:
   ```
   TAVILY_API_KEY  = your_key
   GROQ_API_KEY    = your_key
   ```
5. Click **Deploy**. Your public URL will be:
   `https://market-scout.onrender.com`

### Option B — Manual web service

1. Go to https://dashboard.render.com → **New → Web Service**.
2. Connect your GitHub repo.
3. Set:
   - **Runtime:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python app.py`
4. Add environment variables (same as above).
5. Under **Disks**, add a disk mounted at `/tmp/market_scout_outputs` (1 GB).
6. Deploy.

> **Free tier note:** Render free services spin down after 15 min of inactivity.
> Upgrade to the **Starter plan ($7/mo)** for always-on hosting.

---

## Usage Examples

| You type | What happens |
|---|---|
| `Stripe` | Tracks Stripe's latest features |
| `Track Tesla` | Tracks Tesla's latest releases |
| `Compare Stripe and PayPal` | Runs both and shows side-by-side table |
| `Nike latest features` | Tracks Nike product updates |

---

## Output Files

All files are saved to `outputs/` locally, or `/tmp/market_scout_outputs/` on Render.

| File | Description |
|---|---|
| `market_scout_dashboard.html` | Persistent HTML dashboard (all runs) |
| `market_scout_data.xlsx` | Excel workbook with charts |
| `market_scout_history.json` | Raw JSON history of all runs |
| `{Company}_YYYYMMDD_HHMMSS.pdf` | Per-run PDF report |
| `{Company}_YYYYMMDD_HHMMSS_briefing.txt` | Per-run text briefing |

In the Chainlit UI, PDF, Excel, and briefing files are also available as
**inline download attachments** after each run.

---

## Status Legend

| Colour | Status | Meaning |
|---|---|---|
| 🟢 Green | WEEK | Published in last 7 days |
| 🟡 Yellow | MONTH | Published in last 30 days |
| 🔵 Blue | YEAR | Published in last 365 days |
| ⚪ Grey | OTHER SOURCES | Date unknown |
| 🔴 Red | STALE | Older than 1 year |

---

## Guardrails

| Guardrail | What it blocks |
|---|---|
| Harmful Intent | hack, exploit, malware, illegal |
| Prompt Injection | jailbreak, act as, ignore instructions |
| PII Detection | credit cards, SSN, email, phone numbers |
| Out-of-Scope | recipes, weather, homework, poems |
| Query Length Min | queries shorter than 3 characters |
| Query Length Max | queries longer than 1000 characters |
| Output Safety | PII leaking into responses |
