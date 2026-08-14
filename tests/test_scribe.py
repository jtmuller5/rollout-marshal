"""The email's opening paragraph, and the two ways it must never fail.

The scribe is the only part of this service whose output is prose, so it is the only
part that cannot be checked by comparing it to a number. What can be checked is the
shape around it: that the numbers under the paragraph are still the decision's own,
that a model which throws does not take the email down with it, and that the reader is
told which one wrote the words. Those three are what these tests hold.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from rollout_marshal import notify  # noqa: E402
from rollout_marshal.models import Decision  # noqa: E402
from rollout_marshal.scribe import (  # noqa: E402
    GemmaScribe,
    TemplateScribe,
    build_scribe,
    facts,
)


def decision(action="HALT", crash_free=76.9, fraction=0.2) -> Decision:
    return Decision(
        ts="2026-08-14T01:00:00.000+00:00",
        app="bakedown",
        inputs={
            "app": "bakedown",
            "package": "com.sapidlabs.abis_recipes",
            "track": "alpha",
            "version_code": 121,
            "halt_criterion": 95.0,
            "crash_free": crash_free,
            "sessions": 412,
            "crash_source": "fixture",
            "user_fraction": fraction,
            "hours_at_stage": 8.0,
        },
        proposal={"action": action, "reasoning": "measured below the declared line"},
        gate_verdict={"allowed": True, "reason": "halt is always allowed"},
        action_taken=action,
        api_response={},
        model_reasoning="Proposed HALT; gate allowed it.",
        brain="scripted",
    )


def test_the_template_scribe_needs_no_model_and_no_key(sandbox):
    assert isinstance(build_scribe(), TemplateScribe)


def test_the_halt_paragraph_says_what_was_done_and_what_to_do():
    body, who = TemplateScribe().summarise(decision())
    assert who == "template"
    assert "halted at 20%" in body
    assert "76.9%" in body and "95.0%" in body
    assert "resumed" in body


def test_a_scribe_that_throws_still_produces_the_email(sandbox):
    # `sandbox` removes GOOGLE_API_KEY, so the client construction raises KeyError.
    # That is the same path a quota refusal or a timeout takes.
    body, who = GemmaScribe().summarise(decision())
    assert who.startswith("template (fell back:")
    assert "halted at 20%" in body


def test_the_mail_leads_with_the_paragraph_and_keeps_the_numbers_underneath():
    d = decision()
    subject, mail = notify.compose(d, "2026-08-14T010000.000Z", TemplateScribe())

    assert subject == "Rollout Marshal: bakedown halted at 20%"
    first = mail.splitlines()[0]
    assert first.startswith("bakedown is halted at 20%")

    # The evidence block is assembled from the decision, not from the prose.
    assert "Declared halt line: 95.0% crash-free" in mail
    assert "Measured: 76.9% over 412 sessions (fixture)" in mail
    assert "Decision: decisions/2026-08-14T010000.000Z" in mail


def test_the_reader_is_told_which_model_wrote_the_paragraph():
    _, mail = notify.compose(decision(), "id", TemplateScribe())
    assert "The first paragraph was written by template" in mail
    assert "copied from the decision document" in mail


def test_the_model_is_given_the_facts_and_not_the_credential():
    text = facts(decision())
    assert "76.9% crash-free over 412 sessions" in text
    assert "95.0% crash-free" in text
    assert "action the agent took: HALT" in text
    # Everything the scribe sees is in this string, and none of it is a secret.
    assert "key" not in text.lower()


def test_a_widen_and_a_hold_read_differently():
    widen, _ = TemplateScribe().summarise(decision(action="WIDEN", crash_free=99.6, fraction=0.5))
    hold, _ = TemplateScribe().summarise(decision(action="HOLD", crash_free=100.0))
    assert "now at 50%" in widen and "Nothing needs doing." in widen
    assert "left as it is" in hold
    assert "halt is always allowed" in hold
