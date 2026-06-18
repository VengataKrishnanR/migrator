"""SQLite-backed persistence for the V3 workflow.

Uses the Python stdlib ``sqlite3`` (no extra dependency) behind a thin
repository so the backend can later be swapped for SQLAlchemy/Postgres without
touching callers — every method here is the seam. Artifact *payloads* live on
disk under the job workspace; this DB stores rows, pointers, and hashes only.

Schema (plan §7):
    jobs, phase_runs, artifacts, approvals, audit_events, token_usage

Thread-safety: a single connection guarded by a re-entrant lock. Adequate for
the in-process asyncio worker (plan §8, D6); a connection pool is the swap point
for higher concurrency.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .models import (
    ApprovalRecord,
    AuditEvent,
    Gate,
    ApprovalDecision,
    JobOptions,
    JobRecord,
    JobState,
    StageRecord,
    StageStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    state        TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    options_json TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    error_text   TEXT
);
CREATE TABLE IF NOT EXISTS phase_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL REFERENCES jobs(id),
    phase      INTEGER NOT NULL,
    stage      TEXT NOT NULL,
    chunk_id   TEXT,
    status     TEXT NOT NULL,
    retries    INTEGER NOT NULL DEFAULT 0,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    duration_s REAL NOT NULL DEFAULT 0,
    error_text TEXT,
    started_at REAL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL REFERENCES jobs(id),
    key        TEXT NOT NULL,
    kind       TEXT NOT NULL,
    path       TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(job_id, key)
);
CREATE TABLE IF NOT EXISTS approvals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         TEXT NOT NULL REFERENCES jobs(id),
    gate           TEXT NOT NULL,
    decision       TEXT NOT NULL,
    summary_sha256 TEXT NOT NULL,
    decided_by     TEXT NOT NULL,
    decided_at     REAL NOT NULL,
    comments       TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL REFERENCES jobs(id),
    actor      TEXT NOT NULL,
    event      TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS token_usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL REFERENCES jobs(id),
    phase         INTEGER,
    agent         TEXT,
    model         TEXT,
    tokens_in     INTEGER NOT NULL DEFAULT 0,
    tokens_out    INTEGER NOT NULL DEFAULT 0,
    cost_estimate REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_phase_runs_job ON phase_runs(job_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id);
CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_events(job_id);
"""


def _options_to_json(o: JobOptions) -> str:
    return json.dumps(o.__dict__, sort_keys=True)


def _options_from_json(s: str) -> JobOptions:
    return JobOptions(**json.loads(s))


class JobStore:
    """Repository over a single SQLite database. ``db_path=":memory:"`` for tests."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- jobs ------------------------------------------------------------------
    def save_job(self, rec: JobRecord) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO jobs (id, state, source_type, options_json,
                       created_by, created_at, updated_at, error_text)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                       state=excluded.state, source_type=excluded.source_type,
                       options_json=excluded.options_json,
                       updated_at=excluded.updated_at, error_text=excluded.error_text""",
                (rec.id, rec.state.value, rec.source_type, _options_to_json(rec.options),
                 rec.created_by, rec.created_at, rec.updated_at, rec.error_text),
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        return JobRecord(
            id=row["id"],
            state=JobState(row["state"]),
            source_type=row["source_type"],
            options=_options_from_json(row["options_json"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_text=row["error_text"],
        )

    def list_jobs(self, state: JobState | None = None, limit: int = 100, offset: int = 0) -> list[JobRecord]:
        q = "SELECT * FROM jobs"
        params: list = []
        if state is not None:
            q += " WHERE state=?"
            params.append(state.value)
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [
            JobRecord(
                id=r["id"], state=JobState(r["state"]), source_type=r["source_type"],
                options=_options_from_json(r["options_json"]), created_by=r["created_by"],
                created_at=r["created_at"], updated_at=r["updated_at"], error_text=r["error_text"],
            )
            for r in rows
        ]

    # -- phase_runs ------------------------------------------------------------
    def record_stage(self, job_id: str, phase: int, stage: StageRecord) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO phase_runs (job_id, phase, stage, chunk_id, status,
                       retries, tokens_in, tokens_out, duration_s, error_text,
                       started_at, finished_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id, phase, stage.stage, stage.chunk_id, stage.status.value,
                 stage.retries, stage.tokens_in, stage.tokens_out, stage.duration_s,
                 stage.error_text, time.time() if stage.status == StageStatus.RUNNING else None,
                 time.time() if stage.status in (StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED) else None),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def clear_phase(self, job_id: str, phase: int) -> None:
        """Delete a phase's stage records so it re-runs from scratch.

        Used when a gate decision sends a phase back for revision — unlike a
        crash-resume (which skips completed stages), a revision must actually
        re-execute with the approver's feedback.
        """
        with self._lock:
            self._conn.execute(
                "DELETE FROM phase_runs WHERE job_id=? AND phase=?", (job_id, phase))
            self._conn.commit()

    def completed_stages(self, job_id: str, phase: int) -> set[str]:
        """Stage keys already completed for a phase — drives idempotent resume.
        For chunk stages the key is ``stage:chunk_id`` so partial loops resume."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT stage, chunk_id FROM phase_runs
                   WHERE job_id=? AND phase=? AND status IN ('completed','skipped')""",
                (job_id, phase),
            ).fetchall()
        out: set[str] = set()
        for r in rows:
            out.add(f"{r['stage']}:{r['chunk_id']}" if r["chunk_id"] else r["stage"])
        return out

    # -- artifacts (pointers; payloads live on disk) ---------------------------
    def put_artifact(self, job_id: str, key: str, kind: str, path: str, sha256: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO artifacts (job_id, key, kind, path, sha256, created_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(job_id, key) DO UPDATE SET
                       kind=excluded.kind, path=excluded.path,
                       sha256=excluded.sha256, created_at=excluded.created_at""",
                (job_id, key, kind, path, sha256, time.time()),
            )
            self._conn.commit()

    def list_artifacts(self, job_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, kind, path, sha256, created_at FROM artifacts WHERE job_id=? ORDER BY created_at",
                (job_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- approvals -------------------------------------------------------------
    def record_approval(self, job_id: str, rec: ApprovalRecord) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO approvals (job_id, gate, decision, summary_sha256,
                       decided_by, decided_at, comments)
                   VALUES (?,?,?,?,?,?,?)""",
                (job_id, rec.gate.value, rec.decision.value, rec.report_sha256,
                 rec.decided_by, rec.decided_at, rec.comments),
            )
            self._conn.commit()

    def list_approvals(self, job_id: str, gate: Gate | None = None) -> list[ApprovalRecord]:
        q = "SELECT * FROM approvals WHERE job_id=?"
        params: list = [job_id]
        if gate is not None:
            q += " AND gate=?"
            params.append(gate.value)
        q += " ORDER BY decided_at"
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [
            ApprovalRecord(
                gate=Gate(r["gate"]), decision=ApprovalDecision(r["decision"]),
                decided_by=r["decided_by"], decided_at=r["decided_at"],
                comments=r["comments"] or "", report_sha256=r["summary_sha256"],
            )
            for r in rows
        ]

    def revision_count(self, job_id: str, gate: Gate) -> int:
        """How many times this gate has been sent back for revision — bounds loops."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM approvals WHERE job_id=? AND gate=? AND decision=?",
                (job_id, gate.value, ApprovalDecision.REVISE.value),
            ).fetchone()
        return int(row["n"])

    # -- audit -----------------------------------------------------------------
    def append_audit(self, job_id: str, ev: AuditEvent) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO audit_events (job_id, actor, event, detail_json, created_at)
                   VALUES (?,?,?,?,?)""",
                (job_id, ev.actor, ev.event, json.dumps(ev.detail, sort_keys=True), ev.created_at),
            )
            self._conn.commit()

    def get_audit(self, job_id: str) -> list[AuditEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM audit_events WHERE job_id=? ORDER BY created_at, id", (job_id,),
            ).fetchall()
        return [
            AuditEvent(actor=r["actor"], event=r["event"],
                       detail=json.loads(r["detail_json"]), created_at=r["created_at"])
            for r in rows
        ]

    # -- token usage -----------------------------------------------------------
    def record_tokens(self, job_id: str, phase: int | None, agent: str | None,
                      model: str | None, tokens_in: int, tokens_out: int,
                      cost_estimate: float = 0.0) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO token_usage (job_id, phase, agent, model, tokens_in,
                       tokens_out, cost_estimate) VALUES (?,?,?,?,?,?,?)""",
                (job_id, phase, agent, model, tokens_in, tokens_out, cost_estimate),
            )
            self._conn.commit()

    def total_tokens(self, job_id: str) -> dict[str, int | float]:
        with self._lock:
            row = self._conn.execute(
                """SELECT COALESCE(SUM(tokens_in),0) AS ti, COALESCE(SUM(tokens_out),0) AS to_,
                          COALESCE(SUM(cost_estimate),0) AS cost
                   FROM token_usage WHERE job_id=?""",
                (job_id,),
            ).fetchone()
        return {"tokens_in": int(row["ti"]), "tokens_out": int(row["to_"]), "cost_estimate": float(row["cost"])}
