"""Render the README's mermaid blocks to SVG, for the hosted page.

    python demo/render_diagrams.py

GitHub renders the mermaid in `README.md` itself, but a static page cannot, and the
submission asks for an architecture diagram a judge can look at. So the diagrams on the
page are generated from the same fenced blocks the README carries, rather than drawn
again by hand: there is one source for the architecture, and a page that disagrees with
the README is not possible.

It needs a browser and the network, because mermaid is a JavaScript library. That is why
this is a build step run by a person and its output is committed, rather than something
`publish` does — `rollout_marshal/publish.py` reads the committed SVGs and refuses to
build a page without them.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import glob
import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The blocks appear in this order in README.md, and each one becomes this file.
NAMES = ("architecture", "decision-flow")

MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;background:#fff;font-family:system-ui,sans-serif}}</style>
</head><body><div id="d" class="mermaid">{src}</div>
<script type="module">
import mermaid from "{lib}";
mermaid.initialize({{startOnLoad:false, theme:"neutral"}});
await mermaid.run();
</script></body></html>
"""


class RenderError(RuntimeError):
    """A diagram did not come back as SVG."""


def chrome() -> str:
    """The headless shell, not the full browser.

    `chrome --headless=new --dump-dom` never returns here — it hung for the full
    three-minute timeout on a page that renders in half a second — while
    `chrome-headless-shell` dumps the same DOM immediately. Prefer the shell and only
    fall back to the browser.
    """
    cache = Path.home() / ".cache/ms-playwright"
    for pattern in (
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium-*/chrome-linux64/chrome",
    ):
        hits = sorted(glob.glob(str(cache / pattern)))
        if hits:
            return hits[-1]
    raise RenderError("no headless chromium under ~/.cache/ms-playwright")


def blocks(readme: Path) -> list[str]:
    """Every ```mermaid fence in the README, in order."""
    found = re.findall(r"```mermaid\n(.*?)```", readme.read_text(), flags=re.S)
    if len(found) != len(NAMES):
        raise RenderError(f"README has {len(found)} mermaid blocks, expected {len(NAMES)}")
    return found


def render(src: str) -> str:
    """One mermaid source in, one <svg> element out."""
    # ignore_cleanup_errors: chrome writes into its profile as it exits, so the rmtree
    # races it and raises "Directory not empty" over a diagram that rendered fine.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        page = Path(tmp) / "d.html"
        page.write_text(PAGE.format(src=html.escape(src), lib=MERMAID))
        out = subprocess.run(
            [
                chrome(),
                "--no-sandbox",
                "--disable-gpu",
                f"--user-data-dir={tmp}/profile",
                "--virtual-time-budget=20000",
                "--window-size=2000,4000",
                "--dump-dom",
                page.as_uri(),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    dom = out.stdout
    m = re.search(r"(<svg[^>]*aria-roledescription.*?</svg>)", dom, flags=re.S)
    if not m:
        # mermaid writes its parse errors into the same div, so say what it said.
        detail = re.search(r'class="error-text"[^>]*>(.*?)<', dom, flags=re.S)
        raise RenderError(f"no svg rendered: {detail.group(1) if detail else out.stderr[-400:]}")
    svg = m.group(1)
    if "Syntax error" in svg:
        raise RenderError("mermaid drew a syntax error rather than the diagram")
    return _sized(svg)


def _sized(svg: str) -> str:
    """Give the element its intrinsic size.

    mermaid writes `width="100%"` and no height, and an inline SVG like that is 150px
    tall in HTML whatever its viewBox says. The numbers come from the viewBox, so the
    diagram keeps the proportions mermaid laid out.
    """
    # A sequence diagram's viewBox does not start at the origin, so match four numbers
    # rather than assuming "0 0" — the flowchart's does and the sequence chart's does not.
    box = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', svg)
    if not box:
        raise RenderError("rendered svg carries no viewBox to size it from")
    w, h = box.group(1), box.group(2)
    svg = re.sub(r'\swidth="[^"]*"', "", svg, count=1)
    svg = re.sub(r'\sstyle="[^"]*"', "", svg, count=1)
    return svg.replace(
        "<svg ", f'<svg width="{w}" height="{h}" style="max-width:100%;height:auto" ', 1
    )


def main() -> int:
    assets = ROOT / "docs" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name, src in zip(NAMES, blocks(ROOT / "README.md")):
        svg = render(src)
        path = assets / f"{name}.svg"
        path.write_text(svg + "\n")
        print(f"{path.relative_to(ROOT)}  {len(svg):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
