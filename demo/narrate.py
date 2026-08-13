"""Speak the demo script, and lay the result out on the video's own clock.

    python demo/narrate.py --out narration/          # synthesise
    python demo/narrate.py --dry-run                 # parse and budget only, no audio

`notes/demo-script.md` carries the narration word for word, inside blockquotes, under
headings that already state when each beat starts and how long it runs. That makes the
script a machine-readable timing sheet as well as something a person reads on the day,
so this tool reads it rather than holding a second copy of the words. Edit the script;
never edit a cue here.

What comes out is a 3:55 audio bed with every line sitting at the position the script
gives it, an SRT that matches that bed exactly, and one wav per cue for an editor who
wants to nudge a line. The bed is a draft, not a master: within a beat the tool spreads
the slack evenly between the cues, which is right for most beats and approximate for
4c, where the script asks for one long silence in a particular place. What it will not
do quietly is overrun — a beat whose words do not fit its window is reported, with the
overrun in seconds, and that is the number that decides whether the script is too long.

The voice is synthetic and local (Kokoro, on the CPU). Joe can replace any cue with his
own read and the timings still hold, because each cue is its own file.

The synthesis dependency is deliberately not in `requirements.txt`. A judge cloning the
repo runs the demo and the tests, and neither needs a speech model; `--dry-run` parses
and budgets with the standard library alone. To synthesise on chonky:

    ~/ai-server/.venv/bin/python demo/narrate.py --out narration/

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "notes" / "demo-script.md"

# The narration lives between these two headings. Everything before is setup the reader
# needs and the microphone does not; everything after is rules for the take.
BEGIN = "## The script"
END = "## Rules for the take"

SAMPLE_RATE = 24_000
DEFAULT_VOICE = "am_michael"

# `### 1 · The 2am decision · 0:00–0:22 · *40%*`  — the en dash is the script's.
SHOT = re.compile(r"^###\s+(\d+)\s+·\s+(.*?)\s+·\s+(\d+:\d\d)[–-](\d+:\d\d)\s+·")
# `#### 4a · A tick that does nothing · ~30s`
BEAT = re.compile(r"^####\s+(\d+[a-z])\s+·\s+(.*?)\s+·\s+~(\d+)s")
# `**Branch A — Cloud Run deployed** (needs #1035…)` — shot 5 is written both ways.
BRANCH = re.compile(r"^\*\*Branch ([AB])\b")


def seconds(stamp: str) -> float:
    mins, secs = stamp.split(":")
    return int(mins) * 60 + int(secs)


def clock(value: float) -> str:
    return f"{int(value) // 60}:{int(value) % 60:02d}"


@dataclass
class Cue:
    """One blockquote block: a thing said in one breath, with silence around it."""

    beat: str
    index: int
    text: str
    start: float = 0.0
    seconds: float = 0.0

    @property
    def name(self) -> str:
        return f"{self.beat}-{self.index}"


@dataclass
class Beat:
    """A numbered slot on the video's clock, holding zero or more cues."""

    id: str
    title: str
    start: float
    end: float
    cues: list[Cue] = field(default_factory=list)

    @property
    def window(self) -> float:
        return self.end - self.start


def parse(text: str, branch: str = "B") -> list[Beat]:
    """Read the script into beats and cues.

    `branch` picks between shot 5's two versions. B is the honest one until the Cloud
    Run deploy exists; see the script's own note there.
    """
    lines = text.splitlines()
    try:
        first = next(i for i, ln in enumerate(lines) if ln.strip() == BEGIN) + 1
    except StopIteration:
        raise ValueError(f"{SCRIPT.name} has no {BEGIN!r} heading")
    last = next(
        (i for i, ln in enumerate(lines) if i > first and ln.strip() == END), len(lines)
    )

    beats: list[Beat] = []
    shot: Beat | None = None  # the `###` we are inside, which may hold `####` children
    current: Beat | None = None  # where cues actually land
    wanted = True  # False while we are inside the branch of shot 5 we did not pick
    block: list[str] = []

    def flush() -> None:
        nonlocal block
        if block and current is not None and wanted:
            current.cues.append(
                Cue(current.id, len(current.cues) + 1, " ".join(block))
            )
        block = []

    for line in lines[first:last]:
        if match := SHOT.match(line):
            flush()
            number, title, start, end = match.groups()
            shot = Beat(number, title, seconds(start), seconds(end))
            beats.append(shot)
            current = shot
            wanted = True
            continue
        if match := BEAT.match(line):
            flush()
            if shot is None:
                raise ValueError(f"beat {match.group(1)} appears before any shot")
            # Children run back to back from the parent's start, in the order written.
            used = sum(b.window for b in beats if b.id.startswith(shot.id) and b is not shot)
            length = float(match.group(3))
            current = Beat(
                match.group(1), match.group(2), shot.start + used, shot.start + used + length
            )
            beats.append(current)
            wanted = True
            continue
        if match := BRANCH.match(line):
            flush()
            wanted = match.group(1) == branch
            continue
        if line.startswith(">"):
            block.append(line.lstrip(">").strip())
            continue
        flush()
    flush()

    # A `###` that gained `####` children is a container; its own window is theirs.
    return [b for b in beats if b.cues or not any(
        other.id != b.id and other.id.startswith(b.id) for other in beats
    )]


def spoken(beats: list[Beat]) -> list[Cue]:
    return [cue for beat in beats for cue in beat.cues]


def place(beats: list[Beat]) -> list[str]:
    """Put every cue on the clock. Returns one complaint per beat that overran."""
    problems: list[str] = []
    for beat in beats:
        if not beat.cues:
            continue
        talking = sum(cue.seconds for cue in beat.cues)
        slack = beat.window - talking
        if slack < 0:
            problems.append(
                f"shot {beat.id} ({beat.title}) overruns its window by "
                f"{-slack:.1f}s: {talking:.1f}s of words in {beat.window:.0f}s"
            )
        gap = max(slack, 0.0) / len(beat.cues)
        at = beat.start
        for cue in beat.cues:
            cue.start = at
            at += cue.seconds + gap
    return problems


def sentences(text: str) -> list[str]:
    """Split a cue for reading. `3.5` and `76.9` must not become two subtitles."""
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+(?=[A-Z])", text) if s.strip()]


def srt(cues: list[Cue]) -> str:
    """Subtitles for the bed. A cue is split into sentences and its measured length
    shared out between them by character count, which is an approximation — the cue
    boundaries are measured, the sentence boundaries inside one are not."""

    def stamp(value: float) -> str:
        whole, ms = divmod(round(value * 1000), 1000)
        mins, secs = divmod(whole, 60)
        return f"{mins // 60:02d}:{mins % 60:02d}:{secs:02d},{ms:03d}"

    out, n = [], 0
    for cue in sorted(cues, key=lambda c: c.start):
        parts = sentences(cue.text)
        chars = sum(len(p) for p in parts)
        at = cue.start
        for part in parts:
            n += 1
            length = cue.seconds * len(part) / chars
            out.append(f"{n}\n{stamp(at)} --> {stamp(at + length)}\n{part}\n")
            at += length
    return "\n".join(out)


def synthesise(cues: list[Cue], out: Path, voice: str) -> None:
    """Fill in each cue's `seconds` and write its wav. Imported late, on purpose."""
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a", device="cpu")
    for cue in cues:
        chunks = [chunk.audio.numpy() for chunk in pipeline(cue.text, voice=voice)]
        if not chunks:
            raise RuntimeError(f"cue {cue.name} produced no audio")
        audio = np.concatenate(chunks)
        cue.seconds = len(audio) / SAMPLE_RATE
        sf.write(out / f"{cue.name}.wav", audio, SAMPLE_RATE)
        print(f"  {cue.name:<6} {cue.seconds:5.1f}s  {cue.text[:58]}")


def bed(cues: list[Cue], total: float, out: Path) -> float:
    """Lay the cue files onto one silent track of `total` seconds. Returns its length."""
    import numpy as np
    import soundfile as sf

    end = max(total, max((c.start + c.seconds for c in cues), default=0.0))
    track = np.zeros(int(end * SAMPLE_RATE) + 1, dtype="float32")
    for cue in cues:
        audio, rate = sf.read(out / f"{cue.name}.wav", dtype="float32")
        if rate != SAMPLE_RATE:
            raise RuntimeError(f"{cue.name}.wav is {rate}Hz, not {SAMPLE_RATE}Hz")
        at = int(cue.start * SAMPLE_RATE)
        track[at : at + len(audio)] += audio
    sf.write(out / "narration.wav", track, SAMPLE_RATE)
    return len(track) / SAMPLE_RATE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="narration", help="where the audio goes")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--branch", default="B", choices=("A", "B"),
                        help="shot 5: A is Cloud Run deployed, B is not")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and budget only; no speech model needed")
    args = parser.parse_args(argv)

    beats = parse(SCRIPT.read_text(), branch=args.branch)
    cues = spoken(beats)
    words = sum(len(cue.text.split()) for cue in cues)
    print(f"{len(cues)} cues across {len([b for b in beats if b.cues])} beats, {words} words")

    if args.dry_run:
        for beat in beats:
            if beat.cues:
                said = sum(len(c.text.split()) for c in beat.cues)
                print(f"  {beat.id:<3} {clock(beat.start)}–{clock(beat.end)}  "
                      f"{beat.window:5.0f}s  {said:4d} words  {beat.title}")
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    synthesise(cues, out, args.voice)

    problems = place(beats)
    total = max(b.end for b in beats)
    length = bed(cues, total, out)
    (out / "narration.srt").write_text(srt(cues))
    (out / "manifest.json").write_text(json.dumps({
        "voice": args.voice,
        "branch": args.branch,
        "sample_rate": SAMPLE_RATE,
        "track_seconds": round(length, 2),
        "spoken_seconds": round(sum(c.seconds for c in cues), 2),
        "words": words,
        "beats": [
            {"id": b.id, "title": b.title, "start": b.start, "end": b.end,
             "cues": [{"name": c.name, "start": round(c.start, 2),
                       "seconds": round(c.seconds, 2), "text": c.text}
                      for c in b.cues]}
            for b in beats
        ],
        "problems": problems,
    }, indent=2) + "\n")

    talking = sum(c.seconds for c in cues)
    print(f"\ntrack {length:.1f}s ({clock(length)}), talking {talking:.1f}s, "
          f"silence {length - talking:.1f}s")
    for problem in problems:
        print(f"OVERRUN: {problem}", file=sys.stderr)
    if length > 240:
        print(f"OVERRUN: the bed is {length:.0f}s and only the first 240 are judged",
              file=sys.stderr)
        return 1
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
