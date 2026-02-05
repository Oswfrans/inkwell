"""Archive of Our Own (AO3) site handler."""

from __future__ import annotations

import re
from datetime import datetime
from typing import ClassVar

from bs4 import BeautifulSoup
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

AO3_BASE = "https://archiveofourown.org"


@register
class AO3Handler(SiteHandler):
    site_name: ClassVar[str] = "Archive of Our Own"
    url_patterns: ClassVar[list[str]] = ["archiveofourown.org", "ao3.org"]

    def _work_id(self, url: str) -> str:
        match = re.search(r"/works/(\d+)", url)
        if match:
            return match.group(1)
        raise ParseError(f"Cannot extract work ID from {url}")

    def _is_series(self, url: str) -> bool:
        return "/series/" in url

    def _series_id(self, url: str) -> str:
        match = re.search(r"/series/(\d+)", url)
        if match:
            return match.group(1)
        raise ParseError(f"Cannot extract series ID from {url}")

    async def get_metadata(self, url: str) -> StoryMetadata:
        if self._is_series(url):
            return await self._series_metadata(url)
        return await self._work_metadata(url)

    async def _work_metadata(self, url: str) -> StoryMetadata:
        work_id = self._work_id(url)
        nav_url = f"{AO3_BASE}/works/{work_id}/navigate"
        work_url = f"{AO3_BASE}/works/{work_id}?view_adult=true"

        response = await self.client.get(work_url)
        soup = BeautifulSoup(response.text, "lxml")

        title_tag = soup.select_one("h2.title")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"

        author_tag = soup.select_one("a[rel='author']")
        author = author_tag.get_text(strip=True) if author_tag else "Anonymous"

        summary_tag = soup.select_one("div.summary blockquote")
        summary = summary_tag.get_text(strip=True) if summary_tag else ""

        tags = []
        for tag_list in soup.select("ul.tags li a.tag"):
            tags.append(tag_list.get_text(strip=True))

        # Stats
        stats = soup.select_one("dl.stats")
        word_count = 0
        chapter_count = 1
        status = StoryStatus.COMPLETE
        if stats:
            words_tag = stats.select_one("dd.words")
            if words_tag:
                word_count = int(words_tag.get_text(strip=True).replace(",", "") or "0")
            chapters_tag = stats.select_one("dd.chapters")
            if chapters_tag:
                ch_text = chapters_tag.get_text(strip=True)
                parts = ch_text.split("/")
                chapter_count = int(parts[0])
                if len(parts) == 2 and parts[1] == "?":
                    status = StoryStatus.ONGOING

        # Dates
        published_tag = soup.select_one("dd.published")
        date_published = None
        if published_tag:
            try:
                date_published = datetime.strptime(
                    published_tag.get_text(strip=True), "%Y-%m-%d"
                )
            except ValueError:
                pass

        updated_tag = soup.select_one("dd.status")
        date_updated = None
        if updated_tag:
            try:
                date_updated = datetime.strptime(
                    updated_tag.get_text(strip=True), "%Y-%m-%d"
                )
            except ValueError:
                pass

        language_tag = soup.select_one("dd.language")
        language = language_tag.get_text(strip=True) if language_tag else "en"
        lang_map = {"English": "en", "Español": "es", "Français": "fr", "Deutsch": "de"}
        language = lang_map.get(language, "en")

        return StoryMetadata(
            title=title,
            author=author,
            url=url,
            summary=summary,
            tags=tags,
            language=language,
            status=status,
            chapter_count=chapter_count,
            word_count=word_count,
            date_published=date_published,
            date_updated=date_updated,
            site_name="AO3",
            story_id=work_id,
        )

    async def _series_metadata(self, url: str) -> StoryMetadata:
        series_id = self._series_id(url)
        series_url = f"{AO3_BASE}/series/{series_id}"
        response = await self.client.get(series_url)
        soup = BeautifulSoup(response.text, "lxml")

        title_tag = soup.select_one("h2.heading")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Series"

        author_tag = soup.select_one("dl.series a[rel='author']")
        author = author_tag.get_text(strip=True) if author_tag else "Anonymous"

        desc_tag = soup.select_one("blockquote.userstuff")
        summary = desc_tag.get_text(strip=True) if desc_tag else ""

        work_links = soup.select("ul.series li.work h4 a:first-child")
        chapter_count = len(work_links)

        return StoryMetadata(
            title=title,
            author=author,
            url=url,
            summary=summary,
            chapter_count=chapter_count,
            site_name="AO3",
            story_id=f"series-{series_id}",
        )

    async def get_story(self, url: str, offset: int = 0, limit: int | None = None) -> Story:
        if self._is_series(url):
            return await self._series_story(url, offset, limit)
        return await self._work_story(url, offset, limit)

    async def _work_story(self, url: str, offset: int, limit: int | None) -> Story:
        work_id = self._work_id(url)
        meta = await self._work_metadata(url)

        # Get chapter list from navigation page
        nav_url = f"{AO3_BASE}/works/{work_id}/navigate"
        response = await self.client.get(nav_url)
        soup = BeautifulSoup(response.text, "lxml")

        chapter_links = soup.select("ol.chapter li a")
        chapters = []

        if not chapter_links:
            # Single-chapter work: the whole work is one chapter
            ch_url = f"{AO3_BASE}/works/{work_id}?view_adult=true"
            chapters.append(
                Chapter(
                    index=0,
                    title=meta.title,
                    url=ch_url,
                    status=ChapterStatus.PENDING,
                )
            )
        else:
            for i, link in enumerate(chapter_links):
                if i < offset:
                    continue
                if limit is not None and len(chapters) >= limit:
                    break
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = f"{AO3_BASE}{href}"
                ch_title = link.get_text(strip=True)
                chapters.append(
                    Chapter(
                        index=i,
                        title=ch_title,
                        url=f"{href}?view_adult=true",
                        status=ChapterStatus.PENDING,
                    )
                )

        meta.chapter_count = len(chapters)
        return Story(metadata=meta, chapters=chapters)

    async def _series_story(self, url: str, offset: int, limit: int | None) -> Story:
        series_id = self._series_id(url)
        meta = await self._series_metadata(url)

        series_url = f"{AO3_BASE}/series/{series_id}"
        response = await self.client.get(series_url)
        soup = BeautifulSoup(response.text, "lxml")

        work_links = soup.select("ul.series li.work h4 a:first-child")
        chapters = []
        for i, link in enumerate(work_links):
            if i < offset:
                continue
            if limit is not None and len(chapters) >= limit:
                break
            href = link.get("href", "")
            if not href.startswith("http"):
                href = f"{AO3_BASE}{href}"
            ch_title = link.get_text(strip=True)
            # For series, each "chapter" is actually a complete work
            # We'll download the entire-work view
            work_id = re.search(r"/works/(\d+)", href)
            if work_id:
                full_url = f"{AO3_BASE}/works/{work_id.group(1)}?view_adult=true&view_full_work=true"
            else:
                full_url = href
            chapters.append(
                Chapter(
                    index=i,
                    title=ch_title,
                    url=full_url,
                    status=ChapterStatus.PENDING,
                )
            )

        meta.chapter_count = len(chapters)
        return Story(metadata=meta, chapters=chapters)

    async def get_chapter(self, url: str) -> Chapter:
        response = await self.client.get(url)
        soup = BeautifulSoup(response.text, "lxml")

        # Chapter title
        title_tag = soup.select_one("h3.title")
        if not title_tag:
            title_tag = soup.select_one("h2.title")
        title = title_tag.get_text(strip=True) if title_tag else "Chapter"

        # Chapter content - look for the chapter div
        content_div = soup.select_one("div#chapters div.userstuff")
        if content_div is None:
            # Full work view - may have multiple chapters
            content_div = soup.select_one("div.userstuff[role='article']")
        if content_div is None:
            content_div = soup.select_one("div.userstuff")
        if content_div is None:
            raise ParseError(f"Could not find chapter content at {url}")

        # Remove AO3 landmark headings
        for landmark in content_div.select("h3.landmark"):
            landmark.decompose()

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
