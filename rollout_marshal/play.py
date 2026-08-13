"""The Play Developer API v3 client, and a fixture that behaves the same way.

The call sequence was measured against a real account on 2026-08-13 and is written
down in `notes/play-write-path.md`. There is no single "halt" endpoint. Every state
change is three calls:

    POST   .../edits                       -> {"id": editId}
    PUT    .../edits/{editId}/tracks/{track}
    POST   .../edits/{editId}:commit

A failed step must DELETE the edit, or the dangling edit blocks the next one. About
5.7 seconds end to end, which is why a halt lands inside a single polling interval.

`FixturePlayClient` implements the same two methods over a JSON file so the service
runs with no store credentials. It reproduces the one Play behaviour that matters to
the demo: a halted release can be resumed, so widen and halt and resume are the same
call with a different body.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .models import TrackState

API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"


class PlayClient(Protocol):
    def get_track(self, package: str, track: str) -> TrackState: ...
    def set_release(
        self, package: str, track: str, release: dict[str, Any]
    ) -> dict[str, Any]: ...


def _state_from_track(package: str, track: str, body: dict[str, Any]) -> TrackState:
    """Pick the release that is being rolled out, not the completed one beside it.

    A track normally carries two: the finished release everybody has, and the staged
    one. `inProgress` and `halted` are the two that a rollout decision is about.
    """
    releases = body.get("releases") or []
    live = [r for r in releases if r.get("status") in ("inProgress", "halted")]
    r = live[0] if live else (releases[0] if releases else {})
    return TrackState(
        package=package,
        track=track,
        release_name=r.get("name", ""),
        version_codes=[str(v) for v in (r.get("versionCodes") or [])],
        status=r.get("status", "none"),
        user_fraction=float(r.get("userFraction") or (1.0 if r.get("status") == "completed" else 0.0)),
        raw=body,
    )


class RealPlayClient:
    """Writes to a real Play account. Only `rollout_marshal.executor` is allowed to hold one."""

    def __init__(self, key_path: str | None = None):
        self.key_path = key_path or os.environ.get("PLAY_SERVICE_ACCOUNT_JSON", "")
        if not self.key_path:
            raise RuntimeError(
                "PLAY_SERVICE_ACCOUNT_JSON is not set; the live Play client needs a "
                "service-account key with the androidpublisher scope."
            )

    def _token(self) -> str:
        from google.oauth2 import service_account
        import google.auth.transport.requests as gr

        cr = service_account.Credentials.from_service_account_file(
            self.key_path, scopes=[SCOPE]
        )
        cr.refresh(gr.Request())
        return cr.token

    def _call(
        self, tok: str, url: str, method: str = "GET", body: dict | None = None
    ) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {tok}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode()
        except urllib.error.HTTPError as e:  # Play puts the useful part in the body
            raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {e.read().decode()}")
        return json.loads(raw) if raw.strip() else {}

    def get_track(self, package: str, track: str) -> TrackState:
        tok = self._token()
        eid = self._call(tok, f"{API}/{package}/edits", "POST", {})["id"]
        try:
            body = self._call(tok, f"{API}/{package}/edits/{eid}/tracks/{track}")
        finally:
            # A read must not leave an edit open, or the next write fails on it.
            try:
                self._call(tok, f"{API}/{package}/edits/{eid}", "DELETE")
            except Exception:
                pass
        return _state_from_track(package, track, body)

    def set_release(
        self, package: str, track: str, release: dict[str, Any]
    ) -> dict[str, Any]:
        tok = self._token()
        eid = self._call(tok, f"{API}/{package}/edits", "POST", {})["id"]
        body = {"track": track, "releases": [release]}
        try:
            put = self._call(
                tok, f"{API}/{package}/edits/{eid}/tracks/{track}", "PUT", body
            )
            commit = self._call(tok, f"{API}/{package}/edits/{eid}:commit", "POST")
        except Exception:
            try:
                self._call(tok, f"{API}/{package}/edits/{eid}", "DELETE")
            except Exception:
                pass
            raise
        return {
            "edit_id": eid,
            "request": body,
            "track_after_put": put,
            "commit": commit,
        }


class FixturePlayClient:
    """The same interface over a JSON file. No credentials, no network."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({}, indent=2))

    def _all(self) -> dict[str, Any]:
        return json.loads(self.path.read_text())

    def _key(self, package: str, track: str) -> str:
        return f"{package}/{track}"

    def seed(self, package: str, track: str, releases: list[dict[str, Any]]) -> None:
        d = self._all()
        d[self._key(package, track)] = {"track": track, "releases": releases}
        self.path.write_text(json.dumps(d, indent=2, sort_keys=True))

    def get_track(self, package: str, track: str) -> TrackState:
        body = self._all().get(self._key(package, track), {"track": track, "releases": []})
        return _state_from_track(package, track, body)

    def set_release(
        self, package: str, track: str, release: dict[str, Any]
    ) -> dict[str, Any]:
        d = self._all()
        key = self._key(package, track)
        body = d.get(key, {"track": track, "releases": []})
        keep = [
            r
            for r in body.get("releases", [])
            if r.get("status") not in ("inProgress", "halted")
        ]
        body["releases"] = keep + [release]
        d[key] = body
        self.path.write_text(json.dumps(d, indent=2, sort_keys=True))
        return {
            "edit_id": "fixture-edit",
            "request": {"track": track, "releases": [release]},
            "track_after_put": body,
            "commit": {"id": "fixture-edit"},
        }


def build_play_client() -> PlayClient:
    """`live` writes to Play. Anything else is the fixture, which is the default so
    that running the service by accident cannot touch a store account."""
    if os.environ.get("MARSHAL_PLAY", "fixture").lower() == "live":
        return RealPlayClient()
    return FixturePlayClient(
        os.environ.get("MARSHAL_PLAY_FIXTURE", ".marshal-state/play.json")
    )


def release_body(
    name: str, version_codes: list[str], status: str, fraction: float | None
) -> dict[str, Any]:
    """One release object, in the shape Play accepted in the measured run.

    `completed` must not carry a userFraction; `inProgress` and `halted` must.
    """
    r: dict[str, Any] = {
        "name": name,
        "versionCodes": [str(v) for v in version_codes],
        "status": status,
    }
    if status in ("inProgress", "halted") and fraction is not None:
        r["userFraction"] = round(float(fraction), 4)
    return r
