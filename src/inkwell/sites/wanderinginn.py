"""Wandering Inn site handler.

Uses curl_cffi to bypass Cloudflare protection on wanderinginn.com.
"""

from __future__ import annotations

import re
from typing import ClassVar

import anyio
from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests

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


@register
class WanderingInnHandler(SiteHandler):
    site_name: ClassVar[str] = "Wandering Inn"
    url_patterns: ClassVar[list[str]] = ["wanderinginn.com"]

    async def _fetch(self, url: str) -> str:
        """Fetch a URL using curl_cffi to bypass Cloudflare."""
        response = await anyio.to_thread.run_sync(
            lambda: cf_requests.get(url, impersonate="chrome", timeout=30)
        )
        if response.status_code != 200:
            raise NetworkError(f"HTTP {response.status_code} for {url}")
        return response.text

    async def get_metadata(self, url: str) -> StoryMetadata:
        html = await self._fetch(url)
        soup = BeautifulSoup(html, "lxml")

        # Get title from page
        title_tag = soup.select_one("title")
        title = "The Wandering Inn"
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if " - " in title_text:
                title = title_text.split(" - ")[1]

        # Author is pirateaba
        author = "pirateaba"

        # Try to get summary from meta description
        summary = ""
        meta_desc = soup.select_one('meta[property="og:description"]')
        if meta_desc:
            summary = str(meta_desc.get("content", ""))

        # Get cover from meta image
        cover_url = None
        meta_img = soup.select_one('meta[property="og:image"]')
        if meta_img:
            cover_url = str(meta_img.get("content")) if meta_img.get("content") else None

        # Count chapters from table of contents
        toc_url = url.rstrip("/") + "/table-of-contents/"
        try:
            toc_html = await self._fetch(toc_url)
            toc_soup = BeautifulSoup(toc_html, "lxml")
            chapter_entries = toc_soup.select(".chapter-entry")
            chapter_count = len(chapter_entries)
        except Exception:
            chapter_count = 0

        return StoryMetadata(
            title=title,
            author=author,
            url=url,
            summary=summary,
            cover_url=cover_url,
            tags=["Fantasy", "LitRPG"],
            status=StoryStatus.ONGOING,
            chapter_count=chapter_count,
            word_count=0,  # Will calculate later
            site_name="Wandering Inn",
            story_id="wandering-inn",
        )

    async def get_story(self, url: str, offset: int = 0, limit: int | None = None) -> Story:
        meta = await self.get_metadata(url)

        # Fetch chapter list from table of contents
        toc_url = url.rstrip("/") + "/table-of-contents/"
        toc_html = await self._fetch(toc_url)
        soup = BeautifulSoup(toc_html, "lxml")

        # Find all chapter entries
        chapter_entries = soup.select(".chapter-entry")
        chapters = []

        for i, entry in enumerate(chapter_entries):
            if i < offset:
                continue
            if limit is not None and len(chapters) >= limit:
                break

            # Get chapter link
            link = entry.select_one(".body-web a")
            if not link:
                continue

            ch_url = str(link.get("href", ""))
            ch_title = link.get_text(strip=True)

            # Clean up title
            if not ch_title:
                ch_title = f"Chapter {i + 1}"

            chapters.append(
                Chapter(
                    index=i,
                    title=ch_title,
                    url=ch_url,
                    status=ChapterStatus.PENDING,
                )
            )

        meta.chapter_count = len(chapters)
        return Story(metadata=meta, chapters=chapters)

    async def get_chapter(self, url: str) -> Chapter:
        html = await self._fetch(url)
        soup = BeautifulSoup(html, "lxml")

        # Get chapter title from <title> tag
        title_tag = soup.select_one("title")
        title = "Chapter"
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if " - " in title_text:
                title = title_text.split(" - ", 1)[0]
            else:
                title = title_text

        # Get chapter content - look for the main content area
        content_div = None

        # First try the article content
        article = soup.select_one("article.twi-article")
        if article:
            content_div = article
        else:
            # Try the Elementor post content widget
            content_div = soup.select_one(".elementor-widget-theme-post-content")

        if content_div is None:
            raise ParseError(f"Could not find chapter content at {url}")

        # Remove unwanted elements
        for unwanted in content_div.select(
            ".sharedaddy, .jp-relatedposts, nav, .post-navigation, "
            ".wpdiscuz_top_clearing, #wpdcom, .chapter-announcments, "
            ".elementor-shortcode"
        ):
            unwanted.decompose()

        # Extract images
        images = []
        for img in content_div.find_all("img"):
            src = str(img.get("src", ""))
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
