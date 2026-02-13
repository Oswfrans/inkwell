"""NovelFull site handler.

Uses curl_cffi to bypass Cloudflare protection on novelfull.com.
"""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import urljoin

import anyio
from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
from loguru import logger

from inkwell.core.models import (
    Chapter,
    ChapterStatus,
    ImageRef,
    Story,
    StoryMetadata,
    StoryStatus,
)
from inkwell.exceptions import NetworkError, ParseError
from inkwell.sites import SiteHandler, register

NOVELFULL_BASE = "https://novelfull.com"


@register
class NovelFullHandler(SiteHandler):
    site_name: ClassVar[str] = "NovelFull"
    url_patterns: ClassVar[list[str]] = ["novelfull.com"]

    async def _fetch(self, url: str) -> str:
        """Fetch a URL using curl_cffi to bypass Cloudflare."""
        response = await anyio.to_thread.run_sync(
            lambda: cf_requests.get(url, impersonate="chrome", timeout=30)
        )
        if response.status_code != 200:
            raise NetworkError(
                f"HTTP {response.status_code} for {url}"
            )
        return response.text

    def _normalize_fiction_url(self, url: str) -> str:
        """Extract the base fiction URL, stripping any chapter path."""
        # Story URLs: novelfull.com/story-slug.html
        # Chapter URLs: novelfull.com/story-slug/chapter-name.html
        match = re.search(r"(https?://(?:www\.)?novelfull\.com/[^/]+\.html)", url)
        if match:
            return match.group(1)
        # Strip chapter path: /story-slug/chapter-1.html -> /story-slug.html
        match = re.search(r"(https?://(?:www\.)?novelfull\.com/)([^/]+)/", url)
        if match:
            return f"{match.group(1)}{match.group(2)}.html"
        return url

    async def get_metadata(self, url: str) -> StoryMetadata:
        url = self._normalize_fiction_url(url)
        html = await self._fetch(url)
        soup = BeautifulSoup(html, "lxml")

        # Title
        title_tag = soup.select_one("h3.title")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        # Author
        author = "Unknown"
        author_tag = soup.select_one(".info a[href*='/author/']")
        if author_tag:
            author = author_tag.get_text(strip=True)

        # Cover image
        cover_url = None
        cover_tag = soup.select_one(".book img")
        if cover_tag:
            cover_url = cover_tag.get("data-src") or cover_tag.get("src")
            if cover_url and not cover_url.startswith("http"):
                cover_url = urljoin(NOVELFULL_BASE, cover_url)

        # Summary
        summary_tag = soup.select_one(".desc-text")
        summary = summary_tag.get_text(strip=True) if summary_tag else ""

        # Genres/tags
        tags = []
        for info_item in soup.select(".info div"):
            heading = info_item.find("h3")
            if heading and "genre" in heading.get_text(strip=True).lower():
                for a_tag in info_item.find_all("a"):
                    tag_text = a_tag.get_text(strip=True)
                    if tag_text:
                        tags.append(tag_text)

        # Status
        status = StoryStatus.UNKNOWN
        for info_item in soup.select(".info div"):
            heading = info_item.find("h3")
            if heading and "status" in heading.get_text(strip=True).lower():
                status_text = info_item.get_text(strip=True).upper()
                if "ONGOING" in status_text:
                    status = StoryStatus.ONGOING
                elif "COMPLETED" in status_text or "COMPLETE" in status_text:
                    status = StoryStatus.COMPLETE

        # Chapter count via AJAX
        novel_id = self._extract_novel_id(soup)
        chapter_count = 0
        if novel_id:
            try:
                chapters_html = await self._fetch_chapter_list(novel_id)
                chapter_soup = BeautifulSoup(chapters_html, "lxml")
                chapter_count = len(chapter_soup.select("option[value]"))
            except Exception:
                logger.debug("Could not fetch chapter count for metadata")

        # Story ID from slug
        slug_match = re.search(r"novelfull\.com/([^/]+?)\.html", url)
        story_id = slug_match.group(1) if slug_match else ""

        return StoryMetadata(
            title=title,
            author=author,
            url=url,
            summary=summary,
            cover_url=str(cover_url) if cover_url else None,
            tags=tags,
            status=status,
            chapter_count=chapter_count,
            site_name="NovelFull",
            story_id=story_id,
        )

    def _extract_novel_id(self, soup: BeautifulSoup) -> str | None:
        """Extract the novel ID from the page."""
        el = soup.find(attrs={"data-novel-id": True})
        if el:
            return el["data-novel-id"]

        for script in soup.find_all("script"):
            text = script.string or ""
            match = re.search(r"novelId\s*[=:]\s*['\"]?(\d+)", text)
            if match:
                return match.group(1)

        for a_tag in soup.find_all("a", href=True):
            match = re.search(r"novelId=(\d+)", a_tag["href"])
            if match:
                return match.group(1)

        return None

    async def _fetch_chapter_list(self, novel_id: str) -> str:
        """Fetch the full chapter list via AJAX endpoint."""
        ajax_url = f"{NOVELFULL_BASE}/ajax-chapter-option?novelId={novel_id}"
        return await self._fetch(ajax_url)

    async def get_story(self, url: str, offset: int = 0, limit: int | None = None) -> Story:
        url = self._normalize_fiction_url(url)
        meta = await self.get_metadata(url)

        # Re-fetch the page to get the novel ID
        html = await self._fetch(url)
        soup = BeautifulSoup(html, "lxml")

        novel_id = self._extract_novel_id(soup)
        if not novel_id:
            raise ParseError(f"Could not extract novel ID from {url}")

        # Fetch all chapters via AJAX (returns <option> tags)
        chapters_html = await self._fetch_chapter_list(novel_id)
        chapter_soup = BeautifulSoup(chapters_html, "lxml")

        options = chapter_soup.select("option[value]")
        chapters = []
        for i, opt in enumerate(options):
            if i < offset:
                continue
            if limit is not None and len(chapters) >= limit:
                break

            href = opt.get("value", "")
            if href and not href.startswith("http"):
                href = urljoin(NOVELFULL_BASE, href)

            ch_title = opt.get_text(strip=True) or f"Chapter {i + 1}"

            chapters.append(
                Chapter(
                    index=i,
                    title=ch_title,
                    url=href,
                    status=ChapterStatus.PENDING,
                )
            )

        meta.chapter_count = len(chapters)
        return Story(metadata=meta, chapters=chapters)

    async def get_chapter(self, url: str) -> Chapter:
        html = await self._fetch(url)
        soup = BeautifulSoup(html, "lxml")

        # Chapter title
        title_tag = soup.select_one("a.chapter-title")
        if not title_tag:
            title_tag = soup.select_one("h2")
        title = title_tag.get_text(strip=True) if title_tag else "Chapter"

        # Chapter content
        content_div = soup.select_one("#chapter-content")
        if content_div is None:
            raise ParseError(f"Could not find chapter content at {url}")

        # Extract images before removing divs
        images = []
        for img in content_div.find_all("img"):
            src = img.get("src", "")
            if src:
                if not src.startswith("http"):
                    src = urljoin(NOVELFULL_BASE, src)
                filename = re.sub(r"[^\w.]", "_", src.split("/")[-1].split("?")[0])
                if not filename:
                    filename = f"img_{hash(src) & 0xFFFFFF:06x}.jpg"
                images.append(ImageRef(url=src, filename=filename))

        # Remove ad divs nested inside content
        for div in content_div.find_all("div"):
            div.decompose()

        html_content = str(content_div)
        word_count = len(content_div.get_text().split())

        return Chapter(
            index=0,
            title=title,
            url=url,
            html_content=html_content,
            word_count=word_count,
            images=images,
            status=ChapterStatus.DOWNLOADED,
        )
