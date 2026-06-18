"""Server configuration, read once from the environment (plan §11).

Mirrors the existing ``components/llm/settings.py`` pattern: all env reads happen
here behind a frozen dataclass obtained via :func:`load_settings`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ServerSettings:
    """Immutable snapshot of server configuration."""

    data_dir: str
    """Root for job workspaces and the SQLite DB."""

    db_path: str
    """SQLite file path (``DATABASE_URL`` overrides for Postgres in M6)."""

    auth_mode: str
    """``none`` (dev) | ``apikey`` (shared-secret) | ``oidc`` (prod) — see plan §11."""

    api_key: str
    """Shared secret required on /api/* when ``auth_mode == "apikey"`` (M6)."""

    allow_self_approval: bool
    """Whether a job creator may approve their own gates."""

    data_retention_days: int
    """Job-workspace purge horizon."""


def load_settings() -> ServerSettings:
    data_dir = os.getenv("NGREACT_DATA_DIR", str(_PROJECT_ROOT / ".ngreact_data"))
    db_path = os.getenv("NGREACT_DB_PATH", str(Path(data_dir) / "ngreact.db"))
    return ServerSettings(
        data_dir=data_dir,
        db_path=db_path,
        auth_mode=os.getenv("AUTH_MODE", "none"),
        api_key=os.getenv("NGREACT_API_KEY", ""),
        allow_self_approval=os.getenv("ALLOW_SELF_APPROVAL", "true").strip().lower() == "true",
        data_retention_days=int(os.getenv("DATA_RETENTION_DAYS", "30")),
    )
