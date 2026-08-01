#!/usr/bin/env python3
"""Validate a signed independent-operator external V&V submission bundle.

This validates bundle and detached-signature integrity only. It deliberately
does not authenticate the operator's real-world identity or grant Verification
Level 2, design, commercial, or release authority.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping, NoReturn

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_bounded_planar_external_linear_case_package as linear_package  # noqa: E402
import ingest_bounded_planar_external_linear_results as linear_ingest  # noqa: E402
import build_bounded_planar_external_modal_buckling_case_package as modal_buckling_package  # noqa: E402
import ingest_bounded_planar_external_modal_buckling_results as modal_buckling_ingest  # noqa: E402
import build_bounded_planar_external_negative_case_package as negative_package  # noqa: E402
import ingest_bounded_planar_external_negative_results as negative_ingest  # noqa: E402
import build_bounded_planar_external_scaling_case_package as scaling_package  # noqa: E402
import ingest_bounded_planar_external_scaling_results as scaling_ingest  # noqa: E402
import build_bounded_planar_external_nonlinear_material_recovery_case_package as nonlinear_material_recovery_package  # noqa: E402
import ingest_bounded_planar_external_nonlinear_material_recovery_results as nonlinear_material_recovery_ingest  # noqa: E402
import run_external_code_to_code_technical_receipt as code_receipt  # noqa: E402
import run_external_modal_buckling_technical_receipt as modal_receipt  # noqa: E402


SCHEMA_VERSION = "structural-analysis-external-vv-operator-attestation.v1"
VALIDATION_SCHEMA_VERSION = (
    "structural-analysis-external-vv-operator-attestation-validation.v1"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/external_vv_operator_attestation_v1.schema.json"
)
SUMMARY_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/external_vv_clean_runner_receipt_v1.schema.json"
)
CODE_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/external_code_to_code_technical_receipt_v1.schema.json"
)
MODAL_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/external_modal_buckling_technical_receipt_v1.schema.json"
)
LINEAR_PACKAGE_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_linear_case_package_v1.schema.json"
)
LINEAR_SUPPLEMENT_COMMANDS = (
    "python opensees/bounded_planar_linear_portal.py "
    "external-results/bounded_planar_linear_portal.json",
    "python opensees/bounded_planar_linear_multistory.py "
    "external-results/bounded_planar_linear_multistory.json",
)
MODAL_BUCKLING_SUPPLEMENT_COMMANDS = (
    "python runner/run_case.py --case-id bounded_planar_modal_rigid_mode "
    "--model models/bounded_planar_modal_rigid_mode.model.json "
    "--out external-results/bounded_planar_modal_rigid_mode.json",
    "python runner/run_case.py --case-id bounded_planar_modal_repeated_mode "
    "--model models/bounded_planar_modal_repeated_mode.model.json "
    "--out external-results/bounded_planar_modal_repeated_mode.json",
    "python runner/run_case.py --case-id bounded_planar_buckling_portal "
    "--model models/bounded_planar_buckling_portal.model.json "
    "--out external-results/bounded_planar_buckling_portal.json",
)
NEGATIVE_SUPPLEMENT_COMMANDS = (
    "python opensees/bounded_planar_negative_mechanism.py "
    "external-results/bounded_planar_negative_mechanism.json",
    "python opensees/bounded_planar_negative_singular.py "
    "external-results/bounded_planar_negative_singular.json",
    "python opensees/bounded_planar_negative_invalid_geometry.py "
    "external-results/bounded_planar_negative_invalid_geometry.json",
)
SCALING_SUPPLEMENT_COMMANDS = (
    "python opensees/bounded_planar_scaling_unit_invariance.py "
    "external-results/bounded_planar_scaling_unit_invariance.json",
    "python opensees/bounded_planar_scaling_characteristic_length_invariance.py "
    "external-results/bounded_planar_scaling_characteristic_length_invariance.json",
)
NONLINEAR_MATERIAL_RECOVERY_SUPPLEMENT_COMMANDS = tuple(
    "python runner/run_case.py "
    f"--case-id {case['case_id']} "
    f"--model models/{case['case_id']}.case.json "
    f"--out external-results/{case['case_id']}.json"
    for case in nonlinear_material_recovery_package.CASE_DEFINITIONS
)
_DEDICATED_SUPPLEMENT_CASE_IDS = frozenset(
    {
        "bounded_planar_linear_portal",
        "bounded_planar_linear_multistory",
        "bounded_planar_modal_rigid_mode",
        "bounded_planar_modal_repeated_mode",
        "bounded_planar_buckling_portal",
        "bounded_planar_negative_mechanism",
        "bounded_planar_negative_singular",
        "bounded_planar_negative_invalid_geometry",
        "bounded_planar_scaling_unit_invariance",
        "bounded_planar_scaling_characteristic_length_invariance",
        *(
            case["case_id"]
            for case in nonlinear_material_recovery_package.CASE_DEFINITIONS
        ),
    }
)
_PLACEHOLDERS = ("OWNER_INPUT_REQUIRED", "PLACEHOLDER", "TEMPLATE_ONLY")


class ExternalVVOperatorAttestationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise ExternalVVOperatorAttestationError(code)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def artifact_hash(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("artifact_hash", None)
    return sha256_bytes(canonical_bytes(body))


def signed_payload(attestation: Mapping[str, Any]) -> bytes:
    body = deepcopy(dict(attestation))
    body.pop("signature", None)
    return canonical_bytes(body)


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalVVOperatorAttestationError(code) from exc
    if type(value) is not dict:
        _fail(code)
    return value


def _schema(repo_root: Path) -> Draft202012Validator:
    raw = _load_json(repo_root / SCHEMA_PATH, "operator_attestation_schema_unreadable")
    Draft202012Validator.check_schema(raw)
    return Draft202012Validator(raw, format_checker=FormatChecker())


def _validate_schema(payload: Mapping[str, Any], repo_root: Path) -> None:
    errors = sorted(
        _schema(repo_root).iter_errors(payload),
        key=lambda row: tuple(str(item) for item in row.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(item) for item in errors[0].absolute_path)
        _fail(f"operator_attestation_schema_invalid:{path}")
    text = json.dumps(payload, ensure_ascii=False).upper()
    if any(marker in text for marker in _PLACEHOLDERS):
        _fail("operator_attestation_placeholder_rejected")


def _validate_artifact_schema(
    payload: Mapping[str, Any],
    *,
    repo_root: Path,
    schema_path: Path,
    code: str,
) -> None:
    raw = _load_json(repo_root / schema_path, f"{code}_schema_unreadable")
    Draft202012Validator.check_schema(raw)
    errors = sorted(
        Draft202012Validator(raw, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda row: tuple(str(item) for item in row.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(item) for item in errors[0].absolute_path)
        _fail(f"{code}_schema_invalid:{path}")


def _bundle_file(bundle_root: Path, relative: str) -> Path:
    root = bundle_root.resolve(strict=True)
    candidate = bundle_root / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_bundle_path_invalid"
        ) from exc
    if not resolved.is_file() or candidate.is_symlink():
        _fail("operator_attestation_bundle_file_invalid")
    return resolved


def _check_descriptor(
    descriptor: Mapping[str, Any], bundle_root: Path, *, json_artifact: bool
) -> tuple[Path, dict[str, Any] | None]:
    path = _bundle_file(bundle_root, str(descriptor["path"]))
    if file_sha256(path) != descriptor["file_sha256"]:
        _fail("operator_attestation_bundle_file_hash_mismatch")
    if not json_artifact:
        return path, None
    payload = _load_json(path, "operator_attestation_bundle_json_invalid")
    if payload.get("artifact_hash") != descriptor["artifact_hash"]:
        _fail("operator_attestation_bundle_artifact_binding_mismatch")
    if artifact_hash(payload) != descriptor["artifact_hash"]:
        _fail("operator_attestation_bundle_artifact_hash_invalid")
    return path, payload


def _fresh_child(payload: Mapping[str, Any], *, source_commit_sha: str) -> None:
    replay = payload.get("replay_provenance")
    if not isinstance(replay, Mapping):
        _fail("operator_attestation_child_replay_missing")
    if (
        payload.get("technical_contract_pass") is not True
        or payload.get("source_commit_sha") != source_commit_sha
        or replay.get("external_runtime_executed_in_this_generation") is not True
        or replay.get("external_execution_reused") is not False
        or replay.get("reuse_reason") is not None
        or replay.get("current_product_replay_pass") is not True
    ):
        _fail("operator_attestation_fresh_external_runtime_required")


def _current_repo_head(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_source_commit_unavailable"
        ) from exc
    return completed.stdout.strip()


def _require_sources_at_head(
    repo_root: Path,
    children: tuple[Mapping[str, Any], ...],
) -> None:
    source_paths = sorted(
        {
            str(path)
            for child in children
            for path in child["internal_source"]["input_checksums"]
        }
    )
    if not source_paths:
        _fail("operator_attestation_source_inventory_empty")
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", *source_paths],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        difference = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", *source_paths],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_source_commit_unavailable"
        ) from exc
    tracked_paths = {path for path in tracked.stdout.split("\0") if path}
    if tracked_paths != set(source_paths):
        _fail("operator_attestation_source_path_not_tracked")
    if difference.returncode == 1:
        _fail("operator_attestation_source_bytes_not_at_commit")
    if difference.returncode != 0:
        _fail("operator_attestation_source_commit_unavailable")


def _timestamp(value: object, code: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExternalVVOperatorAttestationError(code) from exc
    if parsed.tzinfo is None:
        _fail(code)
    return parsed


def _validate_bounded_planar_linear_bundle(
    row: Mapping[str, Any],
    *,
    bundle_root: Path,
    repo_root: Path,
    source_commit_sha: str,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path, manifest = _check_descriptor(
        row["execution_package_manifest"], bundle_root, json_artifact=True
    )
    assert manifest is not None
    _validate_artifact_schema(
        manifest,
        repo_root=repo_root,
        schema_path=LINEAR_PACKAGE_SCHEMA_PATH,
        code="operator_attestation_linear_package",
    )
    try:
        consistent, _reason = linear_package.check_package(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
        validated_manifest = linear_package.validate_package_directory(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_linear_package_invalid"
        ) from exc
    if (
        not consistent
        or validated_manifest != manifest
        or manifest.get("source_commit_sha") != source_commit_sha
    ):
        _fail("operator_attestation_linear_package_source_binding_invalid")

    _receipt_path, receipt = _check_descriptor(
        row["technical_receipt"], bundle_root, json_artifact=True
    )
    assert receipt is not None
    try:
        linear_ingest._validate_receipt(receipt, repo_root)
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_linear_receipt_invalid"
        ) from exc
    receipt_claims = receipt.get("claims")
    package_binding = receipt.get("package_binding")
    if (
        receipt.get("technical_contract_pass") is not True
        or receipt.get("status") != "technical_pass"
        or not isinstance(receipt_claims, Mapping)
        or receipt_claims.get("external_results_self_consistent") is not True
        or receipt_claims.get("verification_matrix_credit") is not False
        or receipt_claims.get("verification_level_2") is not False
        or not isinstance(package_binding, Mapping)
        or package_binding.get("source_commit_sha") != source_commit_sha
        or package_binding.get("artifact_hash") != manifest["artifact_hash"]
        or package_binding.get("file_sha256") != file_sha256(manifest_path)
    ):
        _fail("operator_attestation_linear_receipt_contract_invalid")

    result_schema_path = (
        manifest_path.parent / manifest["external_result_schema"]["path"]
    )
    result_rows = row["external_results"]
    assert isinstance(result_rows, list)
    submitted: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for descriptor in result_rows:
        assert isinstance(descriptor, Mapping)
        _path, result = _check_descriptor(descriptor, bundle_root, json_artifact=True)
        assert result is not None
        _validate_artifact_schema(
            result,
            repo_root=repo_root,
            schema_path=result_schema_path,
            code="operator_attestation_linear_result",
        )
        case_id = str(result.get("case_id") or "")
        if case_id in submitted:
            _fail("operator_attestation_linear_result_duplicate")
        submitted[case_id] = (descriptor, result)
    expected_case_ids = [str(case["case_id"]) for case in manifest["cases"]]
    if set(submitted) != set(expected_case_ids):
        _fail("operator_attestation_linear_result_set_invalid")
    receipt_cases = {
        str(case.get("case_id") or ""): case
        for case in receipt.get("cases", [])
        if isinstance(case, Mapping)
    }
    manifest_cases = {str(case["case_id"]): case for case in manifest["cases"]}
    started_at = _timestamp(
        execution.get("started_at"),
        "operator_attestation_execution_window_invalid",
    )
    completed_at = _timestamp(
        execution.get("completed_at"),
        "operator_attestation_execution_window_invalid",
    )
    if completed_at < started_at:
        _fail("operator_attestation_execution_window_invalid")
    for case_id in expected_case_ids:
        descriptor, result = submitted[case_id]
        receipt_case = receipt_cases.get(case_id)
        manifest_case = manifest_cases[case_id]
        external_binding = (
            receipt_case.get("external_result")
            if isinstance(receipt_case, Mapping)
            else None
        )
        executed_at = _timestamp(
            result.get("executed_at"),
            "operator_attestation_linear_result_timestamp_invalid",
        )
        runtime = result.get("runtime")
        if not (started_at <= executed_at <= completed_at):
            _fail("operator_attestation_linear_result_outside_execution_window")
        if not isinstance(runtime, Mapping) or runtime.get("platform") != execution.get(
            "host_platform"
        ):
            _fail("operator_attestation_linear_result_platform_mismatch")
        if (
            result.get("contract_pass") is not True
            or result.get("blockers") != []
            or result.get("runner_file_sha256")
            != manifest_case["opensees_runner"]["file_sha256"]
            or result.get("source_model_file_sha256")
            != manifest_case["model_ir"]["file_sha256"]
            or not isinstance(external_binding, Mapping)
            or external_binding.get("file_sha256") != descriptor["file_sha256"]
            or external_binding.get("artifact_hash") != result["artifact_hash"]
            or receipt_case.get("technical_comparison_pass") is not True
        ):
            _fail("operator_attestation_linear_result_binding_invalid")
    return {
        "execution_package_artifact_hash": manifest["artifact_hash"],
        "technical_receipt_artifact_hash": receipt["artifact_hash"],
        "external_result_artifact_hashes": [
            submitted[case_id][1]["artifact_hash"] for case_id in expected_case_ids
        ],
        "case_ids": expected_case_ids,
        "source_commit_sha": source_commit_sha,
        "fresh_execution_declared_by_signer": True,
        "verification_matrix_credit": False,
    }


def _validate_bounded_planar_modal_buckling_bundle(
    row: Mapping[str, Any],
    *,
    bundle_root: Path,
    repo_root: Path,
    source_commit_sha: str,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path, manifest = _check_descriptor(
        row["execution_package_manifest"], bundle_root, json_artifact=True
    )
    assert manifest is not None
    try:
        validated_manifest = modal_buckling_package.validate_package_directory(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_modal_buckling_package_invalid"
        ) from exc
    if (
        validated_manifest != manifest
        or manifest.get("source_commit_sha") != source_commit_sha
    ):
        _fail("operator_attestation_modal_buckling_package_source_binding_invalid")
    source_files = manifest.get("source_files")
    if not isinstance(source_files, Mapping) or any(
        not (repo_root / str(path)).is_file()
        or file_sha256(repo_root / str(path)) != expected_hash
        for path, expected_hash in source_files.items()
    ):
        _fail("operator_attestation_modal_buckling_source_file_mismatch")

    _receipt_path, receipt = _check_descriptor(
        row["technical_receipt"], bundle_root, json_artifact=True
    )
    assert receipt is not None
    try:
        modal_buckling_ingest._validate_receipt(receipt, repo_root)
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_modal_buckling_receipt_invalid"
        ) from exc
    claims = receipt.get("claims")
    if (
        receipt.get("source_commit_sha") != source_commit_sha
        or receipt.get("technical_contract_pass") is not True
        or not isinstance(claims, Mapping)
        or claims.get("fresh_external_solver_execution") is not False
        or claims.get("same_operator_technical_comparison") is not True
        or claims.get("verification_matrix_credit") is not False
        or claims.get("verification_level_2") is not False
        or receipt.get("package_manifest_artifact_hash") != manifest["artifact_hash"]
        or receipt.get("package_manifest_file_sha256") != file_sha256(manifest_path)
    ):
        _fail("operator_attestation_modal_buckling_receipt_contract_invalid")

    result_schema = _load_json(
        manifest_path.parent / manifest["external_result_schema"]["path"],
        "operator_attestation_modal_buckling_result_schema_invalid",
    )
    submitted: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    result_rows = row["external_results"]
    assert isinstance(result_rows, list)
    for descriptor in result_rows:
        assert isinstance(descriptor, Mapping)
        _path, result = _check_descriptor(descriptor, bundle_root, json_artifact=True)
        assert result is not None
        case_id = str(result.get("case_id") or "")
        if case_id in submitted:
            _fail("operator_attestation_modal_buckling_result_duplicate")
        submitted[case_id] = (descriptor, result)
    expected_case_ids = [str(case["case_id"]) for case in manifest["cases"]]
    if set(submitted) != set(expected_case_ids):
        _fail("operator_attestation_modal_buckling_result_set_invalid")
    manifest_cases = {str(case["case_id"]): case for case in manifest["cases"]}
    receipt_cases = {
        str(case.get("case_id") or ""): case
        for case in receipt.get("cases", [])
        if isinstance(case, Mapping)
    }
    started_at = _timestamp(
        execution.get("started_at"),
        "operator_attestation_execution_window_invalid",
    )
    completed_at = _timestamp(
        execution.get("completed_at"),
        "operator_attestation_execution_window_invalid",
    )
    if completed_at < started_at:
        _fail("operator_attestation_execution_window_invalid")
    for case_id in expected_case_ids:
        descriptor, result = submitted[case_id]
        manifest_case = manifest_cases[case_id]
        receipt_case = receipt_cases.get(case_id)
        executed_at = _timestamp(
            result.get("executed_at"),
            "operator_attestation_modal_buckling_result_timestamp_invalid",
        )
        runtime = result.get("runtime")
        if not (started_at <= executed_at <= completed_at):
            _fail("operator_attestation_modal_buckling_result_outside_execution_window")
        if not isinstance(runtime, Mapping) or runtime.get("platform") != execution.get(
            "host_platform"
        ):
            _fail("operator_attestation_modal_buckling_result_platform_mismatch")
        try:
            _validated_result, comparisons = modal_buckling_ingest._validate_result(
                result_path=_bundle_file(bundle_root, str(descriptor["path"])),
                result_schema=result_schema,
                manifest=manifest,
                case=manifest_case,
                package_root=manifest_path.parent,
            )
        except Exception as exc:
            raise ExternalVVOperatorAttestationError(
                "operator_attestation_modal_buckling_result_invalid"
            ) from exc
        if (
            not isinstance(receipt_case, Mapping)
            or receipt_case.get("result_file_sha256") != descriptor["file_sha256"]
            or receipt_case.get("result_artifact_hash") != result["artifact_hash"]
            or receipt_case.get("comparisons") != comparisons
            or receipt_case.get("technical_contract_pass") is not True
        ):
            _fail("operator_attestation_modal_buckling_result_binding_invalid")
    return {
        "execution_package_artifact_hash": manifest["artifact_hash"],
        "technical_receipt_artifact_hash": receipt["artifact_hash"],
        "external_result_artifact_hashes": [
            submitted[case_id][1]["artifact_hash"] for case_id in expected_case_ids
        ],
        "case_ids": expected_case_ids,
        "source_commit_sha": source_commit_sha,
        "fresh_execution_declared_by_signer": True,
        "verification_matrix_credit": False,
    }


def _validate_bounded_planar_negative_bundle(
    row: Mapping[str, Any],
    *,
    bundle_root: Path,
    repo_root: Path,
    source_commit_sha: str,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path, manifest = _check_descriptor(
        row["execution_package_manifest"], bundle_root, json_artifact=True
    )
    assert manifest is not None
    try:
        consistent, _reason = negative_package.check_package(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
        validated_manifest = negative_package.validate_package_directory(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_negative_package_invalid"
        ) from exc
    if (
        not consistent
        or validated_manifest != manifest
        or manifest.get("source_commit_sha") != source_commit_sha
    ):
        _fail("operator_attestation_negative_package_source_binding_invalid")

    _receipt_path, receipt = _check_descriptor(
        row["technical_receipt"], bundle_root, json_artifact=True
    )
    assert receipt is not None
    try:
        negative_ingest._validate_receipt(receipt, repo_root)
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_negative_receipt_invalid"
        ) from exc
    claims = receipt.get("claims")
    package_binding = receipt.get("package_binding")
    if (
        receipt.get("source_commit_sha") != source_commit_sha
        or receipt.get("technical_contract_pass") is not True
        or receipt.get("status") != "technical_pass"
        or not isinstance(claims, Mapping)
        or claims.get("external_results_self_consistent") is not True
        or claims.get("exact_rejection_classifications") is not True
        or claims.get("invalid_geometry_external_solver_execution") is not False
        or claims.get("verification_matrix_credit") is not False
        or claims.get("verification_level_2") is not False
        or not isinstance(package_binding, Mapping)
        or package_binding.get("source_commit_sha") != source_commit_sha
        or package_binding.get("artifact_hash") != manifest["artifact_hash"]
        or package_binding.get("file_sha256") != file_sha256(manifest_path)
    ):
        _fail("operator_attestation_negative_receipt_contract_invalid")

    result_schema = _load_json(
        manifest_path.parent / manifest["external_result_schema"]["path"],
        "operator_attestation_negative_result_schema_invalid",
    )
    submitted: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    result_rows = row["external_results"]
    assert isinstance(result_rows, list)
    for descriptor in result_rows:
        assert isinstance(descriptor, Mapping)
        _path, result = _check_descriptor(descriptor, bundle_root, json_artifact=True)
        assert result is not None
        case_id = str(result.get("case_id") or "")
        if case_id in submitted:
            _fail("operator_attestation_negative_result_duplicate")
        submitted[case_id] = (descriptor, result)
    expected_case_ids = [str(case["case_id"]) for case in manifest["cases"]]
    if set(submitted) != set(expected_case_ids):
        _fail("operator_attestation_negative_result_set_invalid")
    manifest_cases = {str(case["case_id"]): case for case in manifest["cases"]}
    receipt_cases = {
        str(case.get("case_id") or ""): case
        for case in receipt.get("cases", [])
        if isinstance(case, Mapping)
    }
    started_at = _timestamp(
        execution.get("started_at"),
        "operator_attestation_execution_window_invalid",
    )
    completed_at = _timestamp(
        execution.get("completed_at"),
        "operator_attestation_execution_window_invalid",
    )
    if completed_at < started_at:
        _fail("operator_attestation_execution_window_invalid")
    external_fields = (
        "executed_at",
        "runner_file_sha256",
        "source_model_file_sha256",
        "runtime",
        "external_engine_invoked",
        "model_construction_succeeded",
        "analysis_return_code",
        "exception_type",
        "observation",
    )
    for case_id in expected_case_ids:
        descriptor, result = submitted[case_id]
        manifest_case = manifest_cases[case_id]
        receipt_case = receipt_cases.get(case_id)
        executed_at = _timestamp(
            result.get("executed_at"),
            "operator_attestation_negative_result_timestamp_invalid",
        )
        runtime = result.get("runtime")
        if not (started_at <= executed_at <= completed_at):
            _fail("operator_attestation_negative_result_outside_execution_window")
        if not isinstance(runtime, Mapping) or runtime.get("platform") != execution.get(
            "host_platform"
        ):
            _fail("operator_attestation_negative_result_platform_mismatch")
        try:
            _validated_result, rejection_authority = negative_ingest._validate_result(
                result_path=_bundle_file(bundle_root, str(descriptor["path"])),
                result_schema=result_schema,
                manifest=manifest,
                case=manifest_case,
                package_root=manifest_path.parent,
            )
        except Exception as exc:
            raise ExternalVVOperatorAttestationError(
                "operator_attestation_negative_result_invalid"
            ) from exc
        external_binding = (
            receipt_case.get("external_result")
            if isinstance(receipt_case, Mapping)
            else None
        )
        if (
            not isinstance(receipt_case, Mapping)
            or not isinstance(external_binding, Mapping)
            or receipt_case.get("rejection_authority") != rejection_authority
            or receipt_case.get("technical_rejection_pass") is not True
            or external_binding.get("file_sha256") != descriptor["file_sha256"]
            or external_binding.get("artifact_hash") != result["artifact_hash"]
            or any(
                external_binding.get(key) != result.get(key) for key in external_fields
            )
        ):
            _fail("operator_attestation_negative_result_binding_invalid")
    return {
        "execution_package_artifact_hash": manifest["artifact_hash"],
        "technical_receipt_artifact_hash": receipt["artifact_hash"],
        "external_result_artifact_hashes": [
            submitted[case_id][1]["artifact_hash"] for case_id in expected_case_ids
        ],
        "case_ids": expected_case_ids,
        "source_commit_sha": source_commit_sha,
        "fresh_execution_declared_by_signer": True,
        "external_solver_execution_case_count": 2,
        "independent_preflight_case_count": 1,
        "verification_matrix_credit": False,
    }


def _validate_bounded_planar_scaling_bundle(
    row: Mapping[str, Any],
    *,
    bundle_root: Path,
    repo_root: Path,
    source_commit_sha: str,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path, manifest = _check_descriptor(
        row["execution_package_manifest"], bundle_root, json_artifact=True
    )
    assert manifest is not None
    try:
        consistent, _reason = scaling_package.check_package(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
        validated_manifest = scaling_package.validate_package_directory(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_scaling_package_invalid"
        ) from exc
    if (
        not consistent
        or validated_manifest != manifest
        or manifest.get("source_commit_sha") != source_commit_sha
    ):
        _fail("operator_attestation_scaling_package_source_binding_invalid")

    _receipt_path, receipt = _check_descriptor(
        row["technical_receipt"], bundle_root, json_artifact=True
    )
    assert receipt is not None
    try:
        scaling_ingest._validate_receipt(receipt, repo_root)
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_scaling_receipt_invalid"
        ) from exc
    claims = receipt.get("claims")
    package_binding = receipt.get("package_binding")
    if (
        receipt.get("source_commit_sha") != source_commit_sha
        or receipt.get("technical_contract_pass") is not True
        or receipt.get("status") != "technical_pass"
        or not isinstance(claims, Mapping)
        or claims.get("external_results_self_consistent") is not True
        or claims.get("verification_matrix_credit") is not False
        or claims.get("verification_level_2") is not False
        or not isinstance(package_binding, Mapping)
        or package_binding.get("source_commit_sha") != source_commit_sha
        or package_binding.get("artifact_hash") != manifest["artifact_hash"]
        or package_binding.get("file_sha256") != file_sha256(manifest_path)
    ):
        _fail("operator_attestation_scaling_receipt_contract_invalid")

    result_schema = _load_json(
        manifest_path.parent / manifest["external_result_schema"]["path"],
        "operator_attestation_scaling_result_schema_invalid",
    )
    submitted: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    result_rows = row["external_results"]
    assert isinstance(result_rows, list)
    for descriptor in result_rows:
        assert isinstance(descriptor, Mapping)
        _path, result = _check_descriptor(descriptor, bundle_root, json_artifact=True)
        assert result is not None
        case_id = str(result.get("case_id") or "")
        if case_id in submitted:
            _fail("operator_attestation_scaling_result_duplicate")
        submitted[case_id] = (descriptor, result)
    expected_case_ids = [str(case["case_id"]) for case in manifest["cases"]]
    if set(submitted) != set(expected_case_ids):
        _fail("operator_attestation_scaling_result_set_invalid")
    manifest_cases = {str(case["case_id"]): case for case in manifest["cases"]}
    receipt_cases = {
        str(case.get("case_id") or ""): case
        for case in receipt.get("cases", [])
        if isinstance(case, Mapping)
    }
    started_at = _timestamp(
        execution.get("started_at"),
        "operator_attestation_execution_window_invalid",
    )
    completed_at = _timestamp(
        execution.get("completed_at"),
        "operator_attestation_execution_window_invalid",
    )
    if completed_at < started_at:
        _fail("operator_attestation_execution_window_invalid")
    external_fields = (
        "executed_at",
        "runner_file_sha256",
        "source_model_pair_file_sha256",
        "runtime",
    )
    for case_id in expected_case_ids:
        descriptor, result = submitted[case_id]
        manifest_case = manifest_cases[case_id]
        receipt_case = receipt_cases.get(case_id)
        executed_at = _timestamp(
            result.get("executed_at"),
            "operator_attestation_scaling_result_timestamp_invalid",
        )
        runtime = result.get("runtime")
        if not (started_at <= executed_at <= completed_at):
            _fail("operator_attestation_scaling_result_outside_execution_window")
        if not isinstance(runtime, Mapping) or runtime.get("platform") != execution.get(
            "host_platform"
        ):
            _fail("operator_attestation_scaling_result_platform_mismatch")
        try:
            _validated_result, comparisons = scaling_ingest._validate_result(
                result_path=_bundle_file(bundle_root, str(descriptor["path"])),
                result_schema=result_schema,
                manifest=manifest,
                case=manifest_case,
                package_root=manifest_path.parent,
            )
        except Exception as exc:
            raise ExternalVVOperatorAttestationError(
                "operator_attestation_scaling_result_invalid"
            ) from exc
        external_binding = (
            receipt_case.get("external_result")
            if isinstance(receipt_case, Mapping)
            else None
        )
        if (
            not isinstance(receipt_case, Mapping)
            or not isinstance(external_binding, Mapping)
            or receipt_case.get("metric_comparisons") != comparisons
            or receipt_case.get("technical_comparison_pass") is not True
            or external_binding.get("file_sha256") != descriptor["file_sha256"]
            or external_binding.get("artifact_hash") != result["artifact_hash"]
            or any(
                external_binding.get(key) != result.get(key) for key in external_fields
            )
        ):
            _fail("operator_attestation_scaling_result_binding_invalid")
    return {
        "execution_package_artifact_hash": manifest["artifact_hash"],
        "technical_receipt_artifact_hash": receipt["artifact_hash"],
        "external_result_artifact_hashes": [
            submitted[case_id][1]["artifact_hash"] for case_id in expected_case_ids
        ],
        "case_ids": expected_case_ids,
        "source_commit_sha": source_commit_sha,
        "fresh_execution_declared_by_signer": True,
        "verification_matrix_credit": False,
    }


def _validate_bounded_planar_nonlinear_material_recovery_bundle(
    row: Mapping[str, Any],
    *,
    bundle_root: Path,
    repo_root: Path,
    source_commit_sha: str,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path, manifest = _check_descriptor(
        row["execution_package_manifest"], bundle_root, json_artifact=True
    )
    assert manifest is not None
    try:
        consistent, _reason = nonlinear_material_recovery_package.check_package(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
        validated_manifest = (
            nonlinear_material_recovery_package.validate_package_directory(
                repo_root=repo_root,
                out_dir=manifest_path.parent,
            )
        )
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_nonlinear_material_recovery_package_invalid"
        ) from exc
    if (
        not consistent
        or validated_manifest != manifest
        or manifest.get("source_commit_sha") != source_commit_sha
    ):
        _fail(
            "operator_attestation_nonlinear_material_recovery_package_source_binding_invalid"
        )

    _receipt_path, receipt = _check_descriptor(
        row["technical_receipt"], bundle_root, json_artifact=True
    )
    assert receipt is not None
    try:
        nonlinear_material_recovery_ingest._validate_receipt(receipt, repo_root)
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_nonlinear_material_recovery_receipt_invalid"
        ) from exc
    claims = receipt.get("claims")
    package_binding = receipt.get("package_binding")
    if (
        receipt.get("source_commit_sha") != source_commit_sha
        or receipt.get("technical_contract_pass") is not True
        or receipt.get("status") != "technical_pass"
        or not isinstance(claims, Mapping)
        or claims.get("package_bytes_authenticated") is not True
        or claims.get("external_results_self_consistent") is not True
        or claims.get("fresh_current_source_external_execution") is not False
        or claims.get("independent_operator_attested") is not False
        or claims.get("verification_matrix_credit") is not False
        or claims.get("verification_level_2") is not False
        or not isinstance(package_binding, Mapping)
        or package_binding.get("source_commit_sha") != source_commit_sha
        or package_binding.get("artifact_hash") != manifest["artifact_hash"]
        or package_binding.get("file_sha256") != file_sha256(manifest_path)
    ):
        _fail(
            "operator_attestation_nonlinear_material_recovery_receipt_contract_invalid"
        )

    result_schema = _load_json(
        manifest_path.parent / manifest["external_result_schema"]["path"],
        "operator_attestation_nonlinear_material_recovery_result_schema_invalid",
    )
    try:
        Draft202012Validator.check_schema(result_schema)
    except Exception as exc:
        raise ExternalVVOperatorAttestationError(
            "operator_attestation_nonlinear_material_recovery_result_schema_invalid"
        ) from exc
    submitted: dict[str, tuple[Path, Mapping[str, Any], Mapping[str, Any]]] = {}
    result_rows = row["external_results"]
    assert isinstance(result_rows, list)
    for descriptor in result_rows:
        assert isinstance(descriptor, Mapping)
        path, result = _check_descriptor(descriptor, bundle_root, json_artifact=True)
        assert result is not None
        case_id = str(result.get("case_id") or "")
        if case_id in submitted:
            _fail(
                "operator_attestation_nonlinear_material_recovery_result_duplicate"
            )
        submitted[case_id] = (path, descriptor, result)
    expected_case_ids = [str(case["case_id"]) for case in manifest["cases"]]
    if set(submitted) != set(expected_case_ids):
        _fail(
            "operator_attestation_nonlinear_material_recovery_result_set_invalid"
        )
    manifest_cases = {str(case["case_id"]): case for case in manifest["cases"]}
    receipt_case_rows = receipt.get("cases")
    if not isinstance(receipt_case_rows, list):
        _fail(
            "operator_attestation_nonlinear_material_recovery_receipt_case_set_invalid"
        )
    receipt_cases = {
        str(case.get("case_id") or ""): case
        for case in receipt_case_rows
        if isinstance(case, Mapping)
    }
    if (
        len(receipt_cases) != len(receipt_case_rows)
        or set(receipt_cases) != set(expected_case_ids)
    ):
        _fail(
            "operator_attestation_nonlinear_material_recovery_receipt_case_set_invalid"
        )
    started_at = _timestamp(
        execution.get("started_at"),
        "operator_attestation_execution_window_invalid",
    )
    completed_at = _timestamp(
        execution.get("completed_at"),
        "operator_attestation_execution_window_invalid",
    )
    if completed_at < started_at:
        _fail("operator_attestation_execution_window_invalid")
    external_fields = (
        "executed_at",
        "runner_file_sha256",
        "source_model_file_sha256",
        "runtime",
    )
    for case_id in expected_case_ids:
        path, descriptor, result = submitted[case_id]
        manifest_case = manifest_cases[case_id]
        receipt_case = receipt_cases[case_id]
        executed_at = _timestamp(
            result.get("executed_at"),
            "operator_attestation_nonlinear_material_recovery_result_timestamp_invalid",
        )
        runtime = result.get("runtime")
        if not (started_at <= executed_at <= completed_at):
            _fail(
                "operator_attestation_nonlinear_material_recovery_result_outside_execution_window"
            )
        if not isinstance(runtime, Mapping) or runtime.get("platform") != execution.get(
            "host_platform"
        ):
            _fail(
                "operator_attestation_nonlinear_material_recovery_result_platform_mismatch"
            )
        try:
            validated_receipt_case, _validated_result = (
                nonlinear_material_recovery_ingest._validate_result(
                    case=manifest_case,
                    package_root=manifest_path.parent,
                    results_root=path.parent,
                    result_schema=result_schema,
                )
            )
        except Exception as exc:
            raise ExternalVVOperatorAttestationError(
                "operator_attestation_nonlinear_material_recovery_result_invalid"
            ) from exc
        external_binding = receipt_case.get("external_result")
        validated_external_binding = validated_receipt_case["external_result"]
        if (
            not isinstance(external_binding, Mapping)
            or receipt_case.get("requirement_id")
            != validated_receipt_case["requirement_id"]
            or receipt_case.get("metric_comparisons")
            != validated_receipt_case["metric_comparisons"]
            or receipt_case.get("maximum_absolute_error")
            != validated_receipt_case["maximum_absolute_error"]
            or receipt_case.get("maximum_relative_error")
            != validated_receipt_case["maximum_relative_error"]
            or receipt_case.get("technical_comparison_pass") is not True
            or receipt_case.get("blockers") != []
            or external_binding.get("file_sha256") != descriptor["file_sha256"]
            or external_binding.get("artifact_hash") != result["artifact_hash"]
            or any(
                external_binding.get(key) != validated_external_binding.get(key)
                or external_binding.get(key) != result.get(key)
                for key in external_fields
            )
        ):
            _fail(
                "operator_attestation_nonlinear_material_recovery_result_binding_invalid"
            )
    return {
        "execution_package_artifact_hash": manifest["artifact_hash"],
        "technical_receipt_artifact_hash": receipt["artifact_hash"],
        "external_result_artifact_hashes": [
            submitted[case_id][2]["artifact_hash"] for case_id in expected_case_ids
        ],
        "case_ids": expected_case_ids,
        "source_commit_sha": source_commit_sha,
        "fresh_execution_declared_by_signer": True,
        "external_solver_execution_case_count": len(expected_case_ids),
        "verification_matrix_credit": False,
    }


def _validate_bundle(
    attestation: Mapping[str, Any], bundle_root: Path, repo_root: Path
) -> dict[str, Any]:
    bundle = attestation["bundle"]
    assert isinstance(bundle, Mapping)
    _, summary = _check_descriptor(
        bundle["clean_runner"], bundle_root, json_artifact=True
    )
    _, code = _check_descriptor(bundle["code_to_code"], bundle_root, json_artifact=True)
    _, modal = _check_descriptor(
        bundle["modal_buckling"], bundle_root, json_artifact=True
    )
    assert summary is not None and code is not None and modal is not None
    _validate_artifact_schema(
        summary,
        repo_root=repo_root,
        schema_path=SUMMARY_SCHEMA_PATH,
        code="operator_attestation_clean_runner",
    )
    _validate_artifact_schema(
        code,
        repo_root=repo_root,
        schema_path=CODE_SCHEMA_PATH,
        code="operator_attestation_code_to_code",
    )
    _validate_artifact_schema(
        modal,
        repo_root=repo_root,
        schema_path=MODAL_SCHEMA_PATH,
        code="operator_attestation_modal_buckling",
    )
    source_commit = str(attestation["source_commit_sha"])
    if source_commit != _current_repo_head(repo_root):
        _fail("operator_attestation_source_commit_mismatch")
    _require_sources_at_head(repo_root, (code, modal))

    vector_rows = bundle["mode_vectors"]
    assert isinstance(vector_rows, list)
    submitted: dict[str, str] = {}
    submitted_paths: dict[str, Path] = {}
    for descriptor in vector_rows:
        assert isinstance(descriptor, Mapping)
        path, _ = _check_descriptor(descriptor, bundle_root, json_artifact=False)
        if path.name in submitted:
            _fail("operator_attestation_mode_vector_duplicate")
        submitted[path.name] = str(descriptor["file_sha256"])
        submitted_paths[path.name] = path
    modal_vector_descriptors = modal.get("mode_vector_artifacts", [])
    expected = {
        Path(str(row["artifact_path"])).name: str(row["data_hash"])
        for row in modal_vector_descriptors
        if isinstance(row, Mapping)
    }
    if len(expected) != 4 or submitted != expected:
        _fail("operator_attestation_mode_vector_binding_invalid")
    mode_vector_paths = {
        str(row["name"]): submitted_paths[Path(str(row["artifact_path"])).name]
        for row in modal_vector_descriptors
        if isinstance(row, Mapping)
    }

    try:
        code_receipt.validate_external_code_to_code_technical_receipt(
            dict(code),
            repo_root=repo_root,
            require_current_sources=True,
        )
    except code_receipt.ExternalCodeToCodeReceiptError as exc:
        error_code = (
            "operator_attestation_code_to_code_receipt_sources_stale"
            if exc.code == "receipt_sources_stale"
            else "operator_attestation_code_to_code_receipt_invalid"
        )
        raise ExternalVVOperatorAttestationError(error_code) from exc
    try:
        modal_receipt.validate_external_modal_buckling_technical_receipt(
            dict(modal),
            repo_root=repo_root,
            require_current_sources=True,
            mode_vector_paths=mode_vector_paths,
        )
    except modal_receipt.ExternalModalBucklingReceiptError as exc:
        error_code = (
            "operator_attestation_modal_buckling_receipt_sources_stale"
            if exc.code == "receipt_sources_stale"
            else "operator_attestation_modal_buckling_receipt_invalid"
        )
        raise ExternalVVOperatorAttestationError(error_code) from exc
    _fresh_child(code, source_commit_sha=source_commit)
    _fresh_child(modal, source_commit_sha=source_commit)
    claims = summary.get("claims")
    products = summary.get("product_receipts")
    isolation = summary.get("isolation")
    if (
        summary.get("technical_contract_pass") is not True
        or summary.get("source_commit_sha") != source_commit
        or not isinstance(claims, Mapping)
        or claims.get("same_operator_container_isolated_reproduction") is not True
        or claims.get("actual_external_solver_execution") is not True
        or claims.get("current_candidate_source_bytes_checksum_bound") is not True
        or claims.get("cross_environment_numerical_parity") is not True
        or not isinstance(isolation, Mapping)
        or isolation.get("repository_mount_read_only") is not True
        or isolation.get("runtime_default_network_route_present") is not False
        or not isinstance(products, Mapping)
    ):
        _fail("operator_attestation_clean_runner_contract_invalid")
    for key, child, descriptor in (
        ("code_to_code", code, bundle["code_to_code"]),
        ("modal_buckling", modal, bundle["modal_buckling"]),
    ):
        row = products.get(key)
        internal_source = child.get("internal_source")
        if (
            not isinstance(row, Mapping)
            or not isinstance(internal_source, Mapping)
            or row.get("fresh_external_runtime_execution") is not True
            or row.get("file_sha256") != descriptor["file_sha256"]
            or row.get("artifact_hash") != child["artifact_hash"]
            or row.get("source_set_hash") != internal_source.get("source_set_hash")
        ):
            _fail("operator_attestation_summary_child_binding_invalid")

    additional_bindings: list[dict[str, Any]] = []
    additional_rows = bundle.get("additional_receipts", [])
    if not isinstance(additional_rows, list):
        _fail("operator_attestation_additional_receipts_invalid")
    seen_additional_artifacts: set[str] = set()
    for descriptor in additional_rows:
        if not isinstance(descriptor, Mapping):
            _fail("operator_attestation_additional_receipt_invalid")
        path, receipt = _check_descriptor(descriptor, bundle_root, json_artifact=True)
        assert receipt is not None
        if (
            receipt.get("source_commit_sha") != source_commit
            or receipt.get("technical_contract_pass") is not True
        ):
            _fail("operator_attestation_additional_receipt_contract_invalid")
        cases = receipt.get("cases", receipt.get("comparisons"))
        if not isinstance(cases, list):
            _fail("operator_attestation_additional_receipt_cases_invalid")
        case_ids = sorted(
            str(case.get("case_id") or "")
            for case in cases
            if isinstance(case, Mapping)
            and (
                case.get("technical_comparison_pass") is True
                or case.get("contract_pass") is True
                or case.get("technical_rejection_pass") is True
            )
            and str(case.get("case_id") or "")
        )
        if _DEDICATED_SUPPLEMENT_CASE_IDS.intersection(case_ids):
            _fail("operator_attestation_additional_receipt_dedicated_case_forbidden")
        artifact = str(receipt["artifact_hash"])
        if not case_ids or artifact in seen_additional_artifacts:
            _fail("operator_attestation_additional_receipt_inventory_invalid")
        seen_additional_artifacts.add(artifact)
        additional_bindings.append(
            {
                "path": path.relative_to(bundle_root.resolve()).as_posix(),
                "file_sha256": descriptor["file_sha256"],
                "artifact_hash": artifact,
                "case_ids": case_ids,
                "source_commit_sha": source_commit,
                "fresh_execution_declared_by_signer": True,
            }
        )
    binding = {
        "clean_runner_artifact_hash": summary["artifact_hash"],
        "code_to_code_artifact_hash": code["artifact_hash"],
        "modal_buckling_artifact_hash": modal["artifact_hash"],
        "mode_vector_count": len(submitted),
        "source_commit_sha": source_commit,
        "additional_receipts": additional_bindings,
    }
    linear_row = bundle.get("bounded_planar_linear")
    if linear_row is not None:
        if not isinstance(linear_row, Mapping):
            _fail("operator_attestation_linear_bundle_invalid")
        binding["bounded_planar_linear"] = _validate_bounded_planar_linear_bundle(
            linear_row,
            bundle_root=bundle_root,
            repo_root=repo_root,
            source_commit_sha=source_commit,
            execution=attestation["execution"],
        )
    modal_buckling_row = bundle.get("bounded_planar_modal_buckling")
    if modal_buckling_row is not None:
        if not isinstance(modal_buckling_row, Mapping):
            _fail("operator_attestation_modal_buckling_bundle_invalid")
        binding["bounded_planar_modal_buckling"] = (
            _validate_bounded_planar_modal_buckling_bundle(
                modal_buckling_row,
                bundle_root=bundle_root,
                repo_root=repo_root,
                source_commit_sha=source_commit,
                execution=attestation["execution"],
            )
        )
    negative_row = bundle.get("bounded_planar_negative")
    if negative_row is not None:
        if not isinstance(negative_row, Mapping):
            _fail("operator_attestation_negative_bundle_invalid")
        binding["bounded_planar_negative"] = _validate_bounded_planar_negative_bundle(
            negative_row,
            bundle_root=bundle_root,
            repo_root=repo_root,
            source_commit_sha=source_commit,
            execution=attestation["execution"],
        )
    scaling_row = bundle.get("bounded_planar_scaling")
    if scaling_row is not None:
        if not isinstance(scaling_row, Mapping):
            _fail("operator_attestation_scaling_bundle_invalid")
        binding["bounded_planar_scaling"] = _validate_bounded_planar_scaling_bundle(
            scaling_row,
            bundle_root=bundle_root,
            repo_root=repo_root,
            source_commit_sha=source_commit,
            execution=attestation["execution"],
        )
    nonlinear_material_recovery_row = bundle.get(
        "bounded_planar_nonlinear_material_recovery"
    )
    if nonlinear_material_recovery_row is not None:
        if not isinstance(nonlinear_material_recovery_row, Mapping):
            _fail(
                "operator_attestation_nonlinear_material_recovery_bundle_invalid"
            )
        binding["bounded_planar_nonlinear_material_recovery"] = (
            _validate_bounded_planar_nonlinear_material_recovery_bundle(
                nonlinear_material_recovery_row,
                bundle_root=bundle_root,
                repo_root=repo_root,
                source_commit_sha=source_commit,
                execution=attestation["execution"],
            )
        )
    expected_commands: list[str] = []
    if linear_row is not None:
        expected_commands.extend(LINEAR_SUPPLEMENT_COMMANDS)
    if modal_buckling_row is not None:
        expected_commands.extend(MODAL_BUCKLING_SUPPLEMENT_COMMANDS)
    if negative_row is not None:
        expected_commands.extend(NEGATIVE_SUPPLEMENT_COMMANDS)
    if scaling_row is not None:
        expected_commands.extend(SCALING_SUPPLEMENT_COMMANDS)
    if nonlinear_material_recovery_row is not None:
        expected_commands.extend(NONLINEAR_MATERIAL_RECOVERY_SUPPLEMENT_COMMANDS)
    submitted_commands = attestation["execution"].get(
        "supplementary_runner_commands", []
    )
    if submitted_commands != expected_commands:
        _fail("operator_attestation_supplementary_runner_commands_invalid")
    return binding


def _verify_signature(
    attestation: Mapping[str, Any], bundle_root: Path, openssl: str
) -> dict[str, Any]:
    signature = attestation["signature"]
    operator = attestation["operator"]
    assert isinstance(signature, Mapping) and isinstance(operator, Mapping)
    public_key = _bundle_file(bundle_root, str(signature["public_key_path"]))
    signature_file = _bundle_file(bundle_root, str(signature["signature_path"]))
    if (
        file_sha256(public_key) != signature["public_key_sha256"]
        or signature["public_key_sha256"] != operator["signer_public_key_sha256"]
        or file_sha256(signature_file) != signature["signature_sha256"]
    ):
        _fail("operator_attestation_signature_artifact_hash_mismatch")
    payload = signed_payload(attestation)
    if sha256_bytes(payload) != signature["signed_payload_sha256"]:
        _fail("operator_attestation_signed_payload_hash_mismatch")
    with tempfile.TemporaryDirectory(prefix="external-vv-attestation-") as temporary:
        payload_path = Path(temporary) / "payload.json"
        payload_path.write_bytes(payload)
        try:
            completed = subprocess.run(
                [
                    openssl,
                    "dgst",
                    "-sha256",
                    "-verify",
                    str(public_key),
                    "-signature",
                    str(signature_file),
                    str(payload_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExternalVVOperatorAttestationError(
                "operator_attestation_signature_verifier_unavailable"
            ) from exc
    if completed.returncode != 0 or "Verified OK" not in completed.stdout:
        _fail("operator_attestation_signature_invalid")
    return {
        "algorithm": "rsa-sha256",
        "signed_payload_sha256": signature["signed_payload_sha256"],
        "public_key_sha256": signature["public_key_sha256"],
        "signature_sha256": signature["signature_sha256"],
        "cryptographic_signature_verified": True,
    }


def validate_external_vv_operator_attestation(
    attestation: Mapping[str, Any],
    *,
    bundle_root: Path,
    repo_root: Path = ROOT,
    openssl: str = "openssl",
) -> dict[str, Any]:
    """Validate one submission without promoting its engineering authority."""

    if not isinstance(attestation, Mapping):
        _fail("operator_attestation_object_required")
    _validate_schema(attestation, repo_root)
    bundle_binding = _validate_bundle(attestation, bundle_root, repo_root)
    signature = _verify_signature(attestation, bundle_root, openssl)
    linear_supplement_attached = "bounded_planar_linear" in bundle_binding
    modal_buckling_supplement_attached = (
        "bounded_planar_modal_buckling" in bundle_binding
    )
    negative_supplement_attached = "bounded_planar_negative" in bundle_binding
    scaling_supplement_attached = "bounded_planar_scaling" in bundle_binding
    nonlinear_material_recovery_supplement_attached = (
        "bounded_planar_nonlinear_material_recovery" in bundle_binding
    )
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "attestation_id": attestation["attestation_id"],
        "attestation_sha256": sha256_bytes(canonical_bytes(attestation)),
        "source_commit_sha": attestation["source_commit_sha"],
        "bundle_binding": bundle_binding,
        "signature": signature,
        "operator_independence_declared": True,
        "operator_identity_credentials_verified": False,
        "fresh_external_runtime_execution": True,
        "two_external_solver_slots_bound": True,
        "bounded_planar_linear_supplement_attached": linear_supplement_attached,
        "bounded_planar_linear_fresh_execution_declared": (linear_supplement_attached),
        "bounded_planar_modal_buckling_supplement_attached": (
            modal_buckling_supplement_attached
        ),
        "bounded_planar_modal_buckling_fresh_execution_declared": (
            modal_buckling_supplement_attached
        ),
        "bounded_planar_negative_supplement_attached": (negative_supplement_attached),
        "bounded_planar_negative_fresh_execution_declared": (
            negative_supplement_attached
        ),
        "bounded_planar_scaling_supplement_attached": (scaling_supplement_attached),
        "bounded_planar_scaling_fresh_execution_declared": (
            scaling_supplement_attached
        ),
        "bounded_planar_nonlinear_material_recovery_supplement_attached": (
            nonlinear_material_recovery_supplement_attached
        ),
        "bounded_planar_nonlinear_material_recovery_fresh_execution_declared": (
            nonlinear_material_recovery_supplement_attached
        ),
        "intake_contract_pass": True,
        "claims": {
            "signed_submission_integrity": True,
            "supplementary_linear_execution_signed": linear_supplement_attached,
            "supplementary_modal_buckling_execution_signed": (
                modal_buckling_supplement_attached
            ),
            "supplementary_negative_execution_signed": (negative_supplement_attached),
            "supplementary_scaling_execution_signed": (scaling_supplement_attached),
            "supplementary_nonlinear_material_recovery_execution_signed": (
                nonlinear_material_recovery_supplement_attached
            ),
            "independent_operator_identity_authenticated": False,
            "verification_hierarchy_level_2": False,
            "commercial_equivalence": False,
            "design_authority": False,
            "release_readiness": False,
        },
        "blockers_remaining": [
            "operator_identity_authentication_missing",
            "product_legal_license_approval_missing",
            "verification_hierarchy_operator_manifest_missing",
            "formal_level_2_promotion_decision_missing",
        ],
        "claim_boundary": (
            "This validation proves exact bundle hashes, fresh external-runtime replay "
            "declarations, and possession of the submitted RSA signing key. It does not "
            "authenticate the operator's real-world identity unless separately declared "
            "and reviewed, and never grants Verification Level 2, commercial equivalence, "
            "design authority, or release readiness."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--emit-signing-payload", type=Path)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args()
    payload = _load_json(args.attestation, "operator_attestation_json_invalid")
    if args.emit_signing_payload is not None:
        if args.bundle_root is not None or args.out is not None:
            parser.error(
                "--emit-signing-payload cannot be combined with --bundle-root or --out"
            )
        args.emit_signing_payload.parent.mkdir(parents=True, exist_ok=True)
        args.emit_signing_payload.write_bytes(signed_payload(payload))
        print(sha256_bytes(signed_payload(payload)))
        return 0
    if args.bundle_root is None:
        parser.error("--bundle-root is required for validation")
    try:
        result = validate_external_vv_operator_attestation(
            payload,
            bundle_root=args.bundle_root,
            openssl=args.openssl,
        )
    except ExternalVVOperatorAttestationError as exc:
        print(exc.code)
        return 1
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
