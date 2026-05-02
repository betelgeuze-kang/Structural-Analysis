from __future__ import annotations

import hashlib
import importlib.util
import json
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


def test_hydration_preflight_reports_missing_artifacts_without_integrity_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    summary = verify_release_artifacts_manifest.build_hydration_preflight(_manifest())

    assert summary["ok"] is True
    assert summary["mode"] == "source_checkout"
    assert "clean source checkout" in summary["contract"]
    assert summary["totals"] == {
        "manifest_assets": 1,
        "present": 0,
        "required_missing": 1,
        "optional_missing": 0,
    }
    assert summary["required_missing"][0]["status"] == "hydrate_required"
    assert summary["required_missing"][0]["hydrate_target"] == "implementation/phase1/release/bundle.zip"


def test_hydration_preflight_uses_artifact_root_asset_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "bundle.zip").write_bytes(b"fresh")
    manifest = _manifest(local_path="implementation/phase1/release/nested/bundle.zip")

    summary = verify_release_artifacts_manifest.build_hydration_preflight(
        manifest,
        artifact_root=artifact_root,
    )

    assert summary["ok"] is True
    assert summary["mode"] == "artifact_root"
    assert summary["totals"]["present"] == 1
    assert summary["present"][0]["hydrate_target"] == str(artifact_root / "bundle.zip")
    assert summary["present"][0]["actual_bytes"] == len(b"fresh")


def test_hydration_preflight_cli_succeeds_when_clean_checkout_lacks_artifacts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = tmp_path / "manifest.json"

    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")

    exit_code = verify_release_artifacts_manifest.main(
        ["--manifest", str(manifest_path), "--hydrate-preflight"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Hydrate required: bundle.zip" in captured.out
    assert "no local artifact bytes required" in captured.out
    assert captured.err == ""
