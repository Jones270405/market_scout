# temporal_validation_agent/agent.py
"""
Temporal Validation Sub-Agent
Validates published dates and assigns WEEK / MONTH / YEAR / STALE / OTHER SOURCES.

Key fixes:
  - All parsed dates stripped to naive UTC to avoid offset-aware comparison errors
  - Future dates (data errors) treated as UNVERIFIED instead of crashing
  - Tavily "Thu, 10 Apr 2025 ..." RFC-2822 format handled correctly
  - Category detection broadened
"""

from datetime import datetime, timedelta, timezone
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool


def _to_naive_utc(dt: datetime) -> datetime:
    """Strip timezone info safely — convert to UTC first if aware."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_date(date_str: str) -> datetime | None:
    """
    Parse any date string Tavily might return.
    Always returns a naive datetime in UTC, or None if unparseable.

    Handles:
      2025-04-10                  ISO date
      2025-04-10T14:32:00Z        ISO with Z
      2025-04-10T14:32:00+05:30   ISO with offset
      2025-04-10 14:32:00+05:30   space separator
      Thu, 10 Apr 2025 14:32 GMT  RFC-2822
      April 10, 2025              long form
      Apr 10, 2025                short form
      2024                        year only
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    if date_str.lower() in {"unknown", "none", "null", "n/a", ""}:
        return None

    # Year-only
    if len(date_str) == 4 and date_str.isdigit():
        return datetime(int(date_str), 1, 1)

    # ISO slice — handles "2025-04-10T..." and "2025-04-10 14:..." safely
    if len(date_str) >= 10 and date_str[4] == "-" and date_str[7] == "-":
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            pass

    # Full ISO with timezone via dateutil
    try:
        from dateutil import parser as dup
        parsed = dup.parse(date_str, fuzzy=True)
        return _to_naive_utc(parsed)
    except Exception:
        pass

    return None


def validate_by_timeframe(features: list) -> list:
    """
    Validates each feature's published date and assigns a recency status.
    Also assigns a category based on snippet keywords.
    """
    today = datetime.utcnow()   # naive UTC — consistent reference point
    cutoffs = {
        "WEEK" : today - timedelta(days=7),
        "MONTH": today - timedelta(days=30),
        "YEAR" : today - timedelta(days=365),
    }

    for f in features:
        # ── Categorise by snippet ──
        snippet = (f.get("snippet", "") + " " + f.get("feature", "")).lower()
        if any(k in snippet for k in ["api", "sdk", "endpoint", "webhook", "oauth"]):
            f["category"] = "API"
        elif any(k in snippet for k in ["integration", "partnership", "connect", "partner"]):
            f["category"] = "Integration"
        elif any(k in snippet for k in ["security", "tls", "ssl", "encrypt", "auth", "certificate", "compliance", "gdpr", "soc2"]):
            f["category"] = "Security"
        elif any(k in snippet for k in ["performance", "speed", "latency", "faster", "optimis", "throughput"]):
            f["category"] = "Performance"
        elif any(k in snippet for k in ["model", "ai", "llm", "gpt", "claude", "gemini", "neural"]):
            f["category"] = "AI/ML"
        elif any(k in snippet for k in ["mobile", "ios", "android", "app"]):
            f["category"] = "Mobile"
        else:
            f["category"] = "Product"

        # ── Validate & classify date ──
        pub = _parse_date(f.get("date", ""))

        if pub is None:
            f["status"] = "OTHER SOURCES"
            continue

        # Future date = data error → unverified
        if pub > today + timedelta(days=1):
            f["status"] = "OTHER SOURCES"
            f["date"]   = pub.strftime("%Y-%m-%d")
            continue

        if pub >= cutoffs["WEEK"]:
            f["status"] = "WEEK"
        elif pub >= cutoffs["MONTH"]:
            f["status"] = "MONTH"
        elif pub >= cutoffs["YEAR"]:
            f["status"] = "YEAR"
        else:
            f["status"] = "STALE"

        f["date"] = pub.strftime("%Y-%m-%d")

    return features


validation_tool = FunctionTool(func=validate_by_timeframe)

temporal_validation_agent = LlmAgent(
    name="temporal_validation_agent",
    model=LiteLlm(model="groq/llama-3.1-8b-instant"),
    description="Validates feature dates and assigns WEEK/MONTH/YEAR/STALE/OTHER SOURCES recency status.",
    instruction=(
        "You are a Temporal Validation Agent. "
        "When given a list of feature dicts, call validate_by_timeframe with that list. "
        "Return the resulting validated list exactly as received."
    ),
    tools=[validation_tool],
)
