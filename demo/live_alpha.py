"""Set the demo release on a REAL Play track, by hand, before a take.

This is the one manual step the demo needs and the CLI deliberately will not do:
`cli.py track seed` writes the fixture only, because a release cannot be taken off a
Play track through the API (`notes/play-write-path.md`), so seeding a real track is a
decision a person makes rather than something a command does casually.

    MARSHAL_PLAY=live PLAY_SERVICE_ACCOUNT_JSON=... python demo/live_alpha.py read
    MARSHAL_PLAY=live PLAY_SERVICE_ACCOUNT_JSON=... python demo/live_alpha.py set inProgress 0.2
    MARSHAL_PLAY=live PLAY_SERVICE_ACCOUNT_JSON=... python demo/live_alpha.py set halted 0.5

`set inProgress 0.2` is what puts the track back into the state shot 4 starts from, and
`set halted <fraction>` is the undo for anything this or the agent did. It refuses to run
unless `MARSHAL_PLAY=live` is set, so it cannot touch a store account by accident.

The package and track come from the policy document, so this writes whatever the app is
pointed at rather than a name baked in here.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import os
import sys

from rollout_marshal.play import RealPlayClient, release_body
from rollout_marshal.store import build_store


def _target(app: str) -> tuple[str, str]:
    policy = build_store().get_policy(app)
    if policy is None:
        raise SystemExit(f"no policies/{app}: declare the policy first")
    return policy.package, policy.track


def main(argv: list[str]) -> int:
    if os.environ.get("MARSHAL_PLAY", "fixture").lower() != "live":
        print(
            "refusing to run: this writes a real Play track, so it needs "
            "MARSHAL_PLAY=live set on purpose.",
            file=sys.stderr,
        )
        return 2

    app = os.environ.get("MARSHAL_APP", "bakedown")
    package, track = _target(app)
    client = RealPlayClient()

    if argv[:1] == ["read"]:
        print(json.dumps(client.get_track(package, track).raw, indent=2, sort_keys=True))
        return 0

    if argv[:1] == ["set"] and len(argv) == 3:
        status, fraction = argv[1], float(argv[2])
        before = client.get_track(package, track)
        if not before.version_codes:
            raise SystemExit(
                f"{package}/{track} carries no rollout release; Play refuses to stage "
                f"the first release on a track, so seed one from the Console."
            )
        body = release_body(before.release_name, before.version_codes, status, fraction)
        print("request:", json.dumps(body, sort_keys=True))
        resp = client.set_release(package, track, body)
        print("edit:", resp.get("edit_id"))
        print("read back:", json.dumps(client.get_track(package, track).raw, indent=2, sort_keys=True))
        return 0

    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
