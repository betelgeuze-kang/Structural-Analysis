from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_open_data_external_artifacts_manifest.py"
SPEC = importlib.util.spec_from_file_location("verify_open_data_external_artifacts_manifest", SCRIPT_PATH)
assert SPEC is not None
verify_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verify_manifest)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest(path: str = "implementation/phase1/open_data/sample.bin", data: bytes = b"abc") -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifacts": [
            {
                "path": path,
                "bytes": len(data),
                "sha256": _sha256(data),
                "source_family": "fixture",
                "disposition": "externalize",
            }
        ],
    }


def test_structure_validation_accepts_clean_manifest() -> None:
    errors, rows = verify_manifest.validate_manifest_structure(_manifest())

    assert errors == []
    assert len(rows) == 1


def test_structure_validation_rejects_bad_paths_and_digests() -> None:
    manifest = _manifest(path="../secret.bin")
    manifest["artifacts"][0]["sha256"] = "bad"

    errors, rows = verify_manifest.validate_manifest_structure(manifest)

    assert errors == [
        "artifacts[0].path must be a clean relative path",
        "artifacts[0].sha256 must be a lowercase 64-char hex digest",
    ]
    assert rows == []


def test_require_artifacts_checks_size_and_sha(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data = b"abc"
    artifact = tmp_path / "implementation" / "phase1" / "open_data" / "sample.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(data)

    assert verify_manifest.validate_manifest(_manifest(data=data), require_artifacts=True) == []

    broken = _manifest(data=data)
    broken["artifacts"][0]["bytes"] = len(data) + 1
    assert verify_manifest.validate_manifest(broken, require_artifacts=True) == [
        "bytes mismatch for implementation/phase1/open_data/sample.bin: manifest=4 actual=3"
    ]


def test_cli_structure_only(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--manifest",
            str(manifest_path),
            "--structure-only",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout == "Open-data external artifact manifest OK (structure only)\n"
    assert proc.stderr == ""
