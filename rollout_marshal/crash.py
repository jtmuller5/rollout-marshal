"""Release health: crash-free session rate and session count for one release.

Two implementations behind one interface, and the seam is deliberate rather than a
testing convenience. Shot 4b of the demo injects a crash spike, out loud, by pointing
the fixture feed at a different file — so the fixture has to be swappable while the
service is running, and the swap has to be visible in the log line the agent reads.

`SentryCrashFeed` is the live one. The endpoint is the sessions API:

    GET /organizations/{org}/sessions/
        ?project={id}&field=sum(session)&field=crash_free_rate(session)
        &groupBy=release&statsPeriod=24h

The numbers in `fixtures/spike.json` are not invented. A real app in this portfolio
shipped a release that ran at 76.9% crash-free over 412 sessions against a 95% line,
and was halted by hand. That measurement is the ground truth this agent automates.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .models import CrashReading

SENTRY_API = "https://sentry.io/api/0"


class CrashFeed(Protocol):
    def read(self, app: str, release: str) -> CrashReading: ...


class FixtureCrashFeed:
    """Reads a JSON file on every call, so the file can be replaced mid-run.

    The file is read at call time rather than at construction on purpose: that is the
    whole mechanism behind shot 4b, and it means a spike can be injected into a
    running service without a restart and without a code path that only exists for
    the demo.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self, app: str, release: str) -> CrashReading:
        doc: dict[str, Any] = json.loads(self.path.read_text())
        return CrashReading(
            crash_free_rate=float(doc["crash_free_rate"]),
            sessions=int(doc["sessions"]),
            release=doc.get("release", release),
            source=f"fixture:{doc.get('name', self.path.stem)}",
        )


class SentryCrashFeed:
    """Live release health from Sentry."""

    def __init__(self, org: str | None = None, token: str | None = None):
        self.org = org or os.environ.get("SENTRY_ORG", "")
        self.token = token or os.environ.get("SENTRY_AUTH_TOKEN", "")
        if not (self.org and self.token):
            raise RuntimeError("SENTRY_ORG and SENTRY_AUTH_TOKEN are both required")

    def _get(self, path: str) -> Any:
        req = urllib.request.Request(
            f"{SENTRY_API}{path}", headers={"Authorization": f"Bearer {self.token}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"sentry HTTP {e.code} on {path}: {e.read().decode('utf-8', 'replace')[:300]}"
            )

    def read(self, app: str, release: str) -> CrashReading:
        slug = os.environ.get("SENTRY_PROJECT", app)
        pid = str(self._get(f"/projects/{self.org}/{slug}/")["id"])
        qs = urllib.parse.urlencode(
            [
                ("project", pid),
                ("field", "sum(session)"),
                ("field", "crash_free_rate(session)"),
                ("groupBy", "release"),
                ("interval", "1h"),
                ("statsPeriod", os.environ.get("MARSHAL_CRASH_PERIOD", "24h")),
            ]
        )
        data = self._get(f"/organizations/{self.org}/sessions/?{qs}")
        for g in data.get("groups", []):
            # Sentry's release name usually carries the version code as `name+code`.
            if release and release not in str(g["by"].get("release", "")):
                continue
            n = int(g["totals"].get("sum(session)") or 0)
            rate = g["totals"].get("crash_free_rate(session)")
            if rate is None:
                continue
            return CrashReading(
                crash_free_rate=round(float(rate) * 100, 3),
                sessions=n,
                release=str(g["by"]["release"]),
                source="sentry",
            )
        # An unreadable rate is a gap, not a clean build. Saying zero sessions keeps
        # the session floor closed, so the gate refuses to widen on missing data.
        return CrashReading(0.0, 0, release, "sentry:no-data")


def build_crash_feed() -> CrashFeed:
    if os.environ.get("MARSHAL_CRASH_FEED", "fixture").lower() == "sentry":
        return SentryCrashFeed()
    return FixtureCrashFeed(
        os.environ.get("MARSHAL_CRASH_FIXTURE", "demo/fixtures/quiet.json")
    )
