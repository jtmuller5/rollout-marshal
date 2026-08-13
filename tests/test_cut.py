"""The cut: one clock, shared by the voice and the picture.

`demo/narrate.py` lays the narration on the windows in `notes/demo-script.md`.
`demo/assemble.py` lays the picture on the same windows. The value of that is entirely
in the two never disagreeing, so what is asserted here is the joining: every shot the
script names has a source, every source names a shot, the windows tile without a gap,
and a clip that does not fill its window is refused rather than quietly stretched.

That last one is not a style rule. The entry claims shot 4 is an unedited live
execution, so freezing a frame to cover a short take would make the video lie about
itself. `unedited: true` is what says so in the manifest, and it refuses `pad`.

No media is read here — the takes are gitignored, so a clean clone has none — and no
ffmpeg is run.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))

import assemble  # noqa: E402

SCRIPT = ROOT / "notes" / "demo-script.md"
MANIFEST = json.loads((ROOT / "demo" / "cut.json").read_text())["shots"]

JUDGED_SECONDS = 240  # the rules page: only the first four minutes are evaluated


@pytest.fixture()
def ordered():
    shots = assemble.shots(SCRIPT)
    assemble.titles(SCRIPT, shots)
    return shots


def test_the_shots_tile_the_whole_video(ordered):
    """No gap and no overlap: shot n ends exactly where shot n+1 starts."""
    assert [s.id for s in ordered] == ["1", "2", "3", "4", "5", "6"]
    assert ordered[0].start == 0
    for before, after in zip(ordered, ordered[1:]):
        assert before.end == after.start, f"gap between shot {before.id} and {after.id}"
    assert sum(s.window for s in ordered) == ordered[-1].end


def test_the_cut_fits_inside_four_minutes(ordered):
    assert ordered[-1].end <= JUDGED_SECONDS


def test_shot_four_swallows_its_own_beats(ordered):
    """4a to 4d are one picture window, not four."""
    four = next(s for s in ordered if s.id == "4")
    leaves = assemble.narrate.parse(SCRIPT.read_text())
    children = [b for b in leaves if b.id.startswith("4")]
    assert len(children) == 4
    assert four.start == min(b.start for b in children)
    assert four.end == max(b.end for b in children)


def test_a_gap_in_the_script_is_an_error(tmp_path):
    """A retimed heading that leaves a hole must not silently shift the narration."""
    broken = tmp_path / "script.md"
    broken.write_text(
        "## The script\n\n"
        "### 1 · One · 0:00–0:10 · *x*\n\n> a line\n\n"
        "### 2 · Two · 0:20–0:30 · *x*\n\n> another line\n\n"
        "## Rules for the take\n"
    )
    with pytest.raises(assemble.CutError, match="ends at 10s"):
        assemble.shots(broken)


def test_every_shot_has_a_manifest_entry_and_no_entry_is_orphaned(ordered):
    assert set(MANIFEST) == {s.id for s in ordered}


def test_the_take_is_marked_unedited():
    """Whichever shot holds the live take, it may never be padded."""
    live = [sid for sid, entry in MANIFEST.items() if entry.get("kind") == "clip"]
    assert live, "the manifest has no recorded clip at all"
    for sid in live:
        assert MANIFEST[sid].get("unedited") is True
        assert "pad" not in MANIFEST[sid]


def test_a_slate_says_who_owes_the_shot():
    for sid, entry in MANIFEST.items():
        if entry.get("kind") == "slate":
            assert entry.get("owed", "").strip(), f"shot {sid} is a slate with no owner"


def _shot(window=100.0, **source):
    shot = assemble.Shot("4", "The unedited take", 0.0, window)
    return shot, {"4": source}


def test_a_short_clip_is_refused(monkeypatch, tmp_path):
    clip = tmp_path / "take.mp4"
    clip.write_bytes(b"not really a video")
    monkeypatch.setattr(assemble, "ROOT", tmp_path)
    monkeypatch.setattr(assemble, "probe", lambda path: 78.1)
    shot, manifest = _shot(kind="clip", path="take.mp4", unedited=True)
    problems = assemble.plan([shot], manifest)
    assert len(problems) == 1
    assert "21.9s short" in problems[0]
    assert "dwell" in problems[0]


def test_a_long_clip_is_fine_because_trimming_is_a_length_choice(monkeypatch, tmp_path):
    clip = tmp_path / "take.mp4"
    clip.write_bytes(b"not really a video")
    monkeypatch.setattr(assemble, "ROOT", tmp_path)
    monkeypatch.setattr(assemble, "probe", lambda path: 130.0)
    shot, manifest = _shot(kind="clip", path="take.mp4", unedited=True)
    assert assemble.plan([shot], manifest) == []


def test_padding_an_unedited_clip_is_refused(monkeypatch, tmp_path):
    """The manifest cannot buy its way out of the rule above."""
    clip = tmp_path / "take.mp4"
    clip.write_bytes(b"not really a video")
    monkeypatch.setattr(assemble, "ROOT", tmp_path)
    monkeypatch.setattr(assemble, "probe", lambda path: 78.1)
    shot, manifest = _shot(kind="clip", path="take.mp4", unedited=True, pad="freeze")
    problems = assemble.plan([shot], manifest)
    assert len(problems) == 1
    assert "may not be padded" in problems[0]


def test_a_missing_file_is_named(monkeypatch, tmp_path):
    monkeypatch.setattr(assemble, "ROOT", tmp_path)
    shot, manifest = _shot(kind="clip", path="takes/gone.mp4")
    problems = assemble.plan([shot], manifest)
    assert problems == ["shot 4: takes/gone.mp4 is not on disk"]


def test_a_shot_with_no_entry_becomes_a_slate(ordered):
    """The cut is always full length; a hole would move every later beat."""
    assemble.plan(ordered, {})
    assert all(shot.kind == "slate" for shot in ordered)


def test_the_report_names_every_placeholder(ordered):
    assemble.plan(ordered, MANIFEST)
    text = assemble.report(ordered, [])
    assert "total 3:55" in text
    owed = [s.id for s in ordered if s.kind == "slate"]
    if owed:
        assert f"still owed: {', '.join(owed)}" in text
