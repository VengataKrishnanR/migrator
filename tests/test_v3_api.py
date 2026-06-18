"""M1 tests — FastAPI HTTP shell (routing, validation, approval round-trip).

Background execution is disabled (NGREACT_DISABLE_BG=1) so jobs are driven
deterministically via /resume and approval endpoints inside the request.
"""
from __future__ import annotations

import importlib
import os

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

pytestmark = pytest.mark.api


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NGREACT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NGREACT_DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("NGREACT_DISABLE_BG", "1")
    monkeypatch.setenv("NGREACT_LLM_MODE", "stub")  # real Phase 1 runner, stub model
    import server.app as app_module
    importlib.reload(app_module)  # pick up tmp env in module-level settings/service
    return TestClient(app_module.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_bad_source_type_400(client):
    r = client.post("/api/jobs", json={"source": {"type": "ftp"}})
    assert r.status_code == 400


def test_missing_job_404(client):
    assert client.get("/api/jobs/job_nope").status_code == 404


def test_full_flow_via_gates(client):
    # create (no background run) → job sits at phase1_running
    r = client.post("/api/jobs", json={
        "source": {"type": "paste", "content": "@Component({}) export class FooComponent {}"},
        "options": {"auto_approve_plan": False},
        "created_by": "alice",
    })
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert r.json()["state"] == "phase1_running"

    # drive synchronously → parks at Gate A
    r = client.post(f"/api/jobs/{job_id}/resume")
    assert r.json()["state"] == "awaiting_plan_approval"

    # approve Gate A → advances and parks at Gate B
    r = client.post(f"/api/jobs/{job_id}/approvals/plan",
                    json={"decision": "approve", "actor": "alice"})
    assert r.json()["state"] == "awaiting_final_approval"

    # approve Gate B → integrates → completed
    r = client.post(f"/api/jobs/{job_id}/approvals/final",
                    json={"decision": "approve", "actor": "alice"})
    assert r.json()["state"] == "completed"

    # artifacts present
    arts = client.get(f"/api/jobs/{job_id}/artifacts").json()["artifacts"]
    keys = {a["key"] for a in arts}
    assert "ingestion_manifest" in keys
    assert "phase1_report" in keys


def test_revise_rejected_without_comments(client):
    r = client.post("/api/jobs", json={
        "source": {"type": "paste", "content": "@Component({}) export class FooComponent {}"},
        "options": {"auto_approve_plan": False}})
    job_id = r.json()["job_id"]
    client.post(f"/api/jobs/{job_id}/resume")
    r = client.post(f"/api/jobs/{job_id}/approvals/plan",
                    json={"decision": "revise", "actor": "alice"})
    assert r.status_code == 409  # revision requires comments
