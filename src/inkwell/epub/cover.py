"""Cover image generation using Pillow."""

from __future__ import annotations

import io
import textwrap

from PIL import Image, ImageDraw, ImageFont


def generate_cover(title: str, author: str, width: int = 600, height: int = 900) -> bytes:
    """Generate a simple cover image with title and author text."""
    img = Image.new("RGB", (width, height), color="#1a1a2e")
    draw = ImageDraw.Draw(img)

    # Draw a decorative band
    band_y = height // 3
    band_height = height // 3
    draw.rectangle(
        [(0, band_y), (width, band_y + band_height)],
        fill="#16213e",
    )

    # Draw accent lines
    draw.line([(40, band_y), (width - 40, band_y)], fill="#e94560", width=3)
    draw.line(
        [(40, band_y + band_height), (width - 40, band_y + band_height)],
        fill="#e94560",
        width=3,
    )

    # Use default font (no external font files needed)
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
        author_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except (OSError, IOError):
        title_font = ImageFont.load_default()
        author_font = ImageFont.load_default()

    # Wrap and draw title
    wrapped_title = textwrap.fill(title, width=25)
    title_bbox = draw.multiline_textbbox((0, 0), wrapped_title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    title_x = (width - title_w) // 2
    title_y = band_y + (band_height - title_h) // 2 - 20
    draw.multiline_text(
        (title_x, title_y), wrapped_title, fill="white", font=title_font, align="center"
    )

    # Draw author below the band
    author_text = f"by {author}"
    author_bbox = draw.textbbox((0, 0), author_text, font=author_font)
    author_w = author_bbox[2] - author_bbox[0]
    author_x = (width - author_w) // 2
    author_y = band_y + band_height + 30
    draw.text((author_x, author_y), author_text, fill="#aaa", font=author_font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
