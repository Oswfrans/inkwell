# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Inkwell is a CLI tool that downloads web fiction from various sites and converts them to EPUB format. It uses async HTTP (httpx + HTTP/2), BeautifulSoup for scraping, and ebooklib for EPUB generation.

## Development Commands

```bash
uv sync                  # Install dependencies
uv run inkwell            # Run the CLI
uv run inkwell download <url>   # Download a story
uv run inkwell --help     # Show all commands
```

No test suite or linter is currently configured.

## Architecture

**Pipeline:** CLI (`cli/app.py`) → site handler (`sites/`) → downloader (`core/downloader.py`) → EPUB builder (`epub/builder.py`)

### Site Handler System (`src/inkwell/sites/`)

Site handlers are auto-discovered via `pkgutil.iter_modules` in `sites/__init__.py`. To add a new site:

1. Create `sites/mysite.py`
2. Subclass `SiteHandler` (ABC) and implement `get_metadata()`, `get_story()`, `get_chapter()`
3. Decorate the class with `@register` — auto-discovery handles the rest

Each handler declares `site_name` and `url_patterns` (ClassVar). URL matching uses simple substring checks via `can_handle()`.

Current handlers: Royal Road, AO3, FanFiction.Net, XenForo.

### Core Data Flow

- `SiteHandler.get_story()` returns a `Story` (Pydantic model) containing `StoryMetadata` + list of `Chapter`
- `cli/app.py` iterates chapters, calls `handler.get_chapter()` to populate `html_content`, then `EpubBuilder.build()` assembles the EPUB
- Download state is persisted to disk (`core/cache.py`) after each chapter for resume support

### Key Design Decisions

- **Async throughout**: httpx.AsyncClient with HTTP/2, rate limiting via asyncio lock, run via `anyio.run()`
- **Pydantic models** for all data (Story, Chapter, StoryMetadata, Config) with validation
- **Config**: TOML file loaded from platformdirs config dir (`~/.config/inkwell/inkwell.toml`), Pydantic-based with defaults
- **EPUB generation**: ebooklib with Pillow-generated covers, custom XHTML templates, and embedded CSS
- **Retry/rate-limit**: tenacity for retries, manual rate limiting with configurable delay between requests
