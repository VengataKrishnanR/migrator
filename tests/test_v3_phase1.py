"""M2 tests — real Phase 1 runner (analyzer→risk→planner→state) via stub agents.

Requires google-adk; run from the project venv. NGREACT_LLM_MODE=stub makes the
agents return canned artifacts so the phase runs offline and deterministically.
"""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")

pytestmark = pytest.mark.integration

from server.agent_invoker import AgentInvocationError, extract_json, invoke_agent  # noqa: E402
from server.artifact_schemas import validate_analysis, validate_plan  # noqa: E402
from tools.workflow.artifacts import read_artifact  # noqa: E402
from tools.workflow.models import ApprovalDecision, Gate, JobOptions, JobState  # noqa: E402
from tools.workflow.store import JobStore  # noqa: E402

_PASTE = ("// file: src/app/user-list.component.ts\n"
          "@Component({selector: 'app-user-list'})\n"
          "export class UserListComponent implements OnInit, OnDestroy {}\n")


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("NGREACT_LLM_MODE", "stub")
    from server.phase_runner import RealPhaseRunner
    from server.service import JobService
    store = JobStore(str(tmp_path / "db.sqlite"))
    runner = RealPhaseRunner()  # builds stub model
    return JobService(store, data_dir=str(tmp_path / "data"), runner=runner, auto_gates=False)


# -- unit: JSON extraction + validators ------------------------------------

def test_extract_json_fenced():
    assert extract_json('blah\n```json\n{"a": 1}\n```\nend')["a"] == 1


def test_extract_json_bare_object():
    assert extract_json('prefix {"x": {"y": 2}} suffix')["x"]["y"] == 2


def test_extract_json_none_raises():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_validate_plan_rejects_empty_chunks():
    with pytest.raises(ValueError):
        validate_plan({"chunks": [], "execution_order": []})


# -- integration: Phase 1 happy path ---------------------------------------

def test_phase1_produces_all_artifacts(svc):
    rec = svc.create_job("paste", {"content": _PASTE})
    assert rec.state is JobState.PHASE1_RUNNING
    state = svc.run(rec.id)
    assert state is JobState.AWAITING_PLAN_APPROVAL  # parks at Gate A

    ws = svc._workspace(rec.id)
    for key in ("analysis", "risk", "plan", "state_plan"):
        art = read_artifact(ws, key)
        assert art is not None, f"missing artifact {key}"
    # validators accept the produced shapes
    validate_analysis(read_artifact(ws, "analysis"))
    validate_plan(read_artifact(ws, "plan"))

    # phase1 report recorded 4 completed stages
    done = svc.store.completed_stages(rec.id, 1)
    assert {"analyzer", "risk_detection", "migration_planner", "state_migration_planner"} <= done

    status = svc.status(rec.id)
    assert "analysis" in status["artifacts"] and "phase1_report" in status["artifacts"]


def test_phase1_gate_approve_advances(svc):
    rec = svc.create_job("paste", {"content": _PASTE})
    assert svc.run(rec.id) is JobState.AWAITING_PLAN_APPROVAL
    state = svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    assert state is JobState.AWAITING_FINAL_APPROVAL  # phases 2-4 are stubbed, park at Gate B


def test_phase1_revise_reruns(svc):
    rec = svc.create_job("paste", {"content": _PASTE})
    svc.run(rec.id)
    # revise → clears phase 1 and goes back to PHASE1_RUNNING
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.REVISE, actor="alice",
                        comments="Add risk detail for the OnDestroy hook")
    job = svc._load(rec.id)
    assert job.state is JobState.AWAITING_PLAN_APPROVAL  # re-ran phase 1, parked again
    # stages were genuinely re-run (records repopulated after clear)
    done = svc.store.completed_stages(rec.id, 1)
    assert len(done) == 4
    # the revise decision is in the audit/approval trail
    assert svc.store.revision_count(rec.id, Gate.PLAN) == 1


def test_phase1_full_run_completes_with_auto_gates(tmp_path, monkeypatch):
    monkeypatch.setenv("NGREACT_LLM_MODE", "stub")
    from server.phase_runner import RealPhaseRunner
    from server.service import JobService
    store = JobStore(str(tmp_path / "db.sqlite"))
    svc = JobService(store, data_dir=str(tmp_path / "data"),
                     runner=RealPhaseRunner(), auto_gates=True)
    rec = svc.create_job("paste", {"content": _PASTE}, options=JobOptions(auto_approve_plan=True))
    assert svc.run(rec.id) is JobState.COMPLETED
