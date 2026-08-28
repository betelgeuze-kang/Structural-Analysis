#!/usr/bin/env python3
"""Validate six OpenSees nonlinear/material/recovery results into a receipt."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
SRC_ROOT = ROOT / "src"
for search_root in (SCRIPT_DIR, SRC_ROOT):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import build_bounded_planar_external_nonlinear_material_recovery_case_package as package_builder  # noqa: E402
from strict_json import StrictJSONError, strict_json_load_path  # noqa: E402


SCHEMA_VERSION = (
    "bounded-planar-external-nonlinear-material-recovery-execution-receipt.v1"
)
SCHEMA_PATH = package_builder.RECEIPT_SCHEMA_PATH
ZERO_HASH = "sha256:" + "0" * 64


class ExternalNonlinearMaterialRecoveryResultError(ValueError):
    """Stable fail-closed result or receipt validation error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalNonlinearMaterialRecoveryResultError(code)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = deepcopy(payload)
    body.pop("artifact_hash", None)
    return _hash_bytes(_canonical_bytes(body))


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = strict_json_load_path(path)
    except (OSError, StrictJSONError) as exc:
        raise ExternalNonlinearMaterialRecoveryResultError(code) from exc
    if not isinstance(payload, dict):
        _fail(code)
    return payload


def _resolved(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _relative(repo_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _validate_timestamp(value: object, case_id: str) -> None:
    if not isinstance(value, str):
        _fail(f"external_nonlinear_result_timestamp_invalid:{case_id}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExternalNonlinearMaterialRecoveryResultError(
            f"external_nonlinear_result_timestamp_invalid:{case_id}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"external_nonlinear_result_timestamp_timezone_missing:{case_id}")


def _comparison(
    *,
    metric_id: str,
    product_value: float,
    external_value: float,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    absolute_error = abs(external_value - product_value)
    scale = max(abs(product_value), abs(external_value), 1.0e-30)
    relative_error = absolute_error / scale
    contract_pass = bool(
        absolute_error <= absolute_tolerance or relative_error <= relative_tolerance
    )
    return {
        "metric_id": metric_id,
        "product_value": product_value,
        "external_value": external_value,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "contract_pass": contract_pass,
    }


def _load_result_schema(package_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    descriptor = manifest["external_result_schema"]
    path = package_root / str(descriptor["path"])
    if not path.is_file() or _file_hash(path) != descriptor["file_sha256"]:
        _fail("external_nonlinear_result_schema_binding_invalid")
    return _load_json(path, "external_nonlinear_result_schema_unreadable")


def _validate_result(
    *,
    case: dict[str, Any],
    package_root: Path,
    results_root: Path,
    result_schema: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = str(case["case_id"])
    result_path = results_root / f"{case_id}.json"
    result = _load_json(result_path, f"external_nonlinear_result_unreadable:{case_id}")
    try:
        Draft202012Validator(result_schema, format_checker=FormatChecker()).validate(
            result
        )
    except ValidationError as exc:
        raise ExternalNonlinearMaterialRecoveryResultError(
            f"external_nonlinear_result_schema_invalid:{case_id}"
        ) from exc
    if result.get("artifact_hash") != _artifact_hash(result):
        _fail(f"external_nonlinear_result_artifact_hash_invalid:{case_id}")
    if (
        result.get("package_id") != package_builder.PACKAGE_ID
        or result.get("case_id") != case_id
    ):
        _fail(f"external_nonlinear_result_identity_mismatch:{case_id}")
    _validate_timestamp(result.get("executed_at"), case_id)
    if result.get("contract_pass") is not True or result.get("blockers") != []:
        _fail(f"external_nonlinear_result_contract_blocked:{case_id}")
    runtime = result.get("runtime")
    if not isinstance(runtime, dict):
        _fail(f"external_nonlinear_result_runtime_invalid:{case_id}")
    if runtime.get("openseespy_version") != package_builder.PINNED_OPENSEESPY_VERSION:
        _fail(f"external_nonlinear_result_openseespy_version_invalid:{case_id}")
    if (
        runtime.get("opensees_core_version")
        != package_builder.PINNED_OPENSEES_CORE_VERSION
    ):
        _fail(f"external_nonlinear_result_opensees_core_version_invalid:{case_id}")
    runner_path = package_root / str(case["external_runner"]["path"])
    model_path = package_root / str(case["model"]["path"])
    if (
        result.get("runner_file_sha256") != case["external_runner"]["file_sha256"]
        or _file_hash(runner_path) != case["external_runner"]["file_sha256"]
    ):
        _fail(f"external_nonlinear_result_runner_hash_mismatch:{case_id}")
    if (
        result.get("source_model_file_sha256") != case["model"]["file_sha256"]
        or _file_hash(model_path) != case["model"]["file_sha256"]
    ):
        _fail(f"external_nonlinear_result_model_hash_mismatch:{case_id}")

    product_path = package_root / str(case["product_result"]["path"])
    product = _load_json(
        product_path, f"external_nonlinear_product_result_unreadable:{case_id}"
    )
    if (
        product.get("artifact_hash") != case["product_result"]["artifact_hash"]
        or product.get("artifact_hash") != _artifact_hash(product)
        or product.get("case_id") != case_id
        or product.get("requirement_id") != case["requirement_id"]
        or product.get("contract_pass") is not True
    ):
        _fail(f"external_nonlinear_product_result_binding_invalid:{case_id}")
    product_metrics = product.get("metrics")
    tolerances = product.get("tolerances")
    external_metrics = result.get("metrics")
    if not all(
        isinstance(value, dict)
        for value in (product_metrics, tolerances, external_metrics)
    ):
        _fail(f"external_nonlinear_metric_contract_invalid:{case_id}")
    if sorted(product_metrics) != sorted(case["metric_ids"]):
        _fail(f"external_nonlinear_product_metric_set_invalid:{case_id}")
    if not set(product_metrics).issubset(external_metrics):
        _fail(f"external_nonlinear_external_metric_set_invalid:{case_id}")

    comparisons: list[dict[str, Any]] = []
    for metric_id in sorted(product_metrics):
        tolerance = tolerances.get(metric_id)
        if not isinstance(tolerance, dict):
            _fail(f"external_nonlinear_tolerance_missing:{case_id}:{metric_id}")
        values = (
            product_metrics[metric_id],
            external_metrics[metric_id],
            tolerance.get("absolute_tolerance"),
            tolerance.get("relative_tolerance"),
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        ):
            _fail(f"external_nonlinear_metric_value_invalid:{case_id}:{metric_id}")
        comparisons.append(
            _comparison(
                metric_id=metric_id,
                product_value=float(values[0]),
                external_value=float(values[1]),
                absolute_tolerance=float(values[2]),
                relative_tolerance=float(values[3]),
            )
        )
    technical_pass = all(row["contract_pass"] for row in comparisons)
    receipt_case = {
        "case_id": case_id,
        "requirement_id": case["requirement_id"],
        "external_result": {
            "path": _relative(package_root.parent.parent.parent, result_path),
            "file_sha256": _file_hash(result_path),
            "artifact_hash": result["artifact_hash"],
            "executed_at": result["executed_at"],
            "runner_file_sha256": result["runner_file_sha256"],
            "source_model_file_sha256": result["source_model_file_sha256"],
            "runtime": runtime,
        },
        "metric_comparisons": comparisons,
        "maximum_absolute_error": max(row["absolute_error"] for row in comparisons),
        "maximum_relative_error": max(row["relative_error"] for row in comparisons),
        "technical_comparison_pass": technical_pass,
        "blockers": [] if technical_pass else ["comparison_tolerance_exceeded"],
    }
    return receipt_case, result


def _load_receipt_schema(repo_root: Path) -> dict[str, Any]:
    return _load_json(
        repo_root / SCHEMA_PATH,
        "external_nonlinear_execution_receipt_schema_unreadable",
    )


def _validate_receipt(receipt: dict[str, Any], repo_root: Path) -> None:
    try:
        schema = _load_receipt_schema(repo_root)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(receipt)
    except (SchemaError, ValidationError) as exc:
        raise ExternalNonlinearMaterialRecoveryResultError(
            "external_nonlinear_execution_receipt_invalid"
        ) from exc
    if receipt.get("artifact_hash") != _artifact_hash(receipt):
        _fail("external_nonlinear_execution_receipt_hash_invalid")
    cases = receipt.get("cases")
    if not isinstance(cases, list):
        _fail("external_nonlinear_execution_receipt_case_set_invalid")
    technical_count = sum(row.get("technical_comparison_pass") is True for row in cases)
    summary = receipt.get("summary")
    if not isinstance(summary, dict) or (
        summary.get("case_count") != len(package_builder.CASE_DEFINITIONS)
        or summary.get("self_consistent_result_count")
        != len(package_builder.CASE_DEFINITIONS)
        or summary.get("technical_comparison_pass_count") != technical_count
    ):
        _fail("external_nonlinear_execution_receipt_summary_invalid")
    expected_pass = technical_count == len(package_builder.CASE_DEFINITIONS)
    if receipt.get("technical_contract_pass") is not expected_pass or receipt.get(
        "status"
    ) != ("technical_pass" if expected_pass else "technical_blocked"):
        _fail("external_nonlinear_execution_receipt_contract_invalid")


def build_execution_receipt(
    *,
    repo_root: Path = ROOT,
    package_dir: Path = package_builder.DEFAULT_OUT_DIR,
    results_dir: Path,
) -> dict[str, Any]:
    package_root = _resolved(repo_root, package_dir)
    results_root = _resolved(repo_root, results_dir)
    manifest = package_builder.validate_package_directory(
        repo_root=repo_root, out_dir=package_root
    )
    expected_names = {
        f"{case['case_id']}.json" for case in package_builder.CASE_DEFINITIONS
    }
    actual_names = {path.name for path in results_root.iterdir() if path.is_file()}
    if actual_names != expected_names:
        _fail("external_nonlinear_result_file_set_invalid")
    result_schema = _load_result_schema(package_root, manifest)
    try:
        Draft202012Validator.check_schema(result_schema)
    except SchemaError as exc:
        raise ExternalNonlinearMaterialRecoveryResultError(
            "external_nonlinear_result_schema_invalid"
        ) from exc
    cases: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        receipt_case, _result = _validate_result(
            case=case,
            package_root=package_root,
            results_root=results_root,
            result_schema=result_schema,
        )
        cases.append(receipt_case)
    technical_count = sum(row["technical_comparison_pass"] for row in cases)
    technical_pass = technical_count == len(cases)
    blockers = [
        *(["comparison_tolerance_exceeded"] if not technical_pass else []),
        "fresh_current_source_execution_not_attested",
        "independent_operator_attestation_missing",
        "product_legal_license_approval_missing",
        "formal_level2_promotion_receipt_missing",
    ]
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": manifest["source_commit_sha"],
        "package_binding": {
            "package_id": manifest["package_id"],
            "path": _relative(repo_root, package_root / package_builder.MANIFEST_NAME),
            "file_sha256": _file_hash(package_root / package_builder.MANIFEST_NAME),
            "artifact_hash": manifest["artifact_hash"],
            "source_commit_sha": manifest["source_commit_sha"],
        },
        "runtime_policy": {
            "openseespy_version": package_builder.PINNED_OPENSEESPY_VERSION,
            "opensees_core_version": package_builder.PINNED_OPENSEES_CORE_VERSION,
        },
        "cases": cases,
        "summary": {
            "case_count": len(cases),
            "self_consistent_result_count": len(cases),
            "technical_comparison_pass_count": technical_count,
        },
        "status": "technical_pass" if technical_pass else "technical_blocked",
        "technical_contract_pass": technical_pass,
        "claims": {
            "package_bytes_authenticated": True,
            "external_results_self_consistent": True,
            "fresh_current_source_external_execution": False,
            "independent_operator_attested": False,
            "legal_use_approved": False,
            "verification_matrix_credit": False,
            "verification_level_2": False,
        },
        "blockers": sorted(set(blockers)),
        "claim_boundary": (
            "This receipt authenticates six packaged inputs, product references, "
            "runner bytes, self-hashed OpenSees outputs and pinned runtime versions, "
            "then evaluates only the declared bounded technical metrics. It does "
            "not authenticate the operator identity or source environment, approve "
            "licenses, grant matrix credit or Verification Level 2, establish design "
            "authority, prove commercial equivalence, or create release readiness."
        ),
        "artifact_hash": ZERO_HASH,
    }
    receipt["artifact_hash"] = _artifact_hash(receipt)
    _validate_receipt(receipt, repo_root)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-dir", type=Path, default=package_builder.DEFAULT_OUT_DIR
    )
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fail-technical-blocked", action="store_true")
    args = parser.parse_args()
    try:
        receipt = build_execution_receipt(
            package_dir=args.package_dir,
            results_dir=args.results_dir,
        )
    except ExternalNonlinearMaterialRecoveryResultError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    out = _resolved(ROOT, args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            receipt, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "bounded planar nonlinear/material/recovery receipt: "
        f"technical={receipt['summary']['technical_comparison_pass_count']}/"
        f"{receipt['summary']['case_count']}"
    )
    if args.fail_technical_blocked and not receipt["technical_contract_pass"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
