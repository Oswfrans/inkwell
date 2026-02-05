"""FanFiction.net and FictionPress site handler."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import ClassVar

from bs4 import BeautifulSoup
from loguru import logger

from inkwell.core.models import (
    Chapter,
    ChapterStatus,
    Story,
    StoryMetadata,
    StoryStatus,
)
from inkwell.exceptions import ParseError
from inkwell.sites import SiteHandler, register


def _parse_ffn_timestamp(ts: str) -> datetime | None:
    """Parse a Unix timestamp from FFN's data-xutime attributes."""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, OSError):
        return None


@register
class FanFictionNetHandler(SiteHandler):
    site_name: ClassVar[str] = "FanFiction.net / FictionPress"
    url_patterns: ClassVar[list[str]] = ["fanfiction.net", "fictionpress.com"]

    def _story_id(self, url: str) -> str:
        match = re.search(r"/s/(\d+)", url)
        if match:
            return match.group(1)
        raise ParseError(f"Cannot extract story ID from {url}")

    def _base_url(self, url: str) -> str:
        if "fictionpress.com" in url:
            return "https://www.fictionpress.com"
        return "https://www.fanfiction.net"

    async def get_metadata(self, url: str) -> StoryMetadata:
        story_id = self._story_id(url)
        base = self._base_url(url)
        story_url = f"{base}/s/{story_id}/1"

        response = await self.client.get(story_url)
        soup = BeautifulSoup(response.text, "lxml")

        # Title
        title_tag = soup.select_one("#profile_top b.xcontrast_txt")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        # Author
        author_tag = soup.select_one("#profile_top a.xcontrast_txt")
        author = author_tag.get_text(strip=True) if author_tag else "Unknown"

        # Summary
        summary_tag = soup.select_one("#profile_top div.xcontrast_txt")
        summary = summary_tag.get_text(strip=True) if summary_tag else ""

        # Cover image
        cover_tag = soup.select_one("#profile_top img.cimage")
        cover_url = None
        if cover_tag and cover_tag.get("src"):
            cover_url = cover_tag["src"]
            if cover_url.startswith("//"):
                cover_url = f"https:{cover_url}"

        # Metadata from the grey info bar
        info_tag = soup.select_one("#profile_top span.xgray")
        info_text = info_tag.get_text() if info_tag else ""

        # Word count
        word_match = re.search(r"Words:\s*([\d,]+)", info_text)
        word_count = int(word_match.group(1).replace(",", "")) if word_match else 0

        # Chapter count
        ch_match = re.search(r"Chapters:\s*(\d+)", info_text)
        chapter_count = int(ch_match.group(1)) if ch_match else 1

        # Status
        status = StoryStatus.COMPLETE if "Complete" in info_text else StoryStatus.ONGOING

        # Language
        lang_match = re.search(
            r"(English|Spanish|French|German|Portuguese|Italian|Russian|Chinese|Japanese|Korean)",
            info_text,
        )
        lang_map = {
            "English": "en", "Spanish": "es", "French": "fr",
            "German": "de", "Portuguese": "pt", "Italian": "it",
            "Russian": "ru", "Chinese": "zh", "Japanese": "ja", "Korean": "ko",
        }
        language = lang_map.get(lang_match.group(1), "en") if lang_match else "en"

        # Genre as tags
        tags = []
        genre_match = re.search(r"([A-Z][a-z]+(?:/[A-Z][a-z]+)*)\s+-\s+", info_text)
        if genre_match:
            tags = genre_match.group(1).split("/")

        # Dates from data-xutime
        date_published = None
        date_updated = None
        if info_tag:
            time_spans = info_tag.select("span[data-xutime]")
            if time_spans:
                if len(time_spans) >= 2:
                    date_updated = _parse_ffn_timestamp(time_spans[0]["data-xutime"])
                    date_published = _parse_ffn_timestamp(time_spans[1]["data-xutime"])
                else:
                    date_published = _parse_ffn_timestamp(time_spans[0]["data-xutime"])

        site_name = "FictionPress" if "fictionpress.com" in url else "FanFiction.net"

        return StoryMetadata(
            title=title,
            author=author,
            url=url,
            summary=summary,
            cover_url=cover_url,
            tags=tags,
            language=language,
            status=status,
            chapter_count=chapter_count,
            word_count=word_count,
            date_published=date_published,
            date_updated=date_updated,
            site_name=site_name,
            story_id=story_id,
        )

    async def get_story(self, url: str, offset: int = 0, limit: int | None = None) -> Story:
        meta = await self.get_metadata(url)
        story_id = self._story_id(url)
        base = self._base_url(url)

        # Get chapter titles from the chapter dropdown
        response = await self.client.get(f"{base}/s/{story_id}/1")
        soup = BeautifulSoup(response.text, "lxml")

        chapter_select = soup.select_one("select#chap_select")
        chapters = []

        if chapter_select:
            options = chapter_select.find_all("option")
            for i, opt in enumerate(options):
                if i < offset:
                    continue
                if limit is not None and len(chapters) >= limit:
                    break
                ch_num = opt.get("value", str(i + 1))
                ch_title = opt.get_text(strip=True)
                # Remove leading "N. " prefix
                ch_title = re.sub(r"^\d+\.\s*", "", ch_title)
                if not ch_title:
                    ch_title = f"Chapter {ch_num}"
                chapters.append(
                    Chapter(
                        index=i,
                        title=ch_title,
                        url=f"{base}/s/{story_id}/{ch_num}",
                        status=ChapterStatus.PENDING,
                    )
                )
        else:
            # Single-chapter story
            chapters.append(
                Chapter(
                    index=0,
                    title=meta.title,
                    url=f"{base}/s/{story_id}/1",
                    status=ChapterStatus.PENDING,
                )
            )

        meta.chapter_count = len(chapters)
        return Story(metadata=meta, chapters=chapters)

    async def get_chapter(self, url: str) -> Chapter:
        response = await self.client.get(url)
        soup = BeautifulSoup(response.text, "lxml")

        content_div = soup.select_one("#storytext")
        if content_div is None:
            raise ParseError(f"Could not find chapter content at {url}")

        html_content = str(content_div)
        word_count = len(content_div.get_text().split())

        return Chapter(
            index=0,
            title="Chapter",
            url=url,
            html_content=html_content,
            word_count=word_count,
            status=ChapterStatus.DOWNLOADED,
        )
