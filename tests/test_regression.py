"""Regression tests for every error reported in the re-engineering session.

Each test is named after the exact error it guards against so failures are
immediately diagnosable. These tests must pass without any network access.

Errors guarded:
  1. IllegalTransitionError: phase1_running → phase2_running
  2. State machine: no direct phase skip (phase1_running → phase3_running)
  3. State machine: no transition out of terminal states
  4. extract_json: reasoning text before JSON still extracts correct block
  5. extract_json: multiple JSON blocks picks the last one
  6. extract_json: raw JSON without fences is found
  7. extract_json: fails cleanly when no JSON present
  8. advance_once: full auto-gate pipeline completes without transition error
  9. advance_once: gate parks correctly when auto_gates=False
 10. advance_once: double-call safety — no duplicate transitions
 11. Revise gate: phase re-runs from the correct state
 12. JobService.run: reaches COMPLETED through all 4 phases + 2 gates (auto)
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

pytestmark = pytest.mark.regression

from server.service import ApprovalRequiredError, JobService
from server.json_utils import extract_json   # ADK-free module — always importable
from server.runners import StubPhaseRunner
from tools.workflow.models import (
    ApprovalDecision,
    Gate,
    JobOptions,
    JobState,
)
from tools.workflow.state_machine import IllegalTransitionError, MigrationJob
from tools.workflow.models import JobRecord
from tools.workflow.store import JobStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(tmp_path, *, auto_gates: bool = True) -> JobService:
    store = JobStore(str(tmp_path / "db.sqlite"))
    return JobService(
        store,
        data_dir=str(tmp_path / "data"),
        runner=StubPhaseRunner(),
        auto_gates=auto_gates,
    )


def _angular_paste() -> str:
    return "@Component({selector:'app-root'}) export class AppComponent {}"


def _angular_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("proj/angular.json", "{}")
        zf.writestr("proj/package.json", '{"dependencies":{"@angular/core":"17.0.0"}}')
        zf.writestr("proj/src/app/app.component.ts", "export class AppComponent {}")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. THE bug: phase1_running → phase2_running must NOT raise
# ---------------------------------------------------------------------------

def test_no_illegal_transition_phase1_to_phase2_with_auto_gates(tmp_path):
    """
    Regression for: IllegalTransitionError: phase1_running → phase2_running

    Before the fix, advance_once() modified `nxt` to skip AWAITING_PLAN_APPROVAL
    and passed PHASE2_RUNNING directly to _run_phase, which called
    job.transition(PHASE2_RUNNING) from PHASE1_RUNNING — an illegal move.

    After the fix, the transition goes:
      PHASE1_RUNNING → AWAITING_PLAN_APPROVAL → PHASE2_RUNNING
    """
    svc = _svc(tmp_path, auto_gates=True)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    assert rec.state is JobState.PHASE1_RUNNING

    job = svc._load(rec.id)

    # This call must NOT raise IllegalTransitionError
    svc.advance_once(job)
    assert job.state is JobState.AWAITING_PLAN_APPROVAL

    # Auto-approve gate
    svc.advance_once(job)
    assert job.state is JobState.PHASE2_RUNNING


# ---------------------------------------------------------------------------
# 2. State machine: direct phase skip is still blocked
# ---------------------------------------------------------------------------

def test_phase1_running_cannot_skip_to_phase3():
    job = MigrationJob(JobRecord())
    for s in (JobState.INGESTING, JobState.PHASE1_RUNNING):
        job.transition(s, actor="w")
    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.PHASE3_RUNNING, actor="w")


def test_phase1_running_cannot_jump_to_phase2_directly():
    """The state machine itself blocks phase1_running → phase2_running."""
    job = MigrationJob(JobRecord())
    for s in (JobState.INGESTING, JobState.PHASE1_RUNNING):
        job.transition(s, actor="w")
    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.PHASE2_RUNNING, actor="w")


# ---------------------------------------------------------------------------
# 3. No transition out of terminal states
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("terminal", [
    JobState.COMPLETED,
    JobState.FAILED,
    JobState.REJECTED,
    JobState.CANCELLED,
])
def test_no_transition_out_of_terminal(terminal):
    job = MigrationJob(JobRecord(state=terminal))
    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.PHASE1_RUNNING, actor="w")


# ---------------------------------------------------------------------------
# 4. extract_json: reasoning text BEFORE json block
# ---------------------------------------------------------------------------

def test_extract_json_with_reasoning_before_fence():
    """
    Before the fix, extract_json found the FIRST json block.
    When a model reasons first and then produces the answer, the first block
    may be an intermediate/malformed object. The fix returns the LAST block.
    """
    text = (
        "Let me think about this...\n"
        "The components include:\n"
        "```json\n{\"draft\": true, \"components\": []}\n```\n"
        "After further analysis, my final answer is:\n"
        "```json\n{\"components\": [{\"name\": \"AppComponent\"}], \"total_files\": 1}\n```"
    )
    result = extract_json(text)
    assert result["total_files"] == 1
    assert len(result["components"]) == 1
    assert "draft" not in result


def test_extract_json_picks_last_when_multiple_fences():
    text = (
        '```json\n{"step": 1, "partial": true}\n```\n'
        'Continuing...\n'
        '```json\n{"step": 2, "final": true, "data": [1, 2, 3]}\n```'
    )
    result = extract_json(text)
    assert result["final"] is True
    assert result["step"] == 2


# ---------------------------------------------------------------------------
# 5. extract_json: raw JSON without fences
# ---------------------------------------------------------------------------

def test_extract_json_raw_object_no_fence():
    text = 'Here is the result: {"passed": true, "score": 95}'
    result = extract_json(text)
    assert result["passed"] is True
    assert result["score"] == 95


def test_extract_json_pure_json_string():
    data = {"components": [], "total_files": 0}
    result = extract_json(json.dumps(data))
    assert result == data


# ---------------------------------------------------------------------------
# 6. extract_json: fails cleanly when no JSON present
# ---------------------------------------------------------------------------

def test_extract_json_raises_on_no_json():
    with pytest.raises(ValueError, match="No JSON object found"):
        extract_json("There is no JSON here at all.")


def test_extract_json_raises_on_empty_string():
    with pytest.raises(ValueError):
        extract_json("")


def test_extract_json_raises_on_invalid_json_in_fence():
    text = "```json\n{invalid: json here\n```"
    # Should raise because the fence content is not valid JSON
    # (falls through to raw scan which also finds nothing valid)
    with pytest.raises(ValueError):
        extract_json(text)


# ---------------------------------------------------------------------------
# 7. advance_once: full pipeline through all states, no crash
# ---------------------------------------------------------------------------

def test_full_pipeline_auto_gates_reaches_completed(tmp_path):
    """End-to-end: CREATED → COMPLETED through all 4 phases and 2 auto-gates."""
    svc = _svc(tmp_path, auto_gates=True)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    final = svc.run(rec.id)
    assert final is JobState.COMPLETED


def test_full_pipeline_zip_reaches_completed(tmp_path):
    svc = _svc(tmp_path, auto_gates=True)
    rec = svc.create_job("zip", {"zip_bytes": _angular_zip()})
    assert svc.run(rec.id) is JobState.COMPLETED


# ---------------------------------------------------------------------------
# 8. Gate parks correctly when auto_gates=False
# ---------------------------------------------------------------------------

def test_gate_a_parks_job(tmp_path):
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()},
                         options=JobOptions(auto_approve_plan=False))
    state = svc.run(rec.id)
    assert state is JobState.AWAITING_PLAN_APPROVAL


def test_gate_b_parks_job(tmp_path):
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)
    # Approve gate A → pipeline continues → parks at gate B
    state = svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    assert state is JobState.AWAITING_FINAL_APPROVAL


# ---------------------------------------------------------------------------
# 9. advance_once: no duplicate state transition from double-call
# ---------------------------------------------------------------------------

def test_advance_once_idempotent_on_terminal(tmp_path):
    """advance_once on a COMPLETED job must return COMPLETED, not raise."""
    svc = _svc(tmp_path, auto_gates=True)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)
    job = svc._load(rec.id)
    assert job.state is JobState.COMPLETED
    # Calling advance_once again must be harmless
    result = svc.advance_once(job)
    assert result is JobState.COMPLETED


# ---------------------------------------------------------------------------
# 10. Revise gate: goes back to the correct phase, not a wrong state
# ---------------------------------------------------------------------------

def test_revise_gate_a_sends_back_to_phase1(tmp_path):
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)
    assert svc._load(rec.id).state is JobState.AWAITING_PLAN_APPROVAL

    svc.submit_decision(
        rec.id, Gate.PLAN, ApprovalDecision.REVISE,
        actor="alice", comments="Need more detail on risk score"
    )
    # After revise, must be back at AWAITING_PLAN_APPROVAL (phase 1 re-ran)
    assert svc._load(rec.id).state is JobState.AWAITING_PLAN_APPROVAL


def test_revise_gate_b_sends_back_to_phase4(tmp_path):
    """Gate B revise must NOT jump to an illegal state."""
    svc = _svc(tmp_path, auto_gates=False)
    rec = svc.create_job("paste", {"content": _angular_paste()})
    svc.run(rec.id)
    svc.submit_decision(rec.id, Gate.PLAN, ApprovalDecision.APPROVE, actor="alice")
    # Now at gate B
    assert svc._load(rec.id).state is JobState.AWAITING_FINAL_APPROVAL
    svc.submit_decision(
        rec.id, Gate.FINAL, ApprovalDecision.REVISE,
        actor="alice", comments="Validator score too low"
    )
    assert svc._load(rec.id).state is JobState.AWAITING_FINAL_APPROVAL


# ---------------------------------------------------------------------------
# 11. Non-Angular input fails fast — does not enter pipeline states
# ---------------------------------------------------------------------------

def test_non_angular_never_reaches_phase1(tmp_path):
    svc = _svc(tmp_path)
    rec = svc.create_job("files", {"files": [{"path": "main.py", "content": "print(1)"}]})
    assert rec.state is JobState.FAILED
    # Must never have been in PHASE1_RUNNING
    audit = svc.store.get_audit(rec.id)
    states_visited = {e.detail.get("to") for e in audit if e.event == "state_transition"}
    assert "phase1_running" not in states_visited


# ---------------------------------------------------------------------------
# 12. Zip-slip security: malicious zip rejected at ingest
# ---------------------------------------------------------------------------

def test_zip_slip_rejected_before_pipeline(tmp_path):
    svc = _svc(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0")
    rec = svc.create_job("zip", {"zip_bytes": buf.getvalue()})
    assert rec.state is JobState.FAILED
