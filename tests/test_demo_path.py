"""`bash demo/run_demo.sh`, end to end, plus the narration that has to match it.

The demo is the deliverable, and it breaks in two ways that nothing else here would
catch. It can break as software — a shell script nobody runs between edits, a service
that no longer starts, a shot that prints an empty audit trail. And it can break as a
recording: the shooting script speaks the halt number and the session counts out loud,
so a one-character edit to a fixture makes the voiceover wrong while every test stays
green and the take is only wasted at the cut.

So there are two tests. The first runs the whole script on a free port and looks for
each shot in its output. The second reads the numbers out of the fixtures and the
`policy set` flags and requires the spoken words in `notes/demo-script.md` to agree
with them.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "demo" / "run_demo.sh"
SHOOTING_SCRIPT = ROOT / "notes" / "demo-script.md"
QUIET = json.loads((ROOT / "demo" / "fixtures" / "quiet.json").read_text())
SPIKE = json.loads((ROOT / "demo" / "fixtures" / "spike.json").read_text())


def free_port() -> int:
    """Ask the kernel for one rather than hoping 8811 is idle."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def policy_flag(name: str) -> str:
    """What `run_demo.sh` actually declares, read out of the script itself."""
    m = re.search(rf"--{name} ([0-9.,]+)", SCRIPT.read_text())
    assert m, f"run_demo.sh no longer passes --{name}"
    return m.group(1)


@pytest.fixture
def demo_run(sandbox):
    env = {
        k: v
        for k, v in __import__("os").environ.items()
        if not k.startswith(("MARSHAL_", "SENTRY_", "PLAY_", "GOOGLE_"))
    }
    env.update(sandbox.env())
    env["PORT"] = str(free_port())
    env["MARSHAL_STATE_DIR"] = str(sandbox.root / "state")
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    server_log = Path(env["MARSHAL_STATE_DIR"]) / "server.log"
    assert proc.returncode == 0, (
        f"demo/run_demo.sh exited {proc.returncode}\n"
        f"--- stderr ---\n{proc.stderr[-3000:]}\n"
        f"--- server ---\n"
        + (server_log.read_text()[-3000:] if server_log.exists() else "no server.log")
    )
    return proc.stdout, Path(env["MARSHAL_STATE_DIR"])


def test_the_demo_script_walks_every_shot_on_one_command(demo_run):
    out, state = demo_run

    # shot 3: the release is staged before anything judges it
    assert '"status": "inProgress"' in out
    assert "stage entered 8 hours ago" in out

    # 4a: the agent wants to widen, and the gate refuses on the session floor
    assert '"action_taken": "HOLD"' in out
    assert f"{QUIET['sessions']} sessions" in out
    assert '"allowed": false' in out

    # 4b and 4c: the spike goes in and the halt comes out, same running service
    assert str(SPIKE["crash_free_rate"]) in out
    assert '"action_taken": "HALT"' in out
    assert '"status": "halted"' in out

    # 4d: the audit trail shows the refusal as well as the halt
    assert re.search(r"wanted WIDEN\s+took HOLD\s+gate=REFUSE", out)
    assert re.search(r"wanted HALT\s+took HALT\s+gate=allow", out)
    assert "edit fixture-edit committed" in out

    # 4d: the email, after the fact
    assert "Subject: Rollout Marshal: bakedown halted at 20%" in out
    assert "Sent after the action, not before." in out

    # the right-hand pane had something to show
    assert "events on /stream" in out
    assert (state / "stream.ndjson").read_text().count("data: ") > 10


def test_the_demo_leaves_a_readable_audit_trail_on_disk(demo_run):
    _, state = demo_run
    decisions = sorted((state / "decisions").glob("*.json"))
    assert len(decisions) == 2, "one document per tick, refusal included"

    held, halted = (json.loads(p.read_text()) for p in decisions)
    assert (held["proposal"]["action"], held["action_taken"]) == ("WIDEN", "HOLD")
    assert halted["action_taken"] == "HALT"
    assert halted["api_response"]["request"]["releases"][0]["status"] == "halted"
    assert list((state / "mail").glob("*.eml")), "the halt is emailed, the hold is not"


# The demo script speaks its numbers, so each one needs a spelling to check against.
SPOKEN = {
    "41": "forty-one",
    "412": "four hundred and twelve",
    "120": "a hundred and twenty",
    "95": "ninety-five",
    "76.9": "seventy-six point nine",
    "100.0": "a hundred percent",
    "0.2": "twenty percent",
    "6": "six hours",
}


def spoken(value) -> str:
    key = str(value)
    assert key in SPOKEN, (
        f"the shooting script narrates {key} out loud and this test has no spelling "
        f"for it. Add one to SPOKEN, and check the voiceover still says it."
    )
    return SPOKEN[key]


def test_the_narration_matches_the_numbers_the_demo_runs_on():
    # The file is wrapped, so "a hundred / and twenty" straddles two lines.
    said = " ".join(SHOOTING_SCRIPT.read_text().split()).lower()
    for value in (
        policy_flag("halt"),
        policy_flag("floor"),
        policy_flag("hours"),
        policy_flag("fraction"),
        QUIET["sessions"],
        QUIET["crash_free_rate"],
        SPIKE["crash_free_rate"],
        SPIKE["sessions"],
    ):
        words = spoken(value)
        assert words in said, (
            f"{value} is what the demo runs on, and the shooting script does not say "
            f"'{words}'. One of the two moved."
        )


def test_the_script_narrates_the_readings_it_injects():
    text = SCRIPT.read_text()
    assert (
        f"{QUIET['crash_free_rate']:g}% crash-free over {QUIET['sessions']} sessions"
        in text
    )
    assert f"{SPIKE['crash_free_rate']:g}% over {SPIKE['sessions']} sessions" in text
    assert f"{policy_flag('halt')}" == "95"


def test_the_demo_defaults_to_the_fixtures_on_a_clean_checkout():
    # A demo that reached a real Play account because a variable was left exported is
    # the one failure here nobody could undo.
    text = SCRIPT.read_text()
    assert 'MARSHAL_BRAIN="${MARSHAL_BRAIN:-scripted}"' in text
    for name in ("MARSHAL_PLAY=live", "MARSHAL_STORE=firestore"):
        assert f"export {name}" not in text
