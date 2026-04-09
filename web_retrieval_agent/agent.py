# web_retrieval_agent/agent.py
"""
Web Retrieval Sub-Agent
Searches the web for competitor news and feature releases using Tavily.
"""

import os
from datetime import datetime
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
from dotenv import load_dotenv

load_dotenv()


def get_search_results(company: str) -> str:
    """
    Searches the web for recent competitor features and releases.
    Returns formatted raw text results with title, url, snippet, published date.
    API key is resolved at call time so .env changes are picked up correctly.
    """
    api_key = os.getenv("TAVILY_API_KEY", "")

    try:
        from tavily import TavilyClient

        if not api_key:
            return "ERROR: TAVILY_API_KEY not set in .env file."

        client = TavilyClient(api_key=api_key)
        year   = datetime.now().year
        queries = [
            f"{company} new features release {year - 1} {year}",
            f"{company} product update announcement",
            f"{company} API integration launch",
        ]

        all_results = []
        seen_urls   = set()

        for query in queries:
            try:
                response = client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=5,
                    include_published_date=True,
                )
                for r in response.get("results", []):
                    url = r.get("url", "")
                    if url not in seen_urls:
                        seen_urls.add(url)
                        pub = r.get("published_date", "") or ""
                        all_results.append(
                            f"* Title    : {r.get('title', '')}\n"
                            f"* URL      : {url}\n"
                            f"* Snippet  : {r.get('content', '')[:300]}\n"
                            f"* Published: {pub}\n"
                        )
            except Exception as e:
                all_results.append(f"[Search error for '{query}': {str(e)}]")

        return "\n".join(all_results) if all_results else f"No results found for {company}."

    except ImportError:
        return "ERROR: tavily-python not installed. Run: pip install tavily-python"
    except Exception as e:
        return f"ERROR in web retrieval: {str(e)}"


search_tool = FunctionTool(func=get_search_results)

web_retrieval_agent = LlmAgent(
    name="web_retrieval_agent",
    model=LiteLlm(model="groq/llama-3.1-8b-instant"),
    description="Searches the web for competitor news, features, and product releases.",
    instruction=(
        "You are a Web Retrieval Agent. "
        "When given a company name, call get_search_results with that company name. "
        "Return the raw results exactly as received — do not summarise or modify them."
    ),
    tools=[search_tool],
)
