"""EPUB builder using ebooklib."""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub
from loguru import logger

from inkwell.core.config import Config
from inkwell.core.models import Story
from inkwell.epub.cover import generate_cover
from inkwell.epub.styles import DEFAULT_CSS
from inkwell.epub.templates import chapter_xhtml, frontmatter_xhtml


class EpubBuilder:
    """Builds an EPUB file from a Story object."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def build(self, story: Story, output_path: Path | None = None) -> Path:
        """Build an EPUB file and return the output path."""
        book = epub.EpubBook()
        meta = story.metadata

        # Metadata
        book.set_identifier(f"inkwell-{meta.site_name}-{meta.story_id}")
        book.set_title(meta.title)
        book.set_language(meta.language)
        book.add_author(meta.author)
        if meta.summary:
            book.add_metadata("DC", "description", meta.summary)

        # CSS
        style = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=DEFAULT_CSS.encode("utf-8"),
        )
        book.add_item(style)

        # Cover
        if self.config.epub.include_cover:
            cover_data = generate_cover(meta.title, meta.author)
            book.set_cover("images/cover.jpg", cover_data)

        # Frontmatter
        front_content = frontmatter_xhtml(meta)
        frontmatter = epub.EpubHtml(
            title="Title Page",
            file_name="frontmatter.xhtml",
            lang=meta.language,
        )
        frontmatter.set_content(front_content.encode("utf-8"))
        frontmatter.add_item(style)
        book.add_item(frontmatter)

        # Chapters
        epub_chapters = []
        for ch in story.chapters:
            content = chapter_xhtml(ch.title, ch.html_content, meta.language)
            epub_ch = epub.EpubHtml(
                title=ch.title,
                file_name=f"chapter_{ch.index:04d}.xhtml",
                lang=meta.language,
            )
            epub_ch.set_content(content.encode("utf-8"))
            epub_ch.add_item(style)
            book.add_item(epub_ch)
            epub_chapters.append(epub_ch)

            # Add chapter images
            for img in ch.images:
                if img.data:
                    epub_img = epub.EpubItem(
                        uid=f"img_{ch.index}_{img.filename}",
                        file_name=f"images/{img.filename}",
                        media_type=img.media_type,
                        content=img.data,
                    )
                    book.add_item(epub_img)

        # Table of contents
        book.toc = [frontmatter, *epub_chapters]

        # Spine
        book.spine = ["nav", frontmatter, *epub_chapters]

        # Navigation
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Write file
        if output_path is None:
            output_path = self.config.download.output_dir / story.filename
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        epub.write_epub(str(output_path), book)
        logger.info(f"EPUB saved to {output_path}")
        return output_path
