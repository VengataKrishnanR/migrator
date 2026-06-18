"""Ingestion adapters — paste, files, zip, git → Workspace + IngestionManifest.

Each adapter writes the normalized source under ``workspace.input_dir`` and
returns a manifest (profiled by :func:`profile_workspace`). The public
:func:`ingest` dispatches on ``source_type``.

Git credentials are header-injected at clone time and never written to disk or
logs (plan §6.1 / §11).
"""
from __future__ import annotations

import base64
import re
import subprocess
import tempfile
from pathlib import Path

from tools.workflow.models import IngestionManifest

from .profiler import profile_workspace
from .security import safe_extract_zip
from .workspace import Workspace

# Matches "// file: src/app/foo.component.ts" or "<!-- file: ... -->" style markers
_FILE_MARKER = re.compile(r"^\s*(?://|#|<!--)\s*file:\s*(?P<path>[^\s>]+)", re.IGNORECASE)


class IngestionError(Exception):
    """Raised when ingestion fails (bad input, clone failure, unsafe archive)."""


def _safe_rel(path_str: str) -> Path:
    """Sanitize a user-supplied relative path: strip leading slashes, reject traversal."""
    p = Path(path_str.replace("\\", "/").lstrip("/"))
    if ".." in p.parts or p.is_absolute():
        raise IngestionError(f"Illegal path in input: {path_str!r}")
    return p


# ---------------------------------------------------------------------------
# paste
# ---------------------------------------------------------------------------

def ingest_paste(content: str, workspace: Workspace) -> IngestionManifest:
    """Ingest pasted source. Splits on ``// file: <path>`` markers when present;
    otherwise treats the whole blob as a single ``component.ts``."""
    if not content.strip():
        raise IngestionError("Pasted content is empty")

    input_dir = workspace.input_dir
    manifest = IngestionManifest(source_type="paste")

    # Multi-file paste?
    if _FILE_MARKER.search(content):
        current_path: Path | None = None
        buffer: list[str] = []

        def _flush():
            if current_path is not None:
                target = input_dir / current_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("\n".join(buffer), encoding="utf-8")

        for line in content.splitlines():
            m = _FILE_MARKER.match(line)
            if m:
                _flush()
                current_path = _safe_rel(m.group("path"))
                buffer = []
            else:
                buffer.append(line)
        _flush()
    else:
        target = input_dir / "component.ts"
        target.write_text(content, encoding="utf-8")

    return profile_workspace(input_dir, manifest)


# ---------------------------------------------------------------------------
# files (multipart upload)
# ---------------------------------------------------------------------------

def ingest_files(files: list[dict], workspace: Workspace) -> IngestionManifest:
    """Ingest uploaded files. Each entry: ``{"path": str, "content": bytes|str}``.
    ``content`` may also be ``{"b64": "..."}`` for JSON transport of binary."""
    if not files:
        raise IngestionError("No files provided")

    input_dir = workspace.input_dir
    manifest = IngestionManifest(source_type="files")

    for entry in files:
        rel = _safe_rel(entry["path"])
        content = entry["content"]
        if isinstance(content, dict) and "b64" in content:
            data = base64.b64decode(content["b64"])
        elif isinstance(content, str):
            data = content.encode("utf-8")
        else:
            data = bytes(content)
        target = input_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    return profile_workspace(input_dir, manifest)


# ---------------------------------------------------------------------------
# zip
# ---------------------------------------------------------------------------

def ingest_zip(zip_bytes: bytes | None, workspace: Workspace,
               zip_path: str | None = None) -> IngestionManifest:
    """Ingest a zip archive (bytes or path). Extraction is hardened against
    zip-slip, symlinks, decompression bombs, and nested archives."""
    manifest = IngestionManifest(source_type="zip")

    tmp: Path | None = None
    try:
        if zip_path is not None:
            src = Path(zip_path)
            if not src.exists():
                raise IngestionError(f"Zip not found: {zip_path}")
        elif zip_bytes is not None:
            fd = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            fd.write(zip_bytes)
            fd.close()
            tmp = Path(fd.name)
            src = tmp
        else:
            raise IngestionError("ingest_zip requires zip_bytes or zip_path")

        from .security import UnsafeArchiveError
        try:
            count, _ = safe_extract_zip(src, workspace.input_dir)
        except UnsafeArchiveError as e:
            raise IngestionError(str(e)) from e

        if count == 0:
            manifest.warnings.append("Archive contained no usable files after filtering")
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)

    return profile_workspace(workspace.input_dir, manifest)


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 300) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as e:
        raise IngestionError("git executable not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise IngestionError(f"git operation timed out after {timeout}s") from e
    if proc.returncode != 0:
        # Never echo the token if it leaked into stderr — scrub bearer-ish strings
        err = re.sub(r"(https://)[^@/\s]+@", r"\1***@", proc.stderr.strip())
        raise IngestionError(f"git {args[0]} failed: {err}")
    return proc.stdout.strip()


def ingest_git(repo_url: str, workspace: Workspace, branch: str | None = None,
               token: str | None = None) -> IngestionManifest:
    """Shallow-clone a git repo into the workspace input dir.

    Records remote_url / base_branch / base_commit_sha on the manifest — required
    later to push migration output back (plan §6.2). The token is injected into a
    one-shot credential header, never persisted to disk or the manifest."""
    manifest = IngestionManifest(source_type="git", remote_url=repo_url)
    input_dir = workspace.input_dir

    clone_args = ["clone", "--depth", "1"]
    if branch:
        clone_args += ["--branch", branch]

    # Inject auth via -c http.extraHeader so the token never lands in remote URL,
    # reflog, or on-disk config.
    config_args: list[str] = []
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        config_args = ["-c", f"http.extraHeader=Authorization: Basic {basic}"]

    _run_git([*config_args, *clone_args, repo_url, str(input_dir)])

    manifest.base_branch = branch or _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=input_dir)
    manifest.base_commit_sha = _run_git(["rev-parse", "HEAD"], cwd=input_dir)

    return profile_workspace(input_dir, manifest)


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------

def ingest(source_type: str, payload: dict, workspace: Workspace) -> IngestionManifest:
    """Dispatch to the adapter for ``source_type`` with a typed ``payload``.

    payload by type:
      paste : {"content": str}
      files : {"files": [{"path", "content"}]}
      zip   : {"zip_bytes": bytes} | {"zip_path": str}
      git   : {"repo_url": str, "branch"?: str, "token"?: str}
    """
    if source_type == "paste":
        return ingest_paste(payload["content"], workspace)
    if source_type == "files":
        return ingest_files(payload["files"], workspace)
    if source_type == "zip":
        return ingest_zip(payload.get("zip_bytes"), workspace, zip_path=payload.get("zip_path"))
    if source_type == "git":
        return ingest_git(payload["repo_url"], workspace,
                          branch=payload.get("branch"), token=payload.get("token"))
    raise IngestionError(f"Unknown source_type: {source_type!r}")
