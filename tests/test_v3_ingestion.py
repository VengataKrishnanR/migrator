"""M1 tests — ingestion adapters, Angular detection, and archive security."""
from __future__ import annotations

import io
import zipfile

import pytest

pytestmark = pytest.mark.integration

from tools.ingestion import Workspace, ingest_files, ingest_paste, ingest_zip
from tools.ingestion.adapters import IngestionError
from tools.ingestion.security import UnsafeArchiveError, safe_extract_zip


def _ws(tmp_path):
    return Workspace.for_job("job_test", tmp_path)


# -- paste -----------------------------------------------------------------

def test_paste_single_file(tmp_path):
    m = ingest_paste("@Component({}) export class FooComponent {}", _ws(tmp_path))
    assert m.source_type == "paste"
    assert m.file_count == 1
    assert m.is_angular  # FooComponent + @Component


def test_paste_multifile_markers(tmp_path):
    content = (
        "// file: src/app/user.component.ts\n"
        "export class UserComponent {}\n"
        "// file: src/app/user.service.ts\n"
        "export class UserService {}\n"
    )
    m = ingest_paste(content, _ws(tmp_path))
    assert m.file_count == 2
    assert m.is_angular


def test_paste_empty_rejected(tmp_path):
    with pytest.raises(IngestionError):
        ingest_paste("   ", _ws(tmp_path))


def test_paste_path_traversal_rejected(tmp_path):
    with pytest.raises(IngestionError):
        ingest_paste("// file: ../../etc/passwd\nx", _ws(tmp_path))


# -- files -----------------------------------------------------------------

def test_files_with_package_json(tmp_path):
    files = [
        {"path": "package.json", "content": '{"dependencies":{"@angular/core":"17.0.0"}}'},
        {"path": "src/app/app.component.ts", "content": "export class AppComponent {}"},
    ]
    m = ingest_files(files, _ws(tmp_path))
    assert m.is_angular
    assert m.angular_version == "17.0.0"
    assert m.file_count == 2


def test_files_non_angular_flagged(tmp_path):
    files = [{"path": "main.py", "content": "print('hello')"}]
    m = ingest_files(files, _ws(tmp_path))
    assert not m.is_angular
    assert any("Angular" in w for w in m.warnings)


# -- zip + security --------------------------------------------------------

def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_zip_happy_path(tmp_path):
    zb = _make_zip({
        "proj/angular.json": b"{}",
        "proj/src/app/app.component.ts": b"export class AppComponent {}",
    })
    m = ingest_zip(zb, _ws(tmp_path))
    assert m.is_angular
    assert m.file_count == 2
    assert m.project_root.endswith("proj")


def test_zip_skips_node_modules(tmp_path):
    zb = _make_zip({
        "proj/angular.json": b"{}",
        "proj/node_modules/left-pad/index.js": b"module.exports = 1",
    })
    m = ingest_zip(zb, _ws(tmp_path))
    assert m.file_count == 1  # node_modules skipped


def test_zip_slip_blocked(tmp_path):
    zb = _make_zip({"../../evil.txt": b"pwned"})
    with pytest.raises(IngestionError):
        ingest_zip(zb, _ws(tmp_path))


def test_zip_slip_blocked_at_security_layer(tmp_path):
    import tempfile
    from pathlib import Path
    zb = _make_zip({"../escape.txt": b"x"})
    f = Path(tempfile.mktemp(suffix=".zip"))
    f.write_bytes(zb)
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(f, tmp_path / "dest")


def test_zip_too_many_files(tmp_path, monkeypatch):
    import tools.ingestion.security as sec
    monkeypatch.setattr(sec, "MAX_FILE_COUNT", 3)
    zb = _make_zip({f"proj/f{i}.ts": b"x" for i in range(5)})
    with pytest.raises(IngestionError):
        ingest_zip(zb, _ws(tmp_path))
