from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "verify_release_artifacts_manifest.py"
SPEC = importlib.util.spec_from_file_location("verify_release_artifacts_manifest", SCRIPT_PATH)
assert SPEC is not None
verify_release_artifacts_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verify_release_artifacts_manifest)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest(*, asset_name: str = "bundle.zip", local_path: str = "implementation/phase1/release/bundle.zip", payload: bytes = b"fresh") -> dict:
    return {
        "schema_version": verify_release_artifacts_manifest.SCHEMA_VERSION,
        "release_tag": "test-release",
        "artifacts": [
            {
                "asset_name": asset_name,
                "local_path": local_path,
                "sha256": _sha256(payload),
                "bytes": len(payload),
                "required": True,
            }
        ],
    }


def test_structure_only_passes_with_stale_local_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact_path = tmp_path / "implementation" / "phase1" / "release" / "bundle.zip"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"stale-local")

    errors = verify_release_artifacts_manifest.validate_manifest(_manifest(), structure_only=True)

    assert errors == []


def test_require_artifacts_fails_for_missing_and_mismatched_local_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = _manifest()

    missing_errors = verify_release_artifacts_manifest.validate_manifest(manifest, require_artifacts=True)

    assert any("artifact file missing" in error for error in missing_errors)

    artifact_path = tmp_path / "implementation" / "phase1" / "release" / "bundle.zip"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"stale-local")

    mismatch_errors = verify_release_artifacts_manifest.validate_manifest(manifest, require_artifacts=True)

    assert any("bytes mismatch for bundle.zip" in error for error in mismatch_errors)
    assert any("sha256 mismatch for bundle.zip" in error for error in mismatch_errors)


def test_artifact_root_checks_asset_name_file_instead_of_local_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    local_artifact = tmp_path / "implementation" / "phase1" / "release" / "nested" / "bundle.zip"
    local_artifact.parent.mkdir(parents=True)
    local_artifact.write_bytes(b"stale")
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "bundle.zip").write_bytes(b"fresh")
    manifest = _manifest(local_path="implementation/phase1/release/nested/bundle.zip")

    errors = verify_release_artifacts_manifest.validate_manifest(manifest, artifact_root=artifact_root)

    assert errors == []


def test_structure_only_still_rejects_bad_manifest_schema_path_and_sha() -> None:
    manifest = _manifest(local_path="../release/bundle.zip")
    manifest["schema_version"] = "wrong"
    manifest["artifacts"][0]["sha256"] = "ABC"

    errors = verify_release_artifacts_manifest.validate_manifest(manifest, structure_only=True)

    assert "schema_version must be structural_analysis_release_artifacts_manifest.v1" in errors
    assert "artifacts[0].local_path must be a clean relative path" in errors
    assert "artifacts[0].sha256 must be a lowercase 64-char hex digest" in errors
