#!/usr/bin/env python3
"""Build acyclic, profile-scoped Developer Preview and commercial states.

Developer Preview consumes only Developer Preview evidence. The bounded-planar
commercial state consumes leaf evidence for Developer Preview, workstation,
customer shadow, product/legal approval, and independent external V&V. It never
consumes the legacy PM report, blocker action register, closure board, or any
artifact generated from this commercial state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from jsonschema import SchemaError, ValidationError

from product_authority_policy import (
    PRODUCT_AUTHORITY_POLICY,
    PRODUCT_AUTHORITY_POLICY_SCHEMA,
    load_product_authority_policy,
)
from strict_json import strict_json_loads


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DP_STATUS = (
    ROOT
    / "implementation/phase1/release_evidence/productization/developer_preview_rc_status.json"
)
DEFAULT_CUSTOMER_SHADOW = (
    ROOT / "implementation/phase1/customer_shadow_evidence_status.json"
)
DEFAULT_LICENSE_CLOSURE = (
    ROOT
    / "implementation/phase1/release_evidence/productization/license_status_closure_report.json"
)
DEFAULT_WORKSTATION = ROOT / "implementation/phase1/workstation_delivery_readiness.json"
DEFAULT_EXTERNAL_VV = (
    ROOT / "artifacts/vv/opensees_calculix_clean_runner/clean_runner_receipt.json"
)

LEGACY_CYCLIC_INPUTS = {
    "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json",
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json",
    "implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.json",
}


class ProfileScopedStateError(RuntimeError):
    """Raised when a source product-state artifact is unavailable or malformed."""


def _read_object_and_bytes(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        payload = strict_json_loads(raw)
    except (OSError, UnicodeError, ValueError, SchemaError, ValidationError) as error:
        raise ProfileScopedStateError(f"invalid_json:{path}") from error
    if not isinstance(payload, dict):
        raise ProfileScopedStateError(f"json_not_object:{path}")
    return payload, raw


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def _input_from_bytes(path: Path, raw: bytes) -> dict[str, str]:
    return {
        "path": path.as_posix(),
        "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
    }


def _path_identity(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError as error:
        raise ProfileScopedStateError(f"path_identity_unavailable:{path}") from error


def _paths_alias(left: Path, right: Path) -> bool:
    if _path_identity(left) == _path_identity(right):
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError as error:
        raise ProfileScopedStateError(
            f"path_alias_check_unavailable:{left}:{right}"
        ) from error


def _authority_source_paths(authority_repo_root: Path) -> tuple[Path, Path]:
    return (
        authority_repo_root / PRODUCT_AUTHORITY_POLICY,
        authority_repo_root / PRODUCT_AUTHORITY_POLICY_SCHEMA,
    )


def _legacy_cyclic_paths(authority_repo_root: Path) -> tuple[Path, ...]:
    return tuple(
        authority_repo_root / relative for relative in sorted(LEGACY_CYCLIC_INPUTS)
    )


def _validate_cli_path_separation(
    *,
    developer_preview_out: Path,
    commercial_out: Path,
    input_paths: Sequence[Path],
    authority_repo_root: Path,
) -> None:
    outputs = (developer_preview_out, commercial_out)
    if _paths_alias(outputs[0], outputs[1]):
        raise ProfileScopedStateError("output_paths_alias")
    protected_inputs = (
        *input_paths,
        *_authority_source_paths(authority_repo_root),
        *_legacy_cyclic_paths(authority_repo_root),
    )
    for output in outputs:
        if any(_paths_alias(output, source) for source in protected_inputs):
            raise ProfileScopedStateError("output_path_aliases_protected_input")


def _authority_scope(
    *,
    authority_repo_root: Path,
    target_profile: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, str]]]:
    try:
        policy, policy_sha256, schema_sha256 = load_product_authority_policy(
            authority_repo_root
        )
    except (OSError, UnicodeError, ValueError, SchemaError, ValidationError) as error:
        raise ProfileScopedStateError("product_authority_policy_invalid") from error
    profiles = {
        str(row["profile_id"]): row
        for row in policy["bounded_profiles"]
        if isinstance(row, Mapping)
    }
    profile = profiles.get(target_profile)
    if not isinstance(profile, Mapping):
        raise ProfileScopedStateError(
            f"authority_policy_target_profile_missing:{target_profile}"
        )
    binding = {
        "policy_id": str(policy["policy_id"]),
        "policy_path": PRODUCT_AUTHORITY_POLICY.as_posix(),
        "policy_sha256": policy_sha256,
        "schema_path": PRODUCT_AUTHORITY_POLICY_SCHEMA.as_posix(),
        "schema_sha256": schema_sha256,
        "target_profile": target_profile,
        "g1_required": profile["g1_required"],
        "gpu_required": profile["gpu_required"],
        "release_authority": policy["current_product"]["release_authority"],
        "commercial_authority": policy["current_product"]["commercial_authority"],
    }
    inputs = {
        "product_authority_policy": {
            "path": PRODUCT_AUTHORITY_POLICY.as_posix(),
            "sha256": policy_sha256,
        },
        "product_authority_policy_schema": {
            "path": PRODUCT_AUTHORITY_POLICY_SCHEMA.as_posix(),
            "sha256": schema_sha256,
        },
    }
    return dict(profile), binding, inputs


def _policy_identity(binding: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        binding.get(key)
        for key in (
            "policy_id",
            "policy_path",
            "policy_sha256",
            "schema_path",
            "schema_sha256",
            "release_authority",
            "commercial_authority",
        )
    )


def _blockers(payload: Mapping[str, Any]) -> list[str]:
    rows = payload.get("blockers", [])
    return [str(item) for item in rows] if isinstance(rows, list) else []


def _summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, Mapping) else {}


def _claims(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = payload.get("claims")
    return value if isinstance(value, Mapping) else {}


def build_developer_preview_state(
    *,
    source_commit_sha: str,
    developer_preview_status: Path,
    authority_repo_root: Path = ROOT,
) -> dict[str, Any]:
    rc, rc_raw = _read_object_and_bytes(developer_preview_status)
    _, authority_binding, authority_inputs = _authority_scope(
        authority_repo_root=authority_repo_root,
        target_profile="planar_frame_verified_alpha.v1",
    )
    blockers = _blockers(rc)
    final_gates = [row for row in rc.get("final_gates", []) if isinstance(row, dict)]
    deliverables = [row for row in rc.get("deliverables", []) if isinstance(row, dict)]
    state_ready = bool(
        rc.get("developer_preview_ready")
        or rc.get("developer_preview_release_candidate_ready")
    )
    return {
        "schema_version": "developer-preview-product-state.v1",
        "source_commit_sha": source_commit_sha,
        "target_profile": "planar_frame_verified_alpha.v1",
        "contract_pass": True,
        "state_ready": state_ready,
        "status": "ready" if state_ready else "blocked",
        "public": True,
        "release_eligible": False,
        "deliverable_count": int(rc.get("deliverable_count", len(deliverables))),
        "deliverable_pass_count": int(
            rc.get(
                "deliverable_pass_count",
                sum(1 for row in deliverables if row.get("contract_pass") is True),
            )
        ),
        "final_gate_count": int(rc.get("final_gate_count", len(final_gates))),
        "final_gate_pass_count": int(
            rc.get(
                "final_gate_pass_count",
                sum(1 for row in final_gates if row.get("contract_pass") is True),
            )
        ),
        "blockers": blockers,
        "future_commercial_gates": [
            str(item) for item in rc.get("future_commercial_gates", [])
        ],
        "commercial_inputs_consumed": [],
        "inputs": {
            "developer_preview_status": _input_from_bytes(
                developer_preview_status, rc_raw
            ),
            **authority_inputs,
        },
        "authority_scope_policy": authority_binding,
        "claim_boundary": (
            "This state evaluates the bounded public Developer Preview only. "
            "Customer shadow, product license, license-server operation, SLA, "
            "independent commercial-product readiness, GPU residency, and general "
            "solver breadth remain future gates and do not invalidate this schema."
        ),
    }


def build_commercial_state(
    *,
    source_commit_sha: str,
    developer_preview_state: Mapping[str, Any],
    developer_preview_status: Path,
    customer_shadow_status: Path,
    license_closure: Path,
    workstation_readiness: Path,
    external_vv_receipt: Path,
    developer_preview_state_path: Path,
    authority_repo_root: Path = ROOT,
) -> dict[str, Any]:
    source_paths = (
        developer_preview_status,
        customer_shadow_status,
        license_closure,
        workstation_readiness,
        external_vv_receipt,
        *_authority_source_paths(authority_repo_root),
    )
    if any(
        _paths_alias(developer_preview_state_path, source_path)
        for source_path in source_paths
    ):
        raise ProfileScopedStateError(
            "developer_preview_state_path_aliases_source_input"
        )
    consumed_path_candidates = (developer_preview_state_path, *source_paths)
    if any(
        _paths_alias(consumed_path, legacy_path)
        for consumed_path in consumed_path_candidates
        for legacy_path in _legacy_cyclic_paths(authority_repo_root)
    ):
        raise ProfileScopedStateError("legacy_cyclic_input_consumed")
    expected_developer_state = build_developer_preview_state(
        source_commit_sha=source_commit_sha,
        developer_preview_status=developer_preview_status,
        authority_repo_root=authority_repo_root,
    )
    if dict(developer_preview_state) != expected_developer_state:
        raise ProfileScopedStateError("developer_preview_state_binding_mismatch")
    developer_state_raw = _serialized(expected_developer_state).encode("utf-8")
    customer, customer_raw = _read_object_and_bytes(customer_shadow_status)
    license_report, license_raw = _read_object_and_bytes(license_closure)
    workstation, workstation_raw = _read_object_and_bytes(workstation_readiness)
    external_vv, external_vv_raw = _read_object_and_bytes(external_vv_receipt)
    authority_profile, authority_binding, authority_inputs = _authority_scope(
        authority_repo_root=authority_repo_root,
        target_profile="bounded_planar_limited_commercial",
    )
    developer_authority = developer_preview_state.get("authority_scope_policy")
    if (
        not isinstance(developer_authority, Mapping)
        or _policy_identity(developer_authority) != _policy_identity(authority_binding)
        or developer_authority.get("target_profile") != "planar_frame_verified_alpha.v1"
        or developer_authority.get("g1_required") is not False
        or developer_authority.get("gpu_required") is not False
    ):
        raise ProfileScopedStateError("developer_preview_authority_policy_mismatch")
    external_claims = _claims(external_vv)
    customer_summary = _summary(customer)
    product_receipts = external_vv.get("product_receipts")
    if not isinstance(product_receipts, Mapping):
        product_receipts = {}
    code_receipt = product_receipts.get("code_to_code")
    modal_receipt = product_receipts.get("modal_buckling")
    code_receipt = code_receipt if isinstance(code_receipt, Mapping) else {}
    modal_receipt = modal_receipt if isinstance(modal_receipt, Mapping) else {}

    checks = {
        "developer_preview_ready": developer_preview_state.get("state_ready") is True,
        "workstation_delivery_ready": workstation.get("contract_pass") is True,
        "customer_shadow_ready": customer.get("contract_pass") is True
        and int(customer_summary.get("completed_shadow_case_count", 0))
        >= int(customer_summary.get("min_completed_shadow_cases", 3)),
        "product_license_ready": license_report.get("contract_pass") is True,
        "external_vv_source_matches": external_vv.get("source_commit_sha")
        == source_commit_sha,
        "fresh_code_to_code_execution": code_receipt.get(
            "fresh_external_runtime_execution"
        )
        is True,
        "fresh_modal_buckling_execution": modal_receipt.get(
            "fresh_external_runtime_execution"
        )
        is True,
        "independent_operator_attached": external_claims.get(
            "independent_operator_attestation"
        )
        is True,
        "verification_level_2": external_claims.get("verification_level_2") is True,
        "external_runtime_use_approved": external_claims.get(
            "external_runtime_redistribution_approval"
        )
        is True,
        "external_product_legal_approved": external_claims.get(
            "product_legal_license_approval"
        )
        is True,
    }
    blockers: list[str] = []
    blocker_map = {
        "developer_preview_ready": "developer_preview_not_ready",
        "workstation_delivery_ready": "workstation_delivery_not_ready",
        "customer_shadow_ready": "customer_shadow_not_ready",
        "product_license_ready": "product_license_not_ready",
        "external_vv_source_matches": "external_vv_source_commit_mismatch",
        "fresh_code_to_code_execution": "fresh_code_to_code_execution_missing",
        "fresh_modal_buckling_execution": "fresh_modal_buckling_execution_missing",
        "independent_operator_attached": "independent_operator_attestation_missing",
        "verification_level_2": "verification_level_2_not_achieved",
        "external_runtime_use_approved": "external_runtime_redistribution_approval_missing",
        "external_product_legal_approved": "external_product_legal_approval_missing",
    }
    for key, blocker in blocker_map.items():
        if not checks[key]:
            blockers.append(blocker)
    blockers.extend(f"customer_shadow::{item}" for item in _blockers(customer))
    blockers.extend(f"license::{item}" for item in _blockers(license_report))
    blockers = list(dict.fromkeys(blockers))
    state_ready = not blockers

    input_rows = {
        "customer_shadow_status": _input_from_bytes(
            customer_shadow_status, customer_raw
        ),
        "developer_preview_status": dict(
            expected_developer_state["inputs"]["developer_preview_status"]
        ),
        "developer_preview_state": {
            "path": developer_preview_state_path.as_posix(),
            "sha256": "sha256:" + hashlib.sha256(developer_state_raw).hexdigest(),
        },
        "license_closure": _input_from_bytes(license_closure, license_raw),
        "workstation_readiness": _input_from_bytes(
            workstation_readiness, workstation_raw
        ),
        "external_vv_receipt": _input_from_bytes(external_vv_receipt, external_vv_raw),
        **authority_inputs,
    }
    return {
        "schema_version": "bounded-planar-commercial-product-state.v2",
        "source_commit_sha": source_commit_sha,
        "target_profile": "bounded_planar_limited_commercial",
        "product_scope": "bounded_planar_cpu",
        "contract_pass": True,
        "state_ready": state_ready,
        "status": "ready" if state_ready else "blocked",
        "checks": checks,
        "blockers": blockers,
        "developer_preview_state": {
            "schema_version": developer_preview_state.get("schema_version"),
            "source_commit_sha": developer_preview_state.get("source_commit_sha"),
            "target_profile": developer_preview_state.get("target_profile"),
            "state_ready": developer_preview_state.get("state_ready"),
            "sha256": "sha256:" + hashlib.sha256(developer_state_raw).hexdigest(),
        },
        "inputs": input_rows,
        "authority_scope_policy": authority_binding,
        "legacy_pm_report_consumed": False,
        "legacy_cyclic_inputs_consumed": [],
        "gpu_required_for_scope": authority_profile["gpu_required"],
        "g1_required_for_scope": authority_profile["g1_required"],
        "dependency_dag": {
            "schema_version": "profile-scoped-product-state-dag.v1",
            "acyclic": True,
            "nodes": [
                "product_authority_policy_schema",
                "product_authority_policy",
                "developer_preview_status",
                "developer_preview_state",
                "customer_shadow_status",
                "license_closure",
                "workstation_readiness",
                "external_vv_receipt",
                "bounded_planar_commercial_state",
            ],
            "edges": [
                ["product_authority_policy_schema", "product_authority_policy"],
                ["product_authority_policy", "developer_preview_state"],
                [
                    "product_authority_policy",
                    "bounded_planar_commercial_state",
                ],
                ["developer_preview_status", "developer_preview_state"],
                ["developer_preview_state", "bounded_planar_commercial_state"],
                ["customer_shadow_status", "bounded_planar_commercial_state"],
                ["license_closure", "bounded_planar_commercial_state"],
                ["workstation_readiness", "bounded_planar_commercial_state"],
                ["external_vv_receipt", "bounded_planar_commercial_state"],
            ],
        },
        "claim_boundary": (
            "This state evaluates a bounded planar CPU commercial track. It is "
            "acyclic and does not consume the legacy PM report or its downstream "
            "action/closure artifacts. General solver breadth, G1 full-building "
            "closure, and GPU residency are separate product tracks and cannot be "
            "promoted by this state."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--developer-preview-status", type=Path, default=DEFAULT_DP_STATUS
    )
    parser.add_argument(
        "--customer-shadow-status", type=Path, default=DEFAULT_CUSTOMER_SHADOW
    )
    parser.add_argument("--license-closure", type=Path, default=DEFAULT_LICENSE_CLOSURE)
    parser.add_argument(
        "--workstation-readiness", type=Path, default=DEFAULT_WORKSTATION
    )
    parser.add_argument("--external-vv-receipt", type=Path, default=DEFAULT_EXTERNAL_VV)
    parser.add_argument("--developer-preview-out", type=Path, required=True)
    parser.add_argument("--commercial-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if len(args.source_commit) != 40 or any(
        character not in "0123456789abcdef" for character in args.source_commit
    ):
        raise ProfileScopedStateError("source_commit_sha_invalid")
    _validate_cli_path_separation(
        developer_preview_out=args.developer_preview_out,
        commercial_out=args.commercial_out,
        input_paths=(
            args.developer_preview_status,
            args.customer_shadow_status,
            args.license_closure,
            args.workstation_readiness,
            args.external_vv_receipt,
        ),
        authority_repo_root=ROOT,
    )
    dp = build_developer_preview_state(
        source_commit_sha=args.source_commit,
        developer_preview_status=args.developer_preview_status,
    )
    commercial = build_commercial_state(
        source_commit_sha=args.source_commit,
        developer_preview_state=dp,
        developer_preview_status=args.developer_preview_status,
        customer_shadow_status=args.customer_shadow_status,
        license_closure=args.license_closure,
        workstation_readiness=args.workstation_readiness,
        external_vv_receipt=args.external_vv_receipt,
        developer_preview_state_path=args.developer_preview_out,
    )
    _write_json(args.developer_preview_out, dp)
    _write_json(args.commercial_out, commercial)
    if args.json:
        print(
            _serialized({"developer_preview": dp, "commercial_release": commercial}),
            end="",
        )
    else:
        print(
            "profile-scoped product states: "
            f"developer_preview={dp['status']} | commercial={commercial['status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
