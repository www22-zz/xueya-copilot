"""Web search integration via Tavily Search API."""
import asyncio
import hashlib
import json
import logging
import urllib.request
from typing import Any, Dict, List

from .config import load_config

logger = logging.getLogger("uvicorn.error")


def _safe_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


async def search_tavily(query: str, limit: int = 5, api_key: str | None = None) -> Dict[str, Any]:
    """Execute a web search using Tavily Search API. Returns structured sources."""
    if not api_key:
        config = load_config()
        api_key = getattr(config, "tavily_api_key", "")

    clean_query = str(query or "").strip()
    if not clean_query:
        return {"sources": [], "warnings": ["EMPTY_QUERY"]}
    if not api_key:
        return {"sources": [], "warnings": ["TAVILY_API_KEY_NOT_CONFIGURED"]}

    def _do_search():
        payload = json.dumps({
            "api_key": api_key,
            "query": clean_query,
            "search_depth": "basic",
            "include_answer": False,
            "max_results": max(1, min(int(limit), 8))
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "xueya-app/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        data = await asyncio.to_thread(_do_search)
        results = data.get("results", [])
        sources = []
        for i, item in enumerate(results):
            title = str(item.get("title") or "网页搜索结果")[:200]
            url = str(item.get("url") or "")[:500]
            content = str(item.get("content") or "")[:2500]
            src_id = f"web-{_safe_hash(url or title + str(i))}"
            sources.append({
                "id": src_id,
                "title": title,
                "location": url or "互联网网页",
                "quote": content,
                "isWeb": True,
                "sample": False,
                "url": url
            })
        return {"sources": sources, "warnings": []}
    except Exception as e:
        logger.warning("Tavily web search failed: %s", e)
        return {"sources": [], "warnings": [f"WEB_SEARCH_FAILED: {e}"]}
