"""XenForo-based site handler (SpaceBattles, SufficientVelocity, QuestionableQuesting)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import ClassVar
from urllib.parse import urljoin

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


@register
class XenForoHandler(SiteHandler):
    site_name: ClassVar[str] = "XenForo (SpaceBattles, SV, QQ)"
    url_patterns: ClassVar[list[str]] = [
        "forums.spacebattles.com",
        "forums.sufficientvelocity.com",
        "forum.questionablequesting.com",
    ]

    def _base_url(self, url: str) -> str:
        match = re.match(r"(https?://[^/]+)", url)
        return match.group(1) if match else ""

    def _thread_url(self, url: str) -> str:
        """Normalize to threadmarks URL."""
        # Remove page/post references, get base thread URL
        match = re.match(r"(https?://[^/]+/threads/[^/]+/)", url)
        if match:
            return match.group(1)
        # Handle URLs without trailing slash
        match = re.match(r"(https?://[^/]+/threads/[^?#]+)", url)
        if match:
            return match.group(1).rstrip("/") + "/"
        return url

    def _threadmarks_url(self, url: str) -> str:
        base = self._thread_url(url)
        return f"{base}threadmarks"

    def _reader_url(self, url: str) -> str:
        base = self._thread_url(url)
        return f"{base}reader/"

    async def get_metadata(self, url: str) -> StoryMetadata:
        thread_url = self._thread_url(url)
        base = self._base_url(url)

        response = await self.client.get(thread_url)
        soup = BeautifulSoup(response.text, "lxml")

        # Title
        title_tag = soup.select_one("h1.p-title-value")
        if title_tag:
            # Remove prefix labels
            for span in title_tag.select("span"):
                span.decompose()
            title = title_tag.get_text(strip=True)
        else:
            title = "Unknown"

        # Author from first post
        author_tag = soup.select_one("a.username")
        author = author_tag.get_text(strip=True) if author_tag else "Unknown"

        # Tags/prefixes
        tags = [
            tag.get_text(strip=True)
            for tag in soup.select("a.tagItem")
        ]

        # Get threadmarks to count chapters
        tm_url = self._threadmarks_url(url)
        tm_response = await self.client.get(tm_url)
        tm_soup = BeautifulSoup(tm_response.text, "lxml")

        threadmark_items = tm_soup.select(
            "div.structItem--threadmark a"
        )
        chapter_count = len(threadmark_items)

        # Thread ID
        thread_id_match = re.search(r"/threads/[^/]*?\.?(\d+)/?", thread_url)
        story_id = thread_id_match.group(1) if thread_id_match else ""

        # Determine site name
        if "spacebattles" in url:
            site_name = "SpaceBattles"
        elif "sufficientvelocity" in url:
            site_name = "Sufficient Velocity"
        elif "questionablequesting" in url:
            site_name = "Questionable Questing"
        else:
            site_name = "XenForo"

        return StoryMetadata(
            title=title,
            author=author,
            url=url,
            tags=tags,
            status=StoryStatus.UNKNOWN,
            chapter_count=chapter_count,
            site_name=site_name,
            story_id=story_id,
        )

    async def get_story(self, url: str, offset: int = 0, limit: int | None = None) -> Story:
        meta = await self.get_metadata(url)
        base = self._base_url(url)

        # Fetch threadmarks page
        tm_url = self._threadmarks_url(url)
        response = await self.client.get(tm_url)
        soup = BeautifulSoup(response.text, "lxml")

        threadmark_links = soup.select("div.structItem--threadmark a")
        chapters = []

        for i, link in enumerate(threadmark_links):
            if i < offset:
                continue
            if limit is not None and len(chapters) >= limit:
                break

            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = urljoin(base + "/", href)

            ch_title = link.get_text(strip=True)
            if not ch_title:
                ch_title = f"Chapter {i + 1}"

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
        response = await self.client.get(url)
        soup = BeautifulSoup(response.text, "lxml")

        # Extract the specific post content
        # XenForo URLs with post ID: /posts/12345/ or #post-12345
        post_id_match = re.search(r"post-?(\d+)", url)

        content_div = None
        if post_id_match:
            post_id = post_id_match.group(1)
            post = soup.select_one(f"article[data-content='post-{post_id}']")
            if post:
                content_div = post.select_one("div.bbWrapper")

        if content_div is None:
            # Fallback: get the first post's content with a threadmark
            threadmarked = soup.select_one("article.hasThreadmark div.bbWrapper")
            if threadmarked:
                content_div = threadmarked

        if content_div is None:
            # Last resort: first post
            content_div = soup.select_one("div.bbWrapper")

        if content_div is None:
            raise ParseError(f"Could not find post content at {url}")

        # Extract images
        images = []
        for img in content_div.find_all("img"):
            src = img.get("src", "")
            if src and not src.startswith("data:"):
                filename = re.sub(r"[^\w.]", "_", src.split("/")[-1].split("?")[0])
                if not filename:
                    filename = f"img_{hash(src) & 0xFFFFFF:06x}.jpg"
                images.append(ImageRef(url=src, filename=filename))

        html_content = str(content_div)
        word_count = len(content_div.get_text().split())

        # Try to get title from thread
        title_tag = soup.select_one("h1.p-title-value")
        title = title_tag.get_text(strip=True) if title_tag else "Chapter"

        return Chapter(
            index=0,
            title=title,
            url=url,
            html_content=html_content,
            word_count=word_count,
            images=images,
            status=ChapterStatus.DOWNLOADED,
        )
