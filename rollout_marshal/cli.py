"""Operator commands: declare a policy, seed a demo track, inject a reading, tick.

    python -m rollout_marshal.cli policy set --app bakedown --package com.example.app \
        --track alpha --halt 95 --stages 0.2,0.5,1.0 --hours 6 --floor 120 --baseline 99.4
    python -m rollout_marshal.cli policy show --app bakedown
    python -m rollout_marshal.cli track seed --app bakedown --release 1.0.121 --code 121 \
        --status inProgress --fraction 0.2
    python -m rollout_marshal.cli inject --file demo/fixtures/spike.json
    python -m rollout_marshal.cli tick --app bakedown
    python -m rollout_marshal.cli decisions --app bakedown
    python -m rollout_marshal.cli publish --app bakedown

`policy set` is the CLI shot 2 of the demo needs: the policy document has to exist,
with a created timestamp older than the release, before anything else happens.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .models import Policy
from .play import FixturePlayClient, release_body
from .store import build_store
from .tick import Marshal


def cmd_policy_set(a: argparse.Namespace) -> int:
    policy = Policy(
        app=a.app,
        package=a.package,
        track=a.track,
        halt_crash_free=a.halt,
        stages=[float(s) for s in a.stages.split(",")],
        min_hours_per_stage=a.hours,
        session_floor=a.floor,
        baseline_crash_free=a.baseline,
    )
    build_store().put_policy(policy)
    print(json.dumps(policy.to_dict(), indent=2))
    return 0


def cmd_policy_show(a: argparse.Namespace) -> int:
    p = build_store().get_policy(a.app)
    if p is None:
        print(f"no policies/{a.app}", file=sys.stderr)
        return 1
    print(json.dumps(p.to_dict(), indent=2))
    return 0


def cmd_track_seed(a: argparse.Namespace) -> int:
    """Put a release onto the FIXTURE track only.

    Never the live one: `notes/play-write-path.md` measured that a release cannot be
    taken off a Play track through the API, so seeding a real track is a decision a
    person makes once, not something a CLI should do casually.
    """
    path = os.environ.get("MARSHAL_PLAY_FIXTURE", ".marshal-state/play.json")
    client = FixturePlayClient(path)
    store = build_store()
    policy = store.get_policy(a.app)
    if policy is None:
        print(f"no policies/{a.app}; declare the policy first", file=sys.stderr)
        return 1
    releases = [
        # Play refuses to stage the first release on a track, so the fixture carries
        # the same shape a real track does: a completed release, then the staged one.
        release_body(a.seed_name, [a.seed_code], "completed", None),
        release_body(a.release, [a.code], a.status, a.fraction),
    ]
    client.seed(policy.package, policy.track, releases)
    print(json.dumps(releases, indent=2))
    return 0


def cmd_rollout_stamp(a: argparse.Namespace) -> int:
    """Set when the rollout entered its current stage.

    "Six hours at this stage" is a stored fact rather than something the process
    remembers, because Cloud Run scales to zero between ticks. That makes the clock
    settable, which the demo needs: a release that has been at 20% for eight hours is
    the state where the session floor is the only thing left refusing a widen.
    """
    from .models import iso, now
    import datetime as dt

    store = build_store()
    policy = store.get_policy(a.app)
    if policy is None:
        print(f"no policies/{a.app}; declare the policy first", file=sys.stderr)
        return 1
    track = build_play_client_for_cli().get_track(policy.package, policy.track)
    entered = iso(now() - dt.timedelta(hours=a.hours_ago))
    doc = {
        "app": a.app,
        "package": policy.package,
        "track": policy.track,
        "version_code": track.version_code,
        "release_name": track.release_name,
        "status": track.status,
        "user_fraction": track.user_fraction,
        "stage_entered_at": entered,
        "policy_ref": f"policies/{a.app}",
        "updated_at": iso(now()),
    }
    store.put_rollout(a.app, doc)
    print(json.dumps(doc, indent=2))
    return 0


def build_play_client_for_cli():
    from .play import build_play_client

    return build_play_client()


def cmd_inject(a: argparse.Namespace) -> int:
    """Point the fixture crash feed at a different reading, while the service runs."""
    target = Path(os.environ.get("MARSHAL_CRASH_FIXTURE", ".marshal-state/crash.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.file, target)
    print(f"{a.file} -> {target}")
    print(target.read_text())
    return 0


def cmd_tick(a: argparse.Namespace) -> int:
    print(json.dumps(Marshal().tick(a.app), indent=2))
    return 0


def cmd_decisions(a: argparse.Namespace) -> int:
    print(json.dumps(build_store().list_decisions(a.app, a.limit), indent=2))
    return 0


def cmd_publish(a: argparse.Namespace) -> int:
    """Build the hosted page out of the store this environment points at."""
    from .publish import PublishError, publish

    try:
        page = publish(a.app, Path(a.out) if a.out else None)
    except PublishError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"{page}  {page.stat().st_size:,} bytes")
    return 0


def cmd_writeup(a: argparse.Namespace) -> int:
    """Build the public build write-up page out of notes/build-writeup.md."""
    from .writeup import WriteupError, publish_writeup

    try:
        page = publish_writeup(Path(a.out) if a.out else None)
    except WriteupError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"{page}  {page.stat().st_size:,} bytes")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="marshal")
    sub = p.add_subparsers(dest="cmd", required=True)

    pol = sub.add_parser("policy").add_subparsers(dest="sub", required=True)
    s = pol.add_parser("set")
    s.add_argument("--app", required=True)
    s.add_argument("--package", required=True)
    s.add_argument("--track", default="alpha")
    s.add_argument("--halt", type=float, default=95.0)
    s.add_argument("--stages", default="0.2,0.5,1.0")
    s.add_argument("--hours", type=float, default=6.0)
    s.add_argument("--floor", type=int, default=120)
    s.add_argument("--baseline", type=float, default=99.4)
    s.set_defaults(func=cmd_policy_set)

    s = pol.add_parser("show")
    s.add_argument("--app", required=True)
    s.set_defaults(func=cmd_policy_show)

    tr = sub.add_parser("track").add_subparsers(dest="sub", required=True)
    s = tr.add_parser("seed")
    s.add_argument("--app", required=True)
    s.add_argument("--release", required=True)
    s.add_argument("--code", required=True)
    s.add_argument("--status", default="inProgress")
    s.add_argument("--fraction", type=float, default=0.2)
    s.add_argument("--seed-name", default="1.0.119")
    s.add_argument("--seed-code", default="119")
    s.set_defaults(func=cmd_track_seed)

    ro = sub.add_parser("rollout").add_subparsers(dest="sub", required=True)
    s = ro.add_parser("stamp")
    s.add_argument("--app", required=True)
    s.add_argument("--hours-ago", type=float, default=0.0)
    s.set_defaults(func=cmd_rollout_stamp)

    s = sub.add_parser("inject")
    s.add_argument("--file", required=True)
    s.set_defaults(func=cmd_inject)

    s = sub.add_parser("tick")
    s.add_argument("--app", required=True)
    s.set_defaults(func=cmd_tick)

    s = sub.add_parser("publish")
    s.add_argument("--app", required=True)
    s.add_argument("--out", default=None, help="output directory; defaults to docs/")
    s.set_defaults(func=cmd_publish)

    s = sub.add_parser("writeup")
    s.add_argument("--out", default=None, help="output directory; defaults to docs/build-log/")
    s.set_defaults(func=cmd_writeup)

    s = sub.add_parser("decisions")
    s.add_argument("--app", required=True)
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_decisions)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
