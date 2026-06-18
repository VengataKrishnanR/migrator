"""JobService — queue-agnostic orchestration facade (plan §8, D6).

Owns the MigrationJob lifecycle: ingest → phases → gates → integrate. Drives
:class:`~server.runners.PhaseRunner` implementations, enforces approval gates,
and is **resumable** — ``resume()`` rebuilds a job from the store and continues
from its last persisted state, with idempotent runners skipping completed work.

No web dependency: this is unit-testable without FastAPI. The FastAPI app
(:mod:`server.app`) is a thin shell over these methods.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

from tools.ingestion import Workspace, ingest
from tools.ingestion.adapters import IngestionError
from tools.workflow.artifacts import write_artifact
from tools.workflow.models import (
    ApprovalDecision,
    ApprovalRecord,
    AuditEvent,
    Gate,
    JobOptions,
    JobRecord,
    JobState,
)
from tools.workflow.state_machine import MigrationJob
from tools.workflow.store import JobStore

from .runners import PhaseRunner, StubPhaseRunner

# State → (phase to run, next state) for the four phase-running states.
_PHASE_FLOW = {
    JobState.PHASE1_RUNNING: (1, JobState.AWAITING_PLAN_APPROVAL),
    JobState.PHASE2_RUNNING: (2, JobState.PHASE3_RUNNING),
    JobState.PHASE3_RUNNING: (3, JobState.PHASE4_RUNNING),
    JobState.PHASE4_RUNNING: (4, JobState.AWAITING_FINAL_APPROVAL),
}


class ApprovalRequiredError(RuntimeError):
    """Raised internally to signal the run loop must park awaiting a human."""


class JobService:
    """Create, run, resume, and decide on migration jobs."""

    def __init__(self, store: JobStore, data_dir: str | Path,
                 runner: PhaseRunner | None = None, auto_gates: bool = False):
        self.store = store
        self.data_dir = str(data_dir)
        self.runner = runner or StubPhaseRunner()
        #: When True, gates auto-approve (M1 stub / tests). Production wires real
        #: approvals; only ``options.auto_approve_plan`` skips Gate A.
        self.auto_gates = auto_gates

    # -- workspace / artifacts -------------------------------------------------
    def _workspace(self, job_id: str) -> Workspace:
        return Workspace.for_job(job_id, self.data_dir)

    def _write_artifact(self, job_id: str, key: str, kind: str, obj) -> None:
        write_artifact(self.store, self._workspace(job_id), job_id, key, kind, obj)

    # -- creation + ingestion --------------------------------------------------
    def create_job(self, source_type: str, payload: dict,
                   options: JobOptions | None = None,
                   created_by: str = "anonymous") -> JobRecord:
        """Create a job, ingest its input, and leave it ready at PHASE1_RUNNING.

        Fails the job (terminal FAILED) on ingestion error or non-Angular input.
        Does not run phases — call :meth:`run` to drive the pipeline.
        """
        rec = JobRecord(source_type=source_type, options=options or JobOptions(),
                        created_by=created_by)
        self.store.save_job(rec)
        job = MigrationJob(rec, store=self.store)
        ws = self._workspace(rec.id)

        job.transition(JobState.INGESTING, actor=created_by, reason="ingest start")
        try:
            manifest = ingest(source_type, payload, ws)
        except IngestionError as e:
            job.fail(actor=created_by, reason=f"ingestion failed: {e}")
            return rec

        rec.manifest = manifest
        self._write_artifact(rec.id, "ingestion_manifest", "manifest", asdict(manifest))

        if not manifest.is_angular:
            job.fail(actor=created_by, reason="input is not an Angular project")
            return rec

        job.transition(JobState.PHASE1_RUNNING, actor=created_by, reason="ingest complete")
        return rec

    # -- running ---------------------------------------------------------------
    def _load(self, job_id: str) -> MigrationJob:
        rec = self.store.get_job(job_id)
        if rec is None:
            raise KeyError(f"No such job: {job_id}")
        return MigrationJob(rec, store=self.store)

    def _run_phase(self, job: MigrationJob, phase: int, next_state: JobState) -> None:
        ws = self._workspace(job.id)
        report = self.runner.run(job.id, phase, self.store, ws)
        job.record.phase_reports.append(report)
        self._write_artifact(job.id, f"phase{phase}_report", "phase_report", asdict(report))
        job.transition(next_state, actor="worker", reason=f"phase {phase} complete")

    def _auto_decide_gate(self, job: MigrationJob, gate: Gate) -> bool:
        """Return True if the gate should auto-advance (no human needed)."""
        if gate is Gate.PLAN:
            return self.auto_gates or job.record.options.auto_approve_plan
        return self.auto_gates  # Gate B never auto-skips in production (M5)

    def advance_once(self, job: MigrationJob) -> JobState:
        """Execute exactly one state step. Returns the new (or unchanged) state.

        Raises ApprovalRequiredError when parked at a gate awaiting a human.

        Phase-running states always transition to their natural next state (which
        may be a gate-waiting state). Gate-waiting states are handled in the
        clauses below — auto_gates causes immediate approval so the run loop
        advances through gates without a human round-trip. This keeps state
        machine transitions legal: PHASE1_RUNNING → AWAITING_PLAN_APPROVAL →
        PHASE2_RUNNING, never the illegal direct jump.
        """
        s = job.state
        if s in _PHASE_FLOW:
            phase, nxt = _PHASE_FLOW[s]
            self._run_phase(job, phase, nxt)
            return job.state
        if s is JobState.AWAITING_PLAN_APPROVAL:
            if self._auto_decide_gate(job, Gate.PLAN):
                self._record_decision(job, Gate.PLAN, ApprovalDecision.APPROVE,
                                      actor="auto", comments="auto-approved", advance=True)
                return job.state
            raise ApprovalRequiredError(Gate.PLAN.value)
        if s is JobState.AWAITING_FINAL_APPROVAL:
            if self._auto_decide_gate(job, Gate.FINAL):
                self._record_decision(job, Gate.FINAL, ApprovalDecision.APPROVE,
                                      actor="auto", comments="auto-approved", advance=True)
                return job.state
            raise ApprovalRequiredError(Gate.FINAL.value)
        if s is JobState.INTEGRATING:
            self._integrate(job)
            job.transition(JobState.COMPLETED, actor="worker", reason="integration complete")
            return job.state
        return s

    def _integrate(self, job: MigrationJob) -> None:
        """Assemble the migration deliverable: zip the generated output tree.

        Integration only runs after Gate B approval (enforced by the state flow:
        AWAITING_FINAL_APPROVAL → INTEGRATING). Produces ``deliverable.zip`` in the
        workspace root and records an ``integration`` artifact describing it.
        Git push is opt-in via ``options.target == "git"`` (M6 wires the provider
        adapters); the default deliverable is the zip.
        """
        import zipfile

        ws = self._workspace(job.id)
        out = ws.output_dir
        files = [p for p in out.rglob("*") if p.is_file()] if out.exists() else []
        zip_path = Path(ws.root) / "deliverable.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in files:
                zf.write(p, p.relative_to(out))

        self._write_artifact(job.id, "integration", "integration", {
            "deliverable": str(zip_path),
            "file_count": len(files),
            "files": [str(p.relative_to(out)) for p in files],
            "target": job.record.options.target,
        })

    def run(self, job_id: str) -> JobState:
        """Drive a job forward until it completes, fails, or parks at a gate."""
        job = self._load(job_id)
        while not job.is_terminal:
            try:
                before = job.state
                after = self.advance_once(job)
                if after == before:
                    break  # no progress possible
            except ApprovalRequiredError:
                break  # parked — caller/UI will submit a decision
            except Exception as e:
                # Runner/agent failure — persist the error so the UI can display it
                job.fail(actor="worker", reason=str(e))
                break
        return job.state

    def resume(self, job_id: str) -> JobState:
        """Resume a job after a restart. Idempotent runners skip completed work."""
        job = self._load(job_id)
        self.store.append_audit(job_id, AuditEvent(
            actor="system", event="resume", detail={"from_state": job.state.value}))
        return self.run(job_id)

    # -- approvals (real path used by the API; auto path used by the run loop) --
    def _record_decision(self, job: MigrationJob, gate: Gate, decision: ApprovalDecision,
                         actor: str, comments: str = "", report_sha: str = "",
                         advance: bool = True) -> None:
        rec = ApprovalRecord(gate=gate, decision=decision, decided_by=actor,
                             decided_at=time.time(), comments=comments, report_sha256=report_sha)
        self.store.record_approval(job.id, rec)
        job.record.approvals.append(rec)
        if not advance:
            return
        if decision is ApprovalDecision.APPROVE:
            target = JobState.PHASE2_RUNNING if gate is Gate.PLAN else JobState.INTEGRATING
        elif decision is ApprovalDecision.REVISE:
            # A revision must re-run the phase, not skip completed stages — clear
            # its records so idempotent runners re-execute with the new feedback.
            if gate is Gate.PLAN:
                target = JobState.PHASE1_RUNNING
                self.store.clear_phase(job.id, 1)
            else:
                target = JobState.PHASE4_RUNNING
                self.store.clear_phase(job.id, 4)
        else:  # REJECT
            target = JobState.REJECTED
        job.transition(target, actor=actor, reason=f"{gate.value} {decision.value}")

    def submit_decision(self, job_id: str, gate: Gate, decision: ApprovalDecision,
                        actor: str, comments: str = "") -> JobState:
        """Apply a human gate decision, then continue running. Bounds revisions."""
        job = self._load(job_id)
        expected = (JobState.AWAITING_PLAN_APPROVAL if gate is Gate.PLAN
                    else JobState.AWAITING_FINAL_APPROVAL)
        if job.state is not expected:
            raise ValueError(f"Job {job_id} is not awaiting {gate.value} approval (state={job.state.value})")

        if decision is ApprovalDecision.REVISE:
            if comments.strip() == "":
                raise ValueError("Revision requires comments")
            if self.store.revision_count(job_id, gate) >= job.record.options.max_revisions_per_gate:
                raise ValueError("Maximum revisions reached for this gate; approve or reject")

        self._record_decision(job, gate, decision, actor=actor, comments=comments, advance=True)
        return job.state

    # -- read models -----------------------------------------------------------
    def status(self, job_id: str) -> dict:
        rec = self.store.get_job(job_id)
        if rec is None:
            raise KeyError(job_id)
        return {
            "job_id": rec.id,
            "state": rec.state.value,
            "source_type": rec.source_type,
            "created_by": rec.created_by,
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
            "error_text": rec.error_text,
            "artifacts": [a["key"] for a in self.store.list_artifacts(rec.id)],
            "tokens": self.store.total_tokens(rec.id),
        }
