"""M1 acceptance tests — JobService end-to-end with the stub runner.

Covers plan §12 M1 acceptance: create a job from each source, workspace
materialized, non-Angular rejected, stubbed COMPLETED, and restart-resume.
"""
from __future__ import annotations

import io
import zipfile

import pytest

pytestmark = pytest.mark.integration

from server.runners import StubPhaseRunner
from server.service import JobService
from tools.workflow.models import Gate, ApprovalDecision, JobOptions, JobState
from tools.workflow.store import JobStore


def _service(tmp_path, auto_gates=True):
    store = JobStore(str(tmp_path / "db.sqlite"))
    return JobService(store, data_dir=str(tmp_path / "data"),
                      runner=StubPhaseRunner(), auto_gates=auto_gates)


def _angular_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("proj/angular.json", "{}")
        zf.writestr("proj/package.json", '{"dependencies":{"@angular/core":"17.0.0"}}')
        zf.writestr("proj/src/app/app.component.ts", "export class AppComponent {}")
    return buf.getvalue()


def test_create_from_paste_reaches_completed(tmp_path):
    svc = _service(tmp_path)
    rec = svc.create_job("paste", {"content": "@Component({}) export class FooComponent {}"})
    assert rec.state is JobState.PHASE1_RUNNING
    final = svc.run(rec.id)
    assert final is JobState.COMPLETED


def test_create_from_files(tmp_path):
    svc = _service(tmp_path)
    rec = svc.create_job("files", {"files": [
        {"path": "package.json", "content": '{"dependencies":{"@angular/core":"17.0.0"}}'},
        {"path": "src/app/x.component.ts", "content": "export class XComponent {}"},
    ]})
    assert svc.run(rec.id) is JobState.COMPLETED
    # workspace materialized
    ws = svc._workspace(rec.id)
    assert (ws.input_dir / "package.json").exists()
    assert "ingestion_manifest" in svc.status(rec.id)["artifacts"]


def test_create_from_zip(tmp_path):
    svc = _service(tmp_path)
    rec = svc.create_job("zip", {"zip_bytes": _angular_zip()})
    assert svc.run(rec.id) is JobState.COMPLETED


def test_non_angular_input_fails_fast(tmp_path):
    svc = _service(tmp_path)
    rec = svc.create_job("files", {"files": [{"path": "main.py", "content": "print(1)"}]})
    assert rec.state is JobState.FAILED
    assert "not an Angular project" in (rec.error_text or "")


def test_zip_slip_fails_job(tmp_path):
    svc = _service(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")
    rec = svc.create_job("zip", {"zip_bytes": buf.getvalue()})
    assert rec.state is JobState.FAILED


def test_restart_resume_completes(tmp_path):
    # First service instance: create + step partway, simulating a crash mid-pipeline.
    db = str(tmp_path / "db.sqlite")
    data = str(tmp_path / "data")
    store1 = JobStore(db)
    svc1 = JobService(store1, data_dir=data, runner=StubPhaseRunner(), auto_gates=True)
    rec = svc1.create_job("paste", {"content": "@Component({}) export class FooComponent {}"})
    job = svc1._load(rec.id)
    svc1.advance_once(job)  # phase 1
    svc1.advance_once(job)  # gate A auto-approve -> phase2
    svc1.advance_once(job)  # phase 2 -> phase3
    assert job.state is JobState.PHASE3_RUNNING
    store1.close()

    # Fresh service instance over the same DB + workspace: resume to completion.
    store2 = JobStore(db)
    svc2 = JobService(store2, data_dir=data, runner=StubPhaseRunner(), auto_gates=True)
    assert svc2.resume(rec.id) is JobState.COMPLETED
    # Resume must not double-run phase 2 stages — they resume as SKIPPED.
    assert "resume" in {e.event for e in store2.get_audit(rec.id)}


def test_gate_parks_without_auto_approval(tmp_path):
    svc = _service(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": "@Component({}) export class FooComponent {}"},
                         options=JobOptions(auto_approve_plan=False))
    state = svc.run(rec.id)
    assert state is JobState.AWAITING_PLAN_APPROVAL  # parked at Gate A

    # Human approves Gate A; job advances; parks again at Gate B.
    state = svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    assert state is JobState.AWAITING_FINAL_APPROVAL


def test_revise_requires_comments_and_is_bounded(tmp_path):
    svc = _service(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": "@Component({}) export class FooComponent {}"})
    svc.run(rec.id)
    with pytest.raises(ValueError, match="Revision requires comments"):
        svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.REVISE, actor="alice")
    # revise sends back to phase 1, re-run parks at gate A again
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.REVISE, actor="alice", comments="add detail")
    assert svc._load(rec.id).state is JobState.AWAITING_PLAN_APPROVAL
