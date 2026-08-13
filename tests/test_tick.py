"""One whole tick, with every collaborator faked at its own seam.

This is the test that would have caught the thing the demo actually cares about: that
a refused proposal still reaches the audit trail. An earlier version of the tick
recorded only the agent's last proposal, so a tick that wanted to widen, was refused
and then held looked in Firestore like a tick that had simply held — the refusal, the
one part worth filming, was gone.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import sys
import tempfile

sys.path.insert(0, ".")

from rollout_marshal.agent import ScriptedBrain  # noqa: E402
from rollout_marshal.crash import FixtureCrashFeed  # noqa: E402
from rollout_marshal.log import LogBus  # noqa: E402
from rollout_marshal.models import Policy  # noqa: E402
from rollout_marshal.notify import FileSender  # noqa: E402
from rollout_marshal.play import FixturePlayClient, release_body  # noqa: E402
from rollout_marshal.store import FileStore  # noqa: E402
from rollout_marshal.tick import Marshal  # noqa: E402

import json  # noqa: E402
import datetime as dt  # noqa: E402
from pathlib import Path  # noqa: E402


def build(tmp: Path, crash: dict, fraction=0.2, status="inProgress", hours_ago=8.0):
    store = FileStore(tmp)
    policy = Policy(
        app="demo",
        package="com.example.app",
        track="alpha",
        halt_crash_free=95.0,
        stages=[0.2, 0.5, 1.0],
        min_hours_per_stage=6.0,
        session_floor=120,
        baseline_crash_free=99.4,
    )
    store.put_policy(policy)
    play = FixturePlayClient(tmp / "play.json")
    play.seed(
        policy.package,
        policy.track,
        [
            release_body("1.0.119", ["119"], "completed", None),
            release_body("1.0.121", ["121"], status, fraction),
        ],
    )
    entered = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)
    ).isoformat(timespec="seconds")
    store.put_rollout(
        "demo",
        {"user_fraction": fraction, "status": status, "stage_entered_at": entered},
    )
    feed_path = tmp / "crash.json"
    feed_path.write_text(json.dumps(crash))
    return (
        Marshal(
            store=store,
            play=play,
            crash=FixtureCrashFeed(feed_path),
            brain=ScriptedBrain(),
            sender=FileSender(tmp),
            bus=LogBus(),
        ),
        store,
        play,
        feed_path,
    )


QUIET = {"name": "quiet", "crash_free_rate": 100.0, "sessions": 41}
SPIKE = {"name": "spike", "crash_free_rate": 76.9, "sessions": 412}
HEALTHY = {"name": "healthy", "crash_free_rate": 99.6, "sessions": 380}


def test_a_refused_widen_holds_and_the_refusal_survives_in_the_log():
    with tempfile.TemporaryDirectory() as d:
        m, store, play, _ = build(Path(d), QUIET)
        out = m.tick("demo")

        assert out["action_taken"] == "HOLD"
        assert out["gate"]["allowed"] is False
        assert "41 sessions" in out["gate"]["reason"]

        # the track was not touched
        assert play.get_track("com.example.app", "alpha").user_fraction == 0.2

        [doc] = store.list_decisions("demo")
        assert doc["proposal"]["action"] == "WIDEN"  # what it wanted
        assert doc["action_taken"] == "HOLD"  # what it was allowed
        assert [a["proposal"]["action"] for a in doc["attempts"]] == ["WIDEN", "HOLD"]


def test_a_breach_halts_the_track_and_emails_afterwards():
    with tempfile.TemporaryDirectory() as d:
        m, store, play, _ = build(Path(d), SPIKE)
        out = m.tick("demo")

        assert out["action_taken"] == "HALT"
        track = play.get_track("com.example.app", "alpha")
        assert track.status == "halted"
        assert track.user_fraction == 0.2  # a halt keeps the fraction; it does not roll back

        assert out["mailed"], "the human is told after the fact"
        body = Path(out["mailed"]).read_text()
        assert "76.9" in body and "95.0" in body
        assert out["decision_id"] in body


def test_a_healthy_release_with_enough_evidence_is_widened():
    with tempfile.TemporaryDirectory() as d:
        m, store, play, _ = build(Path(d), HEALTHY)
        out = m.tick("demo")

        assert out["action_taken"] == "WIDEN"
        assert play.get_track("com.example.app", "alpha").user_fraction == 0.5


def test_the_spike_can_be_injected_between_two_ticks():
    # Shot 4b: the same running service, one file swapped underneath it.
    with tempfile.TemporaryDirectory() as d:
        m, store, play, feed = build(Path(d), QUIET)
        assert m.tick("demo")["action_taken"] == "HOLD"
        feed.write_text(json.dumps(SPIKE))
        assert m.tick("demo")["action_taken"] == "HALT"
        assert len(store.list_decisions("demo")) == 2


def test_no_policy_means_no_rollout():
    with tempfile.TemporaryDirectory() as d:
        m, *_ = build(Path(d), QUIET)
        try:
            m.tick("some-other-app")
        except LookupError as e:
            assert "written down before" in str(e)
        else:
            raise AssertionError("a missing policy has to stop the tick")


def test_a_second_tick_after_a_halt_does_nothing():
    with tempfile.TemporaryDirectory() as d:
        m, store, play, _ = build(Path(d), SPIKE)
        m.tick("demo")
        out = m.tick("demo")
        assert out["action_taken"] == "HOLD"
        assert play.get_track("com.example.app", "alpha").status == "halted"
