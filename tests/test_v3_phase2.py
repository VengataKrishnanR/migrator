"""M3 tests — Phase 2 transformation loop (transformer → refactor per chunk).

Stub mode: transformer/refactor agents return canned ReactSource /
RefactoredReactSource so the chunk loop runs offline. Verifies output files,
per-chunk artifacts, chunk-keyed stage records, and idempotent resume.
"""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

pytestmark = pytest.mark.integration

from tools.workflow.artifacts import read_artifact  # noqa: E402
from tools.workflow.models import JobOptions, JobState, StageStatus  # noqa: E402
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


def test_phase2_full_run_writes_react_output(tmp_path, runner_cls):
    svc = _service(tmp_path, runner_cls, auto_gates=True)
    rec = svc.create_job("paste", {"content": _PASTE}, options=JobOptions(auto_approve_plan=True))
    assert svc.run(rec.id) is JobState.COMPLETED

    ws = svc._workspace(rec.id)
    # phase 2 report + per-chunk artifacts present
    assert read_artifact(ws, "phase2_report") is not None
    plan = read_artifact(ws, "plan")
    for chunk_id in plan["execution_order"]:
        assert read_artifact(ws, f"react_{chunk_id}") is not None
        assert read_artifact(ws, f"refactored_{chunk_id}") is not None

    # React files written to the output tree
    tsx = list(ws.output_dir.rglob("*.tsx"))
    assert tsx, "no React output files written"

    # chunk-keyed stage records exist for every chunk
    done = svc.store.completed_stages(rec.id, 2)
    for chunk_id in plan["execution_order"]:
        assert f"transformer:{chunk_id}" in done
        assert f"refactor_optimizer:{chunk_id}" in done


def test_phase2_idempotent_resume(tmp_path, runner_cls):
    # Drive through Phase 1 + Gate A approval so the job enters Phase 2 and runs it.
    svc = _service(tmp_path, runner_cls, auto_gates=False)
    rec = svc.create_job("paste", {"content": _PASTE})
    svc.run(rec.id)  # parks at Gate A
    from tools.workflow.models import ApprovalDecision, Gate
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")  # runs phase 2 → Gate B

    ws = svc._workspace(rec.id)
    first = svc.store.completed_stages(rec.id, 2)
    assert first, "phase 2 produced no stage records"

    # Re-run phase 2 directly: every stage must come back SKIPPED (nothing re-done).
    report = svc.runner._run_phase2(rec.id, svc.store, ws)
    assert report.stages, "expected stage records on resume"
    assert all(s.status is StageStatus.SKIPPED for s in report.stages)
