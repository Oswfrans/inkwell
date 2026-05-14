"""Download state persistence for resume support."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from loguru import logger

from inkwell.core.config import cache_dir
from inkwell.core.models import Chapter, ChapterStatus, ImageRef, Story, StoryMetadata


def _cache_path(url: str) -> Path:
    url_hash = sha256(url.encode()).hexdigest()[:16]
    return cache_dir() / "downloads" / f"{url_hash}.json"


def save_state(story: Story) -> None:
    """Persist download state for resume support."""
    path = _cache_path(story.metadata.url)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "metadata": story.metadata.model_dump(mode="json"),
        "chapters": [
            {
                "index": ch.index,
                "title": ch.title,
                "url": ch.url,
                "html_content": ch.html_content,
                "word_count": ch.word_count,
                "date_published": ch.date_published.isoformat() if ch.date_published else None,
                "images": [
                    {"url": img.url, "filename": img.filename, "media_type": img.media_type}
                    for img in ch.images
                ],
                "status": ch.status.value,
            }
            for ch in story.chapters
        ],
    }
    path.write_text(json.dumps(data, indent=2))
    logger.debug(f"Saved download state to {path}")


def load_state(url: str) -> dict | None:
    """Load previous download state if it exists."""
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to read cache: {exc}")
        return None


def load_story_state(url: str) -> Story | None:
    """Load previous download state as a Story object."""
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        chapters = []
        for ch_data in data.get("chapters", []):
            date_pub = None
            if ch_data.get("date_published"):
                try:
                    raw = ch_data["date_published"]
                    if isinstance(raw, str):
                        raw = raw.replace("Z", "+00:00")
                    date_pub = datetime.fromisoformat(raw)
                except (ValueError, TypeError):
                    pass
            chapters.append(
                Chapter(
                    index=ch_data["index"],
                    title=ch_data["title"],
                    url=ch_data["url"],
                    html_content=ch_data.get("html_content", ""),
                    word_count=ch_data.get("word_count", 0),
                    date_published=date_pub,
                    images=[
                        ImageRef(**img) for img in ch_data.get("images", [])
                    ],
                    status=ChapterStatus(ch_data.get("status", "pending")),
                )
            )
        meta_data = data.get("metadata", {})
        meta = StoryMetadata.model_validate(meta_data)
        return Story(metadata=meta, chapters=chapters)
    except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
        logger.warning(f"Failed to read cache: {exc}")
        return None


def get_completed_urls(url: str) -> set[str]:
    """Return set of chapter URLs that were already downloaded."""
    cached = load_story_state(url)
    if cached is None:
        return set()
    return {
        ch.url
        for ch in cached.chapters
        if ch.status == ChapterStatus.DOWNLOADED
    }


def clear_state(url: str) -> None:
    """Remove cached state for a URL."""
    path = _cache_path(url)
    if path.exists():
        path.unlink()


def list_incomplete() -> list[dict]:
    """List all incomplete downloads."""
    downloads_dir = cache_dir() / "downloads"
    if not downloads_dir.exists():
        return []
    results = []
    for path in downloads_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            chapters = data.get("chapters", [])
            total = len(chapters)
            done = sum(
                1 for ch in chapters if ch.get("status") == ChapterStatus.DOWNLOADED.value
            )
            if done < total:
                results.append(
                    {
                        "url": data.get("url") or data.get("metadata", {}).get("url", "Unknown"),
                        "title": data.get("title") or data.get("metadata", {}).get("title", "Unknown"),
                        "author": data.get("author") or data.get("metadata", {}).get("author", "Unknown"),
                        "progress": f"{done}/{total}",
                    }
                )
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    return results
