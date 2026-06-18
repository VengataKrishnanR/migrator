"""V3 deterministic helper functions for migration pipeline.

Provides fast, non-LLM tools for analysis, parsing, and validation that
agents can call via FunctionTool.
"""
from __future__ import annotations

from typing import Any


def analyze_project_structure(project_path: str) -> dict[str, Any]:
    """Scan project directory and build file inventory.

    Args:
        project_path: Root path of Angular project

    Returns:
        Dict with file counts, directory structure, package.json info
    """
    import json
    from pathlib import Path

    root = Path(project_path)

    if not root.exists():
        return {"error": f"Project path {project_path} does not exist"}

    # Count files by type
    files: dict[str, list[str]] = {
        "components": [],
        "services": [],
        "modules": [],
        "guards": [],
        "pipes": [],
        "directives": [],
    }

    for pattern, key in [
        ("**/*.component.ts", "components"),
        ("**/*.service.ts", "services"),
        ("**/*.module.ts", "modules"),
        ("**/*.guard.ts", "guards"),
        ("**/*.pipe.ts", "pipes"),
        ("**/*.directive.ts", "directives"),
    ]:
        files[key].extend([str(p.relative_to(root)) for p in root.glob(pattern)])

    # Read package.json
    package_json_path = root / "package.json"
    angular_version = ""
    if package_json_path.exists():
        package_data = json.loads(package_json_path.read_text(encoding="utf-8"))
        deps = package_data.get("dependencies", {})
        angular_version = deps.get("@angular/core", "unknown")

    return {
        "project_path": str(root),
        "angular_version": angular_version,
        "file_counts": {k: len(v) for k, v in files.items()},
        "files": files,
        "total_files": sum(len(v) for v in files.values()),
    }


def estimate_migration_complexity(analysis_data: dict) -> dict[str, Any]:
    """Calculate complexity score for migration.

    Args:
        analysis_data: Output from analyzer_agent (AnalysisReport serialized)

    Returns:
        Dict with complexity score and factors
    """
    complexity = 0.0
    factors = []

    # Component count
    component_count = len(analysis_data.get("components", []))
    if component_count > 50:
        complexity += 0.3
        factors.append(f"{component_count} components (large project)")
    elif component_count > 20:
        complexity += 0.15
        factors.append(f"{component_count} components (medium project)")

    # Forms complexity
    forms_count = sum(
        1 for c in analysis_data.get("components", []) if c.get("has_forms")
    )
    if forms_count > 0:
        complexity += min(forms_count * 0.05, 0.25)
        factors.append(f"{forms_count} components with forms")

    # Custom directives (high complexity)
    directives = len(analysis_data.get("directives", []))
    if directives > 0:
        complexity += directives * 0.1
        factors.append(f"{directives} custom directives (no React equivalent)")

    # Lifecycle hooks
    total_hooks = sum(
        len(c.get("lifecycle_hooks", []))
        for c in analysis_data.get("components", [])
    )
    if total_hooks > 50:
        complexity += 0.2
        factors.append(f"{total_hooks} lifecycle hooks")

    return {
        "complexity_score": min(complexity, 1.0),
        "factors": factors,
        "recommendation": (
            "incremental" if complexity > 0.6 else "big-bang" if complexity < 0.3 else "hybrid"
        ),
    }


def validate_chunk_dependencies(chunks: list[dict]) -> dict[str, Any]:
    """Verify chunk dependency ordering is valid (no cycles).

    Args:
        chunks: List of MigrationChunk objects (serialized)

    Returns:
        Dict with validation status and cycle info
    """
    # Build adjacency list
    deps: dict[str, set[str]] = {}
    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        deps[chunk_id] = set(chunk.get("dependencies", []))

    # Detect cycles using DFS
    visited = set()
    rec_stack = set()
    cycles = []

    def has_cycle(node: str, path: list[str]) -> bool:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in deps.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor, path):
                    return True
            elif neighbor in rec_stack:
                # Cycle detected
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])
                return True

        path.pop()
        rec_stack.remove(node)
        return False

    for chunk_id in deps:
        if chunk_id not in visited:
            has_cycle(chunk_id, [])

    return {
        "valid": len(cycles) == 0,
        "cycles": cycles,
        "message": (
            "No cycles detected"
            if not cycles
            else f"{len(cycles)} dependency cycles found"
        ),
    }


def read_angular_file(file_path: str) -> dict[str, Any]:
    """Read a single Angular source file from disk.

    Use this to retrieve the contents of a specific Angular file when doing
    project-path migration. Call for each file returned by analyze_project_structure.

    Args:
        file_path: Absolute or relative path to the Angular TypeScript file.

    Returns:
        Dict with 'file_path', 'content', and 'size_chars', or 'error' on failure.
    """
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    if not path.is_file():
        return {"error": f"Not a file: {file_path}"}

    _MAX = 150_000
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Failed to read {file_path}: {e}"}

    if len(content) > _MAX:
        content = content[:_MAX]
        truncated = True
    else:
        truncated = False

    return {
        "file_path": str(path),
        "content": content,
        "size_chars": len(content),
        "truncated": truncated,
    }


def _find_angular_root(extracted_dir: "Path") -> "Path":
    """Locate the real Angular project root inside an extracted/cloned tree.

    Zips and repos often wrap the project in a top-level folder. Prefer the
    directory that contains angular.json or package.json; otherwise fall back
    to the directory holding the most *.component.ts files.
    """
    from pathlib import Path

    # 1. Directory containing angular.json (most authoritative)
    for marker in ("angular.json", "package.json"):
        hits = sorted(extracted_dir.rglob(marker), key=lambda p: len(p.parts))
        if hits:
            return hits[0].parent

    # 2. Directory with the most component files
    counts: dict[Path, int] = {}
    for comp in extracted_dir.rglob("*.component.ts"):
        counts[comp.parent] = counts.get(comp.parent, 0) + 1
    if counts:
        # Walk up to a sensible root: use the shallowest common-ish parent
        best = max(counts, key=counts.get)
        return best

    # 3. Nothing found — return as-is
    return extracted_dir


def ingest_zip(zip_path: str) -> dict[str, Any]:
    """Extract a local Angular project .zip and inventory its files.

    Use this when the user provides a path to a .zip archive of an Angular
    project (the "upload" flow). Extracts to a temp directory, locates the
    Angular project root, and returns the same inventory shape as
    analyze_project_structure plus the extracted project_path so the rest of
    the pipeline can read individual files with read_angular_file.

    Args:
        zip_path: Absolute or relative path to a .zip file on disk.

    Returns:
        Dict with 'project_path' (extracted root), file inventory, and
        'source': 'zip'. Returns {'error': ...} on failure.
    """
    import tempfile
    import zipfile
    from pathlib import Path

    src = Path(zip_path)
    if not src.exists():
        return {"error": f"Zip not found: {zip_path}"}
    if not zipfile.is_zipfile(src):
        return {"error": f"Not a valid zip archive: {zip_path}"}

    dest = Path(tempfile.mkdtemp(prefix="ngreact_zip_"))
    try:
        with zipfile.ZipFile(src) as zf:
            # Guard against path traversal (zip-slip)
            for member in zf.namelist():
                target = (dest / member).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    return {"error": f"Unsafe path in zip: {member}"}
            zf.extractall(dest)
    except Exception as e:
        return {"error": f"Failed to extract {zip_path}: {e}"}

    root = _find_angular_root(dest)
    inventory = analyze_project_structure(str(root))
    if "error" in inventory:
        return inventory
    inventory["source"] = "zip"
    inventory["archive"] = str(src)
    return inventory


def clone_git_repo(repo_url: str, branch: str = "") -> dict[str, Any]:
    """Clone a git repository of an Angular project and inventory its files.

    Use this when the user provides a git URL (https or ssh). Performs a
    shallow clone into a temp directory, locates the Angular project root,
    and returns the same inventory shape as analyze_project_structure plus
    the cloned project_path so the pipeline can read files with
    read_angular_file.

    Args:
        repo_url: Git URL, e.g. https://github.com/org/repo.git
        branch:   Optional branch/tag to clone. Empty = default branch.

    Returns:
        Dict with 'project_path' (clone root), file inventory, and
        'source': 'git'. Returns {'error': ...} on failure.
    """
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    if not (repo_url.startswith(("http://", "https://", "git@", "ssh://"))):
        return {"error": f"Not a valid git URL: {repo_url}"}

    dest = Path(tempfile.mkdtemp(prefix="ngreact_git_"))

    # Strategy 1 — system git (fastest, supports auth/ssh). Used when available.
    if shutil.which("git") is not None:
        cmd = ["git", "clone", "--depth", "1"]
        if branch.strip():
            cmd += ["--branch", branch.strip()]
        cmd += [repo_url, str(dest)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return {"error": f"git clone timed out after 180s: {repo_url}"}
        except Exception as e:
            return {"error": f"git clone failed: {e}"}
        if proc.returncode != 0:
            return {"error": f"git clone failed: {proc.stderr.strip()[:400]}"}

    # Strategy 2 — dulwich (pure-Python). Works without system git for HTTP(S).
    else:
        if repo_url.startswith(("git@", "ssh://")):
            return {
                "error": "SSH git URLs require system git, which is not installed. "
                "Use an https:// URL, or install Git for Windows."
            }
        try:
            import io
            from dulwich import porcelain
        except ImportError:
            return {
                "error": "Neither system git nor dulwich is available. "
                "Install Git for Windows, or run: pip install dulwich"
            }
        try:
            # Silence dulwich's server-progress relay (it floods stderr otherwise).
            _sink = io.BytesIO()
            porcelain.clone(
                repo_url,
                str(dest),
                depth=1,
                branch=branch.strip().encode() if branch.strip() else None,
                errstream=_sink,
            )
        except Exception as e:
            return {"error": f"git clone (dulwich) failed: {str(e)[:400]}"}

    root = _find_angular_root(dest)
    inventory = analyze_project_structure(str(root))
    if "error" in inventory:
        return inventory
    inventory["source"] = "git"
    inventory["repo_url"] = repo_url
    if branch.strip():
        inventory["branch"] = branch.strip()
    return inventory
