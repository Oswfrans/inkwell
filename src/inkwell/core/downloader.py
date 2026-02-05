"""Async HTTP client with retry logic and rate limiting."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from inkwell.core.config import Config
from inkwell.exceptions import NetworkError, RateLimitError


class Downloader:
    """Async HTTP client with rate limiting and retry support."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._last_request_time: float = 0
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                http2=True,
                follow_redirects=True,
                timeout=httpx.Timeout(self.config.download.timeout),
                headers={"User-Agent": self.config.download.user_agent},
            )
        return self._client

    async def _rate_limit(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            delay = self.config.download.rate_limit
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    @retry(
        retry=retry_if_exception_type(NetworkError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Perform a rate-limited GET request with retries."""
        await self._rate_limit()
        client = await self._get_client()
        try:
            response = await client.get(url, **kwargs)
            if response.status_code == 429:
                raise RateLimitError(f"Rate limited on {url}")
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise NetworkError(f"HTTP {exc.response.status_code} for {url}") from exc
        except httpx.RequestError as exc:
            raise NetworkError(f"Request failed for {url}: {exc}") from exc

    async def get_bytes(self, url: str) -> bytes:
        """Download binary content (images, etc.)."""
        response = await self.get(url)
        return response.content

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> Downloader:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
