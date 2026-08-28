#!/usr/bin/env python3
"""Validate exact modal/buckling results into a non-promoting receipt."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_bounded_planar_external_modal_buckling_case_package as package_builder  # noqa: E402
from strict_json import StrictJSONError, strict_json_load_path  # noqa: E402


SCHEMA_VERSION = "bounded-planar-external-modal-buckling-execution-receipt.v1"
RECEIPT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_modal_buckling_execution_receipt_v1.schema.json"
)
DEFAULT_PACKAGE_DIR = package_builder.DEFAULT_OUT_DIR
ZERO_HASH = "sha256:" + "0" * 64
MODAL_EIGEN_RELATIVE_TOLERANCE = 1.0e-6
BUCKLING_FACTOR_RELATIVE_TOLERANCE = 5.0e-2
ABSOLUTE_TOLERANCE = 1.0e-9
REPEATED_SUBSPACE_CORRELATION_MINIMUM = 0.999


class ExternalModalBucklingResultError(ValueError):
    """Stable failure for an untrusted or inconsistent external result."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalModalBucklingResultError(code)


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
    return _hash_bytes(path.read_bytes())


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = deepcopy(payload)
    body.pop("artifact_hash", None)
    return _hash_bytes(_canonical_bytes(body))


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = strict_json_load_path(path)
    except (OSError, StrictJSONError) as exc:
        raise ExternalModalBucklingResultError(code) from exc
    if not isinstance(payload, dict):
        _fail(code)
    return payload


def _git_head(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _validate_timestamp(value: object, case_id: str) -> None:
    if not isinstance(value, str):
        _fail(f"external_modal_buckling_timestamp_invalid:{case_id}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExternalModalBucklingResultError(
            f"external_modal_buckling_timestamp_invalid:{case_id}"
        ) from exc
    if parsed.tzinfo is None:
        _fail(f"external_modal_buckling_timestamp_timezone_missing:{case_id}")


def _finite_vector(value: object, code: str) -> list[float]:
    if not isinstance(value, list):
        _fail(code)
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            _fail(code)
        number = float(item)
        if not math.isfinite(number):
            _fail(code)
        result.append(number)
    if not result:
        _fail(code)
    return result


def _eigenvalue_comparison(
    *,
    metric_id: str,
    product: float,
    external: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    absolute_error = abs(product - external)
    scale = max(abs(product), abs(external))
    relative_error = absolute_error / scale if scale else 0.0
    return {
        "metric_id": metric_id,
        "product_value": product,
        "external_value": external,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "absolute_tolerance": ABSOLUTE_TOLERANCE,
        "relative_tolerance": relative_tolerance,
        "contract_pass": absolute_error
        <= ABSOLUTE_TOLERANCE + relative_tolerance * scale,
    }


def _rigid_count_comparison(product: object, external: object) -> dict[str, Any]:
    if (
        isinstance(product, bool)
        or isinstance(external, bool)
        or not isinstance(product, int)
        or not isinstance(external, int)
    ):
        _fail("external_modal_buckling_rigid_mode_count_invalid")
    error = float(abs(product - external))
    return {
        "metric_id": "rigid_mode_count",
        "product_value": float(product),
        "external_value": float(external),
        "absolute_error": error,
        "relative_error": error / max(float(product), float(external), 1.0),
        "absolute_tolerance": 0.0,
        "relative_tolerance": 0.0,
        "contract_pass": error == 0.0,
    }


def _subspace_comparison(
    product_vectors: object, external_vectors: object
) -> dict[str, Any]:
    if not isinstance(product_vectors, list) or not isinstance(external_vectors, list):
        _fail("external_modal_buckling_repeated_vectors_invalid")
    product_rows = [
        _finite_vector(row, "external_modal_buckling_repeated_vectors_invalid")
        for row in product_vectors[:2]
    ]
    external_rows = [
        _finite_vector(row, "external_modal_buckling_repeated_vectors_invalid")
        for row in external_vectors[:2]
    ]
    if (
        len(product_rows) != 2
        or len(external_rows) != 2
        or len({len(row) for row in product_rows + external_rows}) != 1
    ):
        _fail("external_modal_buckling_repeated_vectors_invalid")
    product_basis, _ = np.linalg.qr(np.asarray(product_rows, dtype=np.float64).T)
    external_basis, _ = np.linalg.qr(np.asarray(external_rows, dtype=np.float64).T)
    singular = np.linalg.svd(product_basis.T @ external_basis, compute_uv=False)
    minimum = float(np.min(singular))
    if not math.isfinite(minimum):
        _fail("external_modal_buckling_repeated_subspace_invalid")
    return {
        "metric_id": "repeated_mode_minimum_subspace_correlation",
        "product_value": 1.0,
        "external_value": minimum,
        "absolute_error": abs(1.0 - minimum),
        "relative_error": abs(1.0 - minimum),
        "absolute_tolerance": 1.0 - REPEATED_SUBSPACE_CORRELATION_MINIMUM,
        "relative_tolerance": 0.0,
        "contract_pass": minimum >= REPEATED_SUBSPACE_CORRELATION_MINIMUM,
    }


def _comparisons(
    *, case: dict[str, Any], product: dict[str, Any], result: dict[str, Any]
) -> list[dict[str, Any]]:
    product_observations = product.get("observations")
    external_observations = result.get("observations")
    if not isinstance(product_observations, dict) or not isinstance(
        external_observations, dict
    ):
        _fail(f"external_modal_buckling_observations_invalid:{case['case_id']}")
    product_values = _finite_vector(
        product_observations.get("eigenvalues"),
        f"external_modal_buckling_product_eigenvalues_invalid:{case['case_id']}",
    )
    external_values = _finite_vector(
        external_observations.get("eigenvalues"),
        f"external_modal_buckling_external_eigenvalues_invalid:{case['case_id']}",
    )
    comparisons: list[dict[str, Any]] = []
    if case["requirement_id"] == "modal.rigid_mode":
        comparisons.append(
            _rigid_count_comparison(
                product_observations.get("rigid_mode_count"),
                external_observations.get("rigid_mode_count"),
            )
        )
        scale = max(abs(value) for value in external_values)
        threshold = max(1.0e-12, 1.0e-9 * scale)
        external_values = [value for value in external_values if value > threshold]
        relative_tolerance = MODAL_EIGEN_RELATIVE_TOLERANCE
    elif case["requirement_id"] == "modal.repeated_mode":
        relative_tolerance = MODAL_EIGEN_RELATIVE_TOLERANCE
        comparisons.append(
            _subspace_comparison(
                product_observations.get("mode_vectors"),
                external_observations.get("mode_vectors"),
            )
        )
    else:
        relative_tolerance = BUCKLING_FACTOR_RELATIVE_TOLERANCE
    if len(product_values) != len(external_values):
        _fail(f"external_modal_buckling_eigenvalue_count_invalid:{case['case_id']}")
    comparisons.extend(
        _eigenvalue_comparison(
            metric_id=f"eigenvalue_{index}",
            product=product_value,
            external=external_value,
            relative_tolerance=relative_tolerance,
        )
        for index, (product_value, external_value) in enumerate(
            zip(product_values, external_values, strict=True), start=1
        )
    )
    return comparisons


def _validate_result(
    *,
    result_path: Path,
    result_schema: dict[str, Any],
    manifest: dict[str, Any],
    case: dict[str, Any],
    package_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = str(case["case_id"])
    result = _load_json(
        result_path, f"external_modal_buckling_result_unreadable:{case_id}"
    )
    try:
        Draft202012Validator(result_schema, format_checker=FormatChecker()).validate(
            result
        )
    except ValidationError as exc:
        raise ExternalModalBucklingResultError(
            f"external_modal_buckling_result_schema_invalid:{case_id}"
        ) from exc
    if result.get("artifact_hash") != _artifact_hash(result):
        _fail(f"external_modal_buckling_result_artifact_hash_invalid:{case_id}")
    if (
        result.get("package_id") != manifest["package_id"]
        or result.get("case_id") != case_id
        or result.get("analysis_type") != case["analysis_type"]
        or result.get("external_solver") != case["external_solver"]
    ):
        _fail(f"external_modal_buckling_result_identity_mismatch:{case_id}")
    _validate_timestamp(result.get("executed_at"), case_id)
    if result.get("contract_pass") is not True or result.get("blockers") != []:
        _fail(f"external_modal_buckling_result_contract_blocked:{case_id}")
    expected_version = (
        package_builder.PINNED_OPENSEES_CORE_VERSION
        if case["external_solver"] == "OpenSees"
        else package_builder.PINNED_CALCULIX_VERSION
    )
    if result["runtime"].get("solver_version") != expected_version:
        _fail(f"external_modal_buckling_result_solver_version_invalid:{case_id}")
    if result.get("runner_file_sha256") != case["external_runner"]["file_sha256"]:
        _fail(f"external_modal_buckling_result_runner_hash_mismatch:{case_id}")
    if result.get("source_model_file_sha256") != case["model"]["file_sha256"]:
        _fail(f"external_modal_buckling_result_model_hash_mismatch:{case_id}")
    if (
        _file_hash(package_root / case["external_runner"]["path"])
        != case["external_runner"]["file_sha256"]
    ):
        _fail(f"external_modal_buckling_runner_bytes_mismatch:{case_id}")
    if _file_hash(package_root / case["model"]["path"]) != case["model"]["file_sha256"]:
        _fail(f"external_modal_buckling_model_bytes_mismatch:{case_id}")
    product = _load_json(
        package_root / case["product_result"]["path"],
        f"external_modal_buckling_product_result_unreadable:{case_id}",
    )
    if (
        product.get("artifact_hash") != case["product_result"]["artifact_hash"]
        or product.get("source_model_file_sha256") != case["model"]["file_sha256"]
        or product.get("contract_pass") is not True
    ):
        _fail(f"external_modal_buckling_product_result_invalid:{case_id}")
    return result, _comparisons(case=case, product=product, result=result)


def _validate_receipt(receipt: dict[str, Any], repo_root: Path = ROOT) -> None:
    schema = _load_json(
        repo_root / RECEIPT_SCHEMA_PATH,
        "external_modal_buckling_receipt_schema_unreadable",
    )
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(receipt)
    except (SchemaError, ValidationError) as exc:
        raise ExternalModalBucklingResultError(
            "external_modal_buckling_receipt_schema_invalid"
        ) from exc
    if receipt.get("artifact_hash") != _artifact_hash(receipt):
        _fail("external_modal_buckling_receipt_artifact_hash_invalid")
    cases = receipt.get("cases")
    summary = receipt.get("summary")
    claims = receipt.get("claims")
    if (
        not isinstance(cases, list)
        or len(cases) != 3
        or not isinstance(summary, dict)
        or summary.get("case_count") != len(cases)
        or summary.get("technical_pass_count")
        != sum(1 for row in cases if row.get("technical_contract_pass") is True)
        or receipt.get("technical_contract_pass")
        is not all(row.get("technical_contract_pass") is True for row in cases)
        or not isinstance(claims, dict)
        or not isinstance(claims.get("fresh_external_solver_execution"), bool)
        or claims.get("same_operator_technical_comparison") is not True
        or claims.get("independent_operator_attested") is not False
        or claims.get("legal_use_approved") is not False
        or claims.get("verification_matrix_credit") is not False
        or claims.get("verification_level_2") is not False
    ):
        _fail("external_modal_buckling_receipt_contract_invalid")


def build_receipt(
    *,
    repo_root: Path = ROOT,
    package_dir: Path = DEFAULT_PACKAGE_DIR,
    results_dir: Path,
) -> dict[str, Any]:
    package_root = _resolved(repo_root, package_dir)
    results_root = _resolved(repo_root, results_dir)
    try:
        manifest = package_builder.validate_package_directory(
            repo_root=repo_root, out_dir=package_root
        )
    except Exception as exc:
        raise ExternalModalBucklingResultError(
            "external_modal_buckling_package_validation_failed"
        ) from exc
    if manifest["source_commit_sha"] != _git_head(repo_root):
        _fail("external_modal_buckling_package_source_commit_mismatch")
    for source_path, source_hash in manifest["source_files"].items():
        if _file_hash(repo_root / source_path) != source_hash:
            _fail(f"external_modal_buckling_source_file_mismatch:{source_path}")
    result_schema = _load_json(
        package_root / manifest["external_result_schema"]["path"],
        "external_modal_buckling_result_schema_unreadable",
    )
    try:
        Draft202012Validator.check_schema(result_schema)
    except SchemaError as exc:
        raise ExternalModalBucklingResultError(
            "external_modal_buckling_result_schema_invalid"
        ) from exc
    rows: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        result_path = results_root / f"{case['case_id']}.json"
        result, comparisons = _validate_result(
            result_path=result_path,
            result_schema=result_schema,
            manifest=manifest,
            case=case,
            package_root=package_root,
        )
        rows.append(
            {
                "case_id": case["case_id"],
                "requirement_id": case["requirement_id"],
                "external_solver_id": case["external_solver"],
                "result_path": _relative(repo_root, result_path),
                "result_file_sha256": _file_hash(result_path),
                "result_artifact_hash": result["artifact_hash"],
                "comparisons": comparisons,
                "technical_contract_pass": all(
                    row["contract_pass"] for row in comparisons
                ),
            }
        )
    technical_pass = all(row["technical_contract_pass"] for row in rows)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "package_id": manifest["package_id"],
        "source_commit_sha": manifest["source_commit_sha"],
        "package_manifest_file_sha256": _file_hash(
            package_root / package_builder.MANIFEST_NAME
        ),
        "package_manifest_artifact_hash": manifest["artifact_hash"],
        "cases": rows,
        "summary": {
            "case_count": len(rows),
            "technical_pass_count": sum(
                1 for row in rows if row["technical_contract_pass"]
            ),
        },
        "claims": {
            "fresh_external_solver_execution": False,
            "same_operator_technical_comparison": True,
            "independent_operator_attested": False,
            "legal_use_approved": False,
            "verification_matrix_credit": False,
            "verification_level_2": False,
        },
        "technical_contract_pass": technical_pass,
        "blockers": [
            "fresh_current_source_execution_not_attested",
            "independent_operator_attestation_missing",
            "legal_use_approval_missing",
            "formal_promotion_receipt_missing",
        ],
        "claim_boundary": (
            "This receipt validates source-bound same-operator technical execution "
            "for exactly three modal and buckling cases. Repeated modes use a "
            "basis-invariant subspace comparison. No independent operator identity, "
            "legal-use decision, or formal promotion receipt is attached, so it "
            "grants no Verification Level 2, design authority, or release authority."
        ),
        "artifact_hash": ZERO_HASH,
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
        receipt = build_receipt(
            package_dir=args.package_dir,
            results_dir=args.results_dir,
        )
    except ExternalModalBucklingResultError as exc:
        print(exc.code, file=sys.stderr)
        return 2
    output = _resolved(ROOT, args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "bounded planar modal/buckling technical receipt: "
        f"pass={receipt['summary']['technical_pass_count']}/3"
    )
    if args.fail_technical_blocked and not receipt["technical_contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
