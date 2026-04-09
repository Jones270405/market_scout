# content_extraction_agent/agent.py
"""
Content Extraction Sub-Agent
Parses raw search results into structured feature records.
Deduplicates by URL and filters by feature-relevant keywords.
"""

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool

FEATURE_KEYWORDS = [
    "launch", "release", "update", "new", "feature",
    "api", "integration", "improve", "announce",
    "partnership", "expand", "upgrade", "support",
]


def extract_features(raw: str) -> list:
    """
    Parses raw Tavily search text into a list of structured feature dicts.
    Each dict has: feature, category, date, status, url, snippet.
    Deduplicates by URL and filters to feature-relevant content only.
    """
    lines     = raw.split("\n")
    features  = []
    current   = {}
    seen_urls = set()

    for line in lines:
        line = line.strip()

        if line.startswith("* Title"):
            if current and current.get("url") not in seen_urls:
                if any(kw in current.get("snippet", "").lower() for kw in FEATURE_KEYWORDS):
                    seen_urls.add(current.get("url", ""))
                    features.append(current)
            current = {
                "feature" : line.replace("* Title    :", "").strip(),
                "category": "Product",
                "date"    : "unknown",
                "status"  : "UNVERIFIED",
                "url"     : "",
                "snippet" : "",
            }

        elif line.startswith("* URL"):
            current["url"] = line.replace("* URL      :", "").strip()

        elif line.startswith("* Snippet"):
            current["snippet"] = line.replace("* Snippet  :", "").strip()

        elif line.startswith("* Published"):
            date_val        = line.replace("* Published:", "").strip()
            current["date"] = date_val if date_val else "unknown"

    if current and current.get("url") not in seen_urls:
        if any(kw in current.get("snippet", "").lower() for kw in FEATURE_KEYWORDS):
            features.append(current)

    return features


extraction_tool = FunctionTool(func=extract_features)

content_extraction_agent = LlmAgent(
    name="content_extraction_agent",
    model=LiteLlm(model="groq/llama-3.1-8b-instant"),
    description="Extracts and deduplicates structured feature records from raw search results.",
    instruction=(
        "You are a Content Extraction Agent. "
        "When given raw search result text, call extract_features with that text. "
        "Return the resulting list of feature dicts exactly as received. "
        "Do not summarise, modify, or add any commentary."
    ),
    tools=[extraction_tool],
)
