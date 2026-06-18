"""Per-job filesystem workspace.

Layout (plan §7):
    <data_dir>/jobs/<job_id>/
        input/        ingested Angular source (read-only after ingestion)
        artifacts/    JSON/markdown artifact payloads (pointers in the DB)
        output/       generated React tree (assembled after Gate B)
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Workspace:
    """Filesystem locations for one job. All paths are absolute."""

    job_id: str
    root: Path

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    def ensure(self) -> "Workspace":
        for d in (self.input_dir, self.artifacts_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self

    def destroy(self) -> None:
        """Remove the entire workspace (retention purge / cancellation cleanup)."""
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)

    @classmethod
    def for_job(cls, job_id: str, data_dir: str | Path) -> "Workspace":
        root = Path(data_dir) / "jobs" / job_id
        return cls(job_id=job_id, root=root.resolve()).ensure()
