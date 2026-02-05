"""Typer CLI application for Inkwell."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import anyio
import typer
from loguru import logger
from rich.console import Console

from inkwell import __version__
from inkwell.cli.display import (
    console,
    create_progress,
    print_error,
    print_incomplete,
    print_metadata,
    print_sites,
    print_success,
    print_warning,
)
from inkwell.core.cache import get_completed_urls, list_incomplete, save_state
from inkwell.core.config import Config, cache_dir, config_dir
from inkwell.core.models import ChapterStatus
from inkwell.exceptions import InkwellError

app = typer.Typer(
    name="inkwell",
    help="Modern web fiction to EPUB downloader.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def version_callback(value: bool) -> None:
    if value:
        console.print(f"inkwell {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose logging"),
    ] = False,
) -> None:
    """Inkwell: Download web fiction as EPUB."""
    if not verbose:
        logger.disable("inkwell")


async def _download_story(
    url: str,
    output: Path | None,
    dry_run: bool,
    offset: int,
    limit: int | None,
    resume: bool,
) -> None:
    """Core download logic."""
    from inkwell.core.downloader import Downloader
    from inkwell.epub.builder import EpubBuilder
    from inkwell.sites import get_handler

    config = Config.load()

    async with Downloader(config) as dl:
        handler = get_handler(url, dl._client or (await dl._get_client()))

        # Fetch metadata first
        meta = await handler.get_metadata(url)
        print_metadata(meta)

        if dry_run:
            return

        # Get completed chapters for resume
        completed = get_completed_urls(url) if resume else set()
        if completed:
            print_warning(f"Resuming: {len(completed)} chapters already downloaded")

        # Download story
        story = await handler.get_story(url, offset=offset, limit=limit)

        # Download chapters with progress
        with create_progress() as progress:
            task = progress.add_task("Downloading chapters", total=len(story.chapters))
            for chapter in story.chapters:
                if chapter.url in completed:
                    chapter.status = ChapterStatus.DOWNLOADED
                    progress.advance(task)
                    continue
                try:
                    downloaded = await handler.get_chapter(chapter.url)
                    chapter.html_content = downloaded.html_content
                    chapter.word_count = downloaded.word_count
                    chapter.images = downloaded.images
                    chapter.status = ChapterStatus.DOWNLOADED

                    # Download images
                    if config.epub.include_images:
                        for img in chapter.images:
                            try:
                                img.data = await dl.get_bytes(img.url)
                            except Exception as exc:
                                logger.warning(f"Failed to download image {img.url}: {exc}")

                except Exception as exc:
                    chapter.status = ChapterStatus.FAILED
                    print_warning(f"Failed to download '{chapter.title}': {exc}")

                save_state(story)
                progress.advance(task)

        # Build EPUB
        downloaded_count = sum(
            1 for ch in story.chapters if ch.status == ChapterStatus.DOWNLOADED
        )
        if downloaded_count == 0:
            print_error("No chapters were downloaded successfully.")
            raise typer.Exit(1)

        # Filter to only downloaded chapters
        story.chapters = [
            ch for ch in story.chapters if ch.status == ChapterStatus.DOWNLOADED
        ]

        builder = EpubBuilder(config)
        epub_path = builder.build(story, output)
        print_success(f"Saved: {epub_path} ({downloaded_count} chapters)")


@app.command()
def download(
    url: Annotated[str, typer.Argument(help="Story URL to download")],
    output: Annotated[
        Optional[Path], typer.Option("--output", "-o", help="Output EPUB file path")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show metadata without downloading")
    ] = False,
    offset: Annotated[
        int, typer.Option("--offset", help="Skip first N chapters")
    ] = 0,
    limit: Annotated[
        Optional[int], typer.Option("--limit", help="Download at most N chapters")
    ] = None,
    resume: Annotated[
        bool, typer.Option("--resume", help="Resume incomplete download")
    ] = False,
) -> None:
    """Download a story and convert to EPUB."""
    try:
        anyio.run(_download_story, url, output, dry_run, offset, limit, resume)
    except InkwellError as exc:
        print_error(str(exc))
        raise typer.Exit(1)


@app.command()
def batch(
    file: Annotated[Path, typer.Argument(help="File containing URLs (one per line)")],
    output_dir: Annotated[
        Optional[Path], typer.Option("--output-dir", "-o", help="Output directory")
    ] = None,
    resume: Annotated[
        bool, typer.Option("--resume", help="Resume incomplete downloads")
    ] = False,
) -> None:
    """Download multiple stories from a URL list file."""
    if not file.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(1)

    urls = [
        line.strip()
        for line in file.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not urls:
        print_error("No URLs found in file.")
        raise typer.Exit(1)

    console.print(f"Found [bold]{len(urls)}[/bold] URLs to download.\n")

    for i, url in enumerate(urls, 1):
        console.rule(f"[bold cyan]Story {i}/{len(urls)}[/bold cyan]")
        try:
            anyio.run(_download_story, url, output_dir, False, 0, None, resume)
        except (InkwellError, Exception) as exc:
            print_error(f"Failed: {url} - {exc}")
            continue


@app.command()
def info(
    url: Annotated[str, typer.Argument(help="Story URL to inspect")],
) -> None:
    """Show story metadata without downloading."""
    async def _info() -> None:
        from inkwell.core.downloader import Downloader
        from inkwell.sites import get_handler

        config = Config.load()
        async with Downloader(config) as dl:
            handler = get_handler(url, dl._client or (await dl._get_client()))
            meta = await handler.get_metadata(url)
            print_metadata(meta)

    try:
        anyio.run(_info)
    except InkwellError as exc:
        print_error(str(exc))
        raise typer.Exit(1)


@app.command()
def sites() -> None:
    """List supported sites."""
    from inkwell.sites import get_all_handlers

    handlers = get_all_handlers()
    print_sites(handlers)


@app.command(name="resume-list")
def resume_list() -> None:
    """Show incomplete downloads that can be resumed."""
    items = list_incomplete()
    print_incomplete(items)


@app.command(name="config-path")
def config_path() -> None:
    """Show config and cache directory paths."""
    console.print(f"[bold]Config:[/bold] {config_dir()}")
    console.print(f"[bold]Cache:[/bold]  {cache_dir()}")


def run() -> None:
    app()
