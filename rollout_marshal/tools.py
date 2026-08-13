"""The agent's tool surface, bound to one tick.

These four functions are everything the model can do. Three of them read; the fourth
proposes an action and returns what the gate said about it. None of them holds a
credential — `propose_action` reaches the store only through `rollout_marshal.gate`, and only
when the gate returns allowed.

The refusal path is the interesting one. When the gate says no, that comes back here
as an ordinary tool result with the reason attached, and the agent has to answer it.
An agent that can only be told yes has not been given a policy; it has been given a
suggestion.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from . import gate, log
from .executor import Executor
from .models import Evidence, Proposal, Verdict, HOLD


@dataclass
class TickContext:
    """One tick's evidence, and what the agent did with it."""

    evidence: Evidence
    executor: Executor
    bus: log.LogBus = field(default_factory=lambda: log.BUS)
    proposal: Proposal | None = None
    verdict: Verdict | None = None
    api_response: dict[str, Any] | None = None
    acted: bool = False
    attempts: list[tuple[Proposal, Verdict]] = field(default_factory=list)

    @property
    def app(self) -> str:
        return self.evidence.policy.app

    @property
    def action_taken(self) -> str:
        for p, v in self.attempts:
            if v.allowed and p.action != HOLD:
                return p.action
        return HOLD

    @property
    def decisive(self) -> tuple[Proposal | None, Verdict | None]:
        """The attempt the tick is about.

        An allowed action if there was one; otherwise the first refusal, because on a
        tick that ended in a refusal the interesting fact is what the agent wanted and
        was not allowed to do — not the HOLD it settled for afterwards.
        """
        for p, v in self.attempts:
            if v.allowed and p.action != HOLD:
                return p, v
        for p, v in self.attempts:
            if not v.allowed:
                return p, v
        return (self.attempts[-1] if self.attempts else (None, None))

    def record(self, proposal: Proposal, verdict: Verdict) -> None:
        self.attempts.append((proposal, verdict))
        self.proposal, self.verdict = proposal, verdict


def build_tools(ctx: TickContext) -> list[Callable[..., Any]]:
    """Return the four functions the agent is given, closed over this tick."""

    ev = ctx.evidence

    def read_policy() -> dict:
        """Read the rollout policy that was declared before this release shipped.

        Returns the halt crash-free percentage, the stage ladder, the minimum hours
        per stage, the session floor and the pre-release baseline. These are set by a
        human in advance and cannot be changed from here.
        """
        p = ev.policy
        ctx.bus.publish(
            log.READ,
            ctx.app,
            f"policies/{p.app}: halt below {p.halt_crash_free}% crash-free, "
            f"stages {p.stages}, {p.min_hours_per_stage}h per stage, "
            f"floor {p.session_floor} sessions (declared {p.created_at})",
        )
        return p.to_dict()

    def read_track_state() -> dict:
        """Read the current state of the release on the Play track.

        Returns the version code, the release status (inProgress, halted or
        completed), the fraction of users it is currently offered to, and how many
        hours it has been at that fraction.
        """
        t = ev.track
        ctx.bus.publish(
            log.READ,
            ctx.app,
            f"Play {t.package}/{t.track}: {t.release_name} ({t.version_code}) "
            f"{t.status} at {t.user_fraction:.0%}, {ev.hours_at_stage:.1f}h at this stage",
        )
        return {
            "package": t.package,
            "track": t.track,
            "release_name": t.release_name,
            "version_code": t.version_code,
            "status": t.status,
            "user_fraction": t.user_fraction,
            "hours_at_stage": round(ev.hours_at_stage, 2),
        }

    def read_crash_free() -> dict:
        """Read release health for the version currently on the track.

        Returns the crash-free session rate as a percentage, the number of sessions
        it was measured over, and where the reading came from. A small session count
        means the rate says very little, whatever the number is.
        """
        c = ev.crash
        ctx.bus.publish(
            log.READ,
            ctx.app,
            f"release health [{c.source}]: {c.crash_free_rate}% crash-free "
            f"over {c.sessions} sessions",
        )
        return {
            "crash_free_rate": c.crash_free_rate,
            "sessions": c.sessions,
            "release": c.release,
            "source": c.source,
        }

    def propose_action(action: str, reasoning: str, target_fraction: float = -1.0) -> dict:
        """Propose exactly one action for this tick and submit it to the policy gate.

        Args:
          action: one of WIDEN, HALT or HOLD.
          reasoning: why, in one or two sentences, naming the numbers you used.
          target_fraction: for WIDEN only, the fraction to move to, for example 0.5.
            Pass -1.0 to take the next stage from the declared ladder.

        Returns whether the gate allowed it, the reason, and every condition the gate
        re-derived. A refusal is a real answer: read the reason and decide again.
        """
        target = None if target_fraction is None or target_fraction < 0 else target_fraction
        proposal = Proposal(
            action=(action or "").strip().upper(), target_fraction=target, reasoning=reasoning
        )
        ctx.bus.publish(
            log.PROPOSE,
            ctx.app,
            f"agent proposes {proposal.action}"
            + (f" to {target:.0%}" if target is not None else "")
            + f" — {reasoning}",
            action=proposal.action,
            target_fraction=target,
        )

        if ctx.acted:
            v = Verdict(False, "this tick has already taken an action; one per tick.")
            ctx.record(proposal, v)
            ctx.bus.publish(log.GATE_NO, ctx.app, f"gate refuses: {v.reason}")
            return v.to_dict()

        verdict = gate.evaluate(proposal, ev)
        ctx.record(proposal, verdict)

        if not verdict.allowed:
            ctx.bus.publish(
                log.GATE_NO,
                ctx.app,
                f"gate refuses {proposal.action}: {verdict.reason}",
                **verdict.to_dict(),
            )
            out = verdict.to_dict()
            out["action_taken"] = "none"
            return out

        ctx.bus.publish(
            log.GATE_OK,
            ctx.app,
            f"gate allows {proposal.action}: {verdict.reason}",
            **verdict.to_dict(),
        )
        if proposal.action == HOLD:
            ctx.acted = True
            return {**verdict.to_dict(), "action_taken": HOLD}

        resp = ctx.executor.apply(proposal, ev, verdict)
        ctx.api_response, ctx.acted = resp, True
        out = verdict.to_dict()
        out["action_taken"] = proposal.action
        out["api_response"] = {
            "edit_id": resp.get("edit_id"),
            "committed": bool(resp.get("commit")),
            "release": (resp.get("request") or {}).get("releases", [{}])[0],
        }
        return out

    return [read_policy, read_track_state, read_crash_free, propose_action]
