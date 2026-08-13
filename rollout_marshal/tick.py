"""One tick, start to finish.

Cloud Scheduler POSTs `/tick/{app}` every ten minutes. Everything below happens on
that request and nothing is remembered between them: the service is stateless, so a
scale-to-zero between ticks costs nothing and a crashed instance loses no judgement.

    read policy  ->  read track  ->  read crash-free  ->  agent proposes
                 ->  gate re-derives  ->  write to Play  ->  append decision  ->  email

The decision document is written whatever happens, including when the gate refuses
and including when the tick throws. An audit trail with gaps in it where things went
wrong is not an audit trail.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

from typing import Any

from . import log, notify
from .agent import Brain, build_brain
from .crash import CrashFeed, build_crash_feed
from .executor import Executor
from .models import Decision, Evidence, HOLD, Proposal, iso, iso_ms, now, parse
from .play import PlayClient, build_play_client
from .store import Store, build_store, stamp_stage
from .tools import TickContext


def _as_dict(p: Proposal) -> dict[str, Any]:
    return {
        "action": p.action,
        "target_fraction": p.target_fraction,
        "reasoning": p.reasoning,
    }


class Marshal:
    """Holds the collaborators for the life of the process. One per service."""

    def __init__(
        self,
        store: Store | None = None,
        play: PlayClient | None = None,
        crash: CrashFeed | None = None,
        brain: Brain | None = None,
        sender: notify.Sender | None = None,
        bus: log.LogBus | None = None,
    ):
        self.store = store or build_store()
        self.play = play or build_play_client()
        self.crash = crash or build_crash_feed()
        self.brain = brain or build_brain()
        self.sender = sender or notify.build_sender()
        self.bus = bus or log.BUS

    # -- evidence -----------------------------------------------------------

    def gather(self, app: str) -> Evidence:
        policy = self.store.get_policy(app)
        if policy is None:
            raise LookupError(
                f"no policies/{app} document: the halt number has to be written down "
                f"before the release goes out, so there is nothing to enforce."
            )
        track = self.play.get_track(policy.package, policy.track)
        entered = stamp_stage(self.store, app, track.user_fraction, track.status)
        hours = max(0.0, (now() - parse(entered)).total_seconds() / 3600.0)
        crash = self.crash.read(app, track.version_code)
        self.store.put_rollout(
            app,
            {
                "app": app,
                "package": policy.package,
                "track": policy.track,
                "version_code": track.version_code,
                "release_name": track.release_name,
                "status": track.status,
                "user_fraction": track.user_fraction,
                "stage_entered_at": entered,
                "policy_ref": f"policies/{app}",
                "updated_at": iso(now()),
            },
        )
        return Evidence(
            policy=policy,
            track=track,
            crash=crash,
            hours_at_stage=hours,
            stage_entered_at=entered,
        )

    # -- the tick -----------------------------------------------------------

    def tick(self, app: str) -> dict[str, Any]:
        self.bus.publish(log.TICK, app, f"tick: {app}")
        ev = self.gather(app)
        ctx = TickContext(evidence=ev, executor=Executor(self.play, self.bus), bus=self.bus)

        try:
            reasoning = self.brain.run(ctx)
        except Exception as e:  # a broken model must not leave the log silent
            reasoning = f"agent failed: {e.__class__.__name__}: {e}"
            self.bus.publish(log.ERROR, app, reasoning)

        proposal, verdict = ctx.decisive
        decision = Decision(
            ts=iso_ms(now()),
            app=app,
            inputs=ev.summary(),
            proposal=(
                _as_dict(proposal)
                if proposal
                else {"action": HOLD, "reasoning": "the agent proposed nothing"}
            ),
            gate_verdict=verdict.to_dict() if verdict else {},
            action_taken=ctx.action_taken,
            api_response=ctx.api_response,
            model_reasoning=reasoning,
            brain=self.brain.name,
            attempts=[
                {"proposal": _as_dict(p), "verdict": v.to_dict()} for p, v in ctx.attempts
            ],
        )
        decision_id = self.store.append_decision(decision)

        mailed = None
        if decision.action_taken != HOLD:
            subject, body = notify.compose(decision, decision_id)
            mailed = self.sender.send(subject, body)
            self.bus.publish(log.MAIL, app, f"emailed after the fact: {subject}", to=mailed)

        self.bus.publish(
            log.TICK,
            app,
            f"tick complete: {ctx.action_taken} (decisions/{decision_id})",
            decision_id=decision_id,
        )
        return {
            "app": app,
            "decision_id": decision_id,
            "action_taken": ctx.action_taken,
            "gate": decision.gate_verdict,
            "inputs": decision.inputs,
            "mailed": mailed,
        }
