"""Royal Road site handler."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import ClassVar

from bs4 import BeautifulSoup, Tag
from loguru import logger

from inkwell.core.models import (
    Chapter,
    ChapterStatus,
    ImageRef,
    Story,
    StoryMetadata,
    StoryStatus,
)
from inkwell.exceptions import ParseError
from inkwell.sites import SiteHandler, register


@register
class RoyalRoadHandler(SiteHandler):
    site_name: ClassVar[str] = "Royal Road"
    url_patterns: ClassVar[list[str]] = ["royalroad.com"]

    def _normalize_fiction_url(self, url: str) -> str:
        """Extract the base fiction URL from any Royal Road URL."""
        match = re.search(r"(https?://www\.royalroad\.com/fiction/\d+)", url)
        if match:
            return match.group(1)
        return url

    async def get_metadata(self, url: str) -> StoryMetadata:
        url = self._normalize_fiction_url(url)
        response = await self.client.get(url)
        soup = BeautifulSoup(response.text, "lxml")

        title_tag = soup.select_one("h1.font-white")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        author_tag = soup.select_one("h4.font-white a")
        author = author_tag.get_text(strip=True) if author_tag else "Unknown"

        summary_tag = soup.select_one("div.description div.hidden-content")
        summary = summary_tag.get_text(strip=True) if summary_tag else ""

        cover_tag = soup.select_one("div.fic-header img.thumbnail")
        cover_url = cover_tag["src"] if cover_tag and cover_tag.get("src") else None

        tags = [
            tag.get_text(strip=True)
            for tag in soup.select("span.tags a.fiction-tag")
        ]

        # Chapter list
        chapter_rows = soup.select("table#chapters tbody tr[data-url]")
        chapter_count = len(chapter_rows)

        # Stats
        stats_text = soup.get_text()
        word_match = re.search(r"([\d,]+)\s+Pages", stats_text)
        word_count = 0
        if word_match:
            pages = int(word_match.group(1).replace(",", ""))
            word_count = pages * 275  # approximate words per page

        # Status
        status = StoryStatus.UNKNOWN
        status_tag = soup.select_one("span.label-sm")
        if status_tag:
            status_text = status_tag.get_text(strip=True).upper()
            if "ONGOING" in status_text:
                status = StoryStatus.ONGOING
            elif "COMPLETED" in status_text or "COMPLETE" in status_text:
                status = StoryStatus.COMPLETE
            elif "HIATUS" in status_text:
                status = StoryStatus.HIATUS

        # Story ID
        story_id_match = re.search(r"/fiction/(\d+)", url)
        story_id = story_id_match.group(1) if story_id_match else ""

        return StoryMetadata(
            title=title,
            author=author,
            url=url,
            summary=summary,
            cover_url=str(cover_url) if cover_url else None,
            tags=tags,
            status=status,
            chapter_count=chapter_count,
            word_count=word_count,
            site_name="Royal Road",
            story_id=story_id,
        )

    async def get_story(self, url: str, offset: int = 0, limit: int | None = None) -> Story:
        url = self._normalize_fiction_url(url)
        meta = await self.get_metadata(url)

        response = await self.client.get(url)
        soup = BeautifulSoup(response.text, "lxml")

        chapter_rows = soup.select("table#chapters tbody tr[data-url]")
        chapters = []
        for i, row in enumerate(chapter_rows):
            if i < offset:
                continue
            if limit is not None and len(chapters) >= limit:
                break

            ch_url = row.get("data-url", "")
            if ch_url and not ch_url.startswith("http"):
                ch_url = f"https://www.royalroad.com{ch_url}"

            td = row.select_one("td a")
            ch_title = td.get_text(strip=True) if td else f"Chapter {i + 1}"

            time_tag = row.select_one("time")
            date_pub = None
            if time_tag and time_tag.get("datetime"):
                try:
                    date_pub = datetime.fromisoformat(
                        time_tag["datetime"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            chapters.append(
                Chapter(
                    index=i,
                    title=ch_title,
                    url=ch_url,
                    date_published=date_pub,
                    status=ChapterStatus.PENDING,
                )
            )

        meta.chapter_count = len(chapters)
        return Story(metadata=meta, chapters=chapters)

    async def get_chapter(self, url: str) -> Chapter:
        response = await self.client.get(url)
        soup = BeautifulSoup(response.text, "lxml")

        title_tag = soup.select_one("h1.font-white")
        title = title_tag.get_text(strip=True) if title_tag else "Chapter"

        content_div = soup.select_one("div.chapter-content")
        if content_div is None:
            raise ParseError(f"Could not find chapter content at {url}")

        # Extract images
        images = []
        for img in content_div.find_all("img"):
            src = img.get("src", "")
            if src:
                filename = re.sub(r"[^\w.]", "_", src.split("/")[-1].split("?")[0])
                if not filename:
                    filename = f"img_{hash(src) & 0xFFFFFF:06x}.jpg"
                images.append(ImageRef(url=src, filename=filename))

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
