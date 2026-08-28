#!/usr/bin/env python3
"""Shared fail-closed policy for non-promoting authority-bearing JSON."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
import unicodedata

from scripts.strict_json import StrictJSONError, strict_json_load_path


POLICY_PATH = Path("canonical/nonpromotion-authority-key-policy.v1.json")
SCHEMA_VERSION = "nonpromotion-authority-key-policy.v1"
_ROOT_KEYS = frozenset(
    {
        "allowed_true_technical_completeness",
        "allowed_technical_grants",
        "negative_authority_token_containers",
        "prohibited_keys",
        "safe_statuses",
        "schema_version",
    }
)
_POLICY_KEY = re.compile(r"[a-z0-9_]+")
_CAMEL_ACRONYM = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_ALNUM_BOUNDARY = re.compile(r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])")
_SEPARATORS = re.compile(r"[^A-Za-z0-9]+")


class AuthorityPolicyError(ValueError):
    """Raised when the authority policy or a governed payload is unsafe."""


@dataclass(frozen=True)
class AuthorityPolicy:
    prohibited_keys: frozenset[str]
    prohibited_compact_keys: frozenset[str]
    safe_statuses: frozenset[str]
    allowed_true_technical_completeness: frozenset[str]
    allowed_technical_grants: frozenset[str]
    negative_authority_token_containers: frozenset[str]
    negative_authority_token_compact_containers: frozenset[str]


def _policy_strings(payload: dict[str, Any], field: str) -> frozenset[str]:
    values = payload.get(field)
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) for value in values)
        or values != sorted(values)
        or len(values) != len(set(values))
    ):
        raise AuthorityPolicyError(f"authority_policy_{field}_invalid")
    for value in values:
        if (
            unicodedata.normalize("NFKC", value) != value
            or not value.isascii()
            or any(
                unicodedata.category(character) in {"Cc", "Cf"} for character in value
            )
            or value.casefold() != value
            or _POLICY_KEY.fullmatch(value) is None
        ):
            raise AuthorityPolicyError(
                f"authority_policy_{field}_key_invalid:{value!r}"
            )
    return frozenset(values)


def load_authority_policy(path: Path) -> AuthorityPolicy:
    try:
        payload = strict_json_load_path(path)
    except (OSError, StrictJSONError) as exc:
        raise AuthorityPolicyError("authority_policy_unreadable") from exc
    if not isinstance(payload, dict) or set(payload) != _ROOT_KEYS:
        raise AuthorityPolicyError("authority_policy_shape_invalid")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise AuthorityPolicyError("authority_policy_version_invalid")
    prohibited = _policy_strings(payload, "prohibited_keys")
    safe_statuses = _policy_strings(payload, "safe_statuses")
    allowed = _policy_strings(payload, "allowed_true_technical_completeness")
    grants = _policy_strings(payload, "allowed_technical_grants")
    negative_containers = _policy_strings(
        payload, "negative_authority_token_containers"
    )
    if prohibited & (allowed | grants):
        raise AuthorityPolicyError("authority_policy_allow_deny_overlap")
    return AuthorityPolicy(
        prohibited_keys=prohibited,
        prohibited_compact_keys=frozenset(
            value.replace("_", "") for value in prohibited
        ),
        safe_statuses=safe_statuses,
        allowed_true_technical_completeness=allowed,
        allowed_technical_grants=grants,
        negative_authority_token_containers=negative_containers,
        negative_authority_token_compact_containers=frozenset(
            value.replace("_", "") for value in negative_containers
        ),
    )


def canonical_authority_key(key: Any, path: str) -> str:
    if not isinstance(key, str):
        raise AuthorityPolicyError(f"authority_key_not_string:{path}")
    if (
        unicodedata.normalize("NFKC", key) != key
        or not key.isascii()
        or any(unicodedata.category(character) in {"Cc", "Cf"} for character in key)
    ):
        raise AuthorityPolicyError(f"authority_key_not_canonical:{path}:{key!r}")
    separated = _CAMEL_ACRONYM.sub(r"\1_\2", key)
    separated = _CAMEL_BOUNDARY.sub(r"\1_\2", separated)
    separated = _ALNUM_BOUNDARY.sub("_", separated)
    return _SEPARATORS.sub("_", separated).strip("_").casefold()


def compact_authority_key(key: Any, path: str) -> str:
    """Return a separator/acronym-insensitive form after rejecting Unicode aliases."""
    if not isinstance(key, str):
        raise AuthorityPolicyError(f"authority_key_not_string:{path}")
    if (
        unicodedata.normalize("NFKC", key) != key
        or not key.isascii()
        or any(unicodedata.category(character) in {"Cc", "Cf"} for character in key)
    ):
        raise AuthorityPolicyError(f"authority_key_not_canonical:{path}:{key!r}")
    return _SEPARATORS.sub("", key).casefold()


def authority_value_is_nonpromoting(value: Any, policy: AuthorityPolicy) -> bool:
    if value is False or value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, str):
        return value in policy.safe_statuses
    if isinstance(value, dict):
        return (
            set(value) == {"status"}
            and isinstance(value["status"], str)
            and value["status"] in policy.safe_statuses
        )
    return False


def _is_semantic_authority_alias(canonical_key: str) -> bool:
    """Catch future authority synonyms without matching neutral release metadata."""

    tokens = frozenset(canonical_key.split("_"))
    qualifiers = {
        "allow",
        "allowed",
        "approval",
        "approved",
        "authority",
        "candidate",
        "certified",
        "complete",
        "decision",
        "eligible",
        "eligibility",
        "enabled",
        "granted",
        "live",
        "pass",
        "passed",
        "permitted",
        "promoted",
        "promotion",
        "ready",
        "readiness",
        "status",
        "use",
        "validation",
        "verified",
    }
    authority_domains = {
        "customer",
        "design",
        "independent",
        "legal",
        "pilot",
        "production",
        "release",
        "sale",
        "scientific",
    }
    domain_present = bool(tokens & authority_domains) or any(
        token.startswith("commercial") or token.startswith("redistribut")
        for token in tokens
    )
    return bool(
        canonical_key
        in {
            "commercializable",
            "fit_for_use",
            "general_availability",
            "go_live",
            "level_2_eligible",
            "operator_identity_credentials_verified",
            "redistributable",
        }
        or (domain_present and tokens & qualifiers)
    )


def promoted_authority_violations(
    value: Any,
    policy: AuthorityPolicy,
    path: str = "$",
    parent_key: str | None = None,
    inside_open_claims: bool = False,
    json_pointer: tuple[str, ...] = (),
) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key!r}"
            try:
                canonical_key = canonical_authority_key(key, child_path)
                compact_key = compact_authority_key(key, child_path)
            except AuthorityPolicyError as exc:
                violations.append(str(exc))
                continue
            is_grants = canonical_key == "grants" or compact_key == "grants"
            is_negative_container = (
                canonical_key in policy.negative_authority_token_containers
                or compact_key in policy.negative_authority_token_compact_containers
            )
            is_prohibited = (
                canonical_key in policy.prohibited_keys
                or compact_key in policy.prohibited_compact_keys
            )
            affix_prohibited = any(
                prohibited.replace("_", "") in compact_key
                for prohibited in policy.prohibited_keys
                if "_" in prohibited
            )
            semantic_alias = _is_semantic_authority_alias(canonical_key)
            is_open_claims = (
                canonical_key in {"claims", "effective_claims", "stored_claims"}
                or compact_key in {"claims", "effectiveclaims", "storedclaims"}
            )
            if (is_grants or is_negative_container) and not isinstance(child, list):
                violations.append(f"authority_token_container_not_list:{child_path}")
            if is_open_claims and key != canonical_key:
                violations.append(f"noncanonical_open_claim_container:{child_path}")
            if is_prohibited and (
                key != canonical_key or canonical_key not in policy.prohibited_keys
            ):
                violations.append(f"noncanonical_authority_key:{child_path}")
            if (
                is_prohibited or affix_prohibited or semantic_alias
            ) and not authority_value_is_nonpromoting(child, policy):
                violations.append(f"promoted_authority:{child_path}")
            child_pointer = (*json_pointer, canonical_key)
            open_object_keys = {
                ("quality_evidence",): {"status", "authority", "workflow_name", "run_id", "run_number", "run_attempt", "trigger_event", "conclusion", "head_branch", "head_sha", "html_url", "reason"},
                ("authority_tracks", "internal_license_due_diligence", "evidence"): {"path", "sha256", "schema_version", "artifact_hash", "source_commit_sha", "source_commit_matches_current", "contract_pass", "validation_reason", "third_party_redistribution_clearance"},
                ("bounded_planar_external_vv",): {"path", "sha256", "schema_version", "source_commit_sha", "source_commit_matches_current", "artifact_load_pass", "status_check_pass", "validation_pass", "validation_reason", "status", "contract_pass", "claims", "stored_claims", "claim_boundary", "summary", "stored_status", "stored_contract_pass", "stored_summary", "execution_package_binding", "supplemental_execution_package_bindings", "current_source_workflow_binding", "same_operator_execution_binding", "same_operator_supplemental_execution_binding", "operator_intake_binding", "stored_execution_package_binding", "stored_supplemental_execution_package_bindings", "stored_current_source_workflow_binding", "stored_same_operator_execution_binding", "stored_same_operator_supplemental_execution_binding", "stored_operator_intake_binding", "blockers"},
            }
            allowed_object_keys = open_object_keys.get(json_pointer)
            if allowed_object_keys is not None and key not in allowed_object_keys and not authority_value_is_nonpromoting(child, policy):
                violations.append(f"unapproved_truthy_open_object:{child_path}")
            scalar_shapes: dict[tuple[str, ...], dict[str, tuple[type, ...]]] = {
                ("quality_evidence",): {
                    "status": (str,), "authority": (str,), "workflow_name": (str,),
                    "run_id": (int,), "run_number": (int,), "run_attempt": (int,),
                    "trigger_event": (str,), "conclusion": (str,), "head_branch": (str,),
                    "head_sha": (str,), "html_url": (str,), "reason": (str,),
                },
                ("authority_tracks", "internal_license_due_diligence", "evidence"): {
                    "path": (str,), "sha256": (str,), "schema_version": (str, type(None)),
                    "artifact_hash": (str, type(None)), "source_commit_sha": (str, type(None)),
                    "source_commit_matches_current": (bool,), "contract_pass": (bool,),
                    "validation_reason": (str,), "third_party_redistribution_clearance": (str,),
                },
                ("bounded_planar_external_vv",): {
                    "path": (str,), "sha256": (str,), "schema_version": (str, type(None)),
                    "source_commit_sha": (str, type(None)), "source_commit_matches_current": (bool,),
                    "artifact_load_pass": (bool,), "status_check_pass": (bool,), "validation_pass": (bool,),
                    "validation_reason": (str,), "status": (str,), "contract_pass": (bool,),
                    "summary": (dict, type(None)), "stored_status": (str, type(None)),
                    "stored_contract_pass": (bool, type(None)), "stored_summary": (dict, type(None)),
                    "execution_package_binding": (dict, type(None)), "supplemental_execution_package_bindings": (list, type(None)),
                    "current_source_workflow_binding": (dict, type(None)), "same_operator_execution_binding": (dict, type(None)),
                    "same_operator_supplemental_execution_binding": (dict, type(None)), "operator_intake_binding": (dict, type(None)),
                    "stored_execution_package_binding": (dict, type(None)), "stored_supplemental_execution_package_bindings": (list, type(None)),
                    "stored_current_source_workflow_binding": (dict, type(None)), "stored_same_operator_execution_binding": (dict, type(None)),
                    "stored_same_operator_supplemental_execution_binding": (dict, type(None)), "stored_operator_intake_binding": (dict, type(None)),
                    "claims": (dict,), "stored_claims": (dict,), "claim_boundary": (str,), "blockers": (list,),
                },
            }
            expected_types = scalar_shapes.get(json_pointer, {}).get(key)
            if expected_types is not None and (type(child) not in expected_types):
                violations.append(f"open_object_value_shape_invalid:{child_path}")
            numerical_keys = {"bounded_candidate", "bounded_j1_j5_and_exact_engineering_recovery_candidate", "bounded_material_geometric_newton", "bounded_native_coo_csr_and_fail_closed_exact_conditioning_candidate", "bounded_reference_candidate", "bounded_repository_benchmark_candidate", "bounded_source_bound_uniaxial_crack_band_candidate", "comparison_contract_only_no_result_promotion", "constitutive_candidate", "consumer_only", "entity_scan_and_model_health_only", "exact_bounded_candidate", "exact_reaction_member_section_fiber_recovery", "input_translation_with_provenance", "none", "numerical_and_engineering_within_supported_elements", "numerical_within_explicit_frame_truss_mass_profile", "numerical_within_explicit_preload_profile", "proposal_and_evaluation_only", "validated_input_contract"}
            if json_pointer == ("result_authority", "numerical_authority_counts") and (key not in numerical_keys or type(child) is not int or child < 0):
                violations.append(f"numerical_authority_count_invalid:{child_path}")
            exact_pointer_keys = {
                ("bounded_planar_external_vv", "claims"): frozenset({"recommended_matrix_technical_coverage_complete", "fresh_current_source_technical_matrix_complete", "fresh_current_source_external_matrix_complete", "independent_operator_attested", "legal_use_approved", "formal_promotion_receipt_attached", "bounded_planar_profile_level_2"}),
                ("bounded_planar_external_vv", "stored_claims"): frozenset({"recommended_matrix_technical_coverage_complete", "fresh_current_source_technical_matrix_complete", "fresh_current_source_external_matrix_complete", "independent_operator_attested", "legal_use_approved", "formal_promotion_receipt_attached", "bounded_planar_profile_level_2"}),
                ("bounded_planar_external_vv", "summary"): frozenset({"requirement_count", "technical_reference_present_count", "fresh_current_source_technical_count", "current_product_replay_only_count", "fresh_external_technical_count", "fresh_independent_preflight_technical_count", "promotion_eligible_count", "missing_count", "execution_package_available_count", "current_source_execution_prepared_count"}),
                ("bounded_planar_external_vv", "stored_summary"): frozenset({"requirement_count", "technical_reference_present_count", "fresh_current_source_technical_count", "current_product_replay_only_count", "fresh_external_technical_count", "fresh_independent_preflight_technical_count", "promotion_eligible_count", "missing_count", "execution_package_available_count", "current_source_execution_prepared_count"}),
                ("bounded_planar_external_vv", "execution_package_binding"): frozenset({"package_id", "path", "file_sha256", "artifact_hash", "source_commit_sha", "execution_workflow", "requirement_ids", "contract_pass", "external_solver_execution", "verification_matrix_credit"}),
                ("bounded_planar_external_vv", "stored_execution_package_binding"): frozenset({"package_id", "path", "file_sha256", "artifact_hash", "source_commit_sha", "execution_workflow", "requirement_ids", "contract_pass", "external_solver_execution", "verification_matrix_credit"}),
                ("bounded_planar_external_vv", "supplemental_execution_package_bindings"): frozenset({"package_id", "path", "file_sha256", "artifact_hash", "source_commit_sha", "execution_workflow", "requirement_ids", "contract_pass", "external_solver_execution", "verification_matrix_credit"}),
                ("bounded_planar_external_vv", "stored_supplemental_execution_package_bindings"): frozenset({"package_id", "path", "file_sha256", "artifact_hash", "source_commit_sha", "execution_workflow", "requirement_ids", "contract_pass", "external_solver_execution", "verification_matrix_credit"}),
                ("bounded_planar_external_vv", "current_source_workflow_binding"): frozenset("attestation_attached,attestation_required,contract_pass,current_source_execution_attached,external_solver_ids,file_sha256,independent_operator_attested,prepared_case_ids,prepared_requirement_ids,repository_path,same_operator_execution_attached,trigger_branch,verification_level_2,verification_matrix_credit,workflow_id".split(",")),
                ("bounded_planar_external_vv", "stored_current_source_workflow_binding"): frozenset("attestation_attached,attestation_required,contract_pass,current_source_execution_attached,external_solver_ids,file_sha256,independent_operator_attested,prepared_case_ids,prepared_requirement_ids,repository_path,same_operator_execution_attached,trigger_branch,verification_level_2,verification_matrix_credit,workflow_id".split(",")),
                ("bounded_planar_external_vv", "same_operator_execution_binding"): frozenset("actual_external_solver_execution,artifact_hash,cross_environment_numerical_parity,file_sha256,fresh_child_receipt_ids,fresh_external_runtime_execution,independent_operator_attested,path,product_legal_license_approval,reason,same_operator_container_isolated_reproduction,source_commit_sha,status,technical_contract_pass,verification_level_2".split(",")),
                ("bounded_planar_external_vv", "stored_same_operator_execution_binding"): frozenset("actual_external_solver_execution,artifact_hash,cross_environment_numerical_parity,file_sha256,fresh_child_receipt_ids,fresh_external_runtime_execution,independent_operator_attested,path,product_legal_license_approval,reason,same_operator_container_isolated_reproduction,source_commit_sha,status,technical_contract_pass,verification_level_2".split(",")),
                ("bounded_planar_external_vv", "same_operator_supplemental_execution_binding"): frozenset("actual_external_solver_execution,artifact_hash,case_ids,container_isolated_reproduction,current_product_replay_binding_hash,current_product_replay_pass,execution_binding_hash,execution_window,external_engine_invoked_case_count,external_execution_reused,external_execution_source_commit_sha,external_runtime_executed_in_this_generation,family_ids,file_sha256,fresh_current_source_external_execution,historical_execution_binding_hash,historical_execution_input_binding_pass,independent_operator_attested,independent_preflight_case_ids,path,product_legal_license_approval,reason,runtime_asset_bytes_attached,same_operator_local_execution,source_commit_sha,status,technical_contract_pass,verification_level_2".split(",")),
                ("bounded_planar_external_vv", "stored_same_operator_supplemental_execution_binding"): frozenset("actual_external_solver_execution,artifact_hash,case_ids,container_isolated_reproduction,current_product_replay_binding_hash,current_product_replay_pass,execution_binding_hash,execution_window,external_engine_invoked_case_count,external_execution_reused,external_execution_source_commit_sha,external_runtime_executed_in_this_generation,family_ids,file_sha256,fresh_current_source_external_execution,historical_execution_binding_hash,historical_execution_input_binding_pass,independent_operator_attested,independent_preflight_case_ids,path,product_legal_license_approval,reason,runtime_asset_bytes_attached,same_operator_local_execution,source_commit_sha,status,technical_contract_pass,verification_level_2".split(",")),
                ("bounded_planar_external_vv", "operator_intake_binding"): frozenset("attestation_id,attestation_sha256,cryptographic_signature_verified,fresh_external_runtime_execution,intake_contract_pass,operator_identity_credentials_verified,operator_independence_declared,public_key_sha256,reason,signature_sha256,signed_payload_sha256,source_commit_sha,status,verification_level_2".split(",")),
                ("bounded_planar_external_vv", "stored_operator_intake_binding"): frozenset("attestation_id,attestation_sha256,cryptographic_signature_verified,fresh_external_runtime_execution,intake_contract_pass,operator_identity_credentials_verified,operator_independence_declared,public_key_sha256,reason,signature_sha256,signed_payload_sha256,source_commit_sha,status,verification_level_2".split(",")),
                ("bounded_planar_external_vv", "execution_package_binding", "execution_workflow"): frozenset({"repository_path", "packaged_path", "file_sha256"}),
                ("bounded_planar_external_vv", "stored_execution_package_binding", "execution_workflow"): frozenset({"repository_path", "packaged_path", "file_sha256"}),
                ("bounded_planar_external_vv", "supplemental_execution_package_bindings", "execution_workflow"): frozenset({"repository_path", "packaged_path", "file_sha256"}),
                ("bounded_planar_external_vv", "stored_supplemental_execution_package_bindings", "execution_workflow"): frozenset({"repository_path", "packaged_path", "file_sha256"}),
                ("bounded_planar_external_vv", "same_operator_supplemental_execution_binding", "execution_window"): frozenset({"started_at", "completed_at"}),
                ("bounded_planar_external_vv", "stored_same_operator_supplemental_execution_binding", "execution_window"): frozenset({"started_at", "completed_at"}),
            }
            exact_keys = exact_pointer_keys.get(json_pointer)
            if json_pointer[:1] == ("bounded_planar_external_vv",) and len(json_pointer) > 1 and (exact_keys is None or key not in exact_keys) and not authority_value_is_nonpromoting(child, policy):
                violations.append(f"unapproved_truthy_exact_pointer:{child_path}")
            # Technical true claims are deliberately bound to their schema location.
            # A known key transplanted below an arbitrary/future object is not the
            # same claim and must fail closed.
            pointer_true_claims = {
                ("claims",): policy.allowed_true_technical_completeness,
                ("bounded_planar_external_vv", "claims"): frozenset({"recommended_matrix_technical_coverage_complete", "fresh_current_source_technical_matrix_complete", "fresh_current_source_external_matrix_complete"}),
                ("bounded_planar_external_vv", "stored_claims"): frozenset({"recommended_matrix_technical_coverage_complete", "fresh_current_source_technical_matrix_complete", "fresh_current_source_external_matrix_complete"}),
                ("internal_license_due_diligence", "claims"): frozenset({"internal_due_diligence_complete", "license_inventory_complete", "spdx_notices_complete", "redistribution_boundaries_explicit", "source_use_declarations_complete"}),
                ("authority_tracks", "internal_license_due_diligence", "claims"): frozenset({"internal_due_diligence_complete", "license_inventory_complete", "spdx_notices_complete", "redistribution_boundaries_explicit", "source_use_declarations_complete"}),
                ("external_vv_nonpromotion", "effective_claims"): frozenset(),
            }
            allowed_here = pointer_true_claims.get(json_pointer, frozenset())
            canonical_allowed_true = {canonical_authority_key(item, "$policy") for item in policy.allowed_true_technical_completeness}
            if child is True and canonical_key in canonical_allowed_true and key not in allowed_here:
                violations.append(f"unapproved_technical_true_path:{child_path}")
            if inside_open_claims and not authority_value_is_nonpromoting(child, policy):
                if not (
                    child is True
                    and canonical_key in canonical_allowed_true
                    and key in allowed_here
                ):
                    violations.append(f"unapproved_true_open_claim:{child_path}")
            normalized_parent = "grants" if is_grants else canonical_key
            if is_negative_container:
                normalized_parent = next(
                    value
                    for value in policy.negative_authority_token_containers
                    if value == canonical_key or value.replace("_", "") == compact_key
                )
            violations.extend(
                promoted_authority_violations(
                    child,
                    policy,
                    child_path,
                    parent_key=normalized_parent,
                    inside_open_claims=inside_open_claims or is_open_claims,
                    json_pointer=child_pointer,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            if (
                parent_key == "grants"
                or parent_key in policy.negative_authority_token_containers
            ) and not isinstance(child, str):
                violations.append(f"authority_token_not_string:{child_path}")
                continue
            if isinstance(child, str):
                try:
                    canonical_token = canonical_authority_key(child, child_path)
                    compact_token = compact_authority_key(child, child_path)
                except AuthorityPolicyError as exc:
                    violations.append(str(exc))
                    continue
                if parent_key == "grants":
                    if (
                        child != canonical_token
                        or canonical_token not in policy.allowed_technical_grants
                    ):
                        violations.append(f"unapproved_technical_grant:{child_path}")
                elif (
                    parent_key
                    not in {"blockers", "blockers_remaining", "promotion_blockers"}
                    and (
                        canonical_token in policy.prohibited_keys
                        or compact_token in policy.prohibited_compact_keys
                        or any(
                            prohibited.replace("_", "") in compact_token
                            for prohibited in policy.prohibited_keys
                            if "_" in prohibited
                        )
                    )
                ):
                    if parent_key in policy.negative_authority_token_containers:
                        if (
                            child != canonical_token
                            or canonical_token not in policy.prohibited_keys
                        ):
                            violations.append(
                                f"noncanonical_negative_authority_token:{child_path}"
                            )
                    else:
                        violations.append(f"promoted_authority_token:{child_path}")
            else:
                violations.extend(
                    promoted_authority_violations(
                        child,
                        policy,
                        child_path,
                        parent_key=parent_key,
                        inside_open_claims=inside_open_claims,
                        json_pointer=json_pointer,
                    )
                )
    return violations
