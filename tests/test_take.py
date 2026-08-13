"""The recorder: the page it films, and the one thing it must never do live.

`demo/record_take.sh` is the only script here that runs with a real store account behind
it and a camera in front of it, so it fails in two expensive ways. It can fail as
software, which a broken take shows immediately. And it can fail by seeding — wiping the
state directory or writing a fixture track — while wired to the live client, which would
overwrite the very release the take exists to halt, silently, before anyone presses
record. The second one has no undo, so it gets a test rather than a comment.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo" / "take"))

SCRIPT = (ROOT / "demo" / "record_take.sh").read_text()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def page():
    import take_server

    take_server._events.clear()
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), take_server.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.read()


def push(base: str, event: dict) -> dict:
    req = urllib.request.Request(
        base + "/push", data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def test_page_is_served_and_names_its_own_panes(page):
    html = get(page + "/").decode()
    assert "ROLLOUT MARSHAL" in html
    # The three claims the shot list makes about this frame.
    assert "Policy, declared before the release" in html
    assert "Play track, read from the API" in html
    assert "The agent, live on /stream" in html


def test_events_are_append_only_and_served_from_an_offset(page):
    assert json.loads(get(page + "/events?since=0"))["events"] == []
    push(page, {"kind": "beat", "text": "4a", "ts": "t0"})
    push(page, {"kind": "propose", "text": "WIDEN", "ts": "t1"})

    first = json.loads(get(page + "/events?since=0"))
    assert [e["text"] for e in first["events"]] == ["4a", "WIDEN"]
    assert first["next"] == 2

    # A page that has already drawn the first two asks for what came after them, and
    # gets nothing until something else happens. This is what stops the take redrawing.
    assert json.loads(get(page + "/events?since=2"))["events"] == []
    push(page, {"kind": "api", "text": "committed", "ts": "t2"})
    assert [e["text"] for e in json.loads(get(page + "/events?since=2"))["events"]] == [
        "committed"
    ]


def test_the_recorder_is_valid_shell():
    subprocess.run(["bash", "-n", str(ROOT / "demo" / "record_take.sh")], check=True)


def test_live_wiring_never_seeds_and_never_wipes():
    """The seeding commands must sit inside the fixture branch and nowhere else."""
    branches = SCRIPT.split('if [ "$LIVE_PLAY" = "live" ]', 1)
    assert len(branches) == 2, "the live/fixture branch is gone; re-read this test"
    body = branches[1]
    live_arm, fixture_arm = body.split("else", 1)

    for destructive in ("track seed", "rm -rf \"$STATE\"", "policy set"):
        assert destructive not in live_arm, f"{destructive!r} runs against a live track"
        assert destructive in fixture_arm, f"{destructive!r} is no longer in the fixture arm"


def test_the_driver_walks_the_four_beats_the_shot_list_names():
    driver = (ROOT / "demo" / "take" / "drive_take.py").read_text()
    beats = re.findall(r'page\.push\("beat", "([^"]+)"', driver)
    assert [b.split(" · ")[0] for b in beats] == ["4a", "4b", "4c", "4d", "take complete"]
    # 4b is the one fixture in the take, and it is the spike the script says out loud.
    assert "demo/fixtures/spike.json" in driver
    # Nothing may be pushed to the page before the call that produced it, so the tick
    # result is read from the response rather than assumed.
    assert "post_tick(args.port, app)" in driver


def test_a_failed_brain_is_reported_rather_than_raised():
    """A tick whose agent died still returns a decision, with an empty gate verdict.

    Measured on 2026-08-13: the Gemini free tier allows 20 generate-content requests a
    day per model, a live take spends most of them, and the second take of the day got
    429 mid-halt. `result["gate"]["reason"]` then raised `KeyError: 'reason'` on top of
    the real error and the take ended in a traceback that never said "quota".
    """
    import drive_take

    assert drive_take.verdict({"action_taken": "HALT", "gate": {"reason": "breach"}}) == "breach"
    for dead in ({"action_taken": None, "gate": {}}, {"action_taken": None}, {}):
        assert "proposed nothing" in drive_take.verdict(dead)


def test_a_beat_that_did_not_happen_stops_the_take():
    """Better a short recording than beats on screen the picture contradicts."""
    import drive_take

    said: list[tuple] = []

    class FakePage:
        def push(self, kind, text, *rest):
            said.append((kind, text))

    page = FakePage()
    assert drive_take.expect(page, {"action_taken": "HALT", "gate": {"reason": "ok"}},
                             "HALT", "4c") is True
    assert said == []
    assert drive_take.expect(page, {"action_taken": None, "gate": {}}, "HALT", "4c") is False
    assert said[0][0] == "error"
    assert "4c expected HALT" in said[0][1]
    assert "recording is kept" in said[0][1]


class _Recorder:
    """A page that keeps what was pushed to it."""

    def __init__(self) -> None:
        self.said: list[tuple] = []

    def push(self, kind, text="", data=None):
        self.said.append((kind, text))


def _wire(monkeypatch, client, package="com.example.app", track="alpha"):
    """Point the driver's own imports at a client and a policy of our choosing."""
    import rollout_marshal.play as play
    import rollout_marshal.store as store

    class Policy:
        pass

    policy = Policy()
    policy.package, policy.track = package, track
    monkeypatch.setattr(play, "build_play_client", lambda: client)
    monkeypatch.setattr(store, "build_store", lambda: type("S", (), {
        "get_policy": staticmethod(lambda app: policy)})())


def _real_client(status: str, fraction: float):
    """A RealPlayClient with the two API calls replaced, so nothing leaves the process."""
    from rollout_marshal.models import TrackState
    from rollout_marshal.play import RealPlayClient

    client = RealPlayClient(key_path="/dev/null")
    client.writes = []
    state = TrackState(package="com.example.app", track="alpha", release_name="1.0.121",
                       version_codes=["121"], status=status, user_fraction=fraction, raw={})

    def get_track(package, track):
        return client.state

    def set_release(package, track, release):
        client.writes.append(release)
        client.state = TrackState(
            package=package, track=track, release_name=release["name"],
            version_codes=release["versionCodes"], status=release["status"],
            user_fraction=float(release.get("userFraction") or 0.0), raw={},
        )
        return {"edit_id": "edit-1"}

    client.state = state
    client.get_track = get_track
    client.set_release = set_release
    return client


def test_an_aborted_live_take_puts_the_track_back(monkeypatch):
    """The one piece of state a failed take must not leave behind.

    Shot 4 starts from a resumed release. A take that dies at the halt — the free
    tier's 429 is how — leaves it rolling out at 20% to real devices on the track.
    """
    import drive_take

    client = _real_client("inProgress", 0.2)
    _wire(monkeypatch, client)
    page = _Recorder()
    drive_take.restore_track(page, "bakedown")

    assert [w["status"] for w in client.writes] == ["halted"]
    assert client.writes[0]["userFraction"] == 0.2
    assert "put back to halted at 20%" in page.said[0][1]
    assert "edit-1" in page.said[0][1]


def test_a_take_that_reached_the_halt_is_left_alone(monkeypatch):
    """A successful take ends halted. The undo must not fire on it."""
    import drive_take

    client = _real_client("halted", 0.2)
    _wire(monkeypatch, client)
    page = _Recorder()
    drive_take.restore_track(page, "bakedown")

    assert client.writes == []
    assert "nothing to put back" in page.said[0][1]


def test_the_undo_never_writes_through_a_fixture_client(monkeypatch):
    """Whatever went wrong, a rehearsal must not reach a store account."""
    import drive_take
    import rollout_marshal.play as play

    fixture = play.FixturePlayClient(Path("/dev/null"))
    calls: list = []
    fixture.set_release = lambda *a, **k: calls.append(a)  # type: ignore[method-assign]
    _wire(monkeypatch, fixture)
    page = _Recorder()
    drive_take.restore_track(page, "bakedown")

    assert calls == []
    assert page.said == []
