# temporal_validation_agent/agent.py
"""
Temporal Validation Sub-Agent
Validates published dates and assigns WEEK / MONTH / YEAR / STALE / UNVERIFIED
status to each feature. Also categorises features by snippet keywords.
"""

from datetime import datetime, timedelta
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool


def _parse_date(date_str: str) -> datetime | None:
    """
    Attempts to parse a date string using multiple strategies.
    Returns a datetime object or None if unparseable.
    """
    if not date_str or date_str.strip().lower() in {"unknown", "none", "null", ""}:
        return None

    date_str = date_str.strip()

    # Year-only: "2024" -> "2024-01-01"
    if len(date_str) == 4 and date_str.isdigit():
        date_str = f"{date_str}-01-01"

    # Try ISO slice first (handles "2025-04-10T14:32:00Z" etc.)
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        pass

    # Fallback: dateutil (handles "April 10, 2025", "10/04/2025", etc.)
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(date_str, fuzzy=True)
    except Exception:
        pass

    return None


def validate_by_timeframe(features: list) -> list:
    """
    Validates each feature's published date and assigns a recency status:
      WEEK       — published within last 7 days
      MONTH      — published within last 30 days
      YEAR       — published within last 365 days
      STALE      — older than 365 days
      UNVERIFIED — date missing or unparseable

    Also assigns a category based on snippet keywords.
    """
    today   = datetime.now()
    cutoffs = {
        "WEEK" : today - timedelta(days=7),
        "MONTH": today - timedelta(days=30),
        "YEAR" : today - timedelta(days=365),
    }

    for f in features:
        # ── Categorise ──
        snippet = f.get("snippet", "").lower()
        if "api" in snippet:
            f["category"] = "API"
        elif "integration" in snippet or "partnership" in snippet:
            f["category"] = "Integration"
        elif "security" in snippet or "tls" in snippet or "certificate" in snippet:
            f["category"] = "Security"
        elif "performance" in snippet:
            f["category"] = "Performance"
        else:
            f["category"] = "Product"

        # ── Validate date ──
        pub_date = _parse_date(f.get("date", "unknown"))

        if pub_date is None:
            f["status"] = "UNVERIFIED"
            continue

        if pub_date >= cutoffs["WEEK"]:
            f["status"] = "WEEK"
        elif pub_date >= cutoffs["MONTH"]:
            f["status"] = "MONTH"
        elif pub_date >= cutoffs["YEAR"]:
            f["status"] = "YEAR"
        else:
            f["status"] = "STALE"

        f["date"] = pub_date.strftime("%Y-%m-%d")

    return features


validation_tool = FunctionTool(func=validate_by_timeframe)

temporal_validation_agent = LlmAgent(
    name="temporal_validation_agent",
    model=LiteLlm(model="groq/llama-3.1-8b-instant"),
    description="Validates feature dates and assigns WEEK/MONTH/YEAR/STALE/UNVERIFIED recency status.",
    instruction=(
        "You are a Temporal Validation Agent. "
        "When given a list of feature dicts, call validate_by_timeframe with that list. "
        "Return the resulting validated list exactly as received. "
        "Do not summarise, modify, or add any commentary."
    ),
    tools=[validation_tool],
)
