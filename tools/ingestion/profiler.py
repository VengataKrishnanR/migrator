"""Shared post-ingestion profiler — detect Angular and inventory the input.

Runs after every adapter. Computes file_count / total_bytes over the working
set (excluding build/dependency dirs), detects Angular markers, and finds the
project root (the directory containing angular.json or package.json). Non-Angular
input is flagged so the job can fail fast at the INGESTING state.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.workflow.models import IngestionManifest

from .security import SKIP_DIRS

_ANGULAR_FILE_MARKERS = (".component.ts", ".service.ts", ".module.ts", ".directive.ts")

#: Content signals — catch a pasted component/service whose filename lacks markers.
_ANGULAR_CONTENT_SIGNALS = (
    "@Component", "@Injectable", "@NgModule", "@Directive", "@Pipe", "@angular/",
)
_CONTENT_SCAN_BYTES = 4096


def _content_looks_angular(path: Path) -> bool:
    if path.suffix != ".ts":
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:_CONTENT_SCAN_BYTES]
    except OSError:
        return False
    return any(sig in head for sig in _ANGULAR_CONTENT_SIGNALS)


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        yield p


def _find_project_root(input_dir: Path) -> Path:
    """Return the dir containing angular.json (preferred) or package.json, else input_dir."""
    candidates_angular = sorted(input_dir.rglob("angular.json"), key=lambda p: len(p.parts))
    if candidates_angular:
        return candidates_angular[0].parent
    candidates_pkg = sorted(input_dir.rglob("package.json"), key=lambda p: len(p.parts))
    for pkg in candidates_pkg:
        if any(part in SKIP_DIRS for part in pkg.relative_to(input_dir).parts):
            continue
        return pkg.parent
    return input_dir


def _angular_version_from_pkg(project_root: Path) -> str | None:
    pkg = project_root / "package.json"
    if not pkg.exists():
        return None
    try:
        data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return None
    for section in ("dependencies", "devDependencies"):
        ver = data.get(section, {}).get("@angular/core")
        if ver:
            return str(ver)
    return None


def profile_workspace(input_dir: Path, manifest: IngestionManifest) -> IngestionManifest:
    """Populate file inventory + Angular detection on ``manifest`` in place."""
    input_dir = Path(input_dir)
    file_count = 0
    total_bytes = 0
    has_angular_files = False

    for p in _iter_files(input_dir):
        file_count += 1
        try:
            total_bytes += p.stat().st_size
        except OSError:
            pass
        if not has_angular_files:
            if p.name.endswith(_ANGULAR_FILE_MARKERS) or _content_looks_angular(p):
                has_angular_files = True

    project_root = _find_project_root(input_dir)
    angular_version = _angular_version_from_pkg(project_root)
    has_angular_json = (project_root / "angular.json").exists()
    has_angular_dep = angular_version is not None

    manifest.file_count = file_count
    manifest.total_bytes = total_bytes
    manifest.angular_version = angular_version
    manifest.project_root = str(project_root.relative_to(input_dir)) or "."
    manifest.is_angular = bool(has_angular_files or has_angular_json or has_angular_dep)

    if not manifest.is_angular:
        manifest.warnings.append(
            "No Angular markers found (no angular.json, no @angular/core, no *.component.ts). "
            "Input does not look like an Angular project."
        )
    return manifest
