"""M6 tests — optional API-key authentication on the API surface.

AUTH_MODE=apikey requires every /api/* call (except /api/health) to present the
shared secret via `X-API-Key` or `Authorization: Bearer`. AUTH_MODE=none (the
default the other tests run under) leaves everything open.
"""
from __future__ import annotations

import pytest

pytest.importorskip("google.adk")
pytest.importorskip("fastapi")

pytestmark = pytest.mark.api

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client_apikey(monkeypatch):
    import server.app as appmod
    from server.config import ServerSettings
    monkeypatch.setattr(appmod, "settings", ServerSettings(
        data_dir=appmod.settings.data_dir, db_path=appmod.settings.db_path,
        auth_mode="apikey", api_key="secret123",
        allow_self_approval=True, data_retention_days=30))
    return TestClient(appmod.app)


def test_health_is_open_without_key(client_apikey):
    assert client_apikey.get("/api/health").status_code == 200


def test_protected_route_requires_key(client_apikey):
    assert client_apikey.get("/api/jobs").status_code == 401


def test_x_api_key_grants_access(client_apikey):
    r = client_apikey.get("/api/jobs", headers={"X-API-Key": "secret123"})
    assert r.status_code == 200


def test_bearer_token_grants_access(client_apikey):
    r = client_apikey.get("/api/jobs", headers={"Authorization": "Bearer secret123"})
    assert r.status_code == 200


def test_wrong_key_rejected(client_apikey):
    assert client_apikey.get("/api/jobs", headers={"X-API-Key": "nope"}).status_code == 401


def test_static_ui_stays_open(client_apikey):
    # The UI shell is not under /api/ — it must remain reachable for the browser.
    assert client_apikey.get("/").status_code == 200
