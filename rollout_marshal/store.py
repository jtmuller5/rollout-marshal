"""State: the declared policy, the current rollout, and the append-only decision log.

Two implementations behind one interface. `FirestoreStore` is what runs on Cloud Run.
`FileStore` writes the same three collections as JSON under a directory, so the whole
service — agent, gate, Play writes and all — can be run by somebody who has not been
given a Google Cloud project yet. The demo harness uses it, and `tests/` uses it.

The collections are the ones in the README:

    policies/{app}      declared before the release, immutable for its duration
    rollouts/{app}      one document, overwritten each tick
    decisions/{ts}      append-only; the audit trail and the demo's right-hand pane

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Protocol

from .models import Decision, Policy, iso, now


class Store(Protocol):
    def get_policy(self, app: str) -> Policy | None: ...
    def put_policy(self, policy: Policy) -> None: ...
    def get_rollout(self, app: str) -> dict[str, Any] | None: ...
    def put_rollout(self, app: str, state: dict[str, Any]) -> None: ...
    def append_decision(self, d: Decision) -> str: ...
    def list_decisions(self, app: str, limit: int = 50) -> list[dict[str, Any]]: ...


class FileStore:
    """JSON on disk, one file per document. Same shape as the Firestore version."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._lock = threading.Lock()
        for c in ("policies", "rollouts", "decisions"):
            (self.root / c).mkdir(parents=True, exist_ok=True)

    def _read(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _write(self, path: Path, doc: dict[str, Any]) -> None:
        with self._lock:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc, indent=2, sort_keys=True))
            tmp.replace(path)

    def get_policy(self, app: str) -> Policy | None:
        d = self._read(self.root / "policies" / f"{app}.json")
        return Policy.from_dict(d) if d else None

    def put_policy(self, policy: Policy) -> None:
        self._write(self.root / "policies" / f"{policy.app}.json", policy.to_dict())

    def get_rollout(self, app: str) -> dict[str, Any] | None:
        return self._read(self.root / "rollouts" / f"{app}.json")

    def put_rollout(self, app: str, state: dict[str, Any]) -> None:
        self._write(self.root / "rollouts" / f"{app}.json", state)

    def append_decision(self, d: Decision) -> str:
        # The id carries the timestamp so a directory listing is already in order.
        doc_id = f"{d.ts.replace(':', '').replace('-', '')}-{d.app}"
        path = self.root / "decisions" / f"{doc_id}.json"
        base, n = doc_id, 1
        while path.exists():  # append-only: never overwrite an earlier decision
            n += 1
            doc_id = f"{base}-{n}"
            path = self.root / "decisions" / f"{doc_id}.json"
        self._write(path, d.to_dict())
        return doc_id

    def list_decisions(self, app: str, limit: int = 50) -> list[dict[str, Any]]:
        out = []
        for p in sorted((self.root / "decisions").glob("*.json")):
            doc = self._read(p) or {}
            if doc.get("app") == app:
                out.append(doc)
        return out[-limit:]


class FirestoreStore:
    """The real thing. Firestore in Native mode, on the Spark (free) tier."""

    def __init__(self, project: str | None = None, database: str = "(default)"):
        from google.cloud import firestore  # imported late: the file store needs no SDK

        self.db = firestore.Client(project=project, database=database)

    def get_policy(self, app: str) -> Policy | None:
        snap = self.db.collection("policies").document(app).get()
        return Policy.from_dict(snap.to_dict()) if snap.exists else None

    def put_policy(self, policy: Policy) -> None:
        self.db.collection("policies").document(policy.app).set(policy.to_dict())

    def get_rollout(self, app: str) -> dict[str, Any] | None:
        snap = self.db.collection("rollouts").document(app).get()
        return snap.to_dict() if snap.exists else None

    def put_rollout(self, app: str, state: dict[str, Any]) -> None:
        self.db.collection("rollouts").document(app).set(state)

    def append_decision(self, d: Decision) -> str:
        doc_id = f"{d.ts}-{d.app}"
        # create() rather than set(): the log is append-only, so a collision must
        # raise instead of quietly overwriting an earlier decision.
        self.db.collection("decisions").document(doc_id).create(d.to_dict())
        return doc_id

    def list_decisions(self, app: str, limit: int = 50) -> list[dict[str, Any]]:
        # `limit_to_last` is served by a DESCENDING index even though the order_by
        # here reads ascending, so the composite index this needs is (app ASC, ts
        # DESC) — see firestore.indexes.json. An (app ASC, ts ASC) index does not
        # satisfy it, and the error names neither direction.
        from google.cloud.firestore_v1.base_query import FieldFilter

        q = (
            self.db.collection("decisions")
            .where(filter=FieldFilter("app", "==", app))
            .order_by("ts")
            .limit_to_last(limit)
        )
        return [s.to_dict() for s in q.get()]


def build_store() -> Store:
    """Pick a store from the environment. `file` is the default so nothing breaks
    without credentials; Cloud Run sets MARSHAL_STORE=firestore."""
    kind = os.environ.get("MARSHAL_STORE", "file").lower()
    if kind == "firestore":
        return FirestoreStore(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    return FileStore(os.environ.get("MARSHAL_STATE_DIR", ".marshal-state"))


def stamp_stage(store: Store, app: str, fraction: float, status: str) -> str:
    """Record when the rollout entered its current stage, and return that instant.

    "Six hours at this stage" needs a clock that survives a scale-to-zero, so it is a
    stored fact rather than anything the process remembers. The stamp moves only when
    the fraction or the status actually changes.
    """
    prev = store.get_rollout(app) or {}
    if prev.get("user_fraction") == fraction and prev.get("status") == status:
        return prev.get("stage_entered_at") or iso(now())
    return iso(now())
