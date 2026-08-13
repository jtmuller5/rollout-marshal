"""The HTTP surface the demo is actually filmed through.

Shot 4 is not `Marshal.tick()`; it is a POST to a running service and a browser held
open on `/stream`. Those two are the parts a camera sees, and neither was covered:
`tests/test_tick.py` builds the collaborators by hand and never goes near FastAPI.

The service builds its Marshal on first use, so every test here resets that global
before it runs — otherwise the second test in the file talks to the first test's
temporary directory, which is a failure that only appears when the whole file runs.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, ".")

from rollout_marshal import cli, log, server  # noqa: E402
from rollout_marshal.play import FixturePlayClient  # noqa: E402

PACKAGE = "com.mullr.abis_recipes"


@pytest.fixture
def client(sandbox, monkeypatch):
    monkeypatch.setattr(server, "_marshal", None)
    with TestClient(server.app) as c:
        yield c


def stage_the_release(app: str = "bakedown") -> None:
    """Shots 2 and 3, as the demo script runs them."""
    assert cli.main(
        ["policy", "set", "--app", app, "--package", PACKAGE, "--track", "alpha",
         "--halt", "95", "--stages", "0.2,0.5,1.0", "--hours", "6", "--floor", "120",
         "--baseline", "99.4"]
    ) == 0
    assert cli.main(
        ["track", "seed", "--app", app, "--release", "1.0.121", "--code", "121",
         "--status", "inProgress", "--fraction", "0.2"]
    ) == 0
    assert cli.main(["rollout", "stamp", "--app", app, "--hours-ago", "8"]) == 0


def test_healthz_names_the_four_seams_and_defaults_to_the_safe_one(client):
    body = client.get("/healthz").json()
    assert body["ok"] is True
    assert body["brain"] == "scripted"
    # Anything but these four values means the service reached outside on a request
    # nobody authorised, which is exactly what the defaults exist to prevent.
    assert (body["store"], body["play"], body["crash_feed"]) == (
        "file",
        "fixture",
        "fixture",
    )


def test_a_tick_without_a_declared_policy_is_a_404_and_says_why(client, capsys):
    r = client.post("/tick/bakedown")
    assert r.status_code == 404
    assert "written down before the release" in r.json()["detail"]


def test_the_two_ticks_of_shot_four_over_http(client, sandbox, capsys):
    stage_the_release()
    assert cli.main(["inject", "--file", "demo/fixtures/quiet.json"]) == 0

    # 4a — the agent wants to widen and the gate refuses on the session floor.
    first = client.post("/tick/bakedown")
    assert first.status_code == 200
    first = first.json()
    assert first["action_taken"] == "HOLD"
    assert first["gate"]["allowed"] is False
    assert "41 sessions" in first["gate"]["reason"]
    assert first["mailed"] is None, "a hold is not worth waking anybody for"
    play = FixturePlayClient(sandbox.play_fixture)
    assert play.get_track(PACKAGE, "alpha").status == "inProgress"

    # 4b — the spike goes into the feed under the same running service.
    assert cli.main(["inject", "--file", "demo/fixtures/spike.json"]) == 0

    # 4c — the halt, on the same process, with no restart in between.
    second = client.post("/tick/bakedown").json()
    assert second["action_taken"] == "HALT"
    assert second["inputs"]["crash_free"] == 76.9
    assert play.get_track(PACKAGE, "alpha").status == "halted"

    # 4d — both ticks are in the audit trail, refusal included.
    decisions = client.get("/decisions/bakedown").json()["decisions"]
    assert [d["action_taken"] for d in decisions] == ["HOLD", "HALT"]
    assert [a["proposal"]["action"] for a in decisions[0]["attempts"]] == [
        "WIDEN",
        "HOLD",
    ]
    assert decisions[1]["api_response"]["request"]["releases"][0]["status"] == "halted"

    # and the email went out after the fact, not before.
    body = (sandbox.root / "mail").glob("*.eml")
    text = "\n".join(p.read_text() for p in body)
    assert "76.9" in text and second["decision_id"] in text


def test_the_decision_log_survives_a_tick_that_throws(client, sandbox, monkeypatch, capsys):
    stage_the_release()
    assert cli.main(["inject", "--file", "demo/fixtures/quiet.json"]) == 0

    def explode(_ctx):
        raise RuntimeError("model unreachable")

    monkeypatch.setattr(server.marshal().brain, "run", explode)
    out = client.post("/tick/bakedown")
    assert out.status_code == 200, "a broken model is a hold, not a 500"
    out = out.json()
    assert out["action_taken"] == "HOLD"

    [doc] = client.get("/decisions/bakedown").json()["decisions"]
    assert "model unreachable" in doc["model_reasoning"]


def test_the_recent_log_is_filtered_by_app(client, sandbox, capsys):
    stage_the_release()
    assert cli.main(["inject", "--file", "demo/fixtures/quiet.json"]) == 0
    client.post("/tick/bakedown")

    events = client.get("/log", params={"app_id": "bakedown"}).json()["events"]
    assert [e["kind"] for e in events][0] == "tick"
    assert {e["app"] for e in events} == {"bakedown"}
    assert client.get("/log", params={"app_id": "nothing-here"}).json()["events"] == []


@pytest.fixture
def bus(monkeypatch) -> log.LogBus:
    """A bus of this test's own. `log.BUS` is a module global that replays its recent
    events to every new subscriber, so a shared one makes these tests read whatever
    the earlier tests in the file published."""
    fresh = log.LogBus()
    monkeypatch.setattr(log, "BUS", fresh)
    return fresh


async def first_event(response) -> dict:
    chunk = await asyncio.wait_for(response.body_iterator.__anext__(), 3)
    await response.body_iterator.aclose()
    assert chunk.startswith("data: ") and chunk.endswith("\n\n")
    return json.loads(chunk[len("data: ") :])


def test_stream_replays_the_backlog_so_a_late_browser_sees_the_tick(bus, capsys):
    # The pane is opened before the take, but a reconnect mid-shot must not lose the
    # lines already on screen.
    bus.publish(log.GATE_NO, "bakedown", "41 sessions, against a floor of 120")

    async def go():
        response = await server.stream()  # subscribes on the way in
        watcher = bus.subscribe()  # a second subscriber proves the fan-out
        event = await first_event(response)
        return event, watcher.get_nowait()

    event, replayed = asyncio.run(go())
    assert (event["kind"], event["app"]) == ("gate.refuse", "bakedown")
    assert "41 sessions" in event["text"]
    assert replayed == event, "every subscriber gets the same line"


def test_stream_filtered_to_one_app_drops_another_apps_events(bus, capsys):
    async def go():
        response = await server.stream(app_id="bakedown")
        bus.publish(log.TICK, "some-other-app", "not this one")
        bus.publish(log.TICK, "bakedown", "this one")
        return await first_event(response)

    event = asyncio.run(go())
    assert (event["app"], event["text"]) == ("bakedown", "this one")
