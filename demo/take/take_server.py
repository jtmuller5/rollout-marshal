"""The little server behind the on-camera page.

It holds one append-only list of events in memory and hands out slices of it. The driver
POSTs to /push, the page polls /events?since=N, and nothing else happens here: no store,
no credential, no clock of its own. Standard library only, so it starts in milliseconds
and cannot fail for a reason the take would have to explain.

    python demo/take/take_server.py [--port 8812]

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent

_lock = threading.Lock()
_events: list[dict] = []


def append(event: dict) -> int:
    with _lock:
        _events.append(event)
        return len(_events)


def since(n: int) -> tuple[list[dict], int]:
    with _lock:
        return _events[n:], len(_events)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: A003 - quiet; the take reads the page
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
        url = urlparse(self.path)
        if url.path in ("/", "/take.html"):
            self._send(200, (HERE / "take.html").read_bytes(), "text/html; charset=utf-8")
            return
        if url.path == "/events":
            q = parse_qs(url.query)
            n = int(q.get("since", ["0"])[0])
            events, nxt = since(n)
            body = json.dumps({"events": events, "next": nxt}).encode()
            self._send(200, body, "application/json")
            return
        self._send(404, b"not here", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/push":
            self._send(404, b"not here", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            event = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._send(400, b"not json", "text/plain")
            return
        count = append(event)
        self._send(200, json.dumps({"count": count}).encode(), "application/json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8812)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
