"""Default CSS styles for EPUB output."""

DEFAULT_CSS = """\
body {
    font-family: Georgia, "Times New Roman", serif;
    line-height: 1.6;
    margin: 1em;
    color: #222;
}

h1 {
    font-size: 1.8em;
    margin-bottom: 0.5em;
    text-align: center;
}

h2 {
    font-size: 1.4em;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}

h3 {
    font-size: 1.2em;
    margin-top: 1em;
}

p {
    margin: 0.5em 0;
    text-indent: 1.5em;
}

p:first-of-type {
    text-indent: 0;
}

blockquote {
    margin: 1em 2em;
    padding-left: 1em;
    border-left: 3px solid #ccc;
    font-style: italic;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 2em auto;
    width: 40%;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
}

.chapter-title {
    text-align: center;
    margin-bottom: 2em;
}

.story-info {
    text-align: center;
    margin: 2em 0;
}

.story-info .author {
    font-size: 1.2em;
    font-style: italic;
}

.story-info .summary {
    margin-top: 1em;
    text-align: left;
    font-style: italic;
}

.story-info .tags {
    margin-top: 1em;
    font-size: 0.9em;
    color: #666;
}
"""
