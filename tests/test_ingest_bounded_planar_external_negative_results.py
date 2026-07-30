from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ingest_bounded_planar_external_negative_results.py"
SPEC = importlib.util.spec_from_file_location(
    "ingest_bounded_planar_external_negative_results_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
ingest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ingest
SPEC.loader.exec_module(ingest)


def _manifest() -> dict:
    return json.loads(
        (
            ROOT
            / ingest.DEFAULT_PACKAGE_DIR
            / ingest.package_builder.MANIFEST_NAME
        ).read_text(encoding="utf-8")
    )


def _write_result_set(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    manifest = _manifest()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    paths: dict[str, Path] = {}
    for case in manifest["cases"]:
        invalid = case["requirement_id"] == "negative.invalid_geometry"
        singular = case["requirement_id"] == "negative.singular"
        tangent_rank_check = (
            {
                "equation_count": 10,
                "matrix_value_count": 100,
                "maximum_absolute_entry": 2_000_000.0,
                "relative_pivot_tolerance": 1.0e-12,
                "absolute_pivot_tolerance": 2.0e-5,
                "numerical_rank": 9,
                "rank_deficient": True,
            }
            if singular
            else None
        )
        payload = {
            "schema_version": "bounded-planar-opensees-negative-result.v1",
            "package_id": manifest["package_id"],
            "case_id": case["case_id"],
            "executed_at": "2026-07-29T08:00:00+00:00",
            "runner_file_sha256": case["opensees_runner"]["file_sha256"],
            "source_model_file_sha256": case["model_ir"]["file_sha256"],
            "runtime": {
                "python_version": "3.10.19",
                "platform": "Linux-test-fixture",
                "openseespy_version": "3.7.1.2",
                "opensees_core_version": "3.7.1",
            },
            "external_engine_invoked": not invalid,
            "model_construction_succeeded": not invalid,
            "analysis_return_code": None if invalid else (0 if singular else -3),
            "exception_type": None,
            "tangent_rank_check": tangent_rank_check,
            "observation": case["expected_external_observation"],
            "classification_match": True,
            "contract_pass": True,
            "blockers": [],
            "artifact_hash": "sha256:" + "0" * 64,
        }
        payload["artifact_hash"] = ingest._artifact_hash(payload)
        path = results_dir / f"{case['case_id']}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths[case["case_id"]] = path
    return results_dir, paths


def _rewrite(path: Path, mutation, *, rehash: bool = True) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    if rehash:
        payload["artifact_hash"] = ingest._artifact_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_external_negative_execution_receipt_schema_is_valid() -> None:
    schema = json.loads(
        (ROOT / ingest.RECEIPT_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)


def test_exact_rejections_create_non_promoting_technical_receipt(
    tmp_path: Path,
) -> None:
    results_dir, _paths = _write_result_set(tmp_path)

    receipt = ingest.build_execution_receipt(
        repo_root=ROOT,
        results_dir=results_dir,
    )

    assert receipt["status"] == "technical_pass"
    assert receipt["technical_contract_pass"] is True
    assert receipt["summary"] == {
        "case_count": 3,
        "self_consistent_result_count": 3,
        "external_engine_invoked_case_count": 2,
        "independent_preflight_case_count": 1,
        "technical_rejection_pass_count": 3,
    }
    assert [row["rejection_authority"] for row in receipt["cases"]] == [
        "external_solver_expected_rejection",
        "external_solver_tangent_rank_rejection",
        "independent_input_contract_rejection",
    ]
    assert receipt["claims"]["invalid_geometry_external_solver_execution"] is False
    assert receipt["claims"]["fresh_current_source_external_execution"] is False
    assert receipt["claims"]["verification_matrix_credit"] is False
    assert receipt["claims"]["verification_level_2"] is False
    assert receipt["artifact_hash"] == ingest._artifact_hash(receipt)


def test_rehashed_runner_binding_tamper_fails_closed(tmp_path: Path) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    _rewrite(
        paths["bounded_planar_negative_mechanism"],
        lambda payload: payload.__setitem__(
            "runner_file_sha256", "sha256:" + "a" * 64
        ),
    )

    with pytest.raises(
        ingest.ExternalNegativeResultError,
        match="external_negative_result_runner_hash_mismatch",
    ):
        ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)


def test_unrehashed_observation_tamper_fails_self_hash(tmp_path: Path) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    _rewrite(
        paths["bounded_planar_negative_singular"],
        lambda payload: payload.__setitem__(
            "observation", "released_mechanism_rejected"
        ),
        rehash=False,
    )

    with pytest.raises(
        ingest.ExternalNegativeResultError,
        match="external_negative_result_artifact_hash_invalid",
    ):
        ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)


def test_invalid_geometry_cannot_claim_external_engine_execution(
    tmp_path: Path,
) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    _rewrite(
        paths["bounded_planar_negative_invalid_geometry"],
        lambda payload: payload.__setitem__("external_engine_invoked", True),
    )

    with pytest.raises(
        ingest.ExternalNegativeResultError,
        match="external_negative_result_invalid_geometry_authority",
    ):
        ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)


def test_solver_case_requires_actual_rejection_signal(tmp_path: Path) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    _rewrite(
        paths["bounded_planar_negative_mechanism"],
        lambda payload: payload.__setitem__("analysis_return_code", 0),
    )

    with pytest.raises(
        ingest.ExternalNegativeResultError,
        match="external_negative_result_solver_rejection_missing",
    ):
        ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)


def test_singular_tangent_rank_claim_is_recomputed(tmp_path: Path) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    _rewrite(
        paths["bounded_planar_negative_singular"],
        lambda payload: payload["tangent_rank_check"].__setitem__(
            "numerical_rank", 10
        ),
    )

    with pytest.raises(
        ingest.ExternalNegativeResultError,
        match="external_negative_result_tangent_rank_invalid",
    ):
        ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)


def test_unexpected_result_file_fails_closed(tmp_path: Path) -> None:
    results_dir, _paths = _write_result_set(tmp_path)
    (results_dir / "unexpected.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        ingest.ExternalNegativeResultError,
        match="external_negative_result_file_set_invalid",
    ):
        ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)


def test_cli_writes_receipt_without_claiming_matrix_credit(tmp_path: Path) -> None:
    results_dir, _paths = _write_result_set(tmp_path)
    output = tmp_path / "receipt.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--results-dir",
            str(results_dir),
            "--out",
            str(output),
            "--fail-technical-blocked",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["technical_contract_pass"] is True
    assert receipt["claims"]["verification_matrix_credit"] is False
