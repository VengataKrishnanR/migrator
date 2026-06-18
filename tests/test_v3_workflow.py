"""M1 tests — state machine, store, audit, resume scaffolding."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

from tools.workflow import (
    IllegalTransitionError,
    JobRecord,
    JobState,
    MigrationJob,
)
from tools.workflow.models import (
    ApprovalDecision,
    ApprovalRecord,
    Gate,
    JobOptions,
    StageRecord,
    StageStatus,
)
from tools.workflow.store import JobStore


# -- state machine ---------------------------------------------------------

def test_happy_path_transitions():
    job = MigrationJob(JobRecord(source_type="git"))
    seq = [
        JobState.INGESTING, JobState.PHASE1_RUNNING, JobState.AWAITING_PLAN_APPROVAL,
        JobState.PHASE2_RUNNING, JobState.PHASE3_RUNNING, JobState.PHASE4_RUNNING,
        JobState.AWAITING_FINAL_APPROVAL, JobState.INTEGRATING, JobState.COMPLETED,
    ]
    for s in seq:
        job.transition(s, actor="worker")
    assert job.state is JobState.COMPLETED
    assert job.is_terminal


def test_illegal_transition_raises():
    job = MigrationJob(JobRecord())
    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.PHASE2_RUNNING, actor="worker")  # skips ingestion


def test_no_transition_out_of_terminal():
    job = MigrationJob(JobRecord())
    job.transition(JobState.INGESTING, actor="w")
    job.fail(actor="w", reason="boom")
    assert job.state is JobState.FAILED
    with pytest.raises(IllegalTransitionError):
        job.transition(JobState.PHASE1_RUNNING, actor="w")


def test_revise_loop_back_to_phase1():
    job = MigrationJob(JobRecord())
    for s in (JobState.INGESTING, JobState.PHASE1_RUNNING, JobState.AWAITING_PLAN_APPROVAL):
        job.transition(s, actor="w")
    # Gate A "revise" sends back to Phase 1
    job.transition(JobState.PHASE1_RUNNING, actor="approver", reason="add risk detail")
    assert job.state is JobState.PHASE1_RUNNING


def test_cancel_from_any_nonterminal():
    job = MigrationJob(JobRecord())
    job.transition(JobState.INGESTING, actor="w")
    job.cancel(actor="user")
    assert job.state is JobState.CANCELLED


def test_fail_records_error_text():
    job = MigrationJob(JobRecord())
    job.transition(JobState.INGESTING, actor="w")
    job.fail(actor="w", reason="clone failed")
    assert job.record.error_text == "clone failed"


# -- store + audit ---------------------------------------------------------

def test_store_roundtrip_and_audit():
    store = JobStore(":memory:")
    rec = JobRecord(source_type="zip", options=JobOptions(target="git", create_pr=True))
    job = MigrationJob(rec, store=store)
    store.save_job(rec)

    job.transition(JobState.INGESTING, actor="worker", reason="start")
    job.transition(JobState.PHASE1_RUNNING, actor="worker")

    fetched = store.get_job(rec.id)
    assert fetched is not None
    assert fetched.state is JobState.PHASE1_RUNNING
    assert fetched.options.target == "git"
    assert fetched.options.create_pr is True

    audit = store.get_audit(rec.id)
    assert len(audit) == 2
    assert audit[0].detail["to"] == "ingesting"
    assert audit[0].detail["reason"] == "start"


def test_completed_stages_drive_resume():
    store = JobStore(":memory:")
    rec = JobRecord()
    store.save_job(rec)
    store.record_stage(rec.id, 2, StageRecord(stage="transformer", agent="transformer_agent_v3",
                                              chunk_id="UserList_0", status=StageStatus.COMPLETED))
    store.record_stage(rec.id, 2, StageRecord(stage="transformer", agent="transformer_agent_v3",
                                              chunk_id="UserForm_1", status=StageStatus.RUNNING))
    done = store.completed_stages(rec.id, 2)
    assert "transformer:UserList_0" in done
    assert "transformer:UserForm_1" not in done   # still running, must resume


def test_revision_count_bounds_loop():
    store = JobStore(":memory:")
    rec = JobRecord()
    store.save_job(rec)
    for _ in range(2):
        store.record_approval(rec.id, ApprovalRecord(
            gate=Gate.PLAN, decision=ApprovalDecision.REVISE,
            decided_by="approver", decided_at=0.0, comments="again"))
    assert store.revision_count(rec.id, Gate.PLAN) == 2
    assert store.revision_count(rec.id, Gate.FINAL) == 0


def test_list_jobs_filter_by_state():
    store = JobStore(":memory:")
    a = JobRecord(source_type="git"); store.save_job(a)
    b = JobRecord(source_type="zip", state=JobState.COMPLETED); store.save_job(b)
    assert {j.id for j in store.list_jobs(state=JobState.COMPLETED)} == {b.id}
    assert len(store.list_jobs()) == 2
