"""What the still shots put on screen, gathered from the things that already hold it.

The window of each shot comes from `notes/demo-script.md`, through the same parser the
narration uses, so a shot cannot be recorded to a length the voice does not agree with.
The policy comes from the store the environment selects — `MARSHAL_STORE=firestore` and
the credential give the real one, with the real `created_at` — and never from a literal
here. The diagram nodes are named by mermaid's own ids.

    python demo/take/shot_data.py --shot 3 --tests work/pytest.txt \
        --out .marshal-state/shot-data.json

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(ROOT))  # the package, however this file was invoked

import assemble  # noqa: E402  — the one place a shot's window is read from

SCRIPT = ROOT / "notes" / "demo-script.md"

REPO = "https://github.com/jtmuller5/rollout-marshal"
PAGE = "http://joemuller.com/rollout-marshal/"

DISCLOSURE = (
    "Rollout Marshal was built by an autonomous agent working for Joe Muller. "
    "The accounts, the app, and the release it just halted are his."
)

# Shot 3's beats, as fractions of its window. The nodes are mermaid's ids in
# docs/assets/architecture.svg; a rename shows up on camera as MISSING rather than as a
# ring around nothing. The last beat leaves the diagram and shows the proof panel.
BEATS = [
    {"at": 0.04, "node": "ADK", "tag": "PROPOSES",
     "caption": "Gemini 3.5 Flash, as an ADK agent. Four tools in, one proposed action out."},
    {"at": 0.24, "node": "GATE", "tag": "DECIDES",
     "caption": "The policy gate. Plain Python, no model in it, and it can refuse the call."},
    {"at": 0.46, "node": "PLAY", "tag": "ACTS",
     "caption": "Only the gate reaches the Play API. The agent holds no store credential."},
    {"at": 0.66, "diagram": "decision-flow.svg", "tag": "THE RULE",
     "caption": "Widen, hold or halt — the same conditions, re-derived every tick."},
    {"at": 0.76, "panel": "proof", "tag": "ISOLATED",
     "caption": "Every outside edge is off unless it is switched on by name."},
]

# The four edges that can reach something real, and the module that decides each one. The
# default is not written here: it is read out of that module's own `os.environ.get`, so a
# default that stopped being the safe one shows on camera instead of hiding in a comment.
EDGES = [
    {"var": "MARSHAL_BRAIN", "file": "rollout_marshal/agent.py",
     "live": "adk", "real": "Gemini 3.5 Flash, through ADK"},
    {"var": "MARSHAL_PLAY", "file": "rollout_marshal/play.py",
     "live": "live", "real": "the Play Developer API — a real store write"},
    {"var": "MARSHAL_CRASH_FEED", "file": "rollout_marshal/crash.py",
     "live": "sentry", "real": "Sentry release health"},
    {"var": "MARSHAL_STORE", "file": "rollout_marshal/store.py",
     "live": "firestore", "real": "Firestore — the policy and the audit log"},
]


def window(shot: str) -> float:
    for entry in assemble.shots(SCRIPT):
        if entry.id == shot:
            return entry.window
    raise SystemExit(f"no shot {shot} in {SCRIPT}")


def policy(app: str) -> tuple[dict, str]:
    """The policy as the service reads it, plus where it was read from."""
    from rollout_marshal.store import build_store

    found = build_store().get_policy(app)
    if found is None:
        raise SystemExit(f"no policy for {app} in the {os.environ.get('MARSHAL_STORE', 'file')} store")
    kind = os.environ.get("MARSHAL_STORE", "file")
    where = "Firestore · policies/" + app if kind == "firestore" else f"{kind} store · policies/{app}"
    return found.to_dict() if hasattr(found, "to_dict") else dict(found), where


def edges() -> list[dict]:
    """The four switches, with each default read from the line that applies it.

    Nothing here is typed twice. If a module stops reading its variable, or starts
    defaulting to the live edge, this raises rather than putting a stale claim on camera.
    """
    out = []
    for edge in EDGES:
        source = (ROOT / edge["file"]).read_text()
        pattern = re.compile(
            r'os\.environ\.get\(\s*"' + edge["var"] + r'"\s*,\s*"([^"]+)"\s*\)')
        found = [
            (n, m.group(1))
            for n, line in enumerate(source.splitlines(), 1)
            if (m := pattern.search(line))
        ]
        if not found:
            raise SystemExit(
                f"{edge['file']} no longer reads {edge['var']} with a default — "
                "shot 3 would claim a switch that is not there"
            )
        line, default = found[0]
        if default == edge["live"]:
            raise SystemExit(
                f"{edge['var']} defaults to {default!r} in {edge['file']}:{line}, "
                "which is the live edge. The panel's whole claim is that it does not."
            )
        out.append({**edge, "default": default, "line": line})
    return out


def tests(path: Path) -> dict:
    """The pytest run made just before the recorder started, as it reported itself.

    Reads the output of a real run rather than running one here, because shot 3 is
    recorded from inside a process that a test may itself have started.
    """
    text = path.read_text()
    if match := re.search(r"(\d+) failed", text):
        raise SystemExit(f"{match.group(0)} in {path} — a red suite does not go on camera")
    if not (match := re.search(r"(\d+) passed(?:.*?in ([\d.]+)s)?", text, re.S)):
        raise SystemExit(f"no pytest summary in {path}")
    return {
        "passed": int(match.group(1)),
        "seconds": float(match.group(2)) if match.group(2) else None,
        "command": ".venv/bin/python -m pytest tests -q",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shot", required=True, choices=["2", "3", "6"])
    ap.add_argument("--app", default=os.environ.get("MARSHAL_APP", "bakedown"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--tests", type=Path,
                    help="shot 3: the output of the pytest run made before the take")
    args = ap.parse_args()

    data: dict = {"shot": args.shot, "window": window(args.shot), "app": args.app}

    if args.shot == "2":
        found, where = policy(args.app)
        data["policy"] = found
        data["policy_source"] = where
        data["policy_foot"] = (
            "Read at " + datetime.now(timezone.utc).strftime("%H:%M:%SZ")
            + ". A human wrote these fields before the release shipped; the agent may read "
            "them and may not change them."
        )
    elif args.shot == "3":
        if args.tests is None:
            raise SystemExit(
                "shot 3 needs --tests: the panel says how many tests passed, and that "
                "number comes from a run, never from here"
            )
        data["diagram"] = "architecture.svg"
        data["beats"] = BEATS
        data["edges"] = edges()
        data["tests"] = tests(args.tests)
        data["proof_foot"] = (
            "Read at " + datetime.now(timezone.utc).strftime("%H:%M:%SZ")
            + ". The defaults are the fixtures, so a clone of this repo runs the whole "
            "demo with no credential and cannot reach a store account."
        )
    else:
        data["disclosure"] = DISCLOSURE
        data["urls"] = [REPO, PAGE]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, default=str))
    print(f"shot {args.shot}: {data['window']:.0f}s window -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
