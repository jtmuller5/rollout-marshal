"""The public build write-up, rendered from `notes/build-writeup.md`.

The hackathon scores a public post about how the project was built, and only scores it
when the post says it was made to enter the hackathon. That sentence is therefore a
precondition here rather than a nicety: `render` refuses a source that does not carry it,
so the page cannot be published without the thing that makes it count.

The prose lives in markdown and the page is generated from it, for the same reason the
hosted page is generated from the decision log: one source, so the published words and the
words in the repository cannot drift apart.

    python -m rollout_marshal.cli writeup

The markdown subset is deliberately small, because the source is one hand-written essay
and not arbitrary input: headings, paragraphs, emphasis, inline code and links. Anything
outside it is passed through escaped rather than guessed at.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from .publish import CSS, REPO

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "notes" / "build-writeup.md"
OUT = ROOT / "docs" / "build-log"

# The bonus is scored on this sentence being present. Rules, stage three: the content only
# counts when it says it was created for the purposes of entering the hackathon.
DISCLOSURE = "created for the purposes of entering the All Things Agentic Hackathon"

# Both are required: the hackathon disclosure above, and the standing rule that anything
# this agent publishes says an agent wrote it and who it works for.
AUTHORSHIP = "autonomous agent working for Joe Muller"


class WriteupError(RuntimeError):
    """The write-up could not be built from what is on disk."""


def _inline(text: str) -> str:
    """Escape first, then re-introduce the few inline forms the source uses."""
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"&lt;(https?://[^&\s]+)&gt;", r'<a href="\1">\1</a>', out)
    return out


def to_html(md: str) -> tuple[str, str]:
    """Return (title, body html) for the supported subset of markdown."""
    title = ""
    parts: list[str] = []
    for block in re.split(r"\n\s*\n", md.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("# "):
            title = block[2:].strip()
            parts.append(f"<h1>{_inline(title)}</h1>")
        elif block.startswith("## "):
            parts.append(f"<h2>{_inline(block[3:].strip())}</h2>")
        else:
            text = " ".join(block.split())
            # A whole paragraph in italics is a disclosure, not emphasis: both the
            # hackathon sentence and the authorship line are written that way.
            if text.startswith("*") and text.endswith("*") and not text.startswith("**"):
                parts.append(f'<p class="disclosure">{_inline(text.strip("*"))}</p>')
            else:
                parts.append(f"<p>{_inline(text)}</p>")
    if not title:
        raise WriteupError("the source has no `# ` title")
    return title, "\n".join(parts)


def render(md: str) -> str:
    if DISCLOSURE not in md:
        raise WriteupError(
            f"the write-up must contain the hackathon disclosure: {DISCLOSURE!r}"
        )
    if AUTHORSHIP not in md:
        raise WriteupError(f"the write-up must say who wrote it: {AUTHORSHIP!r}")
    title, body = to_html(md)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="How Rollout Marshal was built: an ADK agent on Gemini
 3.5 that halts a staged Google Play rollout against a halt number declared first.">
<style>{CSS}</style>
</head><body><main>
{body}
<footer>
<p><a href="{REPO}">github.com/jtmuller5/rollout-marshal</a> &middot; MIT &middot;
<a href="../">the project, and its live decision log</a></p>
</footer>
</main></body></html>
"""


def publish_writeup(out: Path | None = None, source: Path | None = None) -> Path:
    src = source or SOURCE
    if not src.exists():
        raise WriteupError(f"{src} is missing")
    target = Path(out or OUT)
    target.mkdir(parents=True, exist_ok=True)
    page = target / "index.html"
    page.write_text(render(src.read_text()))
    return page
