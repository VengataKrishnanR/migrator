"""E2E negative scenarios — error paths, security guards, and edge cases.

Verifies that the pipeline fails fast on bad input, that rejection and
cancellation reach the correct terminal states, and that the service
raises the right errors for illegal operations.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from server.runners import StubPhaseRunner
from server.service import JobService
from tools.workflow.models import ApprovalDecision, Gate, JobOptions, JobState
from tools.workflow.state_machine import IllegalTransitionError, MigrationJob
from tools.workflow.models import JobRecord
from tools.workflow.store import JobStore

pytestmark = pytest.mark.e2e_negative


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(tmp_path, *, auto_gates: bool = True) -> JobService:
    store = JobStore(str(tmp_path / "db.sqlite"))
    return JobService(store, data_dir=str(tmp_path / "data"),
                      runner=StubPhaseRunner(), auto_gates=auto_gates)


def _angular_paste() -> str:
    return "@Component({selector:'app-root'}) export class AppComponent {}"


# ── Ingestion failures ────────────────────────────────────────────────────────

def test_e2e_non_angular_python_file_fails_at_ingestion(tmp_path):
    """Python-only input is detected immediately; job state is FAILED."""
    svc = _svc(tmp_path)
    rec = svc.create_job("files", {"files": [{"path": "main.py", "content": "print(1)"}]})
    assert rec.state is JobState.FAILED
    assert rec.error_text  # must carry a reason


def test_e2e_empty_paste_fails_at_ingestion(tmp_path):
    """Whitespace-only paste is rejected by the ingestion adapter; job FAILED."""
    svc = _svc(tmp_path)
    rec = svc.create_job("paste", {"content": "   \n\t  "})
    assert rec.state is JobState.FAILED


def test_e2e_zip_path_traversal_blocked(tmp_path):
    """ZIP containing path-traversal entries (../../) is rejected; job FAILED."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0")
    rec = _svc(tmp_path).create_job("zip", {"zip_bytes": buf.getvalue()})
    assert rec.state is JobState.FAILED


def test_e2e_failed_job_never_enters_phase1(tmp_path):
    """A FAILED job at ingestion must not have phase1_running in its audit trail."""
    svc = _svc(tmp_path)
    rec = svc.create_job("files", {"files": [{"path": "readme.md", "content": "# docs"}]})
    assert rec.state is JobState.FAILED
    audit = svc.store.get_audit(rec.id)
    states = {e.detail.get("to") for e in audit if e.event == "state_transition"}
    assert "phase1_running" not in states


# ── Gate rejection ────────────────────────────────────────────────────────────

def test_e2e_reject_at_gate_a_sets_rejected(tmp_path):
    """Rejecting at Gate A transitions job to REJECTED (terminal)."""
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)
    assert svc._load(rec.id).state is JobState.AWAITING_PLAN_APPROVAL

    state = svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.REJECT, actor="reviewer")
    assert state is JobState.REJECTED


def test_e2e_reject_at_gate_b_sets_rejected(tmp_path):
    """Rejecting at Gate B (after all 4 phases) transitions job to REJECTED."""
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    assert svc._load(rec.id).state is JobState.AWAITING_FINAL_APPROVAL

    state = svc.submit_decision(rec.id, Gate.FINAL, ApprovalDecision.REJECT, actor="alice")
    assert state is JobState.REJECTED


# ── Cancellation ──────────────────────────────────────────────────────────────

def test_e2e_cancel_parked_job_sets_cancelled(tmp_path):
    """cancel() on a job parked at Gate A transitions it to CANCELLED."""
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)  # parks at Gate A

    job = svc._load(rec.id)
    job.cancel(actor="user")
    assert job.state is JobState.CANCELLED


# ── Decision validation ───────────────────────────────────────────────────────

def test_e2e_revise_without_comments_raises_value_error(tmp_path):
    """submit_decision(REVISE) with an empty comments string raises ValueError."""
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)

    with pytest.raises(ValueError, match="Revision requires comments"):
        svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.REVISE,
                            actor="alice", comments="")


def test_e2e_decision_on_wrong_state_raises_value_error(tmp_path):
    """submit_decision on a COMPLETED job raises ValueError (wrong state)."""
    svc = _svc(tmp_path, auto_gates=True)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)
    assert svc._load(rec.id).state is JobState.COMPLETED

    with pytest.raises(ValueError):
        svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")


def test_e2e_unknown_job_id_raises_key_error(tmp_path):
    """status() for a non-existent job_id raises KeyError."""
    svc = _svc(tmp_path)
    with pytest.raises(KeyError):
        svc.status("job_does_not_exist_xyz")


# ── State machine guards ──────────────────────────────────────────────────────

def test_e2e_illegal_phase_skip_blocked_by_state_machine():
    """State machine blocks an illegal direct jump (phase1_running → phase2_running)."""
    job = MigrationJob(JobRecord())
    job.transition(JobState.INGESTING, actor="test")
    job.transition(JobState.PHASE1_RUNNING, actor="test")

    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.PHASE2_RUNNING, actor="test")


def test_e2e_revision_limit_exceeded_raises_value_error(tmp_path):
    """Exceeding max_revisions_per_gate raises ValueError with clear message."""
    svc = _svc(tmp_path, auto_gates=False)
    # Use max_revisions_per_gate=1 to force the limit quickly
    rec = svc.create_job("paste", {"content": _angular_paste()},
                         options=JobOptions(max_revisions_per_gate=1))
    svc.run(rec.id)

    # First revision: allowed
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.REVISE,
                        actor="alice", comments="First pass")
    assert svc._load(rec.id).state is JobState.AWAITING_PLAN_APPROVAL

    # Second revision: exceeds limit=1
    with pytest.raises(ValueError, match="Maximum revisions reached"):
        svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.REVISE,
                            actor="alice", comments="Still not good")
