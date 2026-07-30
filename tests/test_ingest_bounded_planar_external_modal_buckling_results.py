from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "ingest_bounded_planar_external_modal_buckling_results.py"
)
SPEC = importlib.util.spec_from_file_location(
    "ingest_bounded_planar_external_modal_buckling_results_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
intake = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = intake
SPEC.loader.exec_module(intake)


def _write_synthetic_results(directory: Path) -> list[Path]:
    package_root = ROOT / intake.DEFAULT_PACKAGE_DIR
    manifest = json.loads((package_root / "manifest.json").read_text())
    paths: list[Path] = []
    for case in manifest["cases"]:
        product = json.loads(
            (package_root / case["product_result"]["path"]).read_text()
        )
        observations = deepcopy(product["observations"])
        if case["requirement_id"] == "modal.rigid_mode":
            observations["eigenvalues"] = [0.0] * 6 + observations["eigenvalues"]
            observations["mode_vectors"] = [[0.0] * 12 for _ in range(12)]
        elif case["requirement_id"] == "modal.repeated_mode":
            first, second = observations["mode_vectors"]
            scale = 2.0**-0.5
            observations["mode_vectors"] = [
                [scale * (left + right) for left, right in zip(first, second)],
                [scale * (left - right) for left, right in zip(first, second)],
            ]
        payload = {
            "schema_version": "bounded-planar-external-modal-buckling-result.v1",
            "package_id": manifest["package_id"],
            "case_id": case["case_id"],
            "analysis_type": case["analysis_type"],
            "external_solver": case["external_solver"],
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "runner_file_sha256": case["external_runner"]["file_sha256"],
            "source_model_file_sha256": case["model"]["file_sha256"],
            "runtime": {
                "solver_version": (
                    intake.package_builder.PINNED_OPENSEES_CORE_VERSION
                    if case["external_solver"] == "OpenSees"
                    else intake.package_builder.PINNED_CALCULIX_VERSION
                ),
                "python_version": "3.11.0",
                "platform": "synthetic-test-platform",
            },
            "observations": observations,
            "contract_pass": True,
            "blockers": [],
            "artifact_hash": intake.ZERO_HASH,
        }
        payload["artifact_hash"] = intake._artifact_hash(payload)
        path = directory / f"{case['case_id']}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(path)
    return paths


def test_intake_accepts_hash_bound_results_without_promoting(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _write_synthetic_results(results)

    receipt = intake.build_receipt(repo_root=ROOT, results_dir=results)

    assert receipt["technical_contract_pass"] is True
    assert receipt["summary"] == {"case_count": 3, "technical_pass_count": 3}
    assert receipt["claims"]["fresh_external_solver_execution"] is False
    assert "fresh_current_source_execution_not_attested" in receipt["blockers"]
    assert receipt["claims"]["verification_matrix_credit"] is False
    assert receipt["claims"]["verification_level_2"] is False
    repeated = receipt["cases"][1]
    subspace = next(
        row
        for row in repeated["comparisons"]
        if row["metric_id"] == "repeated_mode_minimum_subspace_correlation"
    )
    assert subspace["external_value"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda payload: payload.__setitem__(
                "source_model_file_sha256", "sha256:" + "0" * 64
            ),
            "external_modal_buckling_result_model_hash_mismatch",
        ),
        (
            lambda payload: payload["runtime"].__setitem__(
                "solver_version", "fabricated"
            ),
            "external_modal_buckling_result_solver_version_invalid",
        ),
        (
            lambda payload: payload["observations"]["eigenvalues"].__setitem__(
                -1, payload["observations"]["eigenvalues"][-1] * 100.0
            ),
            None,
        ),
    ],
)
def test_intake_fails_closed_on_tampering(
    tmp_path: Path, mutation, expected: str | None
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    paths = _write_synthetic_results(results)
    payload = json.loads(paths[0].read_text())
    mutation(payload)
    payload["artifact_hash"] = intake._artifact_hash(payload)
    paths[0].write_text(json.dumps(payload), encoding="utf-8")

    if expected is None:
        receipt = intake.build_receipt(repo_root=ROOT, results_dir=results)
        assert receipt["technical_contract_pass"] is False
        assert receipt["cases"][0]["technical_contract_pass"] is False
    else:
        with pytest.raises(intake.ExternalModalBucklingResultError, match=expected):
            intake.build_receipt(repo_root=ROOT, results_dir=results)


def test_intake_rejects_invalid_self_hash_before_comparison(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    paths = _write_synthetic_results(results)
    payload = json.loads(paths[1].read_text())
    payload["observations"]["eigenvalues"][0] *= 2.0
    paths[1].write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        intake.ExternalModalBucklingResultError,
        match="external_modal_buckling_result_artifact_hash_invalid",
    ):
        intake.build_receipt(repo_root=ROOT, results_dir=results)
