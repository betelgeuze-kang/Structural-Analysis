from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "ingest_bounded_planar_external_nonlinear_material_recovery_results.py"
)
SPEC = importlib.util.spec_from_file_location(
    "ingest_bounded_planar_external_nonlinear_material_recovery_results_tests",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
ingest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ingest
SPEC.loader.exec_module(ingest)

RESULTS = (
    ROOT
    / "artifacts/vv/bounded_planar_same_operator_supplemental_execution/"
    "results/nonlinear_material_recovery"
)
STORED_RECEIPT = (
    ROOT
    / "artifacts/vv/bounded_planar_same_operator_supplemental_execution/"
    "receipts/nonlinear-material-recovery-technical-receipt.json"
)
requires_local_supplemental = pytest.mark.skipif(
    not STORED_RECEIPT.is_file(),
    reason="optional same-operator replay bundle is not source-controlled",
)


def _build(results: Path = RESULTS) -> dict:
    return ingest.build_execution_receipt(
        repo_root=ROOT,
        package_dir=ingest.package_builder.DEFAULT_OUT_DIR,
        results_dir=results,
    )


def test_execution_receipt_schema_is_valid() -> None:
    schema = json.loads((ROOT / ingest.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_result_path_uses_explicit_repository_root(tmp_path: Path) -> None:
    package_root = tmp_path / "arbitrary" / "deep" / "depth" / "package"
    manifest = ingest.package_builder.write_package(
        repo_root=ROOT, out_dir=package_root
    )
    case = manifest["cases"][0]
    product = json.loads(
        (package_root / case["product_result"]["path"]).read_text(encoding="utf-8")
    )
    result = {
        "schema_version": "bounded-planar-opensees-nonlinear-material-recovery-result.v1",
        "package_id": ingest.package_builder.PACKAGE_ID,
        "case_id": case["case_id"],
        "executed_at": "2026-01-01T00:00:00+00:00",
        "runner_file_sha256": case["external_runner"]["file_sha256"],
        "source_model_file_sha256": case["model"]["file_sha256"],
        "runtime": {
            "python_version": "3.11",
            "platform": "test-fixture",
            "openseespy_version": ingest.package_builder.PINNED_OPENSEESPY_VERSION,
            "opensees_core_version": ingest.package_builder.PINNED_OPENSEES_CORE_VERSION,
        },
        "return_codes": [0],
        "metrics": product["metrics"],
        "contract_pass": True,
        "blockers": [],
    }
    result["artifact_hash"] = ingest._artifact_hash(result)
    results_root = tmp_path / "results"
    results_root.mkdir()
    (results_root / f"{case['case_id']}.json").write_text(
        json.dumps(result), encoding="utf-8"
    )
    result_schema = json.loads(
        (
            package_root / manifest["external_result_schema"]["path"]
        ).read_text(encoding="utf-8")
    )

    receipt_case, _ = ingest._validate_result(
        case=case,
        repo_root=tmp_path,
        package_root=package_root,
        results_root=results_root,
        result_schema=result_schema,
    )

    assert receipt_case["external_result"]["path"] == (
        f"results/{case['case_id']}.json"
    )


@requires_local_supplemental
def test_committed_results_replay_six_technical_passes() -> None:
    receipt = _build()
    stored = json.loads(STORED_RECEIPT.read_text(encoding="utf-8"))

    assert receipt == stored
    assert receipt["summary"] == {
        "case_count": 6,
        "self_consistent_result_count": 6,
        "technical_comparison_pass_count": 6,
    }
    assert receipt["technical_contract_pass"] is True
    assert all(row["technical_comparison_pass"] for row in receipt["cases"])
    assert receipt["claims"]["fresh_current_source_external_execution"] is False
    assert receipt["claims"]["independent_operator_attested"] is False
    assert receipt["claims"]["verification_matrix_credit"] is False
    assert receipt["claims"]["verification_level_2"] is False


@requires_local_supplemental
def test_runtime_version_tamper_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "results"
    shutil.copytree(RESULTS, target)
    path = target / "bounded_planar_p_delta.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runtime"]["opensees_core_version"] = "forged"
    payload["artifact_hash"] = ingest._artifact_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ingest.ExternalNonlinearMaterialRecoveryResultError,
        match="external_nonlinear_result_schema_invalid:bounded_planar_p_delta",
    ):
        _build(target)


@requires_local_supplemental
def test_runner_hash_tamper_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "results"
    shutil.copytree(RESULTS, target)
    path = target / "bounded_planar_steel_yield.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runner_file_sha256"] = "sha256:" + "0" * 64
    payload["artifact_hash"] = ingest._artifact_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ingest.ExternalNonlinearMaterialRecoveryResultError,
        match="external_nonlinear_result_runner_hash_mismatch",
    ):
        _build(target)


@requires_local_supplemental
def test_metric_outside_declared_tolerance_is_technical_blocked(
    tmp_path: Path,
) -> None:
    target = tmp_path / "results"
    shutil.copytree(RESULTS, target)
    path = target / "bounded_planar_section_recovery.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metrics"]["section.moment_z_kn_m"] += 10.0
    payload["artifact_hash"] = ingest._artifact_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = _build(target)
    rows = {row["case_id"]: row for row in receipt["cases"]}
    assert receipt["technical_contract_pass"] is False
    assert receipt["status"] == "technical_blocked"
    assert rows["bounded_planar_section_recovery"][
        "technical_comparison_pass"
    ] is False
    assert "comparison_tolerance_exceeded" in receipt["blockers"]


@requires_local_supplemental
def test_receipt_hash_tamper_fails_closed() -> None:
    forged = deepcopy(_build())
    forged["summary"]["technical_comparison_pass_count"] = 5

    with pytest.raises(ingest.ExternalNonlinearMaterialRecoveryResultError):
        ingest._validate_receipt(forged, ROOT)
