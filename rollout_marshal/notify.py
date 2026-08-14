"""The email, which goes out after the fact rather than before.

That ordering is the product. A human who has to approve the halt is a human who has
to be awake for it, and then the agent has bought nothing. So the mail says what was
already done, with the numbers it was done on and the decision id to audit it by.

`FileSender` is the default: it writes the message under the state directory, so the
demo and the tests exercise the same code path without sending anything anywhere.
`SmtpSender` is used when the SMTP settings are present.

The opening paragraph comes from `rollout_marshal.scribe` and everything below it is
assembled here from the decision document. Splitting the mail that way is deliberate:
the sentence a person reads first is worth having a model write, and not one number in
it is.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from .models import Decision, iso, now
from .scribe import Scribe, build_scribe


class Sender(Protocol):
    def send(self, subject: str, body: str) -> str: ...


class FileSender:
    def __init__(self, root: str | Path):
        self.root = Path(root) / "mail"
        self.root.mkdir(parents=True, exist_ok=True)

    def send(self, subject: str, body: str) -> str:
        name = iso(now()).replace(":", "").replace("-", "") + ".eml"
        path = self.root / name
        path.write_text(f"Subject: {subject}\n\n{body}\n")
        return str(path)


class SmtpSender:
    def __init__(self, host: str, port: int, user: str, password: str, to: str):
        self.host, self.port, self.user, self.password, self.to = (
            host,
            port,
            user,
            password,
            to,
        )

    def send(self, subject: str, body: str) -> str:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = self.to
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(self.user, self.password)
            s.send_message(msg)
        return f"smtp:{self.to}"


def build_sender() -> Sender:
    user = os.environ.get("MARSHAL_SMTP_USER")
    pwd = os.environ.get("MARSHAL_SMTP_PASSWORD")
    to = os.environ.get("MARSHAL_MAIL_TO")
    if user and pwd and to:
        return SmtpSender(
            os.environ.get("MARSHAL_SMTP_HOST", "smtp.gmail.com"),
            int(os.environ.get("MARSHAL_SMTP_PORT", "587")),
            user,
            pwd,
            to,
        )
    return FileSender(os.environ.get("MARSHAL_STATE_DIR", ".marshal-state"))


def compose(d: Decision, decision_id: str, scribe: Scribe | None = None) -> tuple[str, str]:
    """The message. Short, because it is read on a phone at an unhelpful hour.

    The opening paragraph is written by the scribe; everything under it is assembled
    from the decision document, so the prose can be wrong about tone and still cannot
    be wrong about a number.
    """
    i = d.inputs
    summary, wrote_it = (scribe or build_scribe()).summarise(d)
    verb = {"HALT": "halted", "WIDEN": "widened", "HOLD": "held"}.get(
        d.action_taken, d.action_taken.lower()
    )
    subject = (
        f"Rollout Marshal: {i['app']} {verb}"
        + (f" at {i['user_fraction']:.0%}" if d.action_taken != "HOLD" else "")
    )
    lines = [
        summary,
        "",
        f"{i['app']} — {i['package']} / {i['track']}, version {i['version_code']}",
        "",
        f"Action taken: {d.action_taken}",
        f"Declared halt line: {i['halt_criterion']}% crash-free",
        f"Measured: {i['crash_free']}% over {i['sessions']} sessions ({i['crash_source']})",
        f"Time at stage: {i['hours_at_stage']}h at {i['user_fraction']:.0%}",
        "",
        f"Gate: {d.gate_verdict.get('reason', '')}",
        f"Agent ({d.brain}): {d.model_reasoning}",
        "",
        f"Decision: decisions/{decision_id}",
        "",
        "Sent after the action, not before. Nobody was watching.",
        f"The first paragraph was written by {wrote_it}; every number under it was "
        f"copied from the decision document.",
        "Rollout Marshal is an autonomous agent working for Joe Muller.",
    ]
    return subject, "\n".join(lines)
