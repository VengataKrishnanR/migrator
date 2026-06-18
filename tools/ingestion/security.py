"""Hardening for untrusted ingestion input (plan §6.1 / §11).

Defends archive extraction against zip-slip path traversal, symlink escape,
decompression bombs, and excessive file counts/nesting. All limits are module
constants so they can be tuned from one place.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

# Limits (plan §6.1)
MAX_COMPRESSED_BYTES = 200 * 1024 * 1024       # 200 MB on the wire
MAX_INFLATED_BYTES = 1024 * 1024 * 1024        # 1 GB expanded
MAX_FILE_COUNT = 20_000
MAX_PATH_DEPTH = 40
MAX_NESTED_ZIP_DEPTH = 1                        # reject zips inside zips beyond this

#: Directories never worth ingesting — skipped at extraction time.
SKIP_DIRS = frozenset({"node_modules", "dist", ".git", ".angular", "coverage", ".cache"})


class UnsafeArchiveError(Exception):
    """Raised when an archive violates a security constraint."""


def _is_within(base: Path, target: Path) -> bool:
    """True if ``target`` resolves to a path inside ``base`` (no traversal escape)."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _skipped(member_name: str) -> bool:
    parts = Path(member_name).parts
    return any(p in SKIP_DIRS for p in parts)


def safe_extract_zip(zip_path: Path, dest: Path, _nesting: int = 0) -> tuple[int, int]:
    """Safely extract ``zip_path`` into ``dest``.

    Returns ``(files_written, total_inflated_bytes)``.

    Raises:
        UnsafeArchiveError: on zip-slip, symlink, oversize, too many files,
            excessive depth, or disallowed nested archives.
    """
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)

    if zip_path.stat().st_size > MAX_COMPRESSED_BYTES:
        raise UnsafeArchiveError(
            f"Archive exceeds {MAX_COMPRESSED_BYTES // (1024 * 1024)} MB compressed limit"
        )

    files_written = 0
    inflated = 0

    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILE_COUNT:
            raise UnsafeArchiveError(f"Archive has {len(infos)} entries (limit {MAX_FILE_COUNT})")

        for info in infos:
            name = info.filename
            if _skipped(name):
                continue
            if name.endswith("/"):
                continue  # directory entry — created implicitly below

            # Symlink guard: external_attr high bits encode unix mode; 0xA000 == symlink
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise UnsafeArchiveError(f"Symlink entry rejected: {name}")

            if len(Path(name).parts) > MAX_PATH_DEPTH:
                raise UnsafeArchiveError(f"Path too deep: {name}")

            target = (dest / name)
            if not _is_within(dest, target):
                raise UnsafeArchiveError(f"Zip-slip path traversal blocked: {name}")

            inflated += info.file_size
            if inflated > MAX_INFLATED_BYTES:
                raise UnsafeArchiveError(
                    f"Archive exceeds {MAX_INFLATED_BYTES // (1024 * 1024)} MB inflated limit"
                )

            # Nested archive policy
            if name.lower().endswith(".zip"):
                if _nesting >= MAX_NESTED_ZIP_DEPTH:
                    raise UnsafeArchiveError(f"Nested zip beyond allowed depth: {name}")

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            files_written += 1

    return files_written, inflated
