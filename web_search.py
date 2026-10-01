"""Fetch small, source-labelled web context with Firecrawl."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from runtime_cache import TTLCache


load_dotenv()

SEARCH_URL = "https://api.firecrawl.dev/v2/search"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RESULTS = 3
MAX_CHARS_PER_RESULT = 1_600
WEB_CONTEXT_CACHE_SECONDS = int(os.getenv("FIRECRAWL_CACHE_SECONDS", "900"))
_web_context_cache = TTLCache(WEB_CONTEXT_CACHE_SECONDS)


def get_firecrawl_context(query: str) -> str:
    """Search Firecrawl and return a small block of labelled source material.

    The returned text is for the LLM to read, not for the robot to say aloud.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY is missing from .env")

    cache_key = query.casefold().strip()
    cached = _web_context_cache.get(cache_key)
    if cached:
        print("Firecrawl: cached sources")
        return cached

    request_body = json.dumps(
        {
            "query": query,
            "limit": MAX_RESULTS,
            "scrapeOptions": {"formats": ["markdown"]},
        }
    ).encode("utf-8")
    request = Request(
        SEARCH_URL,
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(f"Firecrawl search failed (HTTP {error.code})") from error
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError("Firecrawl search could not reach the internet") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Firecrawl returned an unreadable search response") from error

    results = payload.get("data", {}).get("web", [])
    source_blocks = []
    for result in results[:MAX_RESULTS]:
        url = result.get("url", "")
        title = result.get("title", "Untitled source")
        content = result.get("markdown") or result.get("description") or ""
        if not url or not content:
            continue
        source_blocks.append(
            f"Source: {title}\nURL: {url}\nContent:\n{content[:MAX_CHARS_PER_RESULT]}"
        )

    if not source_blocks:
        raise RuntimeError("Firecrawl found no readable sources")

    context = "\n\n---\n\n".join(source_blocks)
    _web_context_cache.set(cache_key, context)
    return context
