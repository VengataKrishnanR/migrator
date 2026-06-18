"""M5 tests — Phase 4 (validation + report), Gate B, and integration.

Stub mode: validator returns a canned ValidationReport and report returns a
canned MigrationReport. Verifies the artifacts, Gate B parking + approval, the
assembled deliverable zip, and idempotent resume.
"""
from __future__ import annotations

import zipfile

import pytest

pytest.importorskip("google.adk")

pytestmark = pytest.mark.integration

from tools.workflow.artifacts import read_artifact  # noqa: E402
from tools.workflow.models import (  # noqa: E402
    ApprovalDecision,
    Gate,
    JobOptions,
    JobState,
    StageStatus,
)
from tools.workflow.store import JobStore  # noqa: E402

_PASTE = ("// file: src/app/user-list.component.ts\n"
          "@Component({selector: 'app-user-list'})\n"
          "export class UserListComponent implements OnInit {}\n")


@pytest.fixture()
def runner_cls(monkeypatch):
    monkeypatch.setenv("NGREACT_LLM_MODE", "stub")
    from server.phase_runner import RealPhaseRunner
    return RealPhaseRunner


def _service(tmp_path, runner_cls, auto_gates):
    from server.service import JobService
    store = JobStore(str(tmp_path / "db.sqlite"))
    return JobService(store, data_dir=str(tmp_path / "data"),
                      runner=runner_cls(), auto_gates=auto_gates)


def test_phase4_validation_report_and_deliverable(tmp_path, runner_cls):
    svc = _service(tmp_path, runner_cls, auto_gates=True)
    rec = svc.create_job("paste", {"content": _PASTE}, options=JobOptions(auto_approve_plan=True))
    assert svc.run(rec.id) is JobState.COMPLETED

    ws = svc._workspace(rec.id)
    # Phase 4 artifacts
    assert read_artifact(ws, "phase4_report") is not None
    validation = read_artifact(ws, "validation")
    assert validation is not None and validation.get("passed") is True
    report = read_artifact(ws, "report")
    assert report is not None and report.get("success") is True

    # Integration: deliverable.zip assembled with the generated files
    integ = read_artifact(ws, "integration")
    assert integ is not None and integ["file_count"] > 0
    zip_path = ws.root / "deliverable.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist(), "deliverable zip is empty"

    # Stage records for validator + report
    done = svc.store.completed_stages(rec.id, 4)
    assert "validator" in done and "report" in done


def test_gate_b_parks_then_approves(tmp_path, runner_cls):
    """With gates on, the job parks at Gate B (final approval) before integrating."""
    svc = _service(tmp_path, runner_cls, auto_gates=False)
    rec = svc.create_job("paste", {"content": _PASTE})
    svc.run(rec.id)  # parks at Gate A
    state = svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    # After Gate A: phases 2→3→4 run, then it must PARK at Gate B (not auto-complete)
    assert state is JobState.AWAITING_FINAL_APPROVAL

    # Approve Gate B → integrate → COMPLETED
    final = svc.submit_decision(rec.id, Gate.FINAL, ApprovalDecision.APPROVE, actor="alice")
    assert final is JobState.COMPLETED
    assert read_artifact(svc._workspace(rec.id), "integration") is not None


def test_phase4_idempotent_resume(tmp_path, runner_cls):
    svc = _service(tmp_path, runner_cls, auto_gates=True)
    rec = svc.create_job("paste", {"content": _PASTE}, options=JobOptions(auto_approve_plan=True))
    svc.run(rec.id)

    ws = svc._workspace(rec.id)
    report = svc.runner._run_phase4(rec.id, svc.store, ws)
    assert report.stages
    assert all(s.status is StageStatus.SKIPPED for s in report.stages)
