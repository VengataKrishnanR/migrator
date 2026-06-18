"""V3 workflow layer — deterministic job orchestration for the migration platform.

This package contains the enterprise control plane that sits *around* the
existing V2 agents (``tools/agents``) and pipeline infrastructure
(``tools/pipeline``):

  - models          Typed job/workflow artifacts (JobState, manifests, reports)
  - state_machine   MigrationJob — deterministic, resumable phase transitions
  - store           SQLite-backed persistence (jobs, phase_runs, artifacts, …)

Control flow lives here in Python, never in an LLM prompt. Agents decide
*content*; this layer decides *sequence*, retries, gates, and resume.
"""
from __future__ import annotations

from .models import (
    ApprovalDecision,
    ApprovalRecord,
    AuditEvent,
    Gate,
    IngestionManifest,
    JobOptions,
    JobRecord,
    JobState,
    PhaseReport,
    StageRecord,
    StageStatus,
    TERMINAL_STATES,
)
from .state_machine import (
    IllegalTransitionError,
    MigrationJob,
    TRANSITIONS,
)

__all__ = [
    "ApprovalDecision",
    "ApprovalRecord",
    "AuditEvent",
    "Gate",
    "IngestionManifest",
    "JobOptions",
    "JobRecord",
    "JobState",
    "PhaseReport",
    "StageRecord",
    "StageStatus",
    "TERMINAL_STATES",
    "IllegalTransitionError",
    "MigrationJob",
    "TRANSITIONS",
]
