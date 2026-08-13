"""What the still shots put on screen, gathered from the things that already hold it.

The window of each shot comes from `notes/demo-script.md`, through the same parser the
narration uses, so a shot cannot be recorded to a length the voice does not agree with.
The policy comes from the store the environment selects — `MARSHAL_STORE=firestore` and
the credential give the real one, with the real `created_at` — and never from a literal
here. The diagram nodes are named by mermaid's own ids.

    python demo/take/shot_data.py --shot 3 --out .marshal-state/shot-data.json

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import os
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
# ring around nothing.
BEATS = [
    {"at": 0.05, "node": "ADK", "tag": "PROPOSES",
     "caption": "Gemini 3.5 Flash, as an ADK agent. Four tools in, one proposed action out."},
    {"at": 0.32, "node": "GATE", "tag": "DECIDES",
     "caption": "The policy gate. Plain Python, no model in it, and it can refuse the call."},
    {"at": 0.60, "node": "PLAY", "tag": "ACTS",
     "caption": "Only the gate reaches the Play API. The agent holds no store credential."},
    {"at": 0.90, "diagram": "decision-flow.svg", "tag": "THE RULE",
     "caption": "Widen, hold or halt — the same conditions, re-derived every tick."},
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shot", required=True, choices=["2", "3", "6"])
    ap.add_argument("--app", default=os.environ.get("MARSHAL_APP", "bakedown"))
    ap.add_argument("--out", required=True)
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
        data["diagram"] = "architecture.svg"
        data["beats"] = BEATS
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
