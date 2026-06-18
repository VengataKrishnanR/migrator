"""M4 tests — Phase 3 test generation (test_planner → per-chunk test_generator).

Stub mode: test_planner returns a canned TestPlan and test_generation returns a
canned TestSuite, so the phase runs offline. Verifies the TestPlan artifact,
per-chunk test suites, generated test files, stage records, and idempotent resume.
"""
from __future__ import annotations

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


def test_phase3_generates_test_plan_and_suites(tmp_path, runner_cls):
    svc = _service(tmp_path, runner_cls, auto_gates=True)
    rec = svc.create_job("paste", {"content": _PASTE}, options=JobOptions(auto_approve_plan=True))
    assert svc.run(rec.id) is JobState.COMPLETED

    ws = svc._workspace(rec.id)
    # Phase 3 report + the TestPlan artifact exist
    assert read_artifact(ws, "phase3_report") is not None
    test_plan = read_artifact(ws, "test_plan")
    assert test_plan is not None and test_plan.get("matrix"), "TestPlan missing or empty matrix"

    # Per-chunk test suites + generated *.test.tsx files
    plan = read_artifact(ws, "plan")
    for chunk_id in plan["execution_order"]:
        assert read_artifact(ws, f"tests_{chunk_id}") is not None
    test_files = list(ws.output_dir.rglob("*.test.tsx"))
    assert test_files, "no test files written to the output tree"

    # Stage records: test_planner + per-chunk test_generator
    done = svc.store.completed_stages(rec.id, 3)
    assert "test_planner" in done
    for chunk_id in plan["execution_order"]:
        assert f"test_generator:{chunk_id}" in done


def test_phase3_idempotent_resume(tmp_path, runner_cls):
    svc = _service(tmp_path, runner_cls, auto_gates=False)
    rec = svc.create_job("paste", {"content": _PASTE})
    svc.run(rec.id)  # parks at Gate A
    # Approve Gate A → phase 2 → phase 3 → phase 4 → parks at Gate B
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")

    ws = svc._workspace(rec.id)
    assert svc.store.completed_stages(rec.id, 3), "phase 3 produced no stage records"

    # Re-run phase 3 directly: every stage must come back SKIPPED.
    report = svc.runner._run_phase3(rec.id, svc.store, ws)
    assert report.stages, "expected stage records on resume"
    assert all(s.status is StageStatus.SKIPPED for s in report.stages)
