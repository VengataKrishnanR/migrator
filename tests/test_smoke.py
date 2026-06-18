"""Smoke tests — pure Python sanity checks, zero ADK dependency.

These must always pass regardless of the venv state (no compiled extensions
required). They verify that core modules import cleanly, basic objects
instantiate, and fundamental utilities return correct values.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


# ── Import / module health ────────────────────────────────────────────────────

def test_json_utils_importable():
    from server.json_utils import extract_json, AgentInvocationError
    assert callable(extract_json)
    assert issubclass(AgentInvocationError, RuntimeError)


def test_state_machine_importable():
    from tools.workflow.state_machine import MigrationJob, IllegalTransitionError, TRANSITIONS
    assert isinstance(TRANSITIONS, dict)
    assert len(TRANSITIONS) > 0


def test_workflow_models_importable():
    from tools.workflow.models import JobState, Gate, ApprovalDecision, JobOptions, JobRecord
    assert len(list(JobState)) >= 13
    assert Gate.PLAN.value == "plan"
    assert Gate.FINAL.value == "final"


def test_ingestion_adapters_importable():
    from tools.ingestion import ingest_paste, ingest_files, ingest_zip
    assert callable(ingest_paste)
    assert callable(ingest_files)
    assert callable(ingest_zip)


def test_artifact_schemas_importable():
    from server.artifact_schemas import (
        validate_analysis, validate_plan, validate_risk, validate_validation,
    )
    assert callable(validate_analysis)
    assert callable(validate_plan)


def test_stub_phase_runner_instantiates():
    from server.runners import StubPhaseRunner
    runner = StubPhaseRunner()
    assert hasattr(runner, "run")


def test_job_service_importable():
    from server.service import JobService, ApprovalRequiredError
    assert callable(JobService)
    assert issubclass(ApprovalRequiredError, RuntimeError)


# ── Functional sanity ─────────────────────────────────────────────────────────

def test_migration_job_starts_at_created():
    from tools.workflow.models import JobRecord, JobState
    from tools.workflow.state_machine import MigrationJob
    job = MigrationJob(JobRecord())
    assert job.state is JobState.CREATED
    assert not job.is_terminal


def test_extract_json_returns_correct_value():
    from server.json_utils import extract_json
    assert extract_json('{"result": 42}')["result"] == 42
    assert extract_json("prefix\n```json\n{\"ok\": true}\n```\nend")["ok"] is True


def test_job_store_creates_and_retrieves(tmp_path):
    from tools.workflow.models import JobRecord, JobState
    from tools.workflow.store import JobStore
    store = JobStore(str(tmp_path / "smoke.sqlite"))
    rec = JobRecord(source_type="paste")
    store.save_job(rec)
    fetched = store.get_job(rec.id)
    assert fetched is not None
    assert fetched.id == rec.id
    assert fetched.state is JobState.CREATED
