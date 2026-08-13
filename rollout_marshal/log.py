"""The decision log, streamed.

The demo's right-hand pane is this: every line the agent produces, in order, as it
happens. It is also what the service prints to stdout, which is what Cloud Run's
request log shows in shot 5.

One bus, many subscribers. A subscriber is a plain `queue.Queue`, so the tick can run
on a worker thread and the SSE endpoint can drain it from the event loop without
either of them knowing about the other.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from collections import deque
from typing import Any

from .models import iso, now

# Line kinds, so the demo overlay can style them without parsing prose.
TICK = "tick"
READ = "read"
THINK = "think"
PROPOSE = "propose"
GATE_OK = "gate.allow"
GATE_NO = "gate.refuse"
ACT = "act"
API = "api"
MAIL = "mail"
ERROR = "error"


class LogBus:
    def __init__(self, keep: int = 500):
        self._lock = threading.Lock()
        self._subs: list[queue.Queue] = []
        self._recent: deque[dict[str, Any]] = deque(maxlen=keep)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            for e in self._recent:
                q.put(e)
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, kind: str, app: str, text: str, **data: Any) -> dict[str, Any]:
        event = {"ts": iso(now()), "kind": kind, "app": app, "text": text, "data": data}
        with self._lock:
            self._recent.append(event)
            subs = list(self._subs)
        # stdout is the Cloud Run request log, and one JSON object per line is what
        # Cloud Logging parses into structured entries.
        print(json.dumps(event), file=sys.stdout, flush=True)
        for q in subs:
            q.put(event)
        return event

    def recent(self, app: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            items = [e for e in self._recent if app is None or e["app"] == app]
        return items[-limit:]


BUS = LogBus()
