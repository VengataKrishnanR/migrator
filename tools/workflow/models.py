"""Typed job/workflow artifacts for the V3 migration platform.

These models describe the *control plane* — the job lifecycle, ingestion
results, per-phase reports, approvals, and audit trail. They are deliberately
separate from the V2 content artifacts in ``tools/pipeline/models.py``
(AnalysisReport, ReactSource, …), which describe migration *content*.

All timestamps are stored as Unix epoch floats (UTC). Convert relative dates
to absolute at the boundary; never store wall-clock strings here.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Job lifecycle states (plan §3)
# ---------------------------------------------------------------------------

class JobState(str, Enum):
    """States of a MigrationJob. String-valued for clean JSON/DB serialization."""

    CREATED = "created"
    INGESTING = "ingesting"
    PHASE1_RUNNING = "phase1_running"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"      # Gate A
    PHASE2_RUNNING = "phase2_running"
    PHASE3_RUNNING = "phase3_running"
    PHASE4_RUNNING = "phase4_running"
    AWAITING_FINAL_APPROVAL = "awaiting_final_approval"    # Gate B
    INTEGRATING = "integrating"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: States from which no further transition is allowed.
TERMINAL_STATES: frozenset[JobState] = frozenset(
    {JobState.COMPLETED, JobState.REJECTED, JobState.FAILED, JobState.CANCELLED}
)


class Gate(str, Enum):
    """Human-in-the-loop approval gates."""

    PLAN = "plan"    # Gate A — after Phase 1
    FINAL = "final"  # Gate B — after Phase 4, before integration


class ApprovalDecision(str, Enum):
    """Decision recorded at an approval gate."""

    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class StageStatus(str, Enum):
    """Status of a single agent stage within a phase run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"   # idempotent resume — already done


# ---------------------------------------------------------------------------
# Ingestion (plan §6 / §7)
# ---------------------------------------------------------------------------

@dataclass
class IngestionManifest:
    """Normalized description of ingested input, produced by every adapter.

    ``project_root`` is relative to the job's input workspace. Git fields are
    populated only for the ``git`` source and are required later to push back.
    """

    source_type: str                       # paste | files | zip | git
    file_count: int = 0
    total_bytes: int = 0
    angular_version: str | None = None
    project_root: str = "."
    is_angular: bool = False
    remote_url: str | None = None
    base_branch: str | None = None
    base_commit_sha: str | None = None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase reporting (plan §7) — "what was done in each phase"
# ---------------------------------------------------------------------------

@dataclass
class StageRecord:
    """One agent stage execution within a phase."""

    stage: str
    agent: str
    status: StageStatus = StageStatus.PENDING
    chunk_id: str | None = None
    retries: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    duration_s: float = 0.0
    error_text: str | None = None


@dataclass
class PhaseReport:
    """Human-readable summary of one phase. One per phase; embedded in the report."""

    phase: int
    title: str
    started_at: float = 0.0
    finished_at: float = 0.0
    stages: list[StageRecord] = field(default_factory=list)
    summary_md: str = ""
    artifacts: list[str] = field(default_factory=list)   # artifact registry keys
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)          # structured stats (tokens, effort, …)

    @property
    def duration_s(self) -> float:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 2)
        return 0.0


# ---------------------------------------------------------------------------
# Approvals & audit (plan §5 / §7)
# ---------------------------------------------------------------------------

@dataclass
class ApprovalRecord:
    """Persisted record of a gate decision. ``report_sha256`` binds the decision
    to the exact report markdown the human saw — what was approved is provable."""

    gate: Gate
    decision: ApprovalDecision
    decided_by: str
    decided_at: float
    comments: str = ""
    report_sha256: str = ""


@dataclass
class AuditEvent:
    """Append-only audit row. Written on every state transition and decision."""

    actor: str
    event: str
    detail: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Job options & record (plan §8)
# ---------------------------------------------------------------------------

@dataclass
class JobOptions:
    """Per-job options supplied at creation (plan §8 POST /api/jobs body)."""

    auto_approve_plan: bool = False
    target: str = "screen"          # screen | zip | git
    output_path: str = "react-app"  # where React lands in git output tree
    create_pr: bool = False
    model_profile: str | None = None
    max_revisions_per_gate: int = 3


@dataclass
class JobRecord:
    """The canonical job row. Held in memory by MigrationJob and persisted by the store."""

    id: str = field(default_factory=lambda: f"job_{uuid.uuid4().hex[:16]}")
    state: JobState = JobState.CREATED
    source_type: str = ""
    options: JobOptions = field(default_factory=JobOptions)
    created_by: str = "anonymous"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Runtime, in-memory only (rebuilt from phase_runs/artifacts on resume)
    manifest: IngestionManifest | None = None
    phase_reports: list[PhaseReport] = field(default_factory=list)
    approvals: list[ApprovalRecord] = field(default_factory=list)
    error_text: str | None = None
