"""The four operator commands the demo runs before the camera reaches the agent.

Shot 2 and shot 3 are entirely CLI: a policy is declared, a track is seeded, the
stage clock is stamped, and a reading is injected. If any one of those leaves the
wrong state behind, the first tick makes a decision on the wrong evidence and the
video shows it. They are cheap to run and were never covered.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import datetime as dt
import json
import sys

sys.path.insert(0, ".")

from rollout_marshal import cli  # noqa: E402
from rollout_marshal.crash import FixtureCrashFeed  # noqa: E402
from rollout_marshal.models import now, parse  # noqa: E402
from rollout_marshal.play import FixturePlayClient  # noqa: E402
from rollout_marshal.store import build_store  # noqa: E402

PACKAGE = "com.mullr.abis_recipes"

POLICY = [
    "policy", "set", "--app", "bakedown", "--package", PACKAGE, "--track", "alpha",
    "--halt", "95", "--stages", "0.2,0.5,1.0", "--hours", "6", "--floor", "120",
    "--baseline", "99.4",
]
SEED = [
    "track", "seed", "--app", "bakedown", "--release", "1.0.121", "--code", "121",
    "--status", "inProgress", "--fraction", "0.2",
]
STAMP = ["rollout", "stamp", "--app", "bakedown", "--hours-ago", "8"]


def test_the_demos_setup_commands_leave_the_state_the_first_tick_reads(sandbox, capsys):
    assert cli.main(POLICY) == 0
    assert cli.main(SEED) == 0
    assert cli.main(STAMP) == 0
    assert cli.main(["inject", "--file", "demo/fixtures/quiet.json"]) == 0
    capsys.readouterr()

    store = build_store()
    policy = store.get_policy("bakedown")
    assert policy is not None
    assert (policy.package, policy.track) == (PACKAGE, "alpha")
    assert (policy.halt_crash_free, policy.session_floor) == (95.0, 120)

    # Play refuses to stage the first release on a track, so the seeded fixture has to
    # carry the same shape a real track does: a completed release, then the staged one.
    track = FixturePlayClient(sandbox.play_fixture).get_track(PACKAGE, "alpha")
    assert (track.status, track.user_fraction, track.version_code) == (
        "inProgress",
        0.2,
        "121",
    )
    statuses = [r["status"] for r in track.raw["releases"]]
    assert "completed" in statuses and "inProgress" in statuses

    # The stage clock is a stored fact, because Cloud Run scales to zero between ticks.
    rollout = store.get_rollout("bakedown")
    hours = (now() - parse(rollout["stage_entered_at"])).total_seconds() / 3600.0
    assert 7.9 < hours < 8.1, "the demo needs the clock to have stopped refusing"

    reading = json.loads(sandbox.crash_fixture.read_text())
    assert (reading["crash_free_rate"], reading["sessions"]) == (100.0, 41)


def test_every_command_that_needs_a_policy_refuses_without_one(sandbox, capsys):
    for argv in (["policy", "show", "--app", "bakedown"], SEED, STAMP):
        assert cli.main(argv) == 1, argv
        assert "no policies/bakedown" in capsys.readouterr().err

    assert cli.main(POLICY) == 0
    capsys.readouterr()
    assert cli.main(["policy", "show", "--app", "bakedown"]) == 0
    assert json.loads(capsys.readouterr().out)["package"] == PACKAGE


def test_inject_swaps_the_reading_under_a_feed_that_is_already_running(sandbox, capsys):
    # Shot 4b: the service is up and the file is replaced beneath it, so the feed must
    # read at call time rather than at construction.
    assert cli.main(["inject", "--file", "demo/fixtures/quiet.json"]) == 0
    feed = FixtureCrashFeed(sandbox.crash_fixture)
    assert feed.read("bakedown", "121").sessions == 41

    assert cli.main(["inject", "--file", "demo/fixtures/spike.json"]) == 0
    spike = feed.read("bakedown", "121")
    assert spike.crash_free_rate == 76.9
    assert spike.source == "fixture:spike"
    assert "spike.json" in capsys.readouterr().out


def test_track_seed_cannot_touch_a_live_play_account(sandbox, monkeypatch, capsys):
    """A release cannot be taken off a Play track through the API, so seeding a real
    one is a decision a person makes once. `track seed` holds a fixture client
    outright rather than asking the environment, and this is that promise."""
    monkeypatch.setenv("MARSHAL_PLAY", "live")
    monkeypatch.setenv("PLAY_SERVICE_ACCOUNT_JSON", "/nonexistent-key.json")

    assert cli.main(POLICY) == 0
    assert cli.main(SEED) == 0
    capsys.readouterr()

    seeded = json.loads(sandbox.play_fixture.read_text())
    assert seeded[f"{PACKAGE}/alpha"]["releases"][1]["userFraction"] == 0.2


def test_a_completed_release_never_carries_a_user_fraction(sandbox, capsys):
    # Play rejects the release body otherwise, and the fixture has to reject it too or
    # the demo passes on a body the real account would refuse.
    assert cli.main(POLICY) == 0
    assert cli.main(SEED) == 0
    capsys.readouterr()

    releases = json.loads(sandbox.play_fixture.read_text())[f"{PACKAGE}/alpha"]["releases"]
    by_status = {r["status"]: r for r in releases}
    assert "userFraction" not in by_status["completed"]
    assert "userFraction" in by_status["inProgress"]


def test_the_stamp_reads_the_track_rather_than_being_told_about_it(sandbox, capsys):
    assert cli.main(POLICY) == 0
    assert cli.main(
        ["track", "seed", "--app", "bakedown", "--release", "9.9.9", "--code", "999",
         "--status", "inProgress", "--fraction", "0.5"]
    ) == 0
    assert cli.main(["rollout", "stamp", "--app", "bakedown", "--hours-ago", "0"]) == 0
    capsys.readouterr()

    doc = build_store().get_rollout("bakedown")
    assert (doc["version_code"], doc["release_name"], doc["user_fraction"]) == (
        "999",
        "9.9.9",
        0.5,
    )
    assert now() - parse(doc["stage_entered_at"]) < dt.timedelta(minutes=1)
