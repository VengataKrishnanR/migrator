"""V3 server layer — FastAPI app, JobService, and phase runners.

The JobService is the queue-agnostic orchestration facade (plan §8): it owns the
MigrationJob lifecycle, drives phase runners, enforces gates, and is resumable
after a process restart. The FastAPI app in :mod:`server.app` is a thin HTTP
shell over it; ``server.service`` has no web dependency and is unit-testable
without FastAPI installed.
"""
from __future__ import annotations

from .config import ServerSettings, load_settings
from .runners import PhaseRunner, StubPhaseRunner
from .service import JobService

__all__ = [
    "ServerSettings",
    "load_settings",
    "JobService",
    "PhaseRunner",
    "StubPhaseRunner",
    "build_default_runner",
]


def build_default_runner(fallback=None):
    """Production runner: real Phase 1 agents, fallback (stub) for phases 2–4.

    Imported lazily so the workflow/ingestion layers stay importable without
    google-adk (e.g. in environments that only run the offline core tests).
    """
    from .phase_runner import RealPhaseRunner
    return RealPhaseRunner(fallback=fallback)
