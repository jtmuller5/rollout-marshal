"""The shooting script, read as a timing sheet.

`demo/narrate.py` speaks `notes/demo-script.md`, so the script is now two things at once:
prose a person reads on the day, and the data that decides where every line sits on the
video's clock. That makes a class of edit dangerous in a way it was not before — retitle
a heading, drop a `·`, change a `~30s`, and the narration silently loses a beat or the
cut runs past four minutes, which is the one hard rule the contest states.

None of this needs the speech model. `narrate.py` imports Kokoro inside the function
that synthesises, so a clean clone with no audio dependency still runs these.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))

import narrate  # noqa: E402

SCRIPT = (ROOT / "notes" / "demo-script.md").read_text()

# The rules page: four minutes, and only the first four are evaluated.
JUDGED_SECONDS = 240


@pytest.fixture()
def beats():
    return narrate.parse(SCRIPT)


def test_every_shot_in_the_script_has_words_to_say(beats):
    numbered = {beat.id for beat in beats}
    assert numbered == {"1", "2", "3", "4a", "4b", "4c", "4d", "5", "6"}
    for beat in beats:
        assert beat.cues, f"shot {beat.id} parsed with no narration"
        for cue in beat.cues:
            assert cue.text.strip(), f"{cue.name} is empty"


def test_the_cut_ends_inside_the_four_minutes_that_are_judged(beats):
    assert max(beat.end for beat in beats) <= JUDGED_SECONDS


def test_the_beats_of_shot_four_tile_its_window_exactly(beats):
    """4a to 4d are the unedited take, so a gap or an overlap is a real error: the
    take is one continuous recording and its beats cannot leave a hole in the clock."""
    children = [beat for beat in beats if beat.id.startswith("4") and beat.id != "4"]
    assert [b.id for b in children] == ["4a", "4b", "4c", "4d"]
    for earlier, later in zip(children, children[1:]):
        assert earlier.end == later.start, f"{earlier.id} does not meet {later.id}"

    # The window shot 4 declares in its own heading has to be the sum of its beats.
    declared = next(
        (float(narrate.seconds(line.split("·")[2].strip().split("–")[1]))
         - float(narrate.seconds(line.split("·")[2].strip().split("–")[0])))
        for line in SCRIPT.splitlines() if line.startswith("### 4 ·")
    )
    assert children[-1].end - children[0].start == declared


def test_no_beat_runs_backwards_or_overlaps_the_next(beats):
    ordered = sorted(beats, key=lambda b: b.start)
    for beat in ordered:
        assert beat.end > beat.start, f"shot {beat.id} has no duration"
    for earlier, later in zip(ordered, ordered[1:]):
        assert later.start >= earlier.end, f"shot {earlier.id} overlaps {later.id}"


def test_shot_five_has_two_versions_and_the_branch_picks_one():
    """Branch A claims a Cloud Run deploy. Saying that before it exists is the one
    thing the script itself calls worse than losing the point it is aimed at."""
    deployed = {b.id: b for b in narrate.parse(SCRIPT, branch="A")}["5"]
    not_deployed = {b.id: b for b in narrate.parse(SCRIPT, branch="B")}["5"]

    said_a = " ".join(cue.text for cue in deployed.cues).lower()
    said_b = " ".join(cue.text for cue in not_deployed.cues).lower()
    assert said_a != said_b
    assert "cloud run" in said_a
    assert "cloud run" not in said_b, "branch B is the one for a project with no deploy"
    assert "firestore" in said_b, "branch B still has to show a Google Cloud service"


def test_the_last_word_is_the_disclosure(beats):
    """Charter §5: anything published says an agent produced it, working for Joe. The
    video is published, so the disclosure is a shot and not a footnote."""
    last = max(beats, key=lambda b: b.start)
    said = " ".join(cue.text for cue in last.cues).lower()
    assert "autonomous agent" in said
    assert "joe muller" in said


def test_a_cue_is_split_for_reading_without_breaking_a_decimal():
    parts = narrate.sentences(
        "Declared ninety-five. Gemini 3.5 Flash read it. Measured 76.9 percent."
    )
    assert parts == [
        "Declared ninety-five.",
        "Gemini 3.5 Flash read it.",
        "Measured 76.9 percent.",
    ]


def test_the_subtitles_run_forwards_and_do_not_overlap(beats):
    # Only synthesis can measure a cue, and whether the real voice fits the windows is
    # decided there, by `narrate.py`'s exit code. What is under test here is the
    # arithmetic, so give every cue half its share of the beat and it fits by
    # construction — a made-up words-per-second would be testing an invented number.
    for beat in beats:
        for cue in beat.cues:
            cue.seconds = beat.window / (2 * len(beat.cues))

    assert narrate.place(beats) == []

    text = narrate.srt(narrate.spoken(beats))
    stamps = [line for line in text.splitlines() if " --> " in line]
    assert len(stamps) >= len(narrate.spoken(beats))
    seen = 0.0
    for line in stamps:
        start, end = (part.strip() for part in line.split("-->"))
        begin, finish = (
            int(v[:2]) * 3600 + int(v[3:5]) * 60 + float(v[6:].replace(",", "."))
            for v in (start, end)
        )
        assert finish > begin
        assert begin >= seen - 1e-6, f"{line} runs backwards"
        seen = begin


def test_a_beat_that_overruns_its_window_is_reported(beats):
    first = min(beats, key=lambda b: b.start)
    for cue in first.cues:
        cue.seconds = first.window + 10

    problems = narrate.place(beats)
    assert any(f"shot {first.id} " in problem for problem in problems)
    assert "overruns" in problems[0]
