#!/usr/bin/env python3
"""Cut the demo video: the script's clock, the recorded picture, the spoken narration.

The script in `notes/demo-script.md` already carries the timing — every `###` heading
names the window that shot occupies. `narrate.py` reads those headings and lays the
voice on them. This reads the same headings and lays the *picture* on them, so the two
cannot drift: one file decides where every second goes.

Picture comes from `demo/cut.json`, one entry per shot:

    "4": {"kind": "clip",  "path": "takes/take-….mp4", "unedited": true}
    "3": {"kind": "still", "path": "docs/assets/architecture.svg"}
    "1": {"kind": "slate", "owed": "Joe · a pan of the Play Console rollout page"}

A shot with no entry becomes a slate too, so the cut is always full length and always
watchable — a missing shot shows as a card naming who owes it, in its own slot, rather
than as a hole that shifts every later beat off the narration.

Three rules the fitting obeys, because the video makes a claim about itself:

- A clip longer than its window is trimmed at the end. That is a length choice, not an
  edit inside the take.
- A clip SHORTER than its window is an error. Freezing the last frame to fill the gap
  would put a still into the middle of something the entry calls an unedited live
  execution. Re-record it at a slower `--dwell`, or move the window in the script.
- `"unedited": true` refuses `"pad"` outright, so the rule above cannot be waived by
  editing the manifest.

    python demo/assemble.py                  # cut it, report every shot
    python demo/assemble.py --dry-run        # the report alone, no ffmpeg

Written by an agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import narrate  # noqa: E402  — the one parser for the script's clock

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "demo" / "cut.json"
NARRATION = ROOT / "narration" / "narration.wav"
TAKES = ROOT / "takes"

WIDTH, HEIGHT, FPS = 1920, 1080, 30


class CutError(RuntimeError):
    """The cut cannot be made from what is on disk."""


SLATE = """<!doctype html><meta charset="utf-8"><style>
  html,body{{margin:0;height:100%;background:#0d1117;color:#e6edf3;
    font:400 28px/1.5 ui-monospace,"DejaVu Sans Mono",monospace}}
  .box{{height:100%;display:flex;flex-direction:column;justify-content:center;
    padding:0 140px;box-sizing:border-box}}
  .tag{{color:#f0883e;letter-spacing:.32em;font-size:22px;text-transform:uppercase}}
  h1{{font:600 62px/1.2 ui-sans-serif,"DejaVu Sans",sans-serif;margin:26px 0 0}}
  .when{{color:#8b949e;margin-top:18px;font-size:26px}}
  .owed{{margin-top:64px;border-left:4px solid #f0883e;padding-left:26px;
    color:#e6edf3;font-size:32px;max-width:1200px}}
  .foot{{position:absolute;bottom:60px;left:140px;color:#6e7681;font-size:20px}}
</style><div class="box">
  <div class="tag">shot {sid} · placeholder</div>
  <h1>{title}</h1>
  <div class="when">{start}–{end} · {window:.0f} seconds</div>
  <div class="owed">{owed}</div>
</div><div class="foot">Rollout Marshal · rough cut · this card is not the finished shot</div>
"""


@dataclass
class Shot:
    """One `###` slot on the video's clock, with whatever picture fills it."""

    id: str
    title: str
    start: float
    end: float
    source: dict = field(default_factory=dict)
    actual: float = 0.0  # what the picture on disk really is, before fitting

    @property
    def window(self) -> float:
        return self.end - self.start

    @property
    def kind(self) -> str:
        return self.source.get("kind", "slate")


def shots(script: Path, branch: str = "B") -> list[Shot]:
    """The script's top-level shots, with the `####` children folded back in.

    `narrate.parse` returns the leaves, because the voice is laid per cue. The picture
    is laid per shot, so shot 4's four beats are one 122-second window here.
    """
    leaves = narrate.parse(script.read_text(), branch)
    out: dict[str, Shot] = {}
    for beat in leaves:
        sid = beat.id[0]
        if sid in out:
            out[sid].start = min(out[sid].start, beat.start)
            out[sid].end = max(out[sid].end, beat.end)
        else:
            out[sid] = Shot(sid, beat.title, beat.start, beat.end)
    ordered = [out[k] for k in sorted(out, key=int)]
    for a, b in zip(ordered, ordered[1:]):
        if a.end != b.start:
            raise CutError(f"shot {a.id} ends at {a.end:g}s but shot {b.id} starts at {b.start:g}s")
    return ordered


def titles(script: Path, ordered: list[Shot]) -> None:
    """Shot 4's title comes from its first child, which reads oddly on a slate."""
    text = script.read_text()
    for shot in ordered:
        for line in text.splitlines():
            if match := narrate.SHOT.match(line):
                if match.group(1) == shot.id:
                    shot.title = match.group(2)
                    break


def probe(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def chrome() -> str:
    """The headless shell. `chrome --headless=new` never returns on this machine."""
    cache = Path.home() / ".cache/ms-playwright"
    for pattern in (
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium-*/chrome-linux64/chrome",
    ):
        hits = sorted(glob.glob(str(cache / pattern)))
        if hits:
            return hits[-1]
    raise CutError("no headless chromium under ~/.cache/ms-playwright")


def slate(shot: Shot, out: Path) -> Path:
    """Render the placeholder card for a shot nobody has filmed yet."""
    owed = shot.source.get("owed") or "no source in demo/cut.json"
    page = out / f"slate-{shot.id}.html"
    page.write_text(SLATE.format(
        sid=shot.id, title=shot.title, owed=owed, window=shot.window,
        start=narrate.clock(shot.start), end=narrate.clock(shot.end),
    ))
    png = out / f"slate-{shot.id}.png"
    subprocess.run(
        [chrome(), "--no-sandbox", "--disable-gpu", f"--user-data-dir={out}/profile-{shot.id}",
         "--virtual-time-budget=4000", f"--window-size={WIDTH},{HEIGHT}",
         f"--screenshot={png}", page.as_uri()],
        capture_output=True, text=True, timeout=120,
    )
    if not png.exists() or png.stat().st_size == 0:
        raise CutError(f"shot {shot.id}: the slate did not render")
    return png


def still(path: Path, out: Path, sid: str) -> Path:
    """An SVG has to become a raster before ffmpeg will look at it."""
    if path.suffix.lower() != ".svg":
        return path
    page = out / f"still-{sid}.html"
    page.write_text(
        f'<!doctype html><meta charset="utf-8">'
        f'<style>html,body{{margin:0;height:100%;background:#fff;display:flex;'
        f'align-items:center;justify-content:center}}img{{max-width:92%;max-height:92%}}</style>'
        f'<img src="{path.as_uri()}">'
    )
    png = out / f"still-{sid}.png"
    subprocess.run(
        [chrome(), "--no-sandbox", "--disable-gpu", f"--user-data-dir={out}/profile-s{sid}",
         "--virtual-time-budget=4000", f"--window-size={WIDTH},{HEIGHT}",
         f"--screenshot={png}", page.as_uri()],
        capture_output=True, text=True, timeout=120,
    )
    if not png.exists() or png.stat().st_size == 0:
        raise CutError(f"shot {sid}: the still did not rasterise")
    return png


def plan(ordered: list[Shot], manifest: dict) -> list[str]:
    """Attach a source to every shot and say what is wrong with it. Reads no media."""
    problems: list[str] = []
    for shot in ordered:
        shot.source = dict(manifest.get(shot.id, {}))
        if not shot.source:
            continue
        kind = shot.kind
        if kind not in {"clip", "still", "slate"}:
            problems.append(f"shot {shot.id}: unknown kind {kind!r}")
            continue
        if kind == "slate":
            continue
        raw = shot.source.get("path")
        if not raw:
            problems.append(f"shot {shot.id}: {kind} with no path")
            continue
        path = ROOT / raw
        if not path.exists():
            problems.append(f"shot {shot.id}: {raw} is not on disk")
            continue
        if shot.source.get("unedited") and shot.source.get("pad"):
            problems.append(
                f"shot {shot.id}: marked unedited, so it may not be padded — "
                "re-record it at its real length"
            )
            continue
        if kind == "clip":
            shot.actual = probe(path)
            short = shot.window - shot.actual
            if short > 0.05 and not shot.source.get("pad"):
                problems.append(
                    f"shot {shot.id}: the clip is {shot.actual:.1f}s and the window is "
                    f"{shot.window:.0f}s — {short:.1f}s short. Re-record it slower "
                    f"(record_take.sh --dwell), or move the window in the script."
                )
    return problems


def segment(shot: Shot, out: Path) -> Path:
    """One shot, exactly its window long, at the cut's size and frame rate."""
    dest = out / f"seg-{shot.id}.mp4"
    fit = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
           f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x0d1117")
    encode = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-t", f"{shot.window:.3f}", str(dest)]

    if shot.kind == "clip":
        source = ["-i", str(ROOT / shot.source["path"])]
        if shot.source.get("pad"):
            # Explicit only, and refused by plan() on anything marked unedited.
            fit += (",tpad=stop_mode=clone:stop_duration="
                    f"{max(0.0, shot.window - shot.actual):.3f}")
    else:
        png = (slate(shot, out) if shot.kind == "slate"
               else still(ROOT / shot.source["path"], out, shot.id))
        source = ["-loop", "1", "-i", str(png)]

    subprocess.run(
        ["ffmpeg", "-y", *source, "-vf", f"{fit},fps={FPS},format=yuv420p", *encode],
        capture_output=True, check=True)
    return dest


def report(ordered: list[Shot], problems: list[str]) -> str:
    rows = [f"{'shot':<5}{'window':>16}  {'kind':<7}{'source':<44}{'on disk':>9}"]
    for shot in ordered:
        where = shot.source.get("path") or shot.source.get("owed", "— nothing —")
        rows.append(
            f"{shot.id:<5}"
            f"{narrate.clock(shot.start)}–{narrate.clock(shot.end)} ({shot.window:>3.0f}s)  "
            f"{shot.kind:<7}{where[:43]:<44}"
            f"{(f'{shot.actual:.1f}s' if shot.actual else '—'):>9}"
        )
    total = sum(s.window for s in ordered)
    rows.append(f"\ntotal {narrate.clock(total)} ({total:.0f}s)")
    placeholders = [s.id for s in ordered if s.kind == "slate"]
    if placeholders:
        rows.append(f"placeholder shots, still owed: {', '.join(placeholders)}")
    for problem in problems:
        rows.append(f"PROBLEM  {problem}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--script", type=Path, default=ROOT / "notes" / "demo-script.md")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--narration", type=Path, default=NARRATION)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--branch", default="B", choices=["A", "B"])
    ap.add_argument("--dry-run", action="store_true", help="the report alone, no ffmpeg")
    args = ap.parse_args(argv)

    ordered = shots(args.script, args.branch)
    titles(args.script, ordered)
    manifest = json.loads(args.manifest.read_text()) if args.manifest.exists() else {}
    problems = plan(ordered, manifest.get("shots", manifest))
    print(report(ordered, problems))
    if problems:
        print("\nNothing was cut. Fix the problems above; a shot that does not fit its "
              "window would push every later beat off the narration.")
        return 2
    if args.dry_run:
        return 0

    if not shutil.which("ffmpeg"):
        raise CutError("ffmpeg is not on PATH")
    if not args.narration.exists():
        raise CutError(f"{args.narration} is missing — run demo/narrate.py first")

    TAKES.mkdir(exist_ok=True)
    out = args.out or TAKES / "cut.mp4"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        parts = [segment(shot, work) for shot in ordered]
        listing = work / "parts.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        silent = work / "picture.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c", "copy", str(silent)], capture_output=True, check=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(silent), "-i", str(args.narration),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)],
            capture_output=True, check=True)

    made = probe(out)
    print(f"\n{out.relative_to(ROOT)} — {narrate.clock(made)} ({made:.1f}s), "
          f"{out.stat().st_size / 1e6:.1f} MB")
    if made > 240.5:
        print("WARNING: over four minutes. Only the first four are judged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
