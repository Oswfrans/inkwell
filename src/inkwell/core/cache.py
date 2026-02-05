"""Download state persistence for resume support."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from loguru import logger

from inkwell.core.config import cache_dir
from inkwell.core.models import ChapterStatus, Story


def _cache_path(url: str) -> Path:
    url_hash = sha256(url.encode()).hexdigest()[:16]
    return cache_dir() / "downloads" / f"{url_hash}.json"


def save_state(story: Story) -> None:
    """Persist download state for resume support."""
    path = _cache_path(story.metadata.url)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "url": story.metadata.url,
        "title": story.metadata.title,
        "author": story.metadata.author,
        "chapters": [
            {
                "index": ch.index,
                "title": ch.title,
                "url": ch.url,
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


def get_completed_urls(url: str) -> set[str]:
    """Return set of chapter URLs that were already downloaded."""
    state = load_state(url)
    if state is None:
        return set()
    return {
        ch["url"]
        for ch in state.get("chapters", [])
        if ch.get("status") == ChapterStatus.DOWNLOADED.value
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
                        "url": data["url"],
                        "title": data.get("title", "Unknown"),
                        "author": data.get("author", "Unknown"),
                        "progress": f"{done}/{total}",
                    }
                )
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    return results
