"""Rich display helpers for CLI output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from inkwell.core.models import StoryMetadata

console = Console()
error_console = Console(stderr=True)


def print_metadata(meta: StoryMetadata) -> None:
    """Display story metadata in a rich panel."""
    lines = [
        f"[bold]Author:[/bold] {meta.author}",
        f"[bold]Status:[/bold] {meta.status.value.title()}",
        f"[bold]Chapters:[/bold] {meta.chapter_count}",
    ]
    if meta.word_count:
        lines.append(f"[bold]Words:[/bold] {meta.word_count:,}")
    if meta.tags:
        lines.append(f"[bold]Tags:[/bold] {', '.join(meta.tags[:10])}")
    if meta.date_published:
        lines.append(f"[bold]Published:[/bold] {meta.date_published:%Y-%m-%d}")
    if meta.date_updated:
        lines.append(f"[bold]Updated:[/bold] {meta.date_updated:%Y-%m-%d}")
    if meta.summary:
        summary = meta.summary[:300] + ("..." if len(meta.summary) > 300 else "")
        lines.append(f"\n[italic]{summary}[/italic]")

    panel = Panel(
        "\n".join(lines),
        title=f"[bold cyan]{meta.title}[/bold cyan]",
        subtitle=f"[dim]{meta.site_name}[/dim]",
        border_style="cyan",
    )
    console.print(panel)


def print_sites(handlers: list) -> None:
    """Display supported sites in a table."""
    table = Table(title="Supported Sites", border_style="cyan")
    table.add_column("Site", style="bold")
    table.add_column("URL Patterns")
    for handler in handlers:
        patterns = ", ".join(handler.url_patterns)
        table.add_row(handler.site_name, patterns)
    console.print(table)


def print_incomplete(items: list[dict]) -> None:
    """Display incomplete downloads in a table."""
    if not items:
        console.print("[dim]No incomplete downloads found.[/dim]")
        return
    table = Table(title="Incomplete Downloads", border_style="yellow")
    table.add_column("Title", style="bold")
    table.add_column("Author")
    table.add_column("Progress")
    table.add_column("URL", style="dim")
    for item in items:
        table.add_row(item["title"], item["author"], item["progress"], item["url"])
    console.print(table)


def create_progress() -> Progress:
    """Create a progress bar for chapter downloads."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def print_success(message: str) -> None:
    console.print(f"[bold green]{message}[/bold green]")


def print_error(message: str) -> None:
    error_console.print(f"[bold red]Error:[/bold red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")
