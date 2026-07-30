from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ingest_bounded_planar_external_scaling_results.py"
SPEC = importlib.util.spec_from_file_location(
    "ingest_bounded_planar_external_scaling_results_tests",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
ingest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ingest
SPEC.loader.exec_module(ingest)


def _write_external_results(target: Path) -> dict[str, dict]:
    package_root = ROOT / ingest.package_builder.DEFAULT_OUT_DIR
    manifest = json.loads(
        (package_root / ingest.package_builder.MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )
    target.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    for case in manifest["cases"]:
        product = json.loads(
            (package_root / case["product_result"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        variants = [
            {
                "variant_id": row["variant_id"],
                "raw_metrics_si": dict(row["normalized_metrics"]),
                "normalized_metrics": dict(row["normalized_metrics"]),
            }
            for row in product["variants"]
        ]
        payload = {
            "schema_version": "bounded-planar-opensees-scaling-result.v1",
            "package_id": manifest["package_id"],
            "case_id": case["case_id"],
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "runner_file_sha256": case["opensees_runner"]["file_sha256"],
            "source_model_pair_file_sha256": case["model_pair"]["file_sha256"],
            "runtime": {
                "python_version": "3.10.19",
                "platform": "test-platform",
                "openseespy_version": "3.7.1.2",
                "opensees_core_version": "3.7.1",
            },
            "variants": variants,
            "relative_differences": dict(product["relative_differences"]),
            "maximum_relative_difference": product[
                "maximum_relative_difference"
            ],
            "relative_tolerance": product["relative_tolerance"],
            "contract_pass": True,
            "blockers": [],
            "artifact_hash": "sha256:" + "0" * 64,
        }
        payload["artifact_hash"] = ingest._artifact_hash(payload)
        path = target / f"{case['case_id']}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        results[case["case_id"]] = payload
    return results


def test_scaling_execution_receipt_schema_is_valid() -> None:
    schema = json.loads(
        (ROOT / ingest.RECEIPT_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)


def test_scaling_results_build_non_promoting_technical_receipt(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    _write_external_results(results)

    receipt = ingest.build_execution_receipt(
        repo_root=ROOT,
        results_dir=results,
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
    assert "fresh_current_source_execution_not_attested" in receipt["blockers"]
    assert all(row["technical_comparison_pass"] for row in receipt["cases"])
    ingest._validate_receipt(receipt, ROOT)


def test_scaling_result_rejects_rehashed_model_pair_substitution(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results = _write_external_results(results_dir)
    case_id = "bounded_planar_scaling_unit_invariance"
    payload = deepcopy(results[case_id])
    payload["source_model_pair_file_sha256"] = "sha256:" + "f" * 64
    payload["artifact_hash"] = ingest._artifact_hash(payload)
    (results_dir / f"{case_id}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ingest.ExternalScalingResultError,
        match="external_scaling_result_model_pair_hash_mismatch",
    ):
        ingest.build_execution_receipt(
            repo_root=ROOT,
            results_dir=results_dir,
        )


def test_scaling_result_comparison_exceedance_stays_technical_blocked(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results = _write_external_results(results_dir)
    case_id = "bounded_planar_scaling_unit_invariance"
    payload = deepcopy(results[case_id])
    for variant in payload["variants"]:
        variant["normalized_metrics"]["node.N3.UX_m"] += 1.0
    payload["artifact_hash"] = ingest._artifact_hash(payload)
    (results_dir / f"{case_id}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    receipt = ingest.build_execution_receipt(
        repo_root=ROOT,
        results_dir=results_dir,
    )

    assert receipt["status"] == "technical_blocked"
    assert receipt["technical_contract_pass"] is False
    assert receipt["summary"]["technical_comparison_pass_count"] == 1
    assert "comparison_tolerance_exceeded" in receipt["blockers"]
