"""The agent, and a deterministic stand-in for it.

`AdkBrain` is the real one: an ADK `LlmAgent` on Gemini 3.5, through Vertex AI or the
Gemini API, given the four tools in `rollout_marshal.tools` and told to reach exactly one
proposal per tick. It is the component the contest's model requirement is met by, and
it is genuinely deciding — it reads the numbers, it picks the action, and when the
gate refuses it has to answer the refusal.

`ScriptedBrain` calls the same four tools in the same order with no model at all. It
exists for two honest reasons and neither of them is a fallback in production:

* the gate, the executor, the store and the Play write path can be tested and
  demonstrated without spending a token or holding a Gemini credential, and
* it is the control. If the scripted brain and the agent reach different actions on
  the same evidence, that difference is the model's contribution, stated out loud
  rather than assumed.

Which one runs is `MARSHAL_BRAIN`. Cloud Run sets `adk`.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Protocol

from . import log
from .models import HALT, HOLD, WIDEN
from .tools import TickContext, build_tools

INSTRUCTION = """
You are Rollout Marshal. You own one staged mobile app release and you run unattended,
once per tick, with nobody watching. Your job on this tick is to reach exactly one
action and submit it.

Do this, in order:

1. Call read_policy. The halt number in it was written down by a human before the
   release shipped. It is not yours to reinterpret.
2. Call read_track_state and read_crash_free.
3. State the declared halt number and the measured crash-free rate in your reasoning,
   as numbers, before you choose.
4. Call propose_action exactly once with WIDEN, HALT or HOLD.

How to choose:

* If the measured crash-free rate is below the declared halt number, propose HALT.
  Halting is cheap and reversible in the way that matters: nobody new gets the build,
  and a halted release can be resumed later.
* If the release is healthy and you believe it should reach more users, propose WIDEN.
  Widening is the expensive direction, so the gate holds it to every condition in the
  policy at once: enough hours at the current stage, enough sessions to read the rate
  at all, and no drop against the pre-release baseline.
* Otherwise propose HOLD.

The policy gate is code, not a conversation. If it refuses, the reason it gives is a
fact about the policy, not an obstacle to route around. Do not repeat the same
proposal, do not argue with it, and do not try a different fraction to get past a
condition that is not about the fraction. Accept the refusal, say in one sentence
what you will do instead, and stop. HOLD after a refusal is a correct outcome and is
often the right one.

Never propose more than one action per tick. Finish with one short paragraph: what you
read, what you proposed, what the gate said, and what happens next.
""".strip()


class Brain(Protocol):
    name: str

    def run(self, ctx: TickContext) -> str: ...


class ScriptedBrain:
    """The same four tool calls, with the decision rule written out in Python."""

    name = "scripted"

    def run(self, ctx: TickContext) -> str:
        read_policy, read_track_state, read_crash_free, propose_action = build_tools(ctx)
        policy = read_policy()
        track = read_track_state()
        crash = read_crash_free()

        declared = float(policy["halt_crash_free"])
        measured = float(crash["crash_free_rate"])
        breach = measured < declared
        ctx.bus.publish(
            log.THINK,
            ctx.app,
            f"declared {declared}% crash-free; measured {measured}% over "
            f"{crash['sessions']} sessions — {'breach' if breach else 'within policy'}",
        )

        if breach and track["status"] == "inProgress":
            action, reason = HALT, (
                f"measured {measured}% is below the declared {declared}% halt line "
                f"over {crash['sessions']} sessions"
            )
        elif track["status"] == "inProgress":
            action, reason = WIDEN, (
                f"{measured}% crash-free over {crash['sessions']} sessions after "
                f"{track['hours_at_stage']}h at {track['user_fraction']:.0%}"
            )
        else:
            action, reason = HOLD, f"release is {track['status']}, nothing to decide"

        result = propose_action(action=action, reasoning=reason)
        if not result.get("allowed") and action != HOLD:
            # The refusal comes back as a tool result, and the answer to it is to wait.
            ctx.bus.publish(
                log.THINK,
                ctx.app,
                f"gate refused {action}; accepting the refusal and holding",
            )
            propose_action(
                action=HOLD,
                reasoning=f"gate refused {action}: {result.get('reason')}",
            )
            return (
                f"Proposed {action}; the gate refused ({result.get('reason')}). "
                f"Holding until the next tick."
            )
        return f"Proposed {action}; gate {'allowed' if result.get('allowed') else 'refused'} it."


class AdkBrain:
    """Gemini 3.5 through ADK, with the tools above and nothing else."""

    name = "adk"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("MARSHAL_MODEL", "gemini-3.5-flash")

    def _agent(self, ctx: TickContext):
        from google.adk.agents import LlmAgent

        return LlmAgent(
            name="rollout_marshal",
            model=self.model,
            description="Owns one staged mobile release: widen it, hold it, or halt it.",
            instruction=INSTRUCTION,
            tools=build_tools(ctx),
        )

    async def _run(self, ctx: TickContext) -> str:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        sessions = InMemorySessionService()
        app_name = "rollout-marshal"
        session_id = f"tick-{ctx.evidence.policy.app}-{ctx.evidence.track.version_code}"
        await sessions.create_session(
            app_name=app_name, user_id="scheduler", session_id=session_id
        )
        runner = Runner(app_name=app_name, agent=self._agent(ctx), session_service=sessions)

        prompt = (
            f"Tick for {ctx.evidence.policy.app}. Read the policy, the track state and "
            f"release health, then propose exactly one action."
        )
        final = ""
        async for event in runner.run_async(
            user_id="scheduler",
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        ):
            text = _event_text(event)
            if not text:
                continue
            ctx.bus.publish(log.THINK, ctx.app, text)
            final = text
        return final

    def run(self, ctx: TickContext) -> str:
        return asyncio.run(self._run(ctx))


def _event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    return " ".join(p.text.strip() for p in parts if getattr(p, "text", None)).strip()


def build_brain() -> Brain:
    if os.environ.get("MARSHAL_BRAIN", "scripted").lower() == "adk":
        return AdkBrain()
    return ScriptedBrain()
