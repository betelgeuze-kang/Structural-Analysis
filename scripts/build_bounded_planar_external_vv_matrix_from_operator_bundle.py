#!/usr/bin/env python3
"""Build a non-promoting V&V matrix from one signed operator bundle."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import sys
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import build_bounded_planar_external_vv_matrix as matrix_builder  # noqa: E402
from strict_json import StrictJSONError, strict_json_load_path  # noqa: E402
from validate_external_vv_operator_attestation import (  # noqa: E402
    ExternalVVOperatorAttestationError,
    validate_external_vv_operator_attestation,
)


class OperatorMatrixBuildError(ValueError):
    """Stable failure for an invalid signed-bundle matrix input."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


RUNTIME_LOCK_BLOCKER = (
    "operator_bundle_external_runtime_bytes_not_pre_execution_hash_locked"
)


def _fail(code: str) -> NoReturn:
    raise OperatorMatrixBuildError(code)


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = strict_json_load_path(path)
    except (OSError, StrictJSONError) as exc:
        raise OperatorMatrixBuildError(code) from exc
    if not isinstance(payload, dict):
        _fail(code)
    return payload


def _bundle_file(bundle_root: Path, relative: str) -> Path:
    root = bundle_root.resolve()
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or raw.as_posix() != relative:
        _fail("operator_matrix_bundle_path_invalid")
    candidate = bundle_root / raw
    cursor = root
    for part in raw.parts:
        cursor /= part
        if cursor.is_symlink():
            _fail("operator_matrix_bundle_symlink_rejected")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise OperatorMatrixBuildError("operator_matrix_bundle_path_invalid") from exc
    if not resolved.is_file():
        _fail("operator_matrix_bundle_file_missing")
    return resolved


def _case_ids(receipt: Mapping[str, Any]) -> list[str]:
    cases = receipt.get("cases", receipt.get("comparisons"))
    if not isinstance(cases, list):
        _fail("operator_matrix_receipt_cases_invalid")
    result = sorted(
        str(row.get("case_id") or "")
        for row in cases
        if isinstance(row, Mapping)
        and (
            row.get("contract_pass") is True
            or row.get("technical_comparison_pass") is True
            or row.get("technical_rejection_pass") is True
            or row.get("technical_contract_pass") is True
        )
        and str(row.get("case_id") or "")
    )
    if not result or len(result) != len(set(result)):
        _fail("operator_matrix_receipt_case_inventory_invalid")
    return result


def _descriptor_receipt(
    descriptor: Mapping[str, Any], bundle_root: Path
) -> tuple[Path, dict[str, Any]]:
    path = _bundle_file(bundle_root, str(descriptor.get("path") or ""))
    receipt = _load_json(path, "operator_matrix_receipt_json_invalid")
    if (
        descriptor.get("file_sha256") != matrix_builder._file_sha256(path)
        or descriptor.get("artifact_hash") != receipt.get("artifact_hash")
        or receipt.get("artifact_hash") != matrix_builder._artifact_hash(receipt)
    ):
        _fail("operator_matrix_receipt_binding_invalid")
    return path, receipt


def _core_binding(
    *,
    receipt_id: str,
    descriptor: Mapping[str, Any],
    bundle_root: Path,
    source_commit_sha: str,
) -> dict[str, Any]:
    _path, receipt = _descriptor_receipt(descriptor, bundle_root)
    internal_source = receipt.get("internal_source")
    replay = receipt.get("replay_provenance")
    execution_source_commit = (
        replay.get("external_execution_source_commit_sha")
        if isinstance(replay, Mapping)
        else None
    )
    if (
        receipt.get("source_commit_sha") != source_commit_sha
        or receipt.get("technical_contract_pass") is not True
        or not isinstance(internal_source, Mapping)
        or not str(internal_source.get("source_set_hash") or "").startswith("sha256:")
        or not isinstance(replay, Mapping)
        or replay.get("current_product_replay_pass") is not True
        or (
            execution_source_commit is not None
            and (
                not isinstance(execution_source_commit, str)
                or len(execution_source_commit) != 40
                or any(
                    character not in "0123456789abcdef"
                    for character in execution_source_commit
                )
            )
        )
    ):
        _fail("operator_matrix_core_receipt_contract_invalid")
    case_ids = _case_ids(receipt)
    return {
        "receipt_id": receipt_id,
        "path": str(descriptor["path"]),
        "file_sha256": descriptor["file_sha256"],
        "artifact_hash": descriptor["artifact_hash"],
        "source_commit_sha": source_commit_sha,
        "external_execution_source_commit_sha": execution_source_commit,
        "source_set_hash": internal_source["source_set_hash"],
        "case_ids": case_ids,
        "external_engine_invoked_case_ids": case_ids,
        "technical_contract_pass": True,
        "current_product_replay_pass": True,
        # The v1 operator bundle binds versions and signed result bytes, but it
        # has no descriptor set for the exact OpenSees/CalculiX/BLAS runtime
        # bytes.  Preserve the replay as technical reference material without
        # granting fresh-current-source credit.  At this matrix boundary the
        # unsealed execution is deliberately classified as reused evidence,
        # even when the signed child receipt says it was generated in the
        # operator's current run.
        "external_execution_reused": True,
        "fresh_current_source_external_execution": False,
    }


def _supplemental_binding(
    *,
    receipt_id: str,
    descriptor: Mapping[str, Any],
    bundle_root: Path,
    source_commit_sha: str,
) -> dict[str, Any]:
    _path, receipt = _descriptor_receipt(descriptor, bundle_root)
    if (
        receipt.get("source_commit_sha") != source_commit_sha
        or receipt.get("technical_contract_pass") is not True
    ):
        _fail("operator_matrix_supplemental_receipt_contract_invalid")
    internal_source = receipt.get("internal_source")
    package_binding = receipt.get("package_binding")
    source_binding_hash = (
        internal_source.get("source_set_hash")
        if isinstance(internal_source, Mapping)
        else None
    )
    if source_binding_hash is None and isinstance(package_binding, Mapping):
        source_binding_hash = package_binding.get("artifact_hash")
    if source_binding_hash is None:
        source_binding_hash = receipt.get("source_binding_hash")
    if source_binding_hash is None:
        source_binding_hash = receipt.get("artifact_hash")
    if not str(source_binding_hash).startswith("sha256:"):
        _fail("operator_matrix_supplemental_source_binding_missing")
    case_ids = _case_ids(receipt)
    cases = receipt.get("cases", receipt.get("comparisons"))
    if not isinstance(cases, list):
        _fail("operator_matrix_supplemental_case_inventory_invalid")
    engine_invocation_by_case: dict[str, bool] = {}
    for row in cases:
        if not isinstance(row, Mapping):
            continue
        external_engine_invoked = row.get("external_engine_invoked")
        external_result = row.get("external_result")
        if external_engine_invoked is None and isinstance(external_result, Mapping):
            external_engine_invoked = external_result.get("external_engine_invoked")
        if external_engine_invoked is None:
            external_engine_invoked = True
        engine_invocation_by_case[str(row.get("case_id") or "")] = (
            external_engine_invoked
        )
    if any(
        not isinstance(engine_invocation_by_case.get(case_id), bool)
        for case_id in case_ids
    ):
        _fail("operator_matrix_supplemental_engine_invocation_invalid")
    external_engine_invoked_case_ids = [
        case_id for case_id in case_ids if engine_invocation_by_case[case_id] is True
    ]
    return {
        "receipt_id": receipt_id,
        "path": str(descriptor["path"]),
        "file_sha256": descriptor["file_sha256"],
        "artifact_hash": descriptor["artifact_hash"],
        "source_commit_sha": source_commit_sha,
        "source_binding_hash": source_binding_hash,
        "case_ids": case_ids,
        "external_engine_invoked_case_ids": external_engine_invoked_case_ids,
        "technical_contract_pass": True,
        "current_product_replay_pass": True,
        "external_execution_reused": False,
        "fresh_current_source_external_execution": False,
        "runtime_byte_lock_complete": False,
        "runtime_asset_bytes_attached": False,
        "runtime_asset_metadata_sealed": False,
        "producer_signing_privilege_separated": False,
    }


def _operator_binding(intake: Mapping[str, Any]) -> dict[str, Any]:
    signature = intake.get("signature")
    if not isinstance(signature, Mapping):
        _fail("operator_matrix_signature_binding_missing")
    return {
        "status": "available",
        "attestation_id": intake["attestation_id"],
        "attestation_sha256": intake["attestation_sha256"],
        "source_commit_sha": intake["source_commit_sha"],
        "signed_payload_sha256": signature["signed_payload_sha256"],
        "public_key_sha256": signature["public_key_sha256"],
        "signature_sha256": signature["signature_sha256"],
        "intake_contract_pass": True,
        "fresh_external_runtime_execution": True,
        "cryptographic_signature_verified": True,
        "operator_independence_declared": True,
        "operator_identity_credentials_verified": False,
        "verification_level_2": False,
    }


def build_operator_attested_matrix(
    attestation: Mapping[str, Any],
    *,
    bundle_root: Path,
    expected_source_commit_sha: str,
    repo_root: Path = ROOT,
    openssl: str = "openssl",
) -> dict[str, Any]:
    """Convert one verified signed bundle into fresh technical matrix coverage."""

    try:
        intake = validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=repo_root,
            openssl=openssl,
        )
    except ExternalVVOperatorAttestationError as exc:
        raise OperatorMatrixBuildError(
            f"operator_matrix_attestation_invalid:{exc.code}"
        ) from exc
    if (
        intake.get("intake_contract_pass") is not True
        or intake.get("fresh_external_runtime_execution") is not True
        or intake.get("source_commit_sha") != expected_source_commit_sha
    ):
        _fail("operator_matrix_attestation_authority_invalid")

    baseline = matrix_builder.build_bounded_planar_external_vv_matrix(
        repo_root=repo_root,
        same_operator_supplemental_receipt_path=Path(
            "__signed_operator_bundle_requires_dedicated_supplements__/receipt.json"
        ),
    )
    if baseline["source_commit_sha"] != expected_source_commit_sha:
        _fail("operator_matrix_current_source_mismatch")
    bundle = attestation.get("bundle")
    if not isinstance(bundle, Mapping):
        _fail("operator_matrix_bundle_invalid")

    core_bindings = [
        _core_binding(
            receipt_id=receipt_id,
            descriptor=bundle[key],
            bundle_root=bundle_root,
            source_commit_sha=expected_source_commit_sha,
        )
        for receipt_id, key in (
            ("code_to_code", "code_to_code"),
            ("modal_buckling", "modal_buckling"),
        )
    ]
    supplemental_bindings: list[dict[str, Any]] = []
    linear = bundle.get("bounded_planar_linear")
    if isinstance(linear, Mapping):
        descriptor = linear.get("technical_receipt")
        if not isinstance(descriptor, Mapping):
            _fail("operator_matrix_linear_receipt_descriptor_invalid")
        supplemental_bindings.append(
            _supplemental_binding(
                receipt_id="bounded_planar_linear",
                descriptor=descriptor,
                bundle_root=bundle_root,
                source_commit_sha=expected_source_commit_sha,
            )
        )
    modal_buckling = bundle.get("bounded_planar_modal_buckling")
    if isinstance(modal_buckling, Mapping):
        descriptor = modal_buckling.get("technical_receipt")
        if not isinstance(descriptor, Mapping):
            _fail("operator_matrix_modal_buckling_receipt_descriptor_invalid")
        supplemental_bindings.append(
            _supplemental_binding(
                receipt_id="bounded_planar_modal_buckling",
                descriptor=descriptor,
                bundle_root=bundle_root,
                source_commit_sha=expected_source_commit_sha,
            )
        )
    negative = bundle.get("bounded_planar_negative")
    if isinstance(negative, Mapping):
        descriptor = negative.get("technical_receipt")
        if not isinstance(descriptor, Mapping):
            _fail("operator_matrix_negative_receipt_descriptor_invalid")
        supplemental_bindings.append(
            _supplemental_binding(
                receipt_id="bounded_planar_negative",
                descriptor=descriptor,
                bundle_root=bundle_root,
                source_commit_sha=expected_source_commit_sha,
            )
        )
    scaling = bundle.get("bounded_planar_scaling")
    if isinstance(scaling, Mapping):
        descriptor = scaling.get("technical_receipt")
        if not isinstance(descriptor, Mapping):
            _fail("operator_matrix_scaling_receipt_descriptor_invalid")
        supplemental_bindings.append(
            _supplemental_binding(
                receipt_id="bounded_planar_scaling",
                descriptor=descriptor,
                bundle_root=bundle_root,
                source_commit_sha=expected_source_commit_sha,
            )
        )
    nonlinear_material_recovery = bundle.get(
        "bounded_planar_nonlinear_material_recovery"
    )
    if isinstance(nonlinear_material_recovery, Mapping):
        descriptor = nonlinear_material_recovery.get("technical_receipt")
        if not isinstance(descriptor, Mapping):
            _fail(
                "operator_matrix_nonlinear_material_recovery_receipt_descriptor_invalid"
            )
        supplemental_bindings.append(
            _supplemental_binding(
                receipt_id="bounded_planar_nonlinear_material_recovery",
                descriptor=descriptor,
                bundle_root=bundle_root,
                source_commit_sha=expected_source_commit_sha,
            )
        )
    additional = bundle.get("additional_receipts", [])
    if not isinstance(additional, list):
        _fail("operator_matrix_additional_receipts_invalid")
    for index, descriptor in enumerate(additional, start=1):
        if not isinstance(descriptor, Mapping):
            _fail("operator_matrix_additional_receipt_descriptor_invalid")
        supplemental_bindings.append(
            _supplemental_binding(
                receipt_id=f"operator_additional_{index:03d}",
                descriptor=descriptor,
                bundle_root=bundle_root,
                source_commit_sha=expected_source_commit_sha,
            )
        )

    # A supplemental receipt carries the per-case engine-invocation truth that
    # a broad core receipt cannot express. Prefer it when both cover a row so
    # independent preflight cases are not mislabeled as external executions.
    all_bindings = [*supplemental_bindings, *core_bindings]
    rows: list[dict[str, Any]] = []
    for baseline_row in baseline["requirements"]:
        row = dict(baseline_row)
        required_case_ids = set(row["required_external_case_ids"])
        binding = next(
            (
                candidate
                for candidate in all_bindings
                if required_case_ids.issubset(set(candidate["case_ids"]))
            ),
            None,
        )
        if binding is not None:
            verification_method = str(row["verification_method"])
            external_engine_invoked = required_case_ids.issubset(
                set(binding["external_engine_invoked_case_ids"])
            )
            fresh_technical = bool(
                binding["fresh_current_source_external_execution"] is True
                and binding.get("external_execution_reused") is not True
                and (
                    external_engine_invoked
                    if verification_method == "external_solver_execution"
                    else required_case_ids.isdisjoint(
                        set(binding["external_engine_invoked_case_ids"])
                    )
                )
            )
            row.update(
                {
                    "technical_reference_present": True,
                    "current_product_replay_pass": True,
                    "fresh_current_source_technical_validation": fresh_technical,
                    "fresh_current_source_external_execution": bool(
                        fresh_technical
                        and verification_method == "external_solver_execution"
                    ),
                    "independent_operator_attested": False,
                    "legal_use_approved": False,
                    "scientific_decision_pass": False,
                    "formal_promotion_receipt_attached": False,
                    "level2_eligible": False,
                    "status": (
                        "fresh_external_technical"
                        if verification_method == "external_solver_execution"
                        and fresh_technical
                        else (
                            "fresh_independent_preflight_technical"
                            if verification_method == "independent_preflight"
                            and fresh_technical
                            else "current_product_replay_only"
                        )
                    ),
                    "evidence": [
                        {
                            "receipt_id": binding["receipt_id"],
                            "path": binding["path"],
                            "artifact_hash": binding["artifact_hash"],
                            "case_ids": list(row["required_external_case_ids"]),
                        }
                    ],
                    "blockers": [
                        RUNTIME_LOCK_BLOCKER,
                        "independent_operator_identity_authentication_missing",
                        "product_legal_license_approval_missing",
                        "scientific_promotion_decision_missing",
                        "formal_level2_promotion_receipt_missing",
                    ],
                }
            )
        rows.append(row)

    technical_count = sum(1 for row in rows if row["technical_reference_present"])
    fresh_technical_count = sum(
        1 for row in rows if row["fresh_current_source_technical_validation"]
    )
    fresh_external_count = sum(
        1 for row in rows if row["status"] == "fresh_external_technical"
    )
    fresh_preflight_count = sum(
        1 for row in rows if row["status"] == "fresh_independent_preflight_technical"
    )
    missing_count = sum(1 for row in rows if row["status"] == "missing")
    complete = technical_count == len(rows)
    fresh_technical_complete = fresh_technical_count == len(rows)
    fresh_external_complete = all(
        row["fresh_current_source_external_execution"]
        for row in rows
        if row["verification_method"] == "external_solver_execution"
    )
    blockers = [
        *([] if complete else ["recommended_external_vv_matrix_incomplete"]),
        *(
            []
            if fresh_technical_complete
            else ["fresh_current_source_technical_matrix_incomplete"]
        ),
        *(
            []
            if fresh_external_complete
            else ["fresh_current_source_external_matrix_incomplete"]
        ),
        "independent_operator_identity_authentication_missing",
        "product_legal_license_approval_missing",
        "scientific_promotion_decision_missing",
        "formal_level2_promotion_receipt_missing",
        "bounded_planar_profile_level2_not_achieved",
        RUNTIME_LOCK_BLOCKER,
    ]
    baseline.update(
        {
            "receipt_bindings": core_bindings,
            "supplemental_receipt_bindings": supplemental_bindings,
            "operator_intake_binding": _operator_binding(intake),
            "requirements": rows,
            "summary": {
                "requirement_count": len(rows),
                "technical_reference_present_count": technical_count,
                "fresh_current_source_technical_count": fresh_technical_count,
                "current_product_replay_only_count": sum(
                    1 for row in rows if row["status"] == "current_product_replay_only"
                ),
                "fresh_external_technical_count": fresh_external_count,
                "fresh_independent_preflight_technical_count": (fresh_preflight_count),
                "promotion_eligible_count": 0,
                "missing_count": missing_count,
                "execution_package_available_count": sum(
                    1 for row in rows if row["execution_package_available"]
                ),
                "current_source_execution_prepared_count": sum(
                    1 for row in rows if row["current_source_execution_prepared"]
                ),
            },
            "status": "blocked",
            "contract_pass": True,
            "blockers": sorted(set(blockers)),
            "claims": {
                "recommended_matrix_technical_coverage_complete": complete,
                "fresh_current_source_technical_matrix_complete": (
                    fresh_technical_complete
                ),
                "fresh_current_source_external_matrix_complete": (
                    fresh_external_complete
                ),
                "independent_operator_attested": False,
                "legal_use_approved": False,
                "formal_promotion_receipt_attached": False,
                "bounded_planar_profile_level_2": False,
            },
            "claim_boundary": (
                "This matrix accepts only exact case inventories from a cryptographically "
                "verified, fresh operator bundle for the exact current source commit. "
                "The signer declares independence, but identity credentials, conflict "
                "review and the exact transitive external-runtime bytes are not bound. "
                "The signed execution remains replay/reference material and receives no "
                "fresh-current-source credit. Legal approval, scientific decisions, and "
                "formal promotion are not established; no Verification Level 2, design, "
                "commercial, or release authority is granted."
            ),
        }
    )
    baseline["artifact_hash"] = matrix_builder._artifact_hash(baseline)
    matrix_builder._validate_status(
        baseline,
        repo_root,
        verified_operator_context={
            "receipt_bindings": core_bindings,
            "supplemental_receipt_bindings": supplemental_bindings,
            "operator_intake_binding": _operator_binding(intake),
        },
    )
    return baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args(argv)
    attestation = _load_json(
        args.attestation, "operator_matrix_attestation_json_invalid"
    )
    payload = build_operator_attested_matrix(
        attestation,
        bundle_root=args.bundle_root,
        expected_source_commit_sha=args.expected_source_commit,
        repo_root=ROOT,
        openssl=args.openssl,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(args.out.name + ".tmp")
    temporary.write_text(
        json.dumps(
            payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.out)
    print(
        "operator-attested bounded-planar matrix: "
        f"fresh={payload['summary']['fresh_external_technical_count']}/"
        f"{payload['summary']['requirement_count']} | "
        f"level2={payload['claims']['bounded_planar_profile_level_2']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
