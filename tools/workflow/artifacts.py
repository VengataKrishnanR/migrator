"""Artifact payload persistence — JSON on disk, pointer + hash in the DB.

Shared by :class:`server.service.JobService` and the phase runners so artifacts
are written one consistent way: payload under ``<workspace>/artifacts/<key>.json``,
SHA-256 + path registered in the ``artifacts`` table. Reading back (for resume or
cross-phase handoff) goes through :func:`read_artifact`.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from tools.ingestion.workspace import Workspace
from tools.workflow.store import JobStore


def write_artifact(store: JobStore, workspace: Workspace, job_id: str,
                   key: str, kind: str, obj: Any) -> str:
    """Serialize ``obj`` to ``<artifacts>/<key>.json``, register it, return sha256."""
    payload = json.dumps(obj, default=str, indent=2, sort_keys=True)
    path = workspace.artifacts_dir / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    store.put_artifact(job_id, key, kind, str(path), sha)
    return sha


def read_artifact(workspace: Workspace, key: str) -> Any | None:
    """Load a previously written artifact payload, or None if absent."""
    path = workspace.artifacts_dir / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
