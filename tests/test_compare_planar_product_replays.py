from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/compare_planar_product_replays.py"
spec = importlib.util.spec_from_file_location(
    "compare_planar_product_replays_test_module",
    SCRIPT,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def _materialize_coordinate(root: Path, os_label: str) -> None:
    coordinate = root / f"planar-product-replay-{os_label}-python-3.12"
    wheel_bytes = b"canonical-wheel"
    files = {
        "model_sha256": ("runtime/public-model.json", b'{"model":true}\n'),
        "result_sha256": ("runtime/public-result.json", b'{"result":true}\n'),
        "report_sha256": ("runtime/public-report.json", b'{"report":true}\n'),
        "checkpoint_sha256": (
            "runtime/public-checkpoint.json",
            b'{"checkpoint":true}\n',
        ),
        "workbench_case_sha256": (
            "runtime/workbench-case.json",
            b'{"workbench":true}\n',
        ),
    }
    wheel_path = coordinate / "wheel/structural_analysis-0.3.0-py3-none-any.whl"
    wheel_path.parent.mkdir(parents=True, exist_ok=True)
    wheel_path.write_bytes(wheel_bytes)
    artifact_hashes: dict[str, str] = {}
    for field, (relative, data) in files.items():
        path = coordinate / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        artifact_hashes[field] = _sha256(data)

    source_commit = "a" * 40
    replay = {
        "schema_version": "planar-product-replay.v1",
        "contract_pass": True,
        "profile": "planar_frame_verified_alpha.v1",
        "source_commit_sha": source_commit,
        "engine_version": "structural-analysis@0.3.0",
        "coordinate": {
            "os_label": os_label,
            "requested_python_version": "3.12",
        },
        "wheel": {
            "filename": wheel_path.name,
            "sha256": _sha256(wheel_bytes),
        },
        "artifacts": artifact_hashes,
        "result_truth": {
            "status": "converged",
            "converged": True,
            "result_hash": "sha256:" + "b" * 64,
            "artifact_contract_pass": True,
            "execution_contract_pass": True,
            "numerical_result_authority": True,
            "engineering_result_authority": True,
        },
    }
    browser = {
        "schema_version": "workbench-product-replay-browser.v1",
        "contract_pass": True,
        "source_commit_sha": source_commit,
        "coordinate": replay["coordinate"],
        "immutable_analysis_core_sha256": "sha256:" + "c" * 64,
        "review_envelope_sha256": "sha256:" + "d" * 64,
        "analysis_result_sha256": "sha256:" + "c" * 64,
        "product_profile": {
            "id": {
                "status": "available",
                "value": "planar_frame_verified_alpha.v1",
            }
        },
        "analysis_status": "converged",
        "provenance_contract": {"status": "available", "issues": []},
    }
    _write_json(coordinate / "runtime/product-replay.json", replay)
    _write_json(coordinate / "runtime/browser-replay.json", browser)


def test_cross_platform_comparison_requires_identical_canonical_evidence(
    tmp_path: Path,
) -> None:
    for os_label in module.EXPECTED_OS_LABELS:
        _materialize_coordinate(tmp_path, os_label)

    receipt = module.compare_product_replays(
        artifacts_root=tmp_path,
        expected_source_commit="a" * 40,
    )

    assert receipt["contract_pass"] is True
    assert receipt["blockers"] == []
    assert receipt["coordinate_count"] == 2
    assert all(receipt["matching"].values())


def test_cross_platform_comparison_blocks_review_envelope_drift(
    tmp_path: Path,
) -> None:
    for os_label in module.EXPECTED_OS_LABELS:
        _materialize_coordinate(tmp_path, os_label)
    browser_path = (
        tmp_path
        / "planar-product-replay-windows-latest-python-3.12"
        / "runtime/browser-replay.json"
    )
    browser = json.loads(browser_path.read_text(encoding="utf-8"))
    browser["review_envelope_sha256"] = "sha256:" + "e" * 64
    _write_json(browser_path, browser)

    receipt = module.compare_product_replays(artifacts_root=tmp_path)

    assert receipt["contract_pass"] is False
    assert receipt["matching"]["review_envelope_sha256"] is False
    assert "cross_platform_review_envelope_sha256_mismatch" in receipt["blockers"]


def test_cross_platform_comparison_validates_recorded_artifact_bytes(
    tmp_path: Path,
) -> None:
    for os_label in module.EXPECTED_OS_LABELS:
        _materialize_coordinate(tmp_path, os_label)
    result_path = (
        tmp_path
        / "planar-product-replay-windows-latest-python-3.12"
        / "runtime/public-result.json"
    )
    result_path.write_bytes(b"tampered\n")

    receipt = module.compare_product_replays(artifacts_root=tmp_path)

    assert receipt["contract_pass"] is False
    assert "windows-latest:result_sha256_bytes_missing_or_mismatched" in receipt[
        "blockers"
    ]
