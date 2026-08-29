#!/usr/bin/env python3
"""Validate two OpenSees results into a non-promoting technical receipt."""

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
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_bounded_planar_external_linear_case_package as package_builder  # noqa: E402
from strict_json import StrictJSONError, strict_json_load_path  # noqa: E402


SCHEMA_VERSION = "bounded-planar-external-linear-execution-receipt.v1"
RECEIPT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_linear_execution_receipt_v1.schema.json"
)
DEFAULT_PACKAGE_DIR = package_builder.DEFAULT_OUT_DIR
_ZERO_HASH = "sha256:" + "0" * 64
_RELATIVE_TOLERANCE = 1.0e-5
_NODE_ABSOLUTE_TOLERANCE = 1.0e-8
_REACTION_ABSOLUTE_TOLERANCE = 1.0e-5


class ExternalLinearResultError(ValueError):
    """Stable failure for untrusted or inconsistent external result input."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalLinearResultError(code)


def _resolved(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


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
        value = strict_json_load_path(path)
    except (OSError, StrictJSONError) as exc:
        raise ExternalLinearResultError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return value


def _validate_timestamp(value: str, case_id: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExternalLinearResultError(
            f"external_linear_result_timestamp_invalid:{case_id}"
        ) from exc
    if parsed.tzinfo is None:
        _fail(f"external_linear_result_timestamp_timezone_missing:{case_id}")


def _comparison(
    metric_id: str, product_value: object, external_value: object
) -> dict[str, Any]:
    if (
        isinstance(product_value, bool)
        or isinstance(external_value, bool)
        or not isinstance(product_value, (int, float))
        or not isinstance(external_value, (int, float))
    ):
        _fail(f"external_linear_result_metric_not_numeric:{metric_id}")
    product = float(product_value)
    external = float(external_value)
    if not math.isfinite(product) or not math.isfinite(external):
        _fail(f"external_linear_result_metric_not_finite:{metric_id}")
    absolute_error = abs(product - external)
    scale = max(abs(product), abs(external))
    relative_error = absolute_error / scale if scale > 0.0 else 0.0
    absolute_tolerance = (
        _REACTION_ABSOLUTE_TOLERANCE
        if metric_id.startswith("reaction.")
        else _NODE_ABSOLUTE_TOLERANCE
    )
    tolerance = absolute_tolerance + _RELATIVE_TOLERANCE * scale
    return {
        "metric_id": metric_id,
        "product_value": product,
        "external_value": external,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": _RELATIVE_TOLERANCE,
        "contract_pass": absolute_error <= tolerance,
    }


def _validate_result(
    *,
    result_path: Path,
    result_schema: dict[str, Any],
    package_id: str,
    case: dict[str, Any],
    package_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = str(case["case_id"])
    result = _load_json(result_path, f"external_linear_result_unreadable:{case_id}")
    try:
        Draft202012Validator(result_schema, format_checker=FormatChecker()).validate(
            result
        )
    except ValidationError as exc:
        raise ExternalLinearResultError(
            f"external_linear_result_schema_invalid:{case_id}"
        ) from exc
    if result.get("artifact_hash") != _artifact_hash(result):
        _fail(f"external_linear_result_artifact_hash_invalid:{case_id}")
    if result.get("package_id") != package_id or result.get("case_id") != case_id:
        _fail(f"external_linear_result_identity_mismatch:{case_id}")
    _validate_timestamp(str(result["executed_at"]), case_id)
    if result.get("contract_pass") is not True or result.get("blockers") != []:
        _fail(f"external_linear_result_contract_blocked:{case_id}")
    if result.get("return_codes") != [0, 0, 0, 0]:
        _fail(f"external_linear_result_return_codes_invalid:{case_id}")
    runtime = result["runtime"]
    if runtime.get("openseespy_version") != package_builder._PINNED_OPENSEESPY_VERSION:
        _fail(f"external_linear_result_openseespy_version_invalid:{case_id}")
    if (
        runtime.get("opensees_core_version")
        != package_builder._PINNED_OPENSEES_CORE_VERSION
    ):
        _fail(f"external_linear_result_opensees_core_version_invalid:{case_id}")
    if result.get("runner_file_sha256") != case["opensees_runner"]["file_sha256"]:
        _fail(f"external_linear_result_runner_hash_mismatch:{case_id}")
    if result.get("source_model_file_sha256") != case["model_ir"]["file_sha256"]:
        _fail(f"external_linear_result_model_hash_mismatch:{case_id}")
    runner_path = package_root / case["opensees_runner"]["path"]
    model_path = package_root / case["model_ir"]["path"]
    if _file_hash(runner_path) != result["runner_file_sha256"]:
        _fail(f"external_linear_result_runner_bytes_mismatch:{case_id}")
    if _file_hash(model_path) != result["source_model_file_sha256"]:
        _fail(f"external_linear_result_model_bytes_mismatch:{case_id}")

    product_path = package_root / case["product_result"]["path"]
    product = _load_json(
        product_path, f"external_linear_product_result_unreadable:{case_id}"
    )
    product_metrics = product.get("metrics")
    external_metrics = result.get("metrics")
    expected_ids = list(case["metric_ids"])
    if not isinstance(product_metrics, dict) or set(product_metrics) != set(
        expected_ids
    ):
        _fail(f"external_linear_product_metric_set_invalid:{case_id}")
    if not isinstance(external_metrics, dict) or set(external_metrics) != set(
        expected_ids
    ):
        _fail(f"external_linear_result_metric_set_invalid:{case_id}")
    comparisons = [
        _comparison(metric_id, product_metrics[metric_id], external_metrics[metric_id])
        for metric_id in expected_ids
    ]
    return result, comparisons


def _load_receipt_schema(repo_root: Path) -> dict[str, Any]:
    schema = _load_json(
        repo_root / RECEIPT_SCHEMA_PATH,
        "external_linear_execution_receipt_schema_unreadable",
    )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ExternalLinearResultError(
            "external_linear_execution_receipt_schema_invalid"
        ) from exc
    return schema


def _validate_receipt(receipt: dict[str, Any], repo_root: Path) -> None:
    schema = _load_receipt_schema(repo_root)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(receipt)
    except ValidationError as exc:
        raise ExternalLinearResultError(
            "external_linear_execution_receipt_invalid"
        ) from exc
    if receipt["artifact_hash"] != _artifact_hash(receipt):
        _fail("external_linear_execution_receipt_hash_invalid")
    technical_count = sum(row["technical_comparison_pass"] for row in receipt["cases"])
    if receipt["summary"]["technical_comparison_pass_count"] != technical_count:
        _fail("external_linear_execution_receipt_summary_invalid")
    expected_pass = technical_count == len(receipt["cases"])
    if receipt["technical_contract_pass"] is not expected_pass:
        _fail("external_linear_execution_receipt_contract_invalid")
    expected_status = "technical_pass" if expected_pass else "technical_blocked"
    if receipt["status"] != expected_status:
        _fail("external_linear_execution_receipt_status_invalid")


def build_execution_receipt(
    *,
    repo_root: Path = ROOT,
    package_dir: Path = DEFAULT_PACKAGE_DIR,
    results_dir: Path,
) -> dict[str, Any]:
    package_root = _resolved(repo_root, package_dir).resolve()
    manifest = package_builder.validate_package_directory(
        repo_root=repo_root, out_dir=package_root
    )
    result_schema_path = package_root / manifest["external_result_schema"]["path"]
    result_schema = _load_json(
        result_schema_path, "external_linear_result_schema_unreadable"
    )
    try:
        Draft202012Validator.check_schema(result_schema)
    except SchemaError as exc:
        raise ExternalLinearResultError(
            "external_linear_result_schema_invalid"
        ) from exc
    actual_results_root = _resolved(repo_root, results_dir).resolve()
    case_rows: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        case_id = str(case["case_id"])
        result_path = actual_results_root / f"{case_id}.json"
        result, comparisons = _validate_result(
            result_path=result_path,
            result_schema=result_schema,
            package_id=str(manifest["package_id"]),
            case=case,
            package_root=package_root,
        )
        comparison_pass = all(row["contract_pass"] for row in comparisons)
        case_rows.append(
            {
                "case_id": case_id,
                "requirement_id": case["requirement_id"],
                "external_result": {
                    "path": _relative(repo_root, result_path),
                    "file_sha256": _file_hash(result_path),
                    "artifact_hash": result["artifact_hash"],
                    "executed_at": result["executed_at"],
                    "runner_file_sha256": result["runner_file_sha256"],
                    "source_model_file_sha256": result["source_model_file_sha256"],
                    "runtime": result["runtime"],
                },
                "metric_comparisons": comparisons,
                "maximum_absolute_error": max(
                    row["absolute_error"] for row in comparisons
                ),
                "maximum_relative_error": max(
                    row["relative_error"] for row in comparisons
                ),
                "technical_comparison_pass": comparison_pass,
                "blockers": (
                    [] if comparison_pass else ["comparison_tolerance_exceeded"]
                ),
            }
        )
    technical_count = sum(row["technical_comparison_pass"] for row in case_rows)
    technical_pass = technical_count == len(case_rows)
    blockers = [
        *([] if technical_pass else ["comparison_tolerance_exceeded"]),
        "fresh_current_source_execution_not_attested",
        "independent_operator_attestation_missing",
        "product_legal_license_approval_missing",
        "formal_level2_promotion_receipt_missing",
    ]
    manifest_path = package_root / package_builder.MANIFEST_NAME
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": manifest["source_commit_sha"],
        "package_binding": {
            "package_id": manifest["package_id"],
            "path": _relative(repo_root, manifest_path),
            "file_sha256": _file_hash(manifest_path),
            "artifact_hash": manifest["artifact_hash"],
            "source_commit_sha": manifest["source_commit_sha"],
        },
        "runtime_policy": {
            "openseespy_version": package_builder._PINNED_OPENSEESPY_VERSION,
            "opensees_core_version": package_builder._PINNED_OPENSEES_CORE_VERSION,
        },
        "cases": case_rows,
        "summary": {
            "case_count": len(case_rows),
            "self_consistent_result_count": len(case_rows),
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
        "blockers": blockers,
        "claim_boundary": (
            "This receipt authenticates the packaged model and runner bytes, validates "
            "the self-hashed OpenSees result structures and pinned runtime versions, "
            "and evaluates bounded technical metrics. It does not authenticate the "
            "operator identity or source environment, approve source use or licenses, "
            "grant V&V matrix credit or Verification Level 2, establish design "
            "authority, prove commercial equivalence, or create release readiness."
        ),
        "artifact_hash": _ZERO_HASH,
    }
    receipt["artifact_hash"] = _artifact_hash(receipt)
    _validate_receipt(receipt, repo_root)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE_DIR)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fail-technical-blocked", action="store_true")
    args = parser.parse_args()
    try:
        receipt = build_execution_receipt(
            package_dir=args.package_dir,
            results_dir=args.results_dir,
        )
    except ExternalLinearResultError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    target = _resolved(ROOT, args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            receipt, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "bounded planar external linear receipt: "
        f"{receipt['status']} | "
        f"comparisons={receipt['summary']['technical_comparison_pass_count']}/2 | "
        "matrix_credit=false"
    )
    if args.fail_technical_blocked and not receipt["technical_contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
