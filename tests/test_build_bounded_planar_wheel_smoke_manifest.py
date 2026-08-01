from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_bounded_planar_wheel_smoke_manifest.py"
SPEC = importlib.util.spec_from_file_location("wheel_smoke_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


SOURCE_COMMIT = "a" * 40
SOURCE_TREE = "b" * 40
WHEEL_FILENAME = "structural_analysis-0.3.0-py3-none-any.whl"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_coordinate_artifacts(
    root: Path,
    *,
    coordinate: str,
    wheel_bytes: bytes,
) -> Path:
    os_label, python_version = coordinate.split("|python-", maxsplit=1)
    artifact = root / (f"bounded-planar-wheel-smoke-{os_label}-python-{python_version}")
    wheel = artifact / "wheel" / WHEEL_FILENAME
    wheel.parent.mkdir(parents=True)
    wheel.write_bytes(wheel_bytes)
    wheel_hash = _sha256(wheel_bytes)
    receipt = {
        "schema_version": "bounded-planar-wheel-smoke.v4",
        "contract_pass": True,
        "source_commit_sha": SOURCE_COMMIT,
        "source_tree_sha": SOURCE_TREE,
        "build_system_requirements": module.EXPECTED_BUILD_SYSTEM_REQUIREMENTS,
        "runtime_constraints": {
            "path": module.EXPECTED_RUNTIME_CONSTRAINTS_PATH,
            "sha256": _sha256(b"runtime-constraints"),
        },
        "coordinate": {
            "coordinate_id": coordinate,
            "os_label": os_label,
            "requested_python_version": python_version,
        },
        "runtime": {
            "python_version": python_version + ".9",
            "python_implementation": "CPython",
            "system": "Linux" if os_label == "ubuntu-latest" else "Windows",
            "platform": "fixture-platform",
            "packages": {
                "pip": "25.1.1",
                **module.EXPECTED_RUNTIME_VERSIONS,
            },
        },
        "same_run_build_count": 2,
        "same_run_wheel_byte_identical": True,
        "wheel_filename": WHEEL_FILENAME,
        "wheel_sha256": wheel_hash,
        "wheel_builds": [
            {
                "build_number": build_number,
                "wheel_filename": WHEEL_FILENAME,
                "wheel_sha256": wheel_hash,
            }
            for build_number in (1, 2)
        ],
        "installed_console_script_executed": True,
    }
    receipt_path = artifact / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path


def _write_four_coordinates(root: Path) -> None:
    for index, coordinate in enumerate(module.EXPECTED_COORDINATES, start=1):
        _write_coordinate_artifacts(
            root,
            coordinate=coordinate,
            wheel_bytes=f"wheel-{index}".encode(),
        )


def test_manifest_binds_exactly_four_receipts_and_retained_wheels(
    tmp_path: Path,
) -> None:
    _write_four_coordinates(tmp_path)

    manifest = module.build_manifest(
        artifacts_directory=tmp_path,
        source_commit_sha=SOURCE_COMMIT,
    )

    assert manifest["contract_pass"] is True
    assert manifest["source_commit_sha"] == SOURCE_COMMIT
    assert manifest["source_tree_sha"] == SOURCE_TREE
    assert manifest["required_coordinates"] == list(module.EXPECTED_COORDINATES)
    assert manifest["observed_coordinate_count"] == 4
    assert len(manifest["coordinates"]) == 4
    assert manifest["claims"] == {
        "each_coordinate_same_run_wheel_byte_identity": True,
        "four_coordinate_preserved_wheel_hashes_verified": True,
        "installed_console_script_executed_on_all_coordinates": True,
    }
    assert manifest["manifest_sha256"].startswith("sha256:")


def test_manifest_rejects_missing_coordinate(tmp_path: Path) -> None:
    _write_four_coordinates(tmp_path)
    first_artifact = next(tmp_path.iterdir())
    (first_artifact / "receipt.json").unlink()

    with pytest.raises(module.WheelSmokeManifestError, match="receipt_count_invalid"):
        module.build_manifest(
            artifacts_directory=tmp_path,
            source_commit_sha=SOURCE_COMMIT,
        )


def test_manifest_rejects_retained_wheel_hash_drift(tmp_path: Path) -> None:
    _write_four_coordinates(tmp_path)
    first_wheel = next(tmp_path.glob("*/wheel/*.whl"))
    first_wheel.write_bytes(b"tampered")

    with pytest.raises(
        module.WheelSmokeManifestError,
        match="preserved_wheel_hash_mismatch",
    ):
        module.build_manifest(
            artifacts_directory=tmp_path,
            source_commit_sha=SOURCE_COMMIT,
        )
