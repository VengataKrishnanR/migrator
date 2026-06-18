"""V3 ingestion layer — normalize any input into a Workspace + IngestionManifest.

Supported sources (plan §6.1): paste, file upload(s), zip archive, git repo.
Every adapter writes files under ``<workspace>/input/`` and returns an
:class:`~tools.workflow.models.IngestionManifest`. A shared profiler then detects
Angular markers and computes the file inventory; non-Angular input fails fast.

Security is mandatory for untrusted archives — see :mod:`tools.ingestion.security`
(zip-slip, symlink, size, file-count, and nesting guards).
"""
from __future__ import annotations

from .adapters import (
    IngestionError,
    ingest,
    ingest_files,
    ingest_git,
    ingest_paste,
    ingest_zip,
)
from .profiler import profile_workspace
from .workspace import Workspace

__all__ = [
    "IngestionError",
    "Workspace",
    "ingest",
    "ingest_paste",
    "ingest_files",
    "ingest_zip",
    "ingest_git",
    "profile_workspace",
]
