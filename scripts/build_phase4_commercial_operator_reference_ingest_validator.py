#!/usr/bin/env python3
"""Build and run the Phase 4 commercial operator reference ingest validator receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from build_phase4_commercial_operator_reference_contract import (  # noqa: E402
    DEFAULT_OUT as OPERATOR_REFERENCE_CONTRACT_OUT,
)
from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from strict_json import StrictJSONError, strict_json_load_path  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.model_ir import canonicalize_model_ir_v2  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = (
    PRODUCTIZATION / "phase4_commercial_operator_reference_ingest_validator.json"
)
REFERENCE_SCHEMA = Path(
    "native/crates/structural-contracts/schemas/"
    "external_linear_frame3d_reference_v1.schema.json"
)

MODELING_CONVENTION_FIELDS = [
    "unit_system",
    "local_axis_convention",
    "rigid_offset_policy",
    "end_release_policy",
    "diaphragm_policy",
    "mass_source_policy",
    "self_weight_policy",
    "material_modulus_convention",
    "shell_formulation",
    "mesh_density",
    "damping_policy",
    "p_delta_policy",
    "eigen_solver",
    "load_combinations",
    "convergence_tolerance",
]

FORBIDDEN_AUTHORITY_FIELDS = (
    "external_vv_credit",
    "operator_attested",
    "operator_attestation_verified",
    "legal_use_approved",
    "promotion_eligible",
    "verification_level_2",
    "design_authority",
    "commercial_equivalence",
    "release_readiness",
)

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
FULL_EXPORT_RECEIPT_SCHEMA = "commercial-frame3d-full-result-normalization-receipt.v1"
REFERENCE_SOLVER_ALIASES = {
    "midas": "midas_gen",
    "midas gen": "midas_gen",
    "midas gen nx": "midas_gen",
    "midas_gen": "midas_gen",
    "midas_gen_nx": "midas_gen",
    "sap 2000": "sap2000",
    "sap2000": "sap2000",
}
SEMANTIC_AUTHORITY_BLOCKERS = (
    "repository_owned_trust_registry_not_implemented",
    "full_canonical_vendor_semantic_projection_not_implemented",
    "vendor_executable_and_runtime_manifest_byte_replay_not_implemented",
    "isolated_transitive_runtime_not_implemented",
    "independent_operator_identity_not_established",
)


def _json_text(payload: dict[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = strict_json_load_path(path)
    except StrictJSONError as exc:
        raise ValueError(f"{path} is not strict JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _resolve_package_file(package_root: Path, rel_path: str) -> Path | None:
    candidate = Path(rel_path)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.as_posix() != rel_path
    ):
        return None
    root = package_root.resolve()
    path = root / candidate
    cursor = root
    for part in candidate.parts:
        cursor /= part
        if cursor.is_symlink():
            return None
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _strict_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _is_declared(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and not value.startswith("DECLARED_BY_OPERATOR")
    if isinstance(value, list):
        return bool(value)
    return True


def validate_operator_reference_package(
    package: dict[str, Any],
    *,
    package_root: Path,
    verify_file_hashes: bool = True,
    require_normalized_results: bool = True,
    require_two_reference_solvers: bool = True,
) -> dict[str, Any]:
    """Validate an ingest preflight without granting V&V or legal authority.

    The relaxed flags exist only for a one-solver raw adapter before it has
    generated ReferenceIR.  Relaxed success is explicitly normalization-only.
    """

    blockers: list[str] = []
    warnings: list[str] = []
    relaxed_raw_preflight = not (
        require_normalized_results and require_two_reference_solvers
    )

    def reject_authority_claims(value: object, scope: str) -> None:
        if isinstance(value, dict):
            for field in FORBIDDEN_AUTHORITY_FIELDS:
                if value.get(field) is True:
                    blockers.append(f"forbidden_authority_claim:{scope}:{field}")
            for child in value.values():
                reject_authority_claims(child, scope)
        elif isinstance(value, list):
            for child in value:
                reject_authority_claims(child, scope)

    reject_authority_claims(package, "package")
    if not verify_file_hashes:
        blockers.append("file_hash_verification_disabled")

    for field in ("case_id", "modeling_convention_id"):
        if not _is_declared(package.get(field)):
            blockers.append(f"missing_field:{field}")

    permission = package.get("permission_scope")
    if not isinstance(permission, dict):
        blockers.append("permission_scope_missing")
    else:
        reject_authority_claims(permission, "permission_scope")
        if permission.get("comparison_use_allowed") is not True:
            blockers.append("comparison_use_permission_missing")
        approval = permission.get("approval_receipt")
        if relaxed_raw_preflight and _is_declared(approval):
            warnings.append("permission_is_operator_declaration_not_legal_approval")
        elif not isinstance(approval, dict):
            blockers.append("permission_approval_receipt_descriptor_missing")
        else:
            required_approval = {
                "path",
                "file_sha256",
                "operator_id",
                "approved_at",
                "comparison_scope",
            }
            if set(approval) != required_approval:
                blockers.append("permission_approval_receipt_descriptor_invalid")
            if not _is_declared(approval.get("operator_id")):
                blockers.append("permission_operator_id_missing")
            if not _strict_timestamp(approval.get("approved_at")):
                blockers.append("permission_approved_at_invalid")
            if approval.get("comparison_scope") != "non_released_internal_comparison":
                blockers.append("permission_comparison_scope_invalid")
        if permission.get("redistribution_allowed") is True:
            warnings.append(
                "redistribution_allowed_true_requires_separate_release_review"
            )

    solvers = package.get("reference_solvers")
    solvers = solvers if isinstance(solvers, list) else []
    canonical_solver_ids: list[str] = []
    for solver in solvers:
        if not isinstance(solver, dict):
            blockers.append("reference_solver_row_invalid")
            continue
        raw_name = solver.get("engine_name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            blockers.append("reference_solver_name_missing")
            continue
        canonical = REFERENCE_SOLVER_ALIASES.get(raw_name.strip().lower())
        if canonical is None:
            blockers.append(f"reference_solver_unsupported:{raw_name.strip()}")
            continue
        canonical_solver_ids.append(canonical)
    distinct_solver_names = sorted(set(canonical_solver_ids))
    if require_two_reference_solvers and set(distinct_solver_names) != {
        "midas_gen",
        "sap2000",
    }:
        blockers.append("two_reference_solver_comparison_not_available")
    if len(canonical_solver_ids) != len(set(canonical_solver_ids)):
        blockers.append("reference_solver_name_duplicate")

    modeling_convention = package.get("modeling_convention")
    modeling_convention = (
        modeling_convention if isinstance(modeling_convention, dict) else {}
    )
    for field in MODELING_CONVENTION_FIELDS:
        if not _is_declared(modeling_convention.get(field)):
            blockers.append(f"modeling_convention_missing:{field}")

    file_checksums = package.get("file_checksums")
    file_checksums = file_checksums if isinstance(file_checksums, dict) else {}
    paths: list[str] = []
    for key in ("raw_input_files", "raw_result_files"):
        values = package.get(key)
        if isinstance(values, list) and values:
            valid_values = [
                value for value in values if isinstance(value, str) and value
            ]
            if len(valid_values) != len(values):
                blockers.append(f"{key}_invalid")
            if len(valid_values) != len(set(valid_values)):
                blockers.append(f"{key}_duplicate")
            paths.extend(valid_values)
        else:
            blockers.append(f"{key}_missing")
    solver_raw_files: list[str] = []
    solver_operator_ids: list[str] = []
    solver_run_ids: list[str] = []
    for solver in solvers:
        if isinstance(solver, dict):
            reject_authority_claims(solver, "reference_solver")
            operator_id = solver.get("operator_id")
            run_id = solver.get("run_id")
            raw_result_file = solver.get("raw_result_file")
            raw_result_files = solver.get("raw_result_files")
            normalization_receipt_file = solver.get("normalization_receipt_file")
            if not isinstance(solver.get("engine_version"), str) or not _is_declared(
                solver.get("engine_version")
            ):
                blockers.append("reference_solver_version_missing")
            if require_normalized_results:
                if not isinstance(operator_id, str) or not _is_declared(operator_id):
                    blockers.append("reference_solver_operator_id_missing")
                else:
                    solver_operator_ids.append(operator_id)
                if not isinstance(run_id, str) or not _is_declared(run_id):
                    blockers.append("reference_solver_run_id_missing")
                else:
                    solver_run_ids.append(run_id)
                if isinstance(raw_result_files, list) and raw_result_files:
                    if (
                        any(not isinstance(value, str) or not value for value in raw_result_files)
                        or len(raw_result_files) != len(set(raw_result_files))
                        or raw_result_file is not None
                    ):
                        blockers.append("reference_solver_raw_result_files_invalid")
                    else:
                        solver_raw_files.extend(raw_result_files)
                        paths.extend(raw_result_files)
                elif isinstance(raw_result_file, str) and raw_result_file:
                    solver_raw_files.append(raw_result_file)
                    paths.append(raw_result_file)
                else:
                    blockers.append("reference_solver_raw_result_file_missing")
                if (
                    not isinstance(normalization_receipt_file, str)
                    or not normalization_receipt_file
                ):
                    blockers.append("normalization_receipt_file_missing")
                else:
                    paths.append(normalization_receipt_file)
            result_file = solver.get("normalized_result_file")
            if isinstance(result_file, str) and result_file:
                if require_normalized_results:
                    paths.append(result_file)
            elif require_normalized_results:
                blockers.append("normalized_result_file_missing")
    if require_normalized_results and len(solver_run_ids) != len(set(solver_run_ids)):
        blockers.append("reference_solver_run_id_duplicate")
    declared_raw_results = package.get("raw_result_files")
    if (
        require_normalized_results
        and isinstance(declared_raw_results, list)
        and sorted(solver_raw_files)
        != sorted(str(value) for value in declared_raw_results if isinstance(value, str))
    ):
        blockers.append("reference_solver_raw_result_set_mismatch")

    for rel_path in sorted(set(paths)):
        checksum = file_checksums.get(rel_path)
        if not (isinstance(checksum, str) and SHA256_PATTERN.fullmatch(checksum)):
            blockers.append(f"checksum_missing:{rel_path}")
            continue
        if verify_file_hashes:
            resolved = _resolve_package_file(package_root, rel_path)
            if resolved is None:
                blockers.append(f"operator_file_missing_or_outside_package:{rel_path}")
                continue
            actual = _sha256(resolved)
            if actual != checksum:
                blockers.append(f"checksum_mismatch:{rel_path}")

    if not relaxed_raw_preflight and isinstance(permission, dict):
        approval = permission.get("approval_receipt")
        if isinstance(approval, dict):
            approval_path = approval.get("path")
            approval_hash = approval.get("file_sha256")
            if isinstance(approval_path, str):
                paths.append(approval_path)
                resolved = _resolve_package_file(package_root, approval_path)
                if resolved is None or _sha256(resolved) != approval_hash:
                    blockers.append("permission_approval_receipt_file_binding_invalid")
                else:
                    try:
                        approval_payload = _load_json(resolved)
                    except ValueError:
                        blockers.append("permission_approval_receipt_json_invalid")
                    else:
                        reject_authority_claims(
                            approval_payload, "permission_declaration"
                        )
                        if (
                            approval_payload.get("schema_version")
                            != "commercial-reference-permission-declaration.v1"
                            or approval_payload.get("operator_id")
                            != approval.get("operator_id")
                            or approval_payload.get("case_id") != package.get("case_id")
                            or approval_payload.get("comparison_use_allowed")
                            is not True
                            or approval_payload.get("legal_use_approved") is not False
                            or approval_payload.get("signature_verified") is not False
                        ):
                            blockers.append(
                                "permission_approval_receipt_semantics_invalid"
                            )

    reference_schema_path = ROOT / REFERENCE_SCHEMA
    try:
        reference_schema = _load_json(reference_schema_path)
        Draft202012Validator.check_schema(reference_schema)
        reference_validator = Draft202012Validator(reference_schema)
    except (OSError, ValueError, SchemaError) as exc:
        raise ValueError("commercial_reference_schema_invalid") from exc
    model_hashes: set[str] = set()
    load_bindings: set[tuple[object, object]] = set()
    entity_bindings: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    reference_ids: list[str] = []
    normalization_schemas: list[str] = []
    if require_normalized_results:
        for solver in solvers:
            if not isinstance(solver, dict):
                blockers.append("reference_solver_row_invalid")
                continue
            normalized_rel = solver.get("normalized_result_file")
            receipt_rel = solver.get("normalization_receipt_file")
            raw_rel = solver.get("raw_result_file")
            raw_rels = solver.get("raw_result_files")
            if not all(
                isinstance(value, str) and value
                for value in (normalized_rel, receipt_rel)
            ):
                continue
            normalized_path = _resolve_package_file(package_root, normalized_rel)
            normalization_path = _resolve_package_file(package_root, receipt_rel)
            if normalized_path is None or normalization_path is None:
                continue
            try:
                reference = _load_json(normalized_path)
                reference_validator.validate(reference)
                normalization = _load_json(normalization_path)
            except (ValueError, ValidationError):
                blockers.append(
                    f"normalized_reference_or_receipt_invalid:{normalized_rel}"
                )
                continue
            reject_authority_claims(reference, "normalized_reference")
            reject_authority_claims(normalization, "normalization_receipt")
            engine = str(solver.get("engine_name") or "").strip().lower()
            expected_tool = REFERENCE_SOLVER_ALIASES.get(engine)
            raw_hash = file_checksums.get(raw_rel) if isinstance(raw_rel, str) else None
            normalized_hash = file_checksums.get(normalized_rel)
            normalization_schema = normalization.get("schema_version")
            if isinstance(normalization_schema, str):
                normalization_schemas.append(normalization_schema)
            is_full_export_bridge = normalization_schema == FULL_EXPORT_RECEIPT_SCHEMA
            expected_export_hash = (
                normalization.get("source_export_set_sha256")
                if is_full_export_bridge
                else raw_hash
            )
            if (
                expected_tool is None
                or reference.get("source", {}).get("tool") != expected_tool
                or reference.get("source", {}).get("version")
                != solver.get("engine_version")
                or reference.get("source", {}).get("origin")
                != "operator_attached_external"
                or reference.get("source", {}).get("export_sha256")
                != expected_export_hash
            ):
                blockers.append(
                    f"normalized_reference_raw_binding_invalid:{normalized_rel}"
                )
            model_hash = reference.get("bindings", {}).get("model_content_hash")
            if isinstance(model_hash, str):
                model_hashes.add(model_hash)
            load_bindings.add(
                (
                    reference.get("bindings", {}).get("load_pattern_id"),
                    reference.get("bindings", {}).get("load_combination_id"),
                )
            )
            node_ids = [str(row["node_id"]) for row in reference["nodes"]]
            member_ids = [str(row["member_id"]) for row in reference["members"]]
            if len(node_ids) != len(set(node_ids)) or len(member_ids) != len(
                set(member_ids)
            ):
                blockers.append(
                    f"normalized_reference_entity_id_duplicate:{normalized_rel}"
                )
            entity_bindings.add((tuple(sorted(node_ids)), tuple(sorted(member_ids))))
            reference_ids.append(str(reference.get("reference_id") or ""))
            if is_full_export_bridge:
                expected_source_files = [
                    {
                        "role": role,
                        "path": path,
                        "sha256": file_checksums.get(path),
                    }
                    for role, path in (
                        ("member_end_forces", raw_rels[2]),
                        ("model_input", package["raw_input_files"][0]),
                        ("node_displacements", raw_rels[0]),
                        ("node_reactions", raw_rels[1]),
                    )
                ] if (
                    isinstance(raw_rels, list)
                    and len(raw_rels) == 3
                    and isinstance(package.get("raw_input_files"), list)
                    and len(package["raw_input_files"]) == 1
                ) else []
                try:
                    canonical_reference_hash = "sha256:" + hashlib.sha256(
                        canonicalize_model_ir_v2(reference).encode("utf-8")
                    ).hexdigest()
                except (TypeError, ValueError):
                    canonical_reference_hash = ""
                if (
                    not expected_source_files
                    or normalization.get("case_id") != package.get("case_id")
                    or normalization.get("modeling_convention_id")
                    != package.get("modeling_convention_id")
                    or normalization.get("tool") != expected_tool
                    or normalization.get("version") != solver.get("engine_version")
                    or normalization.get("run_id") != solver.get("run_id")
                    or normalization.get("source_files") != expected_source_files
                    or normalization.get("source_export_set_sha256")
                    != _canonical_sha256(expected_source_files)
                    or normalization.get("reference_ir_canonical_sha256")
                    != canonical_reference_hash
                    or normalization.get("normalization_only") is not True
                    or normalization.get("trust_state")
                    != "untrusted_operator_preflight_only"
                    or normalization.get("repository_owned_trust_anchor_used")
                    is not False
                    or normalization.get("caller_provided_trust_material_consumed")
                    is not False
                    or normalization.get("semantic_equivalence_prerequisite_passed")
                    is not False
                    or normalization.get("eligible_as_semantically_bound_comparison_input")
                    is not False
                    or normalization.get("eligible_for_external_vv_credit") is not False
                    or normalization.get("eligible_for_promotion") is not False
                    or normalization.get("eligible_for_release") is not False
                    or normalization.get("authority", {}).get("external_validation")
                    != "not_established"
                    or normalization.get("authority", {}).get("comparison")
                    != "not_executed"
                ):
                    blockers.append(
                        f"full_export_normalization_bridge_invalid:{receipt_rel}"
                    )
                else:
                    warnings.append(
                        f"full_export_normalization_bridge_non_authoritative:{receipt_rel}"
                    )
            elif (
                normalization_schema != "commercial-reference-normalization-receipt.v1"
                or normalization.get("case_id") != package.get("case_id")
                or normalization.get("operator_id") != solver.get("operator_id")
                or normalization.get("run_id") != solver.get("run_id")
                or normalization.get("engine_name") != solver.get("engine_name")
                or normalization.get("engine_version") != solver.get("engine_version")
                or normalization.get("raw_result_file") != raw_rel
                or normalization.get("raw_result_file_sha256") != raw_hash
                or normalization.get("normalized_result_file") != normalized_rel
                or normalization.get("normalized_result_file_sha256") != normalized_hash
                or normalization.get("model_content_hash") != model_hash
                or normalization.get("operator_attested") is not False
                or normalization.get("legal_use_approved") is not False
                or normalization.get("promotion_eligible") is not False
            ):
                blockers.append(f"normalization_receipt_binding_invalid:{receipt_rel}")
        if len(model_hashes) != 1:
            blockers.append("normalized_reference_model_binding_mismatch")
        raw_input_hashes = {
            file_checksums.get(path)
            for path in package.get("raw_input_files", [])
            if isinstance(path, str)
        }
        uses_only_full_export_bridge = (
            len(normalization_schemas) == len(solvers)
            and set(normalization_schemas) == {FULL_EXPORT_RECEIPT_SCHEMA}
        )
        if (
            len(model_hashes) != 1
            or (
                not uses_only_full_export_bridge
                and not model_hashes.issubset(raw_input_hashes)
            )
        ):
            blockers.append("normalized_reference_raw_model_binding_missing")
        if len(load_bindings) != 1:
            blockers.append("normalized_reference_load_binding_mismatch")
        if len(entity_bindings) != 1:
            blockers.append("normalized_reference_entity_binding_mismatch")
        if len(reference_ids) != len(set(reference_ids)):
            blockers.append("normalized_reference_id_duplicate")
        if len(set(solver_operator_ids)) != 1:
            blockers.append("reference_solver_operator_identity_mismatch")
        approval = (
            permission.get("approval_receipt") if isinstance(permission, dict) else None
        )
        if (
            isinstance(approval, dict)
            and solver_operator_ids
            and any(
                value != approval.get("operator_id") for value in solver_operator_ids
            )
        ):
            blockers.append("permission_operator_solver_identity_mismatch")

    unsupported_features = package.get("unsupported_features")
    if not isinstance(unsupported_features, list):
        blockers.append("unsupported_features_not_declared")
    elif unsupported_features:
        blockers.append("unsupported_features_present")
    package_warnings = package.get("warnings")
    if not isinstance(package_warnings, list):
        blockers.append("warnings_not_declared")

    preflight_pass = not blockers
    result = {
        "status": (
            "raw_preflight_pass_non_authoritative"
            if preflight_pass and relaxed_raw_preflight
            else ("preflight_pass_non_authoritative" if preflight_pass else "blocked")
        ),
        "contract_pass": False,
        "preflight_contract_pass": preflight_pass,
        "normalization_only": relaxed_raw_preflight,
        "external_vv_credit": False,
        "trusted_rust_comparison_verified": False,
        "operator_attestation_verified": False,
        "legal_use_approved": False,
        "promotion_eligible": False,
        "semantic_equivalence_prerequisite_passed": False,
        "eligible_as_semantically_bound_comparison_input": False,
        "eligible_for_external_vv_credit": False,
        "eligible_for_promotion": False,
        "eligible_for_release": False,
        "authority_blockers": list(SEMANTIC_AUTHORITY_BLOCKERS),
        "blockers": sorted(set(blockers)),
        "warnings": warnings,
        "case_id": package.get("case_id", ""),
        "modeling_convention_id": package.get("modeling_convention_id", ""),
        "reference_solver_count": len(solvers),
        "distinct_reference_solver_count": len(distinct_solver_names),
        "distinct_reference_solvers": distinct_solver_names,
        "checked_file_count": len(sorted(set(paths))),
        "checksum_declared_count": sum(
            1
            for path in sorted(set(paths))
            if isinstance(file_checksums.get(path), str)
        ),
        "verify_file_hashes": verify_file_hashes,
    }
    if relaxed_raw_preflight:
        result["raw_preflight_pass"] = preflight_pass
    return result


def build_phase4_commercial_operator_reference_ingest_validator(
    *,
    repo_root: Path = ROOT,
    package_path: Path | None = None,
    source_commit_sha: str | None = None,
    verify_file_hashes: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    package_path_text = package_path.as_posix() if package_path is not None else ""
    validation_result = {
        "status": "blocked",
        "contract_pass": False,
        "preflight_contract_pass": False,
        "normalization_only": False,
        "external_vv_credit": False,
        "trusted_rust_comparison_verified": False,
        "operator_attestation_verified": False,
        "legal_use_approved": False,
        "promotion_eligible": False,
        "semantic_equivalence_prerequisite_passed": False,
        "eligible_as_semantically_bound_comparison_input": False,
        "eligible_for_external_vv_credit": False,
        "eligible_for_promotion": False,
        "eligible_for_release": False,
        "authority_blockers": list(SEMANTIC_AUTHORITY_BLOCKERS),
        "blockers": ["operator_reference_package_missing"],
        "warnings": [],
        "case_id": "",
        "modeling_convention_id": "",
        "reference_solver_count": 0,
        "distinct_reference_solver_count": 0,
        "distinct_reference_solvers": [],
        "checked_file_count": 0,
        "checksum_declared_count": 0,
        "verify_file_hashes": verify_file_hashes,
    }
    if package_path is not None:
        resolved_package = (
            package_path if package_path.is_absolute() else repo_root / package_path
        )
        if resolved_package.exists() and not resolved_package.is_symlink():
            package = _load_json(resolved_package)
            validation_result = validate_operator_reference_package(
                package,
                package_root=resolved_package.parent,
                verify_file_hashes=verify_file_hashes,
            )
        else:
            validation_result["blockers"] = [
                f"operator_reference_package_missing:{package_path_text}"
            ]

    return {
        "schema_version": "phase4-commercial-operator-reference-ingest-preflight.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path(
                    "scripts/build_phase4_commercial_operator_reference_ingest_validator.py"
                ),
                Path("scripts/strict_json.py"),
                Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
                Path("scripts/build_phase4_commercial_comparison_import_template.py"),
                REFERENCE_SCHEMA,
                Path("src/structure-viewer/viewer-commercial-tool-crosswalk-model.js"),
                Path("src/structure-viewer/viewer-report-export.js"),
            ],
            repo_root=repo_root,
        ),
        "status": validation_result["status"],
        "contract_pass": False,
        "preflight_contract_pass": validation_result["preflight_contract_pass"],
        "external_vv_credit": False,
        "trusted_rust_comparison_verified": False,
        "operator_attestation_verified": False,
        "legal_use_approved": False,
        "promotion_eligible": False,
        "semantic_equivalence_prerequisite_passed": False,
        "eligible_as_semantically_bound_comparison_input": False,
        "eligible_for_external_vv_credit": False,
        "eligible_for_promotion": False,
        "eligible_for_release": False,
        "phase3_closure_claim": False,
        "phase4_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "selected_benchmark_lanes": ["commercial-cross-solver"],
        "truth_class": "operator_declared_ingest_preflight",
        "operator_reference_contract": str(OPERATOR_REFERENCE_CONTRACT_OUT),
        "package_path": package_path_text,
        "validation_result": validation_result,
        "remaining_blockers": (
            validation_result["blockers"]
            if validation_result["blockers"]
            else [
                "commercial_cross_solver_execution_missing",
                "trusted_rust_comparison_receipt_missing",
                "operator_comparison_trace_rows_missing",
                "phase4_two_solver_comparison_metrics_not_recorded",
                *SEMANTIC_AUTHORITY_BLOCKERS,
            ]
        ),
        "claim_boundary": (
            "This non-authoritative ingest preflight validates strict ReferenceIR syntax, "
            "raw/normalized hashes, declared run and operator identity, modeling conventions, "
            "and normalization-receipt consistency. Even preflight_pass_non_authoritative "
            "keeps contract_pass, external_vv_credit, operator_attestation_verified, "
            "legal_use_approved, and promotion_eligible false. It does not independently "
            "authenticate the operator, execute a licensed solver, invoke the trusted Rust "
            "comparison boundary, or grant legal "
            "approval, or close any product, scientific, commercial, or release gate."
        ),
    }


def write_phase4_commercial_operator_reference_ingest_validator(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    package_path: Path | None = None,
    source_commit_sha: str | None = None,
    verify_file_hashes: bool = True,
) -> dict[str, Any]:
    payload = build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=repo_root,
        package_path=package_path,
        source_commit_sha=source_commit_sha,
        verify_file_hashes=verify_file_hashes,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase4_commercial_operator_reference_ingest_validator(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    package_path: Path | None = None,
    source_commit_sha: str | None = None,
    verify_file_hashes: bool = True,
) -> tuple[bool, str]:
    expected = build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=repo_root,
        package_path=package_path,
        source_commit_sha=source_commit_sha,
        verify_file_hashes=verify_file_hashes,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return (
            False,
            f"phase4_commercial_operator_reference_ingest_validator_missing:{out_path.as_posix()}",
        )
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            "phase4_commercial_operator_reference_ingest_validator_unreadable:"
            f"{out_path.as_posix()}:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase4_commercial_operator_reference_ingest_validator_mismatch"
    return True, "phase4_commercial_operator_reference_ingest_validator_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--package", type=Path, default=None)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--no-verify-file-hashes", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verify_file_hashes = not args.no_verify_file_hashes
    if args.check:
        ok, message = check_phase4_commercial_operator_reference_ingest_validator(
            out_path=args.out,
            package_path=args.package,
            source_commit_sha=args.source_commit_sha,
            verify_file_hashes=verify_file_hashes,
        )
        print(
            f"Phase 4 commercial operator reference ingest validator check: {message}"
        )
        return 0 if ok else 1
    payload = write_phase4_commercial_operator_reference_ingest_validator(
        out_path=args.out,
        package_path=args.package,
        source_commit_sha=args.source_commit_sha,
        verify_file_hashes=verify_file_hashes,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 4 commercial operator reference ingest validator: "
            f"{payload['status']} | blockers={len(payload['remaining_blockers'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
