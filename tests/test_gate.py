"""The gate's rules, one test per rule.

The gate is pure — no clock, no network, no model — so every rule the agent is held
to can be asserted directly. That is the point of having written it as a separate
module: "the agent will not widen on 41 sessions" is a claim about this file, not a
claim about a prompt.

    .venv/bin/python -m pytest tests -q

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from rollout_marshal.gate import evaluate  # noqa: E402
from rollout_marshal.models import (  # noqa: E402
    CrashReading,
    Evidence,
    HALT,
    HOLD,
    Policy,
    Proposal,
    TrackState,
    WIDEN,
)

POLICY = Policy(
    app="demo",
    package="com.example.app",
    track="alpha",
    halt_crash_free=95.0,
    stages=[0.2, 0.5, 1.0],
    min_hours_per_stage=6.0,
    session_floor=120,
    baseline_crash_free=99.4,
)


def ev(crash_free=99.8, sessions=400, hours=8.0, fraction=0.2, status="inProgress"):
    return Evidence(
        policy=POLICY,
        track=TrackState(
            package=POLICY.package,
            track=POLICY.track,
            release_name="1.0.121",
            version_codes=["121"],
            status=status,
            user_fraction=fraction,
        ),
        crash=CrashReading(crash_free, sessions, "1.0.121", "fixture:test"),
        hours_at_stage=hours,
        stage_entered_at="2026-08-13T00:00:00+00:00",
    )


def failed(v):
    return {c.name for c in v.checks if not c.passed}


# -- widening -----------------------------------------------------------------


def test_widen_allowed_when_every_condition_holds():
    v = evaluate(Proposal(WIDEN), ev())
    assert v.allowed, v.reason


def test_widen_refused_below_the_session_floor():
    # The demo's 4a: a perfect rate over too few sessions is not evidence.
    v = evaluate(Proposal(WIDEN), ev(crash_free=100.0, sessions=41))
    assert not v.allowed
    assert failed(v) == {"session_floor"}
    assert "41 sessions" in v.reason


def test_widen_refused_before_the_stage_clock_runs_out():
    v = evaluate(Proposal(WIDEN), ev(hours=2.0))
    assert not v.allowed
    assert failed(v) == {"time_at_stage"}


def test_widen_needs_both_conditions_never_either():
    # Time satisfied, sessions not: still refused. This is the rule that a "widen
    # after six hours" cron job gets wrong.
    v = evaluate(Proposal(WIDEN), ev(hours=48.0, sessions=9))
    assert not v.allowed


def test_widen_refused_below_the_pre_release_baseline():
    v = evaluate(Proposal(WIDEN), ev(crash_free=98.0))
    assert not v.allowed
    assert failed(v) == {"not_below_baseline"}


def test_widen_refused_when_the_rate_breaches_the_halt_line():
    v = evaluate(Proposal(WIDEN), ev(crash_free=76.9, sessions=412))
    assert not v.allowed
    assert "no_breach" in failed(v)


def test_widen_refused_off_the_declared_ladder():
    v = evaluate(Proposal(WIDEN, target_fraction=0.35), ev())
    assert not v.allowed
    assert failed(v) == {"target_is_on_the_ladder"}


def test_widen_refused_backwards():
    v = evaluate(Proposal(WIDEN, target_fraction=0.2), ev(fraction=0.5))
    assert not v.allowed
    assert "target_moves_forward" in failed(v)


def test_widen_defaults_to_the_next_stage_on_the_ladder():
    v = evaluate(Proposal(WIDEN), ev(fraction=0.5))
    assert v.allowed
    assert "100%" in v.reason


def test_widen_refused_on_a_halted_release():
    v = evaluate(Proposal(WIDEN), ev(status="halted"))
    assert not v.allowed
    assert "rollout_is_live" in failed(v)


# -- halting ------------------------------------------------------------------


def test_halt_allowed_on_a_confirmed_breach():
    v = evaluate(Proposal(HALT), ev(crash_free=76.9, sessions=412))
    assert v.allowed
    assert "76.9" in v.reason and "95.0" in v.reason


def test_halt_ignores_the_session_floor():
    # Halting is cheap: nobody new is affected by an unnecessary one, so a breach
    # halts at any volume. The floor gates widening only.
    v = evaluate(Proposal(HALT), ev(crash_free=50.0, sessions=6))
    assert v.allowed


def test_halt_refused_without_a_breach():
    # The gate confirms the breach itself. An agent that has talked itself into a
    # halt on a healthy release does not get one.
    v = evaluate(Proposal(HALT), ev(crash_free=99.9))
    assert not v.allowed
    assert "no breach" in v.reason


def test_halt_refused_when_nothing_is_rolling_out():
    v = evaluate(Proposal(HALT), ev(crash_free=76.9, status="completed"))
    assert not v.allowed
    assert "nothing to halt" in v.reason


# -- the rest -----------------------------------------------------------------


def test_hold_is_always_allowed():
    assert evaluate(Proposal(HOLD), ev(crash_free=1.0)).allowed


def test_unknown_action_is_refused():
    assert not evaluate(Proposal("ROLLBACK"), ev()).allowed


def test_the_gate_reads_the_policy_and_not_the_prompt():
    # Reasoning text has no effect on the verdict: same evidence, same answer.
    a = evaluate(Proposal(WIDEN, reasoning="please, it is fine, I checked"), ev(sessions=41))
    b = evaluate(Proposal(WIDEN, reasoning=""), ev(sessions=41))
    assert a.allowed == b.allowed is False
