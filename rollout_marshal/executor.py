"""The only place a store credential is used.

The agent proposes. The gate allows. This module writes. Splitting the third step out
is not tidiness: it is the answer to "are the tools properly isolated and scoped for
security?" — the model's tool surface is `rollout_marshal.tools`, which holds no credential
and can reach this module only through a `Verdict` that `rollout_marshal.gate` produced.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

from typing import Any

from . import log
from .gate import resolve_target
from .models import Evidence, Proposal, Verdict, HALT, WIDEN
from .play import PlayClient, release_body


class Executor:
    def __init__(self, play: PlayClient, bus: log.LogBus | None = None):
        self.play = play
        self.bus = bus or log.BUS

    def apply(self, proposal: Proposal, ev: Evidence, verdict: Verdict) -> dict[str, Any]:
        """Perform the allowed action. Raises if called with a refusal."""
        if not verdict.allowed:
            raise AssertionError("executor called on a refused proposal")

        app = ev.policy.app
        track = ev.track

        if proposal.action == HALT:
            body = release_body(
                track.release_name, track.version_codes, "halted", track.user_fraction
            )
        elif proposal.action == WIDEN:
            target = resolve_target(proposal, ev)
            body = release_body(
                track.release_name, track.version_codes, "inProgress", target
            )
        else:
            return {"noop": True}

        self.bus.publish(
            log.ACT,
            app,
            f"{proposal.action}: PUT tracks/{track.track} "
            f"{body['status']} userFraction={body.get('userFraction')}",
            request=body,
            package=ev.policy.package,
            track=track.track,
        )
        resp = self.play.set_release(ev.policy.package, track.track, body)
        self.bus.publish(
            log.API,
            app,
            f"Play committed edit {resp.get('edit_id')} — "
            f"{body['status']} at {body.get('userFraction')}",
            response=resp,
        )
        return resp
