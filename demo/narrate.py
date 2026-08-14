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

The voice is `gemini-2.5-flash-preview-tts`, which answers with 24kHz PCM — the rate
this tool already lays its bed on, so nothing is resampled. `--tts kokoro` is the local
CPU fallback and needs no key, which is what to use when the day's free-tier requests
are gone. Joe can replace any cue with his own read and the timings still hold, because
each cue is its own file.

Neither speech dependency is in `requirements.txt`. A judge cloning the repo runs the
demo and the tests, and neither needs a voice; `--dry-run` parses and budgets with the
standard library alone. To synthesise:

    GOOGLE_API_KEY=… ./.venv/bin/python demo/narrate.py --out narration/
    ~/ai-server/.venv/bin/python demo/narrate.py --tts kokoro --out narration/

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "notes" / "demo-script.md"

# The narration lives between these two headings. Everything before is setup the reader
# needs and the microphone does not; everything after is rules for the take.
BEGIN = "## The script"
END = "## Rules for the take"

SAMPLE_RATE = 24_000

# Two voices, one per engine, both at 24kHz so the bed below never resamples anything.
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_ENGINE = os.environ.get("MARSHAL_TTS", "gemini")
VOICES = {"gemini": "Charon", "kokoro": "am_michael"}

# Three requests a minute to the TTS model on the free tier, measured 2026-08-14 from
# the 429 body itself: quotaId GenerateRequestsPerMinutePerProjectPerModel-FreeTier,
# quotaValue 3. Twenty-one seconds is that with a second of margin.
TTS_GAP = 21.0
_LAST_CALL = 0.0

# Said to the model in front of every line, and to nobody in the finished audio. A
# narrator reading a script about a crashing release will play the drama unless told
# not to, and the shots underneath are of an agent doing its job correctly.
DIRECTION = (
    "Read this line as a calm, level technical narrator. Steady pace, no drama, "
    "no rising inflection at the end. Say only the line:"
)

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


def _paced(call):
    """Keep one request every `TTS_GAP` seconds, and wait out a refusal rather than fail.

    The free tier allows three requests a minute to this model, per project, and the
    script is twelve cues, so an unpaced run gets nine of them and then a 429 with the
    ninth line already written to disk. Waiting is the only correct response to a rate
    limit: a second key for a second allowance would be evading it.
    """
    global _LAST_CALL
    for attempt in range(4):
        wait = TTS_GAP - (time.monotonic() - _LAST_CALL)
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.monotonic()
        try:
            return call()
        except Exception as e:
            delay = _retry_delay(e)
            if delay is None or attempt == 3:
                raise
            print(f"    rate limited; waiting {delay:.0f}s", file=sys.stderr)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def _retry_delay(error: Exception) -> float | None:
    """The server's own `retryDelay`, in seconds, or None if this was not a 429."""
    if getattr(error, "code", None) != 429:
        return None
    for detail in (getattr(error, "details", None) or {}).get("error", {}).get("details", []):
        if detail.get("@type", "").endswith("RetryInfo"):
            return float(str(detail.get("retryDelay", "20s")).rstrip("s")) + 1.0
    return TTS_GAP


def speak_gemini(text: str, voice: str):
    """One cue, spoken by `gemini-2.5-flash-preview-tts`. Returns float32 at 24kHz.

    The model answers with raw signed 16-bit PCM at 24,000Hz, which is the rate this
    tool already lays its bed on, so there is no resampling step to get wrong. The
    direction in front of the line is not decoration: without it the model reads a
    sentence about a crashing release as though it were bad news, and the shots it sits
    over are of an agent behaving correctly.
    """
    import numpy as np
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=os.environ["GOOGLE_API_KEY"],
        http_options=types.HttpOptions(timeout=120_000),
    )
    def call():
        return client.models.generate_content(
            model=os.environ.get("MARSHAL_TTS_MODEL", GEMINI_TTS_MODEL),
            contents=f"{DIRECTION}\n\n{text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                ),
            ),
        )

    reply = _paced(call)
    blob = reply.candidates[0].content.parts[0].inline_data
    if f"rate={SAMPLE_RATE}" not in (blob.mime_type or ""):
        raise RuntimeError(f"{blob.mime_type} is not {SAMPLE_RATE}Hz PCM")
    return np.frombuffer(blob.data, dtype="<i2").astype("float32") / 32768.0


def speak_kokoro(text: str, voice: str):
    """One cue, spoken on this machine's CPU. No key, no quota, no network."""
    import numpy as np
    from kokoro import KPipeline

    global _KOKORO
    if _KOKORO is None:
        _KOKORO = KPipeline(lang_code="a", device="cpu")
    chunks = [chunk.audio.numpy() for chunk in _KOKORO(text, voice=voice)]
    if not chunks:
        raise RuntimeError("kokoro produced no audio")
    return np.concatenate(chunks)


ENGINES = {"gemini": speak_gemini, "kokoro": speak_kokoro}
_KOKORO = None


def synthesise(
    cues: list[Cue], out: Path, voice: str, engine: str = DEFAULT_ENGINE, resume: bool = False
) -> None:
    """Fill in each cue's `seconds` and write its wav. Imported late, on purpose.

    `resume` keeps whatever is already on disk. A run that dies on the eleventh cue has
    ten good files and a limited number of requests left in the day, so re-speaking
    them is the wrong instinct; it is also how a cue Joe has re-recorded himself
    survives the next run.
    """
    speak = ENGINES[engine]
    for cue in cues:
        path = out / f"{cue.name}.wav"
        if resume and path.exists():
            # `wave` rather than soundfile: measuring a file needs no audio library, so
            # a resumed run works in an interpreter that could not have spoken it.
            with wave.open(str(path)) as w:
                cue.seconds = w.getnframes() / w.getframerate()
            print(f"  {cue.name:<6} {cue.seconds:5.1f}s  (kept)")
            continue
        import soundfile as sf

        audio = speak(cue.text, voice)
        if len(audio) == 0:
            raise RuntimeError(f"cue {cue.name} produced no audio")
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
    parser.add_argument("--tts", default=DEFAULT_ENGINE, choices=tuple(ENGINES),
                        help="gemini needs GOOGLE_API_KEY; kokoro runs on this CPU")
    parser.add_argument("--voice", default=None,
                        help="default depends on --tts: " + ", ".join(
                            f"{k}={v}" for k, v in VOICES.items()))
    parser.add_argument("--branch", default="B", choices=("A", "B"),
                        help="shot 5: A is Cloud Run deployed, B is not")
    parser.add_argument("--resume", action="store_true",
                        help="keep any cue wav already in --out rather than re-speaking it")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and budget only; no speech model needed")
    args = parser.parse_args(argv)
    voice = args.voice or VOICES[args.tts]

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
    synthesise(cues, out, voice, args.tts, args.resume)

    problems = place(beats)
    total = max(b.end for b in beats)
    length = bed(cues, total, out)
    (out / "narration.srt").write_text(srt(cues))
    (out / "manifest.json").write_text(json.dumps({
        "engine": args.tts,
        "model": GEMINI_TTS_MODEL if args.tts == "gemini" else "kokoro",
        "voice": voice,
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
