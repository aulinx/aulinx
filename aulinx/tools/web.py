"""Web tools — search the web, fetch URLs."""

import httpx

from aulinx.tools.base import Tier, Tool


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using DuckDuckGo Instant Answer API (no API key needed)."""
    try:
        async with httpx.AsyncClient() as client:
            # DuckDuckGo instant answer API
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []

            # Abstract (main answer)
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("Heading", ""),
                    "text": data["AbstractText"],
                    "url": data.get("AbstractURL", ""),
                    "source": data.get("AbstractSource", ""),
                })

            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("Text", "")[:100],
                        "text": topic.get("Text", ""),
                        "url": topic.get("FirstURL", ""),
                    })

            if not results:
                # Try the HTML search as fallback
                return [{"text": f"No instant answer for '{query}'. Try opening a browser.", "url": f"https://duckduckgo.com/?q={query}"}]

            return results[:max_results]

    except Exception as e:
        return [{"error": f"Web search failed: {e}"}]


async def fetch_url(url: str, max_length: int = 5000) -> dict:
    """Fetch the text content of a URL."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

            if "text" in content_type or "json" in content_type:
                text = resp.text[:max_length]
                return {"url": url, "status": resp.status_code, "text": text, "length": len(resp.text)}
            else:
                return {"url": url, "status": resp.status_code, "content_type": content_type, "size_bytes": len(resp.content)}

    except Exception as e:
        return {"error": f"Failed to fetch {url}: {e}"}


TOOLS = [
    Tool(
        name="search_web",
        description="Search the web using DuckDuckGo (no API key). Returns titles, text snippets, and URLs.",
        fn=search_web,
        parameters={
            "query": "string (search query)",
            "max_results": "int (default 5)",
        },
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="fetch_url",
        description="Fetch the text content of a URL (web page, API endpoint, etc.)",
        fn=fetch_url,
        parameters={
            "url": "string (full URL including https://)",
            "max_length": "int (max chars to return, default 5000)",
        },
        tier=Tier.OBSERVE,
    ),
]
