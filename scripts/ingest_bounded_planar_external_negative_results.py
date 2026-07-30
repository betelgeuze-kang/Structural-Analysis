#!/usr/bin/env python3
"""Validate three expected-rejection outputs into a non-promoting receipt."""

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

import build_bounded_planar_external_negative_case_package as package_builder  # noqa: E402


SCHEMA_VERSION = "bounded-planar-external-negative-execution-receipt.v1"
RECEIPT_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_negative_execution_receipt_v1.schema.json"
)
DEFAULT_PACKAGE_DIR = package_builder.DEFAULT_OUT_DIR
_ZERO_HASH = "sha256:" + "0" * 64


class ExternalNegativeResultError(ValueError):
    """Stable failure for untrusted or inconsistent negative result input."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalNegativeResultError(code)


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
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalNegativeResultError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return value


def _validate_timestamp(value: str, case_id: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExternalNegativeResultError(
            f"external_negative_result_timestamp_invalid:{case_id}"
        ) from exc
    if parsed.tzinfo is None:
        _fail(f"external_negative_result_timestamp_timezone_missing:{case_id}")


def _validate_result_semantics(result: dict[str, Any], case: dict[str, Any]) -> str:
    case_id = str(case["case_id"])
    requirement_id = str(case["requirement_id"])
    if result["observation"] != case["expected_external_observation"]:
        _fail(f"external_negative_result_observation_mismatch:{case_id}")
    if result["classification_match"] is not True:
        _fail(f"external_negative_result_classification_mismatch:{case_id}")

    if requirement_id == "negative.invalid_geometry":
        if not (
            result["external_engine_invoked"] is False
            and result["model_construction_succeeded"] is False
            and result["analysis_return_code"] is None
            and result["exception_type"] is None
            and result["tangent_rank_check"] is None
        ):
            _fail(f"external_negative_result_invalid_geometry_authority:{case_id}")
        return "independent_input_contract_rejection"

    rank_rejected = False
    rank_check = result["tangent_rank_check"]
    if requirement_id == "negative.singular" and rank_check is not None:
        equation_count = int(rank_check["equation_count"])
        matrix_value_count = int(rank_check["matrix_value_count"])
        maximum_absolute_entry = float(rank_check["maximum_absolute_entry"])
        relative_pivot_tolerance = float(
            rank_check["relative_pivot_tolerance"]
        )
        absolute_pivot_tolerance = float(
            rank_check["absolute_pivot_tolerance"]
        )
        numerical_rank = int(rank_check["numerical_rank"])
        expected_absolute_tolerance = (
            maximum_absolute_entry
            * equation_count
            * relative_pivot_tolerance
        )
        expected_rank_deficient = numerical_rank < equation_count
        if not (
            equation_count > 0
            and matrix_value_count == equation_count**2
            and math.isfinite(maximum_absolute_entry)
            and maximum_absolute_entry >= 0.0
            and relative_pivot_tolerance == 1.0e-12
            and math.isfinite(absolute_pivot_tolerance)
            and math.isclose(
                absolute_pivot_tolerance,
                expected_absolute_tolerance,
                rel_tol=1.0e-12,
                abs_tol=1.0e-30,
            )
            and 0 <= numerical_rank <= equation_count
            and rank_check["rank_deficient"] is expected_rank_deficient
            and result["model_construction_succeeded"] is True
        ):
            _fail(f"external_negative_result_tangent_rank_invalid:{case_id}")
        rank_rejected = expected_rank_deficient
    elif rank_check is not None:
        _fail(f"external_negative_result_tangent_rank_unexpected:{case_id}")

    solver_rejected = result["exception_type"] is not None or (
        isinstance(result["analysis_return_code"], int)
        and not isinstance(result["analysis_return_code"], bool)
        and result["analysis_return_code"] != 0
    )
    rejected = solver_rejected or rank_rejected
    if result["external_engine_invoked"] is not True or not rejected:
        _fail(f"external_negative_result_solver_rejection_missing:{case_id}")
    if rank_rejected:
        return "external_solver_tangent_rank_rejection"
    return "external_solver_expected_rejection"


def _validate_result(
    *,
    result_path: Path,
    result_schema: dict[str, Any],
    manifest: dict[str, Any],
    case: dict[str, Any],
    package_root: Path,
) -> tuple[dict[str, Any], str]:
    case_id = str(case["case_id"])
    result = _load_json(
        result_path, f"external_negative_result_unreadable:{case_id}"
    )
    try:
        Draft202012Validator(
            result_schema, format_checker=FormatChecker()
        ).validate(result)
    except ValidationError as exc:
        raise ExternalNegativeResultError(
            f"external_negative_result_schema_invalid:{case_id}"
        ) from exc
    if result.get("artifact_hash") != _artifact_hash(result):
        _fail(f"external_negative_result_artifact_hash_invalid:{case_id}")
    if (
        result.get("package_id") != manifest["package_id"]
        or result.get("case_id") != case_id
    ):
        _fail(f"external_negative_result_identity_mismatch:{case_id}")
    _validate_timestamp(str(result["executed_at"]), case_id)
    if result.get("contract_pass") is not True or result.get("blockers") != []:
        _fail(f"external_negative_result_contract_blocked:{case_id}")
    runtime = result["runtime"]
    if runtime.get("openseespy_version") != package_builder._PINNED_OPENSEESPY_VERSION:
        _fail(f"external_negative_result_openseespy_version_invalid:{case_id}")
    if runtime.get("opensees_core_version") != package_builder._PINNED_OPENSEES_CORE_VERSION:
        _fail(f"external_negative_result_opensees_core_version_invalid:{case_id}")
    if result.get("runner_file_sha256") != case["opensees_runner"]["file_sha256"]:
        _fail(f"external_negative_result_runner_hash_mismatch:{case_id}")
    if result.get("source_model_file_sha256") != case["model_ir"]["file_sha256"]:
        _fail(f"external_negative_result_model_hash_mismatch:{case_id}")
    runner_path = package_root / case["opensees_runner"]["path"]
    model_path = package_root / case["model_ir"]["path"]
    if _file_hash(runner_path) != result["runner_file_sha256"]:
        _fail(f"external_negative_result_runner_bytes_mismatch:{case_id}")
    if _file_hash(model_path) != result["source_model_file_sha256"]:
        _fail(f"external_negative_result_model_bytes_mismatch:{case_id}")
    return result, _validate_result_semantics(result, case)


def _load_receipt_schema(repo_root: Path) -> dict[str, Any]:
    schema = _load_json(
        repo_root / RECEIPT_SCHEMA_PATH,
        "external_negative_execution_receipt_schema_unreadable",
    )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ExternalNegativeResultError(
            "external_negative_execution_receipt_schema_invalid"
        ) from exc
    return schema


def _validate_receipt(receipt: dict[str, Any], repo_root: Path) -> None:
    try:
        Draft202012Validator(
            _load_receipt_schema(repo_root), format_checker=FormatChecker()
        ).validate(receipt)
    except ValidationError as exc:
        raise ExternalNegativeResultError(
            "external_negative_execution_receipt_invalid"
        ) from exc
    if receipt["artifact_hash"] != _artifact_hash(receipt):
        _fail("external_negative_execution_receipt_hash_invalid")
    if receipt["summary"] != {
        "case_count": 3,
        "self_consistent_result_count": 3,
        "external_engine_invoked_case_count": 2,
        "independent_preflight_case_count": 1,
        "technical_rejection_pass_count": 3,
    }:
        _fail("external_negative_execution_receipt_summary_invalid")
    if [row["requirement_id"] for row in receipt["cases"]] != [
        "negative.mechanism",
        "negative.singular",
        "negative.invalid_geometry",
    ]:
        _fail("external_negative_execution_receipt_case_order_invalid")


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
    result_schema = _load_json(
        package_root / manifest["external_result_schema"]["path"],
        "external_negative_result_schema_unreadable",
    )
    try:
        Draft202012Validator.check_schema(result_schema)
    except SchemaError as exc:
        raise ExternalNegativeResultError(
            "external_negative_result_schema_invalid"
        ) from exc
    results_root = _resolved(repo_root, results_dir).resolve()
    expected_names = {
        f"{case['case_id']}.json" for case in manifest["cases"]
    }
    actual_names = {
        path.name for path in results_root.glob("*.json") if path.is_file()
    }
    if actual_names != expected_names:
        _fail("external_negative_result_file_set_invalid")

    cases: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        case_id = str(case["case_id"])
        result_path = results_root / f"{case_id}.json"
        result, authority = _validate_result(
            result_path=result_path,
            result_schema=result_schema,
            manifest=manifest,
            case=case,
            package_root=package_root,
        )
        cases.append(
            {
                "case_id": case_id,
                "requirement_id": case["requirement_id"],
                "rejection_authority": authority,
                "external_result": {
                    "path": _relative(repo_root, result_path),
                    "file_sha256": _file_hash(result_path),
                    "artifact_hash": result["artifact_hash"],
                    "executed_at": result["executed_at"],
                    "runner_file_sha256": result["runner_file_sha256"],
                    "source_model_file_sha256": result[
                        "source_model_file_sha256"
                    ],
                    "runtime": result["runtime"],
                    "external_engine_invoked": result["external_engine_invoked"],
                    "model_construction_succeeded": result[
                        "model_construction_succeeded"
                    ],
                    "analysis_return_code": result["analysis_return_code"],
                    "exception_type": result["exception_type"],
                    "tangent_rank_check": result["tangent_rank_check"],
                    "observation": result["observation"],
                },
                "technical_rejection_pass": True,
                "blockers": [],
            }
        )
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
        "cases": cases,
        "summary": {
            "case_count": 3,
            "self_consistent_result_count": 3,
            "external_engine_invoked_case_count": 2,
            "independent_preflight_case_count": 1,
            "technical_rejection_pass_count": 3,
        },
        "status": "technical_pass",
        "technical_contract_pass": True,
        "claims": {
            "package_bytes_authenticated": True,
            "external_results_self_consistent": True,
            "exact_rejection_classifications": True,
            "invalid_geometry_external_solver_execution": False,
            "fresh_current_source_external_execution": False,
            "independent_operator_attested": False,
            "legal_use_approved": False,
            "verification_matrix_credit": False,
            "verification_level_2": False,
        },
        "blockers": [
            "fresh_current_source_execution_not_attested",
            "independent_operator_attestation_missing",
            "product_legal_license_approval_missing",
            "formal_level2_promotion_receipt_missing",
        ],
        "claim_boundary": (
            "This receipt authenticates package, model, runner, and result bytes and "
            "validates three exact expected-rejection classifications. OpenSees engine "
            "rejection exists only for the mechanism and singular cases; invalid "
            "geometry is an independent checksum-bound preflight and is not an external "
            "solver execution. Operator identity, fresh-source provenance, license "
            "approval, matrix credit, Verification Level 2, design authority, "
            "commercial equivalence, and release readiness remain unavailable."
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
    except ExternalNegativeResultError as exc:
        print(exc.code, file=sys.stderr)
        return 2
    output = _resolved(ROOT, args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "bounded planar negative execution receipt: technical_pass | "
        "engine=2/3 | independent_preflight=1/3 | matrix_credit=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
