"""Drive shot 4 of the demo while the screen is being recorded.

This runs the four beats of the unedited take — the refused widen, the injected spike,
the halt, the audit trail — against whatever wiring the environment selects, and pushes
what happens to the on-camera page at :8812. It is the same sequence as
`demo/run_demo.sh`; the difference is that the output goes somewhere a camera can read.

Two rules it keeps, because the take is evidence:

* Every line on screen is something that already happened. Nothing is announced before
  the call that produces it, and no text is invented for the page.
* The only waiting it adds is between beats, at the pace an operator would type. It
  never pads the agent's own latency, which is the part worth filming.

    .venv/bin/python demo/take/drive_take.py --take-url http://127.0.0.1:8812

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Page:
    """The on-camera page, as somewhere to push events."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/") + "/push"
        self.lock = threading.Lock()

    def push(self, kind: str, text: str = "", data: dict | None = None) -> None:
        event = {"ts": iso(), "kind": kind, "text": text, "data": data or {}}
        body = json.dumps(event).encode()
        req = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"}
        )
        with self.lock:
            try:
                urllib.request.urlopen(req, timeout=5).read()
            except OSError as exc:  # the page is not the work; never kill a take for it
                print(f"push failed ({kind}): {exc}", file=sys.stderr)
        print(f"[{event['ts']}] {kind}: {text}", flush=True)


def tail_stream(page: Page, port: int, stop: threading.Event) -> None:
    """Forward the service's SSE log to the page, one line at a time."""
    url = f"http://127.0.0.1:{port}/stream"
    try:
        resp = urllib.request.urlopen(url, timeout=600)
    except OSError as exc:
        page.push("error", f"cannot read {url}: {exc}")
        return
    for raw in resp:
        if stop.is_set():
            return
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line[6:])
        except ValueError:
            continue
        page.push(event.get("kind", "read"), event.get("text", ""))


def read_track(app: str) -> dict:
    """One independent read of the track, from this process rather than the service."""
    from rollout_marshal.play import build_play_client
    from rollout_marshal.store import build_store

    policy = build_store().get_policy(app)
    client = build_play_client()
    track = client.get_track(policy.package, policy.track)
    return {
        "status": track.status,
        "user_fraction": track.user_fraction,
        "version_code": track.version_code,
        "release": track.release_name,
        "source": type(client).__name__.replace("PlayClient", "").lower() + " Play client",
    }


def poll_track(page: Page, app: str, every: float, stop: threading.Event) -> None:
    last = None
    while not stop.is_set():
        try:
            state = read_track(app)
        except Exception as exc:  # noqa: BLE001 - a failed read is worth showing
            page.push("error", f"track read failed: {exc}")
            state = None
        if state is not None and state != last:
            page.push("track", "", state)
            last = state
        stop.wait(every)


def post_tick(port: int, app: str) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/tick/{app}", method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    return (out.stdout or out.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--take-url", default="http://127.0.0.1:8812")
    ap.add_argument("--port", type=int, default=8811, help="the marshal service")
    ap.add_argument("--app", default=os.environ.get("MARSHAL_APP", "bakedown"))
    ap.add_argument("--dwell", type=float, default=6.0, help="seconds between beats")
    args = ap.parse_args()

    page = Page(args.take_url)
    app = args.app
    py = os.environ.get("PY", ".venv/bin/python")

    from rollout_marshal.store import build_store

    policy = build_store().get_policy(app)
    page.push("start", f"{app} · {policy.package} · {policy.track}")
    page.push(
        "policy",
        "",
        {
            "rows": [
                ["halt below", f"{policy.halt_crash_free}% crash-free"],
                ["stages", ", ".join(f"{s:.0%}" for s in policy.stages)],
                ["min hours per stage", f"{policy.min_hours_per_stage:g}h"],
                ["session floor", str(policy.session_floor)],
                ["baseline", f"{policy.baseline_crash_free}%"],
                ["declared", policy.created_at[:19].replace("T", " ")],
            ]
        },
    )

    stop = threading.Event()
    threads = [
        threading.Thread(target=tail_stream, args=(page, args.port, stop), daemon=True),
        threading.Thread(target=poll_track, args=(page, app, 4.0, stop), daemon=True),
    ]
    for t in threads:
        t.start()
    time.sleep(args.dwell)

    tick_cmd = f"curl -sf -X POST http://127.0.0.1:{args.port}/tick/{app}"

    # 4a — the tick that does nothing, because the gate refuses the widen.
    page.push("beat", "4a · a tick that does nothing")
    page.push("cmd", tick_cmd)
    time.sleep(2.0)
    first = post_tick(args.port, app)
    page.push("note", f"tick returned {first['action_taken']} — {first['gate']['reason']}")
    time.sleep(args.dwell)

    # 4b — the spike, said out loud. This is the one fixture in the take.
    page.push("beat", "4b · the spike, injected out loud")
    inject = f"{py} -m rollout_marshal.cli inject --file demo/fixtures/spike.json"
    page.push("cmd", inject)
    time.sleep(2.0)
    injected = run([py, "-m", "rollout_marshal.cli", "inject",
                    "--file", "demo/fixtures/spike.json"])
    page.push("note", injected.splitlines()[0] if injected else "injected")
    spike = json.loads((ROOT / "demo/fixtures/spike.json").read_text())
    page.push("note", f"the feed now reads {spike['crash_free_rate']}% crash-free "
                      f"over {spike['sessions']} sessions")
    time.sleep(args.dwell)

    # 4c — the halt. Nothing is pushed between the command and the agent's own lines.
    page.push("beat", "4c · the halt")
    page.push("cmd", tick_cmd)
    time.sleep(2.0)
    started = time.monotonic()
    second = post_tick(args.port, app)
    took = time.monotonic() - started
    page.push("note", f"tick returned {second['action_taken']} in {took:.0f}s "
                      f"— {second['gate']['reason']}")
    api = second.get("inputs", {})
    page.push("note", f"decision {second['decision_id']}")
    time.sleep(args.dwell)

    # 4d — the audit trail, read back out of the store the agent wrote it to.
    page.push("beat", "4d · the audit trail")
    show = f"{py} demo/show_decisions.py {app}"
    page.push("cmd", show)
    time.sleep(2.0)
    for line in run([py, "demo/show_decisions.py", app]).splitlines()[-14:]:
        if line.strip():
            page.push("note", line.rstrip())
            time.sleep(0.35)

    # The email the human gets afterwards. FileSender writes it; SMTP does not, and then
    # there is nothing on disk to show, which the page simply leaves out.
    mail = sorted((ROOT / os.environ.get("MARSHAL_STATE_DIR", ".marshal-state") / "mail")
                  .glob("*.eml")) if second.get("mailed") else []
    if mail:
        page.push("email", mail[-1].read_text().strip())
    time.sleep(args.dwell)

    stop.set()
    page.push("beat", "take complete")
    print(json.dumps({"first": first["action_taken"], "second": second["action_taken"],
                      "decision": second["decision_id"], "inputs": api}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
