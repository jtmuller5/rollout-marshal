"""The little server behind the still shots — 2, 3 and 6 of the demo.

Shot 4 has its own page and its own driver, because it is a live execution and has to
render events that already happened. These three are held pictures: a policy card read
out of the store, the architecture diagram with the components named in turn, and the
disclosure card. So this server does less than `take_server.py`: it serves the page, the
data the recorder wrote for it, and the two SVGs out of `docs/assets/`.

    python demo/take/shot_server.py --data .marshal-state/shot-data.json [--port 8813]

The page does not start its own clock until the recorder POSTs to /go, which happens
after ffmpeg is running. That is what stops the first seconds of every shot being spent
on a page that has already finished.

Standard library only, like the take server, so it cannot fail for a reason the
recording would have to explain.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ASSETS = ROOT / "docs" / "assets"

_lock = threading.Lock()
_go = False


class Handler(BaseHTTPRequestHandler):
    data_path = Path()

    def log_message(self, fmt, *args):  # noqa: A003 - quiet; the recording reads the page
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
        path = urlparse(self.path).path
        if path in ("/", "/stills.html"):
            self._send(200, (HERE / "stills.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/data.json":
            with _lock:
                go = _go
            try:
                data = json.loads(self.data_path.read_text())
            except (OSError, ValueError):
                data = {}
            data["go"] = go
            self._send(200, json.dumps(data).encode(), "application/json")
            return
        if path.startswith("/asset/"):
            name = Path(path[len("/asset/"):]).name
            svg = ASSETS / name
            # Resolve and compare, so a crafted name cannot walk out of docs/assets.
            if svg.suffix != ".svg" or not svg.is_file() or svg.parent != ASSETS:
                self._send(404, b"not here", "text/plain")
                return
            self._send(200, svg.read_bytes(), "image/svg+xml")
            return
        self._send(404, b"not here", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        global _go
        if urlparse(self.path).path != "/go":
            self._send(404, b"not here", "text/plain")
            return
        with _lock:
            _go = True
        self._send(200, b'{"go": true}', "application/json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8813)
    ap.add_argument("--data", required=True, help="the JSON the recorder wrote for the page")
    args = ap.parse_args()
    Handler.data_path = Path(args.data).resolve()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
