"""The still shots — 2, 3 and 6 — and the things that can silently break them.

Shot 3 rings a node of the architecture diagram by mermaid's own id, and mermaid derives
that id from the node name in the README. So renaming a node in the README does not fail
anything: the recording just comes back with a ring around nothing, and nobody looks at
34 seconds of diagram twice. That is the failure this file exists to catch, and it is
checked against the SVG that is actually on disk in `docs/assets/`.

The rest is the same joining `test_cut.py` asserts for the cut: a shot's length is the
window in `notes/demo-script.md` and is read from there rather than typed anywhere else.

No media is read here — `takes/` is gitignored, so a clean clone has none — and neither
Xvfb nor ffmpeg is run.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(ROOT / "demo" / "take"))

import assemble  # noqa: E402
import shot_data  # noqa: E402

ASSETS = ROOT / "docs" / "assets"
STILLS = ROOT / "demo" / "take" / "stills.html"


@pytest.fixture(scope="module")
def architecture() -> str:
    return (ASSETS / "architecture.svg").read_text()


@pytest.mark.parametrize("shot", ["2", "3", "6"])
def test_a_shot_is_as_long_as_the_script_says(shot):
    windows = {s.id: s.window for s in assemble.shots(ROOT / "notes" / "demo-script.md")}
    assert shot_data.window(shot) == windows[shot]


def test_every_beat_names_a_node_the_diagram_still_has(architecture):
    for beat in shot_data.BEATS:
        if not beat.get("node"):
            continue
        assert f"-flowchart-{beat['node']}-" in architecture, (
            f"the diagram has no node '{beat['node']}' — renaming it in the README "
            "leaves shot 3 ringing nothing"
        )


def test_every_beat_diagram_is_on_disk():
    for beat in shot_data.BEATS:
        if name := beat.get("diagram"):
            assert (ASSETS / name).is_file()


def test_the_beats_run_in_order_and_inside_the_window():
    ats = [beat["at"] for beat in shot_data.BEATS]
    assert ats == sorted(ats)
    assert all(0 <= at < 1 for at in ats)


def test_the_last_beat_is_left_on_screen_long_enough_to_read():
    # A beat that lands in the final second is a flash nobody can read.
    window = shot_data.window("3")
    assert (1 - shot_data.BEATS[-1]["at"]) * window >= 2.0


def test_the_diagram_does_not_claim_vertex_ai(architecture):
    # What has actually run is the Gemini API key. The diagram is on camera in shot 3,
    # so a claim there is a claim a judge can check.
    assert "Vertex AI" not in architecture


def test_the_page_can_render_every_shot_it_is_offered():
    page = STILLS.read_text()
    for shot in ("2", "3", "6"):
        assert f'id="shot{shot}"' in page


def test_the_disclosure_says_who_built_it():
    assert "autonomous agent" in shot_data.DISCLOSURE
    assert "Joe Muller" in shot_data.DISCLOSURE


def test_a_recorded_shot_is_a_clip_in_the_manifest():
    manifest = json.loads((ROOT / "demo" / "cut.json").read_text())["shots"]
    for shot in ("2", "3", "6"):
        assert manifest[shot]["kind"] == "clip", f"shot {shot} was recorded by #1063"
        assert manifest[shot]["path"].startswith("takes/")
