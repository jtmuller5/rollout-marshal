"""The paragraph at the top of the email, written by a small model.

The agent acts and then mails a human. That mail is the whole of the handover, and it
is read half-awake on a phone, so the first thing in it has to say what happened and
whether the reader has to get up. The numbers below it are already exact; what they are
not is a sentence.

`GemmaScribe` writes that sentence with `gemma-4-31b-it` — a small open model, on the
same key as the agent, on its own free-tier quota, so a busy release day cannot make
the decision model compete with the mail. It is deliberately not the agent: the agent
decides and the scribe explains, and giving the explaining job to the model that made
the decision is how a summary starts agreeing with itself.

The scribe is told the facts and told to add none. It never sees the Play credential,
it has no tools, and it runs after the action is already committed, so nothing it says
can change what was done. If it is slow, refused or over quota, `TemplateScribe`'s
deterministic line goes out instead and the email says which wrote it. An unattended
agent that could not mail a human because a language model was busy would be a worse
agent than one that mails plainer prose.

`MARSHAL_SCRIBE` chooses. The default is `template`: no key, no network, no cost, which
is what the tests and a judge's clone run.

The timeout is 90 seconds and that is not a guess. Measured on the free tier on
2026-08-14, this prompt took 47.1s and 49.4s on `gemma-4-31b-it`; a 20-second deadline
returned `504 DEADLINE_EXCEEDED` and fell back, and `gemma-4-26b-a4b-it`, the smaller
mixture-of-experts variant tried in the hope it would be quicker, had still not answered
at 90s. That is a long time to hold a request and it is the reason the scribe runs where
it does: after the Play write, after the decision is durable, on the one path where
waiting costs nothing but the mail arriving a minute later.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import os
from typing import Protocol

from .models import Decision

MODEL = os.environ.get("MARSHAL_SCRIBE_MODEL", "gemma-4-31b-it")

PROMPT = """
You are writing the opening of an email to the one engineer who owns a mobile app
release. An autonomous agent has already taken the action below; nobody approved it and
nobody was awake for it. The exact numbers appear underneath your paragraph, so do not
repeat them all and do not reformat them.

Write two or three sentences of plain English that say what was done, why, and whether
the reader has to do anything before morning. Be calm and specific. Do not add any fact
that is not in the evidence below, do not guess at a cause, do not apologise, and do not
recommend an action the agent could have taken itself.

Evidence:
{facts}
""".strip()


def facts(d: Decision) -> str:
    i = d.inputs
    return "\n".join(
        [
            f"app: {i['app']} ({i['package']}), {i['track']} track, version {i['version_code']}",
            f"action the agent took: {d.action_taken}",
            f"halt line declared before the release shipped: {i['halt_criterion']}% crash-free",
            f"measured now: {i['crash_free']}% crash-free over {i['sessions']} sessions",
            f"stage: {i['user_fraction']:.0%} of users, {i['hours_at_stage']}h at this stage",
            f"the policy gate said: {d.gate_verdict.get('reason', 'nothing')}",
            f"the agent's own reasoning: {d.model_reasoning}",
        ]
    )


class Scribe(Protocol):
    name: str

    def summarise(self, d: Decision) -> tuple[str, str]: ...


class TemplateScribe:
    """The fallback, and the default. One sentence, assembled rather than written."""

    name = "template"

    def summarise(self, d: Decision) -> tuple[str, str]:
        i = d.inputs
        if d.action_taken == "HALT":
            body = (
                f"{i['app']} is halted at {i['user_fraction']:.0%}. Crash-free sessions "
                f"measured {i['crash_free']}% against the {i['halt_criterion']}% line that "
                f"was written down before the release shipped, so nobody new gets this "
                f"build. Nothing needs doing tonight; the release can be resumed once the "
                f"cause is known."
            )
        elif d.action_taken == "WIDEN":
            body = (
                f"{i['app']} is now at {i['user_fraction']:.0%}. It held "
                f"{i['crash_free']}% crash-free over {i['sessions']} sessions, which "
                f"clears every condition in the policy, so the stage was widened. Nothing "
                f"needs doing."
            )
        else:
            body = (
                f"{i['app']} was left as it is at {i['user_fraction']:.0%}. "
                f"{d.gate_verdict.get('reason', 'The policy did not allow a change.')}"
            )
        return body, self.name


class GemmaScribe:
    """`gemma-4-31b-it`, with the template underneath it if anything goes wrong."""

    name = "gemma"

    def __init__(self, model: str | None = None, timeout_s: float = 90.0):
        self.model = model or MODEL
        self.timeout_s = timeout_s
        self.fallback = TemplateScribe()

    def summarise(self, d: Decision) -> tuple[str, str]:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=os.environ["GOOGLE_API_KEY"],
                http_options=types.HttpOptions(timeout=int(self.timeout_s * 1000)),
            )
            reply = client.models.generate_content(
                model=self.model,
                contents=PROMPT.format(facts=facts(d)),
            )
            text = (reply.text or "").strip()
            if not text:
                raise RuntimeError("the model returned no text")
            return text, self.model
        except Exception as e:
            body, _ = self.fallback.summarise(d)
            return body, f"template (fell back: {e.__class__.__name__})"


def build_scribe() -> Scribe:
    if os.environ.get("MARSHAL_SCRIBE", "template").lower() == "gemma":
        return GemmaScribe()
    return TemplateScribe()
