"""Pydantic data models for stories, chapters, and metadata."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class StoryStatus(str, Enum):
    ONGOING = "ongoing"
    COMPLETE = "complete"
    HIATUS = "hiatus"
    UNKNOWN = "unknown"


class ImageRef(BaseModel):
    """Reference to an image used in a chapter or as a cover."""

    url: str
    filename: str
    media_type: str = "image/jpeg"
    data: bytes | None = None


class ChapterStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Chapter(BaseModel):
    """A single chapter of a story."""

    index: int
    title: str
    url: str
    html_content: str = ""
    word_count: int = 0
    date_published: datetime | None = None
    images: list[ImageRef] = Field(default_factory=list)
    status: ChapterStatus = ChapterStatus.PENDING


class StoryMetadata(BaseModel):
    """Metadata about a story without full chapter content."""

    title: str
    author: str
    url: str
    summary: str = ""
    cover_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    language: str = "en"
    status: StoryStatus = StoryStatus.UNKNOWN
    chapter_count: int = 0
    word_count: int = 0
    date_published: datetime | None = None
    date_updated: datetime | None = None
    site_name: str = ""
    story_id: str = ""


class Story(BaseModel):
    """A complete story with metadata and chapters."""

    metadata: StoryMetadata
    chapters: list[Chapter] = Field(default_factory=list)

    @property
    def filename(self) -> str:
        safe_title = "".join(
            c if c.isalnum() or c in " -_" else "" for c in self.metadata.title
        ).strip()
        safe_author = "".join(
            c if c.isalnum() or c in " -_" else "" for c in self.metadata.author
        ).strip()
        return f"{safe_title} - {safe_author}.epub"
