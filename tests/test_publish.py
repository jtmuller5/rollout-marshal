"""The hosted page, and the promise that every figure on it came out of the store.

The page is the submission's project URL, so the failure that matters is not a broken
layout. It is a page that keeps saying "halted at 20%" after the halt has stopped
working. These tests hold `publish` to reading the decision log: change a number in the
store and the page has to change with it, empty the log and there must be no page at all.

The other half is provenance. A tick that read a fixture crash feed and a tick that wrote
a real Play edit are very different claims, and the page has to tell them apart.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from rollout_marshal import cli, publish  # noqa: E402
from rollout_marshal.models import Decision, Policy  # noqa: E402
from rollout_marshal.store import build_store  # noqa: E402

PACKAGE = "com.mullr.abis_recipes"

POLICY = Policy(
    app="bakedown",
    package=PACKAGE,
    track="alpha",
    halt_crash_free=95.0,
    stages=[0.2, 0.5, 1.0],
    min_hours_per_stage=6.0,
    session_floor=120,
    baseline_crash_free=99.4,
)


def _inputs(crash_free: float, sessions: int, source: str) -> dict:
    return {
        "app": "bakedown",
        "package": PACKAGE,
        "track": "alpha",
        "crash_free": crash_free,
        "sessions": sessions,
        "crash_source": source,
        "halt_criterion": 95.0,
        "baseline_crash_free": 99.4,
        "session_floor": 120,
        "hours_at_stage": 8.0,
        "min_hours_per_stage": 6.0,
        "stages": [0.2, 0.5, 1.0],
        "status": "inProgress",
        "user_fraction": 0.2,
        "version_code": "121",
    }


def _decision(action: str, inputs: dict, edit_id: str | None, ts: str) -> Decision:
    return Decision(
        app="bakedown",
        ts=ts,
        inputs=inputs,
        proposal={"action": action, "reasoning": f"proposed {action}"},
        gate_verdict={
            "allowed": action != "HOLD",
            "reason": f"{action} verdict",
            "checks": [
                {"name": "no_breach", "detail": "measured vs halt line", "passed": True},
                {"name": "session_floor", "detail": "41 vs 120", "passed": False},
            ],
        },
        action_taken=action,
        api_response={"edit_id": edit_id} if edit_id else None,
        attempts=[
            {
                "proposal": {"action": action, "reasoning": f"proposed {action}"},
                "verdict": {"allowed": True, "reason": "allowed", "checks": []},
            }
        ],
        model_reasoning=f"Proposed {action}.",
        brain="adk" if edit_id else "scripted",
    )


def _seed(store, *, live_edit: str | None = "06187374055212919847") -> None:
    store.put_policy(POLICY)
    store.put_rollout(
        "bakedown",
        {"status": "halted", "user_fraction": 0.2, "release_name": "1.0.121"},
    )
    store.append_decision(
        _decision("HOLD", _inputs(100.0, 41, "fixture:quiet"), None, "2026-08-13T17:00:00.000+00:00")
    )
    store.append_decision(
        _decision(
            "HALT", _inputs(76.9, 412, "fixture:spike"), live_edit,
            "2026-08-13T17:29:28.474+00:00",
        )
    )


def test_the_page_states_the_numbers_the_decision_log_holds(sandbox, tmp_path):
    store = build_store()
    _seed(store)

    page = publish.publish("bakedown", out=tmp_path / "site")
    html = page.read_text()

    # The two readings, the declared line and the stage, all out of the documents above.
    assert "76.9%" in html and "100.0%" in html
    assert "95.0%" in html
    assert "412" in html and "41" in html
    # The proof panel names the real Play edit and the package it was committed against.
    assert "06187374055212919847" in html
    assert PACKAGE in html
    # Both decisions are on the page, and the halt is the newest, so it comes first.
    assert html.count("<article class=") == 2
    assert html.index(">HALT<") < html.index(">HOLD<")


def test_a_changed_reading_changes_the_page(sandbox, tmp_path):
    """The point of building the page from the log rather than writing it."""
    store = build_store()
    _seed(store)
    first = publish.render(publish.collect("bakedown", store))
    assert "76.9%" in first

    store.append_decision(
        _decision("HALT", _inputs(42.5, 900, "sentry"), "77770000111122223333",
                  "2026-08-13T18:00:00.000+00:00")
    )
    second = publish.render(publish.collect("bakedown", store))
    assert "42.5%" in second and "900" in second
    assert "77770000111122223333" in second
    # The newest live write is the one the proof panel leads with.
    assert publish.proof(publish.collect("bakedown", store))["inputs"]["crash_free"] == 42.5


def test_a_fixture_write_is_never_reported_as_a_real_one(sandbox, tmp_path):
    store = build_store()
    _seed(store, live_edit="fixture-edit")
    facts = publish.collect("bakedown", store)

    assert publish.proof(facts) is None
    html = publish.render(facts)
    assert "This page was built from a fixture run" in html
    assert "It halted a real release" not in html
    assert "fixture Play client" in html


def test_the_source_line_names_the_model_and_the_feed(sandbox, tmp_path):
    store = build_store()
    _seed(store)
    html = publish.render(publish.collect("bakedown", store))

    assert "Gemini 3.5 through ADK" in html  # the live halt ran on the model
    assert "scripted control, no model" in html  # the earlier tick did not
    assert "crash feed fixture:spike" in html


def test_there_is_no_page_without_a_policy_or_a_decision(sandbox, tmp_path):
    store = build_store()
    with pytest.raises(publish.PublishError, match="no policies/bakedown"):
        publish.collect("bakedown", store)

    store.put_policy(POLICY)
    with pytest.raises(publish.PublishError, match="the agent has not run"):
        publish.collect("bakedown", store)

    # And nothing was written while it refused.
    assert not (tmp_path / "site").exists()


def test_the_page_carries_the_diagrams_and_refuses_without_them(sandbox, tmp_path):
    store = build_store()
    _seed(store)
    facts = publish.collect("bakedown", store)

    html = publish.render(facts)
    # Inlined, so the page is one file: both diagrams are <svg> elements in the markup.
    assert html.count("<svg") >= 2
    assert "aria-roledescription" in html

    with pytest.raises(publish.PublishError, match="render_diagrams"):
        publish.render(facts, assets=tmp_path / "nothing-here")


def test_the_diagrams_are_the_readmes_own_mermaid_blocks():
    """One source for the architecture: the page cannot drift from the README."""
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    blocks = re.findall(r"```mermaid\n(.*?)```", readme, flags=re.S)
    assert len(blocks) == 2

    for name, block in zip(("architecture", "decision-flow"), blocks):
        svg = (Path("docs/assets") / f"{name}.svg").read_text()
        # A node label in the flowchart, and a participant name in the sequence chart:
        # the two blocks are written in different mermaid dialects, so both are parsed
        # and an empty list is a failure rather than a silently skipped check.
        labels = re.findall(r'\["?([A-Za-z][^"\[\]<]{4,40})', block)
        labels += re.findall(r"participant \w+ as ([^\n]+)", block)
        assert labels, f"no labels parsed out of the {name} block"
        for label in labels[:6]:
            assert label.split("<br")[0].strip() in svg, f"{name}.svg is missing {label!r}"


def test_the_cli_publishes_and_reports_the_file(sandbox, tmp_path, capsys):
    store = build_store()
    _seed(store)
    out = tmp_path / "site"

    assert cli.main(["publish", "--app", "bakedown", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert str(out / "index.html") in printed
    assert (out / "index.html").read_text().startswith("<!doctype html>")

    # An app with no log is a non-zero exit and no file, not an empty page.
    assert cli.main(["publish", "--app", "nobody", "--out", str(out / "b")]) == 1
    assert not (out / "b" / "index.html").exists()


def test_the_committed_page_is_the_one_publish_builds(sandbox):
    """The page in docs/ is generated, so a hand edit to it is a bug."""
    committed = Path("docs/index.html")
    assert committed.exists(), "docs/index.html has not been published yet"
    text = committed.read_text()
    assert "Built by an autonomous agent working for Joe Muller" in text
    assert "github.com/jtmuller5/rollout-marshal" in text
    # Published from a store with a real Play edit in it, not from a fixture run.
    assert "It halted a real release" in text
    assert re.search(r"Published \d{4}-\d\d-\d\dT", text)
