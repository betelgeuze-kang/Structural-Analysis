from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ingest_bounded_planar_external_linear_results.py"
SPEC = importlib.util.spec_from_file_location(
    "ingest_bounded_planar_external_linear_results_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
ingest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ingest
SPEC.loader.exec_module(ingest)


def _manifest() -> dict:
    path = ROOT / ingest.DEFAULT_PACKAGE_DIR / ingest.package_builder.MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def _write_result_set(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    manifest = _manifest()
    package_root = ROOT / ingest.DEFAULT_PACKAGE_DIR
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    paths: dict[str, Path] = {}
    for case in manifest["cases"]:
        case_id = case["case_id"]
        product = json.loads(
            (package_root / case["product_result"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        payload = {
            "schema_version": "bounded-planar-opensees-linear-result.v1",
            "package_id": manifest["package_id"],
            "case_id": case_id,
            "executed_at": "2026-07-29T04:00:00+00:00",
            "runner_file_sha256": case["opensees_runner"]["file_sha256"],
            "source_model_file_sha256": case["model_ir"]["file_sha256"],
            "runtime": {
                "python_version": "3.10.19",
                "platform": "Linux-test-fixture",
                "openseespy_version": "3.7.1.2",
                "opensees_core_version": "3.7.1",
            },
            "return_codes": [0, 0, 0, 0],
            "metrics": product["metrics"],
            "contract_pass": True,
            "blockers": [],
            "artifact_hash": "sha256:" + "0" * 64,
        }
        payload["artifact_hash"] = ingest._artifact_hash(payload)
        path = results_dir / f"{case_id}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths[case_id] = path
    return results_dir, paths


def _rewrite(path: Path, mutation) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    payload["artifact_hash"] = ingest._artifact_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_external_linear_execution_receipt_schema_is_valid() -> None:
    schema = json.loads(
        (ROOT / ingest.RECEIPT_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)


def test_self_consistent_results_create_non_promoting_technical_receipt(
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
        "case_count": 2,
        "self_consistent_result_count": 2,
        "technical_comparison_pass_count": 2,
    }
    assert receipt["claims"] == {
        "package_bytes_authenticated": True,
        "external_results_self_consistent": True,
        "fresh_current_source_external_execution": False,
        "independent_operator_attested": False,
        "legal_use_approved": False,
        "verification_matrix_credit": False,
        "verification_level_2": False,
    }
    assert "independent_operator_attestation_missing" in receipt["blockers"]
    assert receipt["artifact_hash"] == ingest._artifact_hash(receipt)


def test_runner_hash_tamper_fails_closed(tmp_path: Path) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    path = paths["bounded_planar_linear_portal"]
    _rewrite(path, lambda payload: payload.__setitem__("runner_file_sha256", "sha256:" + "a" * 64))

    with pytest.raises(
        ingest.ExternalLinearResultError,
        match="external_linear_result_runner_hash_mismatch",
    ):
        ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)


def test_metric_set_tamper_fails_closed(tmp_path: Path) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    path = paths["bounded_planar_linear_portal"]

    def remove_metric(payload: dict) -> None:
        payload["metrics"].pop(next(iter(payload["metrics"])))

    _rewrite(path, remove_metric)
    with pytest.raises(
        ingest.ExternalLinearResultError,
        match="external_linear_result_metric_set_invalid",
    ):
        ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)


def test_rehashed_metric_deviation_is_visible_but_not_promoted(tmp_path: Path) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    path = paths["bounded_planar_linear_multistory"]

    def change_metric(payload: dict) -> None:
        metric_id = next(iter(payload["metrics"]))
        payload["metrics"][metric_id] += 1.0

    _rewrite(path, change_metric)
    receipt = ingest.build_execution_receipt(repo_root=ROOT, results_dir=results_dir)

    assert receipt["status"] == "technical_blocked"
    assert receipt["technical_contract_pass"] is False
    assert receipt["summary"]["technical_comparison_pass_count"] == 1
    assert "comparison_tolerance_exceeded" in receipt["blockers"]
    assert receipt["claims"]["verification_matrix_credit"] is False


def test_unrehashed_result_tamper_fails_self_hash(tmp_path: Path) -> None:
    results_dir, paths = _write_result_set(tmp_path)
    path = paths["bounded_planar_linear_portal"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    metric_id = next(iter(payload["metrics"]))
    payload["metrics"][metric_id] += 1.0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ingest.ExternalLinearResultError,
        match="external_linear_result_artifact_hash_invalid",
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
