"""Ported from src/tools/WebFetch.ts."""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

from ..utils.logging import logger


@dataclass
class WebFetchResult:
    url: str
    status: int
    content: str
    content_type: str
    timestamp: float
    duration: float


class WebFetch:
    DEFAULT_TIMEOUT = 10.0
    DEFAULT_RETRIES = 3
    USER_AGENT = "JARVIS/1.0.0 (Local AI Assistant)"

    async def fetch_url(self, url: str, timeout: float = DEFAULT_TIMEOUT, max_retries: int = DEFAULT_RETRIES) -> WebFetchResult:
        start = time.perf_counter()
        last_error: Optional[Exception] = None

        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"Fetching {url} (attempt {attempt}/{max_retries})")
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(url, headers=headers)

                duration = (time.perf_counter() - start) * 1000
                result = WebFetchResult(
                    url=url,
                    status=response.status_code,
                    content=response.text,
                    content_type=response.headers.get("content-type", "unknown"),
                    timestamp=time.time() * 1000,
                    duration=duration,
                )

                if response.is_success:
                    logger.debug(f"Successfully fetched {url} ({len(result.content)} chars, {duration:.1f}ms)")
                    return result
                raise RuntimeError(f"HTTP {response.status_code}")
            except Exception as error:  # noqa: BLE001
                last_error = error
                logger.warn(f"Fetch attempt {attempt} failed for {url}:", error)
                if attempt < max_retries:
                    await asyncio.sleep(min(1 * (2 ** (attempt - 1)), 5))

        logger.error(f"Failed to fetch {url} after {max_retries} attempts")
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    async def fetch_multiple(self, urls: list[str], **kwargs) -> list[WebFetchResult]:
        logger.info(f"Fetching {len(urls)} URLs in parallel")

        async def safe_fetch(url: str) -> Optional[WebFetchResult]:
            try:
                return await self.fetch_url(url, **kwargs)
            except Exception as error:  # noqa: BLE001
                logger.warn(f"Failed to fetch {url}:", error)
                return None

        results = await asyncio.gather(*(safe_fetch(u) for u in urls))
        successful = [r for r in results if r is not None]
        logger.info(f"Successfully fetched {len(successful)}/{len(urls)} URLs")
        return successful

    async def search_google(self, query: str, **kwargs) -> list[WebFetchResult]:
        logger.warn("Google search not implemented - using placeholder")
        try:
            return [await self.fetch_url(f"https://www.google.com/search?q={quote(query)}", **kwargs)]
        except Exception as error:  # noqa: BLE001
            logger.error("Google search failed:", error)
            return []

    def extract_text(self, html: str) -> str:
        html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<[^>]*>", "", html)
        return re.sub(r"\s+", " ", html).strip()

    def extract_title(self, html: str) -> str:
        match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html, flags=re.IGNORECASE)
        return match.group(1).strip() if match else "No title"

    def is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False
