"""
Web tools — HTTP requests, URL content extraction, web search.

Gives agents the ability to interact with external web resources.
Network operations require approval in Agent mode.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from ..base import BaseTool, ToolDescriptor, ToolParam


class WebFetchTool(BaseTool):
    descriptor = ToolDescriptor(
        name="web_fetch",
        description="Fetch content from a URL and extract text (supports HTML → text conversion)",
        parameters=[
            ToolParam(name="url", description="The URL to fetch", required=True),
            ToolParam(name="max_length", description="Max characters to return", type="number", required=False),
        ],
        category="web",
        requires_approval=True,
    )

    async def execute(self, url: str, max_length: int = 5000) -> str:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "OmniAgent/0.2"})
                resp.raise_for_status()
                text = resp.text
                # Simple HTML → text
                text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.I)
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                return text[:max_length]
        except Exception as e:
            return f"Error fetching URL: {e}"


class WebSearchTool(BaseTool):
    descriptor = ToolDescriptor(
        name="web_search",
        description="Search the web and return results (requires search provider config)",
        parameters=[
            ToolParam(name="query", description="Search query", required=True),
            ToolParam(name="max_results", description="Max results to return", type="number", required=False),
        ],
        category="web",
        requires_approval=True,
    )

    async def execute(self, query: str, max_results: int = 5) -> str:
        # DuckDuckGo HTML search (no API key needed)
        try:
            import urllib.parse
            search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(search_url, headers={"User-Agent": "OmniAgent/0.2"})
                resp.raise_for_status()

                # Extract result snippets
                results = re.findall(
                    r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    resp.text, re.DOTALL,
                )
                lines = []
                for i, (url, title, snippet) in enumerate(results[:max_results]):
                    title_clean = re.sub(r"<[^>]+>", "", title).strip()
                    snippet_clean = re.sub(r"<[^>]+>", "", snippet).strip()
                    lines.append(f"{i+1}. {title_clean}\n   {url}\n   {snippet_clean}")

                return "\n\n".join(lines) if lines else "No results found"
        except Exception as e:
            return f"Search error: {e}. Try web_fetch for direct URL access."


class HttpRequestTool(BaseTool):
    descriptor = ToolDescriptor(
        name="http_request",
        description="Make an HTTP request (GET, POST, PUT, DELETE) with headers and body",
        parameters=[
            ToolParam(name="url", description="Request URL", required=True),
            ToolParam(name="method", description="HTTP method", required=False),
            ToolParam(name="headers", description="JSON headers object", required=False),
            ToolParam(name="body", description="Request body", required=False),
        ],
        category="web",
        requires_approval=True,
    )

    async def execute(self, url: str, method: str = "GET", headers: str = "{}", body: str = "") -> str:
        import json
        try:
            hdrs = json.loads(headers) if headers else {}
            hdrs["User-Agent"] = hdrs.get("User-Agent", "OmniAgent/0.2")
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                if method.upper() == "POST":
                    resp = await client.post(url, headers=hdrs, content=body or None)
                elif method.upper() == "PUT":
                    resp = await client.put(url, headers=hdrs, content=body or None)
                elif method.upper() == "DELETE":
                    resp = await client.delete(url, headers=hdrs)
                else:
                    resp = await client.get(url, headers=hdrs)
                return f"HTTP {resp.status_code}\n{resp.text[:2000]}"
        except Exception as e:
            return f"HTTP request error: {e}"
