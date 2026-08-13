"""The values that move through one tick.

Everything here is plain data. The gate, the agent and the store all speak in these
types, which is what lets the crash feed and the Play client be swapped between a
fixture and the real API without any of them noticing.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import Any

WIDEN = "WIDEN"
HALT = "HALT"
HOLD = "HOLD"
ACTIONS = (WIDEN, HALT, HOLD)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def iso_ms(t: dt.datetime) -> str:
    """Milliseconds, for the decision log: two ticks can land inside one second, and
    the log is append-only, so its ids have to be distinct without a counter."""
    return t.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds")


def parse(t: str | dt.datetime) -> dt.datetime:
    if isinstance(t, dt.datetime):
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(t.replace("Z", "+00:00"))


@dataclass
class Policy:
    """Declared before the release ships, and immutable for its duration.

    The halt number is the whole point: it is written down by a human while nobody is
    under pressure, and neither the model nor the gate may move it.
    """

    app: str
    package: str
    track: str
    halt_crash_free: float
    stages: list[float]
    min_hours_per_stage: float
    session_floor: int
    baseline_crash_free: float
    created_at: str = field(default_factory=lambda: iso(now()))

    def next_stage(self, current: float) -> float | None:
        for s in self.stages:
            if s > current + 1e-9:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Policy":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class TrackState:
    """What the Play track says right now, read fresh every tick."""

    package: str
    track: str
    release_name: str
    version_codes: list[str]
    status: str  # inProgress | halted | completed | draft
    user_fraction: float
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def version_code(self) -> str:
        return self.version_codes[0] if self.version_codes else ""


@dataclass
class CrashReading:
    """Release health for the version on the track."""

    crash_free_rate: float
    sessions: int
    release: str
    source: str  # "sentry" or "fixture:<name>"


@dataclass
class Evidence:
    """Everything one tick knows, assembled before the model is called."""

    policy: Policy
    track: TrackState
    crash: CrashReading
    hours_at_stage: float
    stage_entered_at: str

    def summary(self) -> dict[str, Any]:
        return {
            "app": self.policy.app,
            "package": self.policy.package,
            "track": self.track.track,
            "version_code": self.track.version_code,
            "status": self.track.status,
            "user_fraction": self.track.user_fraction,
            "crash_free": self.crash.crash_free_rate,
            "sessions": self.crash.sessions,
            "crash_source": self.crash.source,
            "hours_at_stage": round(self.hours_at_stage, 2),
            "halt_criterion": self.policy.halt_crash_free,
            "session_floor": self.policy.session_floor,
            "min_hours_per_stage": self.policy.min_hours_per_stage,
            "baseline_crash_free": self.policy.baseline_crash_free,
            "stages": self.policy.stages,
        }


@dataclass
class Proposal:
    """Exactly one action per tick, with the model's reasoning attached."""

    action: str
    target_fraction: float | None = None
    reasoning: str = ""


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Verdict:
    """What the gate decided, and every condition it re-derived to decide it."""

    allowed: bool
    reason: str
    checks: list[Check] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "checks": [asdict(c) for c in self.checks],
        }


@dataclass
class Decision:
    """One append-only row of the audit trail. Also the demo's right-hand pane."""

    ts: str
    app: str
    inputs: dict[str, Any]
    proposal: dict[str, Any]
    gate_verdict: dict[str, Any]
    action_taken: str
    api_response: dict[str, Any] | None
    model_reasoning: str
    brain: str
    # Every proposal the agent made this tick, in order, with what the gate said to
    # each. A refused proposal is part of the record: it is what the agent wanted.
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
