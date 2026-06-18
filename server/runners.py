"""Phase runners — the swap point where real agents plug into the pipeline.

A :class:`PhaseRunner` executes one phase for a job and returns a
:class:`PhaseReport`. M1 ships :class:`StubPhaseRunner`, which records a single
completed stage per phase with no LLM/network — enough to drive the full state
machine end-to-end and prove resume. M2–M5 replace it with runners that invoke
the existing V2 agents (analyzer, transformer, …) via the ADK Runner.

Runners must be **idempotent**: they consult ``store.completed_stages`` and skip
work already done, so a job resumes from the last completed stage after a crash.
"""
from __future__ import annotations

import time
from typing import Protocol

from tools.ingestion.workspace import Workspace
from tools.workflow.models import PhaseReport, StageRecord, StageStatus
from tools.workflow.store import JobStore

_PHASE_TITLES = {
    1: "Discovery & Planning",
    2: "Transformation",
    3: "Test Generation",
    4: "Validation & Reporting",
}

#: Representative stages per phase (names match the V2 agent set).
_PHASE_STAGES = {
    1: ["analyzer", "risk_detection", "migration_planner", "state_migration_planner"],
    2: ["transformer", "refactor_optimizer"],
    3: ["test_planner", "test_generator"],
    4: ["validator", "report"],
}


class PhaseRunner(Protocol):
    """Executes one phase and returns its report. Implementations must be idempotent."""

    def run(self, job_id: str, phase: int, store: JobStore, workspace: Workspace) -> PhaseReport:
        ...


class StubPhaseRunner:
    """No-op runner for M1 — records stages without invoking any agent.

    Honors idempotent resume: stages already marked completed in ``phase_runs``
    are recorded as SKIPPED rather than re-run.
    """

    def run(self, job_id: str, phase: int, store: JobStore, workspace: Workspace) -> PhaseReport:
        started = time.time()
        report = PhaseReport(phase=phase, title=_PHASE_TITLES.get(phase, f"Phase {phase}"),
                             started_at=started)
        already = store.completed_stages(job_id, phase)

        for stage_name in _PHASE_STAGES.get(phase, []):
            if stage_name in already:
                rec = StageRecord(stage=stage_name, agent=f"{stage_name}_agent_v3",
                                  status=StageStatus.SKIPPED)
            else:
                rec = StageRecord(stage=stage_name, agent=f"{stage_name}_agent_v3",
                                  status=StageStatus.COMPLETED, duration_s=0.0)
                store.record_stage(job_id, phase, rec)
            report.stages.append(rec)

        report.finished_at = time.time()
        report.summary_md = f"Phase {phase} ({report.title}) completed [stub]."
        return report
