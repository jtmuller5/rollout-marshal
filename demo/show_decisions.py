#!/usr/bin/env python3
"""Print the decision log as one line per tick, for the demo's 4d scroll.

    python demo/show_decisions.py <app>

Written by an autonomous agent working for Joe Muller.
"""

import sys

sys.path.insert(0, ".")

from rollout_marshal.store import build_store  # noqa: E402


def main() -> int:
    app = sys.argv[1] if len(sys.argv) > 1 else "bakedown"
    for d in build_store().list_decisions(app, 50):
        v = d.get("gate_verdict", {})
        want = d.get("proposal", {}).get("action", "?")
        print(f"{d['ts']}  wanted {want:5}  took {d['action_taken']:5}  "
              f"gate={'allow' if v.get('allowed') else 'REFUSE'}")
        print(f"    inputs : {d['inputs']['crash_free']}% crash-free over "
              f"{d['inputs']['sessions']} sessions, {d['inputs']['hours_at_stage']}h at "
              f"{d['inputs']['user_fraction']:.0%}, halt line {d['inputs']['halt_criterion']}%")
        print(f"    gate   : {v.get('reason', '')}")
        if d.get("api_response"):
            rel = (d["api_response"].get("request") or {}).get("releases", [{}])[0]
            print(f"    store  : edit {d['api_response'].get('edit_id')} committed — {rel}")
        print(f"    agent  : {d.get('model_reasoning', '')[:300]}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
