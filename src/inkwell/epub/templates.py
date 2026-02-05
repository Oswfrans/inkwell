"""XHTML templates for EPUB chapters and frontmatter."""

from __future__ import annotations

from xml.sax.saxutils import escape

from inkwell.core.models import StoryMetadata


def frontmatter_xhtml(meta: StoryMetadata) -> str:
    """Generate the title page XHTML."""
    tags_html = ""
    if meta.tags:
        tag_list = ", ".join(escape(t) for t in meta.tags)
        tags_html = f'<p class="tags">Tags: {tag_list}</p>'

    summary_html = ""
    if meta.summary:
        summary_html = f'<div class="summary"><p>{escape(meta.summary)}</p></div>'

    status_html = ""
    if meta.status:
        status_html = f"<p>Status: {escape(meta.status.value.title())}</p>"

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{escape(meta.language)}">
<head>
    <title>{escape(meta.title)}</title>
    <link rel="stylesheet" type="text/css" href="style/default.css"/>
</head>
<body>
    <div class="story-info">
        <h1>{escape(meta.title)}</h1>
        <p class="author">by {escape(meta.author)}</p>
        {summary_html}
        {status_html}
        {tags_html}
    </div>
</body>
</html>"""


def chapter_xhtml(title: str, content: str, language: str = "en") -> str:
    """Generate chapter XHTML wrapping the chapter's HTML content."""
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{escape(language)}">
<head>
    <title>{escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="style/default.css"/>
</head>
<body>
    <div class="chapter-title">
        <h1>{escape(title)}</h1>
    </div>
    <div class="chapter-content">
        {content}
    </div>
</body>
</html>"""
