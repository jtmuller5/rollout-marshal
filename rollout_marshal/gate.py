"""The policy gate: deterministic Python, no model, no network.

The agent decides. The gate decides whether the agent is allowed to have decided
that. It re-derives every condition from the same evidence, and a refusal comes back
to the agent as a tool result it has to respond to.

Three properties make this worth having rather than a comment in a prompt:

* It cannot be argued with. There is no text input to this module at all — it reads
  the `Policy` and the `Evidence` and returns a `Verdict`.
* It is pure. Same inputs, same verdict, no clock and no I/O, so the whole rule set
  is covered by unit tests in `tests/test_gate.py`.
* It is where the credential boundary sits. Nothing the model can reach holds a Play
  key; the write is performed by `rollout_marshal.executor` only after this returns allowed.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

from .models import Check, Evidence, Proposal, Verdict, HALT, HOLD, WIDEN


def _v(allowed: bool, reason: str, checks: list[Check]) -> Verdict:
    return Verdict(allowed=allowed, reason=reason, checks=checks)


def evaluate(proposal: Proposal, ev: Evidence) -> Verdict:
    """Allow or refuse one proposed action against the pre-declared policy."""

    if proposal.action not in (WIDEN, HALT, HOLD):
        return _v(False, f"unknown action {proposal.action!r}", [])

    if proposal.action == HOLD:
        return _v(True, "holding takes no action and is always allowed", [])

    breach = ev.crash.crash_free_rate < ev.policy.halt_crash_free

    if proposal.action == HALT:
        return _halt(ev, breach)
    return _widen(proposal, ev, breach)


def _halt(ev: Evidence, breach: bool) -> Verdict:
    """A halt is allowed only when the gate confirms the breach on its own.

    Halting is the cheap direction — nobody new is affected by an unnecessary one —
    so there is no session floor and no waiting period here. What there is instead is
    an independent confirmation, because "the model said the number looked bad" is
    not the same fact as "the measured rate is below the number written down first".
    """
    checks = [
        Check(
            "breach_confirmed",
            breach,
            f"measured {ev.crash.crash_free_rate:.1f}% vs declared "
            f"{ev.policy.halt_crash_free:.1f}% crash-free",
        ),
        Check(
            "rollout_is_live",
            ev.track.status == "inProgress",
            f"track status is {ev.track.status}",
        ),
    ]
    if not breach:
        return _v(
            False,
            f"no breach: {ev.crash.crash_free_rate:.1f}% is at or above the declared "
            f"halt line of {ev.policy.halt_crash_free:.1f}%. Hold instead.",
            checks,
        )
    if ev.track.status != "inProgress":
        return _v(
            False,
            f"nothing to halt: the release is {ev.track.status}, not inProgress.",
            checks,
        )
    return _v(
        True,
        f"breach confirmed independently: {ev.crash.crash_free_rate:.1f}% crash-free "
        f"over {ev.crash.sessions} sessions is below the declared "
        f"{ev.policy.halt_crash_free:.1f}%.",
        checks,
    )


def _widen(proposal: Proposal, ev: Evidence, breach: bool) -> Verdict:
    """Widening needs every condition, never any of them.

    The session floor is the one that catches the real mistake. At 20% of a small app
    a fresh release may have forty sessions, and "100% crash-free over 41 sessions"
    reads like evidence while carrying almost none. Below the floor the answer is
    wait, not widen.
    """
    p = ev.policy
    nxt = p.next_stage(ev.track.user_fraction)
    target = proposal.target_fraction if proposal.target_fraction is not None else nxt

    checks = [
        Check(
            "no_breach",
            not breach,
            f"measured {ev.crash.crash_free_rate:.1f}% vs halt line "
            f"{p.halt_crash_free:.1f}%",
        ),
        Check(
            "session_floor",
            ev.crash.sessions >= p.session_floor,
            f"{ev.crash.sessions} sessions vs floor of {p.session_floor}",
        ),
        Check(
            "time_at_stage",
            ev.hours_at_stage >= p.min_hours_per_stage,
            f"{ev.hours_at_stage:.1f}h at {ev.track.user_fraction:.0%} vs minimum "
            f"{p.min_hours_per_stage:.0f}h",
        ),
        Check(
            "not_below_baseline",
            ev.crash.crash_free_rate >= p.baseline_crash_free,
            f"measured {ev.crash.crash_free_rate:.1f}% vs pre-release baseline "
            f"{p.baseline_crash_free:.1f}%",
        ),
        Check(
            "rollout_is_live",
            ev.track.status == "inProgress",
            f"track status is {ev.track.status}",
        ),
        Check(
            "target_is_on_the_ladder",
            target is not None and any(abs(target - s) < 1e-9 for s in p.stages),
            f"target {target} vs declared stages {p.stages}",
        ),
        Check(
            "target_moves_forward",
            target is not None and target > ev.track.user_fraction + 1e-9,
            f"target {target} vs current {ev.track.user_fraction}",
        ),
    ]

    failed = [c for c in checks if not c.passed]
    if failed:
        return _v(False, "; ".join(c.detail for c in failed), checks)
    return _v(
        True,
        f"every widen condition holds: {ev.crash.sessions} sessions, "
        f"{ev.hours_at_stage:.1f}h at stage, {ev.crash.crash_free_rate:.1f}% crash-free. "
        f"Widening {ev.track.user_fraction:.0%} to {target:.0%}.",
        checks,
    )


def resolve_target(proposal: Proposal, ev: Evidence) -> float | None:
    """The fraction a WIDEN would be written at, after defaulting to the ladder."""
    if proposal.target_fraction is not None:
        return proposal.target_fraction
    return ev.policy.next_stage(ev.track.user_fraction)
