"""One sandbox fixture, and the reason it pins more variables than it uses.

Every outside edge of this service is chosen by an environment variable, and each one
defaults to the safe fixture. That default is only safe for a test if the variable is
unset, and a developer who has just run the live demo has `MARSHAL_PLAY=live` and a
Play service-account key exported in the same shell. A test that set only
`MARSHAL_STATE_DIR` would then write to a real Play track, and `MARSHAL_SMTP_USER`
would put the halt email in somebody's inbox.

So `sandbox` pins the whole set — the ones the test uses and the ones it does not —
and points every path inside `tmp_path`.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")

# Everything any edge of the service reads. Anything named here is either set to a
# sandbox value below or removed outright.
CLEARED = (
    "MARSHAL_PLAY",
    "MARSHAL_STORE",
    "MARSHAL_CRASH_FEED",
    "MARSHAL_SMTP_USER",
    "MARSHAL_SMTP_PASSWORD",
    "MARSHAL_SMTP_HOST",
    "MARSHAL_SMTP_PORT",
    "MARSHAL_MAIL_TO",
    "MARSHAL_CRASH_PERIOD",
    "MARSHAL_SCRIBE",
    "MARSHAL_SCRIBE_MODEL",
    "MARSHAL_TTS",
    "PLAY_SERVICE_ACCOUNT_JSON",
    "SENTRY_ORG",
    "SENTRY_AUTH_TOKEN",
    "SENTRY_PROJECT",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_API_KEY",
)


ROOT = Path(__file__).resolve().parent.parent


# The suite reads `demo/fixtures/*.json` by relative path, as the demo does. Run from
# anywhere else and every test module fails to import instead, which reads as a broken
# checkout rather than a wrong working directory. This runs before collection, which is
# why it is here and not in a fixture.
if Path.cwd() != ROOT:
    raise pytest.UsageError(
        f"run the tests from {ROOT}: `.venv/bin/python -m pytest tests -q`"
    )


class Sandbox:
    def __init__(self, root: Path):
        self.root = root
        self.play_fixture = root / "play.json"
        self.crash_fixture = root / "crash.json"

    def env(self) -> dict[str, str]:
        """The same settings as a dict, for a subprocess."""
        return {
            "MARSHAL_STATE_DIR": str(self.root),
            "MARSHAL_PLAY_FIXTURE": str(self.play_fixture),
            "MARSHAL_CRASH_FIXTURE": str(self.crash_fixture),
            "MARSHAL_BRAIN": "scripted",
        }


@pytest.fixture
def sandbox(tmp_path, monkeypatch) -> Sandbox:
    s = Sandbox(tmp_path)
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    for name, value in s.env().items():
        monkeypatch.setenv(name, value)
    return s
