"""E2E positive scenarios — happy paths through the full migration pipeline.

All tests use StubPhaseRunner (no ADK dependency) to exercise service logic,
state machine transitions, gate flows, and audit trail — exactly as a real
job would behave but with deterministic zero-latency agent responses.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from server.runners import StubPhaseRunner
from server.service import JobService
from tools.workflow.models import ApprovalDecision, Gate, JobOptions, JobState
from tools.workflow.store import JobStore

pytestmark = pytest.mark.e2e_positive


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(tmp_path, *, auto_gates: bool = True) -> JobService:
    store = JobStore(str(tmp_path / "db.sqlite"))
    return JobService(store, data_dir=str(tmp_path / "data"),
                      runner=StubPhaseRunner(), auto_gates=auto_gates)


def _angular_paste() -> str:
    return (
        "@Component({selector: 'app-root'})\n"
        "export class AppComponent implements OnInit, OnDestroy {}"
    )


def _multifile_paste() -> str:
    return (
        "// file: src/app/user-list.component.ts\n"
        "@Component({selector: 'app-user-list'})\n"
        "export class UserListComponent implements OnInit {}\n"
        "// file: src/app/user.service.ts\n"
        "export class UserService { getData() {} }\n"
    )


def _angular_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("proj/angular.json", "{}")
        zf.writestr("proj/package.json", '{"dependencies":{"@angular/core":"17.0.0"}}')
        zf.writestr("proj/src/app/app.component.ts", "export class AppComponent {}")
        zf.writestr("proj/src/app/app.service.ts", "export class AppService {}")
    return buf.getvalue()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_e2e_paste_angular_component_reaches_completed(tmp_path):
    """Single Angular component pasted → auto-gates → COMPLETED."""
    svc = _svc(tmp_path)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    assert rec.state is JobState.PHASE1_RUNNING
    assert svc.run(rec.id) is JobState.COMPLETED


def test_e2e_zip_angular_project_reaches_completed(tmp_path):
    """Angular project uploaded as ZIP → all 4 phases → COMPLETED."""
    svc = _svc(tmp_path)
    rec = svc.create_job("zip", {"zip_bytes": _angular_zip()})
    assert svc.run(rec.id) is JobState.COMPLETED


def test_e2e_multifile_paste_reaches_completed(tmp_path):
    """Paste with multiple // file: markers is ingested as multiple files → COMPLETED."""
    svc = _svc(tmp_path)
    rec = svc.create_job("paste", {"content": _multifile_paste()})
    assert svc.run(rec.id) is JobState.COMPLETED


def test_e2e_manual_gate_a_approve_advances_to_gate_b(tmp_path):
    """With auto_gates=False, Gate A parks the job; approving drives to Gate B."""
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    assert svc.run(rec.id) is JobState.AWAITING_PLAN_APPROVAL

    state = svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    assert state is JobState.AWAITING_FINAL_APPROVAL


def test_e2e_both_gates_approved_reaches_completed(tmp_path):
    """Approve Gate A then Gate B → integration → COMPLETED."""
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    state = svc.submit_decision(rec.id, Gate.FINAL, ApprovalDecision.APPROVE, actor="alice")
    assert state is JobState.COMPLETED


def test_e2e_revise_gate_a_reruns_and_approve_completes(tmp_path):
    """Revise at Gate A → phase 1 re-runs → approve both gates → COMPLETED."""
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)

    # Revise: phase 1 re-runs, parks at Gate A again
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.REVISE,
                        actor="alice", comments="Add more risk detail")
    assert svc._load(rec.id).state is JobState.AWAITING_PLAN_APPROVAL

    # Approve both gates
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    state = svc.submit_decision(rec.id, Gate.FINAL, ApprovalDecision.APPROVE, actor="alice")
    assert state is JobState.COMPLETED


def test_e2e_all_four_phases_record_stages(tmp_path):
    """All 4 phases complete and each records at least one stage in the store."""
    svc = _svc(tmp_path)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)

    for phase in (1, 2, 3, 4):
        stages = svc.store.completed_stages(rec.id, phase)
        assert stages, f"Phase {phase} recorded no stages"


def test_e2e_audit_trail_records_all_phase_transitions(tmp_path):
    """Audit trail contains state_transition events for every pipeline state."""
    svc = _svc(tmp_path)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)

    audit = svc.store.get_audit(rec.id)
    visited = {e.detail.get("to") for e in audit if e.event == "state_transition"}

    for expected in ("ingesting", "phase1_running", "awaiting_plan_approval",
                     "phase2_running", "phase3_running", "phase4_running",
                     "awaiting_final_approval", "integrating", "completed"):
        assert expected in visited, f"State '{expected}' absent from audit trail"


def test_e2e_status_returns_job_id_state_and_artifacts(tmp_path):
    """status() returns job_id, state=completed, and a non-empty artifact list."""
    svc = _svc(tmp_path)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)

    status = svc.status(rec.id)
    assert status["job_id"] == rec.id
    assert status["state"] == "completed"
    assert "ingestion_manifest" in status["artifacts"]
    assert len(status["artifacts"]) >= 4  # manifest + 4 phase reports minimum
