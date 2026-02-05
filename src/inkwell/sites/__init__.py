"""Site handler registry with auto-discovery."""

from __future__ import annotations

import importlib
import pkgutil
from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

from inkwell.core.models import Chapter, Story, StoryMetadata


class SiteHandler(ABC):
    """Abstract base class for site-specific scrapers."""

    site_name: ClassVar[str]
    url_patterns: ClassVar[list[str]]

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return any(pattern in url for pattern in cls.url_patterns)

    @abstractmethod
    async def get_metadata(self, url: str) -> StoryMetadata:
        """Fetch story metadata without downloading chapters."""

    @abstractmethod
    async def get_story(self, url: str, offset: int = 0, limit: int | None = None) -> Story:
        """Fetch full story with all chapters."""

    @abstractmethod
    async def get_chapter(self, url: str) -> Chapter:
        """Fetch a single chapter by URL."""


# Global registry
_registry: list[type[SiteHandler]] = []


def register(cls: type[SiteHandler]) -> type[SiteHandler]:
    """Decorator to register a site handler."""
    _registry.append(cls)
    return cls


def get_handler(url: str, client: httpx.AsyncClient) -> SiteHandler:
    """Return an instantiated handler for the given URL."""
    for handler_cls in _registry:
        if handler_cls.can_handle(url):
            return handler_cls(client)
    from inkwell.exceptions import UnsupportedSiteError
    raise UnsupportedSiteError(f"No handler found for URL: {url}")


def get_all_handlers() -> list[type[SiteHandler]]:
    """Return all registered handler classes."""
    return list(_registry)


def _discover() -> None:
    """Import all site modules to trigger @register decorators."""
    package = importlib.import_module("inkwell.sites")
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        importlib.import_module(f"inkwell.sites.{info.name}")


_discover()
