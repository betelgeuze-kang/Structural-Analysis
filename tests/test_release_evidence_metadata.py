from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from release_evidence_metadata import directory_sha256  # noqa: E402


def test_directory_sha256_ignores_python_cache_artifacts(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    baseline = directory_sha256(source_dir)

    cache_dir = source_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "module.cpython-310.pyc").write_bytes(b"cache")
    (source_dir / ".pytest_cache").mkdir()
    (source_dir / ".pytest_cache" / "README.md").write_text("cache\n", encoding="utf-8")

    assert directory_sha256(source_dir) == baseline
