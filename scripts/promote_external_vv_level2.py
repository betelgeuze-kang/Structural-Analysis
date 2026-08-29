#!/usr/bin/env python3
"""Build Level 2 hierarchy evidence from independently signed, reviewed V&V.

The gate is intentionally fail-closed.  Operator key possession, same-operator
container replay, or a project-side declaration alone cannot create hierarchy
credit.  Exact bundle hashes, operator-attestation validation, identity review,
solver-specific legal approvals, scientific decisions, and a project reviewer
signature are all mandatory.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, NoReturn

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
SCRIPTS_ROOT = ROOT / "scripts"
for search_root in (SRC_ROOT, SCRIPTS_ROOT):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

from structural_analysis.benchmark.acceptance import (  # noqa: E402
    inspect_benchmark_decision_receipt,
)
from structural_analysis.benchmark.verification_hierarchy import (  # noqa: E402
    VERIFICATION_EVIDENCE_SCHEMA_VERSION,
    inspect_verification_evidence,
)
from validate_external_vv_operator_attestation import (  # noqa: E402
    ExternalVVOperatorAttestationError,
    artifact_hash,
    canonical_bytes,
    file_sha256,
    sha256_bytes,
    validate_external_vv_operator_attestation,
)
import build_bounded_planar_external_vv_matrix as vv_matrix  # noqa: E402
import build_bounded_planar_external_vv_matrix_from_operator_bundle as operator_matrix  # noqa: E402
from strict_json import StrictJSONError, strict_json_load_path  # noqa: E402


SCHEMA_VERSION = "external-vv-level2-promotion.v1"
RECEIPT_SCHEMA_VERSION = "external-vv-level2-promotion-receipt.v1"
MANIFEST_SCHEMA_VERSION = "structural-verification-evidence-manifest.v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/external_vv_level2_promotion_v1.schema.json"
)
TRUST_REGISTRY_PATH = Path("canonical/external_vv_level2_trust_registry.v1.json")
PLACEHOLDER_MARKERS = ("OWNER_INPUT_REQUIRED", "PLACEHOLDER", "TBD")
CATEGORY_POLICY = {
    "opensees_code_to_code": {
        "solver": "OpenSees",
        "distribution": "openseespylinux",
        "required_metric_family": "opensees_external_comparison",
    },
    "second_solver_code_to_code": {
        "solver": "CalculiX",
        "distribution": "calculix-ccx",
        "required_metric_family": "calculix_external_comparison",
    },
}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ExternalVVLevel2PromotionError(ValueError):
    """Stable failure code for a non-promotable Level 2 submission."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ExternalVVLevel2PromotionError(code)


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = strict_json_load_path(path)
    except (OSError, StrictJSONError) as exc:
        raise ExternalVVLevel2PromotionError(code) from exc
    if not isinstance(payload, dict):
        _fail(code)
    return payload


def _bundle_file(bundle_root: Path, relative: str) -> Path:
    root = bundle_root.resolve()
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or raw.as_posix() != relative:
        _fail("level2_promotion_bundle_path_invalid")
    candidate = bundle_root / raw
    cursor = root
    for part in raw.parts:
        cursor /= part
        if cursor.is_symlink():
            _fail("level2_promotion_symlink_rejected")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ExternalVVLevel2PromotionError(
            "level2_promotion_bundle_path_invalid"
        ) from exc
    if not resolved.is_file():
        _fail("level2_promotion_bundle_file_required")
    return resolved


def _validate_schema(payload: Mapping[str, Any], repo_root: Path) -> None:
    schema = _load_json(repo_root / SCHEMA_PATH, "level2_promotion_schema_unreadable")
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(f"level2_promotion_schema_invalid:{path}")
    serialized = json.dumps(payload, ensure_ascii=False)
    if any(marker in serialized for marker in PLACEHOLDER_MARKERS):
        _fail("level2_promotion_placeholder_rejected")


def _check_file_descriptor(
    value: Mapping[str, Any], bundle_root: Path, *, json_artifact: bool
) -> tuple[Path, dict[str, Any] | None]:
    path = _bundle_file(bundle_root, str(value["path"]))
    if file_sha256(path) != value["file_sha256"]:
        _fail("level2_promotion_artifact_file_hash_mismatch")
    if not json_artifact:
        return path, None
    payload = _load_json(path, "level2_promotion_json_artifact_invalid")
    if payload.get("artifact_hash") != value["artifact_hash"]:
        _fail("level2_promotion_artifact_hash_descriptor_mismatch")
    if artifact_hash(payload) != payload.get("artifact_hash"):
        _fail("level2_promotion_artifact_self_hash_invalid")
    return path, payload


def promotion_signed_payload(promotion: Mapping[str, Any]) -> bytes:
    """Return canonical project-review signing bytes, excluding signature metadata."""

    body = deepcopy(dict(promotion))
    body.pop("signature", None)
    return canonical_bytes(body)


def _verify_project_signature(
    promotion: Mapping[str, Any], bundle_root: Path, openssl: str
) -> dict[str, Any]:
    signature = promotion["signature"]
    reviewer = promotion["project_reviewer"]
    assert isinstance(signature, Mapping) and isinstance(reviewer, Mapping)
    public_key = _bundle_file(bundle_root, str(signature["public_key_path"]))
    signature_file = _bundle_file(bundle_root, str(signature["signature_path"]))
    if (
        file_sha256(public_key) != signature["public_key_sha256"]
        or signature["public_key_sha256"] != reviewer["signer_public_key_sha256"]
        or file_sha256(signature_file) != signature["signature_sha256"]
    ):
        _fail("level2_promotion_signature_artifact_hash_mismatch")
    payload = promotion_signed_payload(promotion)
    if sha256_bytes(payload) != signature["signed_payload_sha256"]:
        _fail("level2_promotion_signed_payload_hash_mismatch")
    with tempfile.TemporaryDirectory(prefix="external-vv-level2-promotion-") as temp:
        payload_path = Path(temp) / "payload.json"
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
            raise ExternalVVLevel2PromotionError(
                "level2_promotion_signature_verifier_unavailable"
            ) from exc
    if completed.returncode != 0 or "Verified OK" not in completed.stdout:
        _fail("level2_promotion_signature_invalid")
    return {
        "algorithm": "rsa-sha256",
        "signed_payload_sha256": signature["signed_payload_sha256"],
        "public_key_sha256": signature["public_key_sha256"],
        "signature_sha256": signature["signature_sha256"],
        "cryptographic_signature_verified": True,
    }


def _runtime_asset(
    receipts: Sequence[Mapping[str, Any]], distribution: str
) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for receipt in receipts:
        assets = receipt.get("external_assets")
        if not isinstance(assets, Sequence) or isinstance(assets, (str, bytes)):
            _fail("level2_promotion_external_assets_invalid")
        selected = [
            row
            for row in assets
            if isinstance(row, Mapping) and row.get("distribution") == distribution
        ]
        if len(selected) != 1:
            _fail("level2_promotion_reference_runtime_asset_missing")
        matches.append(selected[0])
    if any(dict(row) != dict(matches[0]) for row in matches[1:]):
        _fail("level2_promotion_reference_runtime_asset_inconsistent")
    return matches[0]


def _validate_license_reviews(
    promotion: Mapping[str, Any], bundle_root: Path
) -> dict[str, Mapping[str, Any]]:
    rows = promotion["license_reviews"]
    assert isinstance(rows, list)
    by_solver = {str(row["solver"]): row for row in rows if isinstance(row, Mapping)}
    if set(by_solver) != {"OpenSees", "CalculiX"} or len(by_solver) != len(rows):
        _fail("level2_promotion_license_solver_set_invalid")
    for row in rows:
        assert isinstance(row, Mapping)
        _check_file_descriptor(row["evidence"], bundle_root, json_artifact=False)
    return by_solver


def _load_trust_registry(repo_root: Path) -> dict[str, Any]:
    registry = _load_json(
        repo_root / TRUST_REGISTRY_PATH,
        "level2_promotion_trust_registry_unreadable",
    )
    if set(registry) != {
        "schema_version",
        "registry_epoch",
        "approved_signers",
        "revocations",
        "claim_boundary",
    } or registry.get("schema_version") != "external-vv-level2-trust-registry.v1":
        _fail("level2_promotion_trust_registry_invalid")
    epoch = registry.get("registry_epoch")
    approved = registry.get("approved_signers")
    revocations = registry.get("revocations")
    if (
        type(epoch) is not int
        or epoch < 1
        or not isinstance(approved, list)
        or not isinstance(revocations, list)
        or not isinstance(registry.get("claim_boundary"), str)
    ):
        _fail("level2_promotion_trust_registry_invalid")
    return registry


def _require_repo_owned_signer(
    promotion: Mapping[str, Any], *, repo_root: Path
) -> None:
    """Reject bundle-supplied signer authority before reading bundle material."""

    registry = _load_trust_registry(repo_root)
    key_hash = promotion["signature"]["public_key_sha256"]
    epoch = registry["registry_epoch"]
    for row in registry["revocations"]:
        if (
            isinstance(row, Mapping)
            and row.get("public_key_sha256") == key_hash
            and type(row.get("revoked_at_epoch")) is int
            and row["revoked_at_epoch"] <= epoch
        ):
            _fail("level2_promotion_project_signer_revoked")
    matches = [
        row
        for row in registry["approved_signers"]
        if isinstance(row, Mapping) and row.get("public_key_sha256") == key_hash
    ]
    if len(matches) != 1:
        _fail("level2_promotion_project_signer_not_approved")


def _validate_repo_owned_trust(
    promotion: Mapping[str, Any],
    *,
    child_receipts: Sequence[Mapping[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    """Require a repository-owned exact signer and decision authorization.

    The registry is deliberately empty in source until a separately reviewed
    authority decision is committed.  A public key or review text carried by
    the submitted bundle can never populate this registry.
    """

    _require_repo_owned_signer(promotion, repo_root=repo_root)
    registry = _load_trust_registry(repo_root)
    epoch = registry["registry_epoch"]
    signature = promotion["signature"]
    reviewer = promotion["project_reviewer"]
    assert isinstance(signature, Mapping) and isinstance(reviewer, Mapping)
    key_hash = str(signature["public_key_sha256"])
    revoked: set[str] = set()
    for row in registry["revocations"]:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"public_key_sha256", "revoked_at_epoch"}
            or type(row.get("revoked_at_epoch")) is not int
            or row["revoked_at_epoch"] < 1
            or not isinstance(row.get("public_key_sha256"), str)
            or SHA256_RE.fullmatch(row["public_key_sha256"]) is None
        ):
            _fail("level2_promotion_trust_registry_invalid")
        if row["revoked_at_epoch"] <= epoch:
            revoked.add(str(row["public_key_sha256"]))
    if key_hash in revoked:
        _fail("level2_promotion_project_signer_revoked")
    required = {
        "public_key_sha256",
        "approval_epoch",
        "source_commit_sha",
        "reviewer",
        "identity_evidence_sha256",
        "license_reviews",
        "runtime_assets",
    }
    for row in registry["approved_signers"]:
        if (
            not isinstance(row, Mapping)
            or set(row) != required
            or not isinstance(row.get("public_key_sha256"), str)
            or SHA256_RE.fullmatch(row["public_key_sha256"]) is None
            or type(row.get("approval_epoch")) is not int
            or row["approval_epoch"] < 1
            or not isinstance(row.get("source_commit_sha"), str)
            or re.fullmatch(r"[0-9a-f]{40}", row["source_commit_sha"]) is None
            or not isinstance(row.get("reviewer"), Mapping)
            or not isinstance(row.get("identity_evidence_sha256"), str)
            or SHA256_RE.fullmatch(row["identity_evidence_sha256"]) is None
            or not isinstance(row.get("license_reviews"), list)
            or not isinstance(row.get("runtime_assets"), list)
        ):
            _fail("level2_promotion_trust_registry_invalid")
    signer_hashes = [row["public_key_sha256"] for row in registry["approved_signers"]]
    if len(signer_hashes) != len(set(signer_hashes)):
        _fail("level2_promotion_trust_registry_invalid")
    matches = [
        row for row in registry["approved_signers"] if row["public_key_sha256"] == key_hash
    ]
    if len(matches) != 1:
        _fail("level2_promotion_project_signer_not_approved")
    trusted = matches[0]
    if (
        type(trusted.get("approval_epoch")) is not int
        or not 1 <= trusted["approval_epoch"] <= epoch
        or trusted.get("source_commit_sha") != promotion["source_commit_sha"]
        or trusted.get("reviewer") != dict(reviewer)
    ):
        _fail("level2_promotion_trusted_decision_binding_invalid")
    identity = promotion["identity_review"]
    assert isinstance(identity, Mapping)
    if (
        trusted.get("identity_evidence_sha256")
        != identity["credential_evidence"]["file_sha256"]
    ):
        _fail("level2_promotion_trusted_identity_decision_invalid")
    submitted_licenses = {
        row["solver"]: {
            "license_id": row["license_id"],
            "local_execution_allowed": row["local_execution_allowed"],
            "commercial_use_allowed": row["commercial_use_allowed"],
            "redistribution_allowed": row["redistribution_allowed"],
            "evidence_sha256": row["evidence"]["file_sha256"],
        }
        for row in promotion["license_reviews"]
    }
    trusted_licenses = trusted.get("license_reviews")
    license_fields = {
        "solver",
        "license_id",
        "local_execution_allowed",
        "commercial_use_allowed",
        "redistribution_allowed",
        "evidence_sha256",
    }
    if not isinstance(trusted_licenses, list) or any(
        not isinstance(row, Mapping)
        or set(row) != license_fields
        or not isinstance(row.get("solver"), str)
        or not isinstance(row.get("evidence_sha256"), str)
        or SHA256_RE.fullmatch(row["evidence_sha256"]) is None
        for row in trusted_licenses
    ):
        _fail("level2_promotion_trust_registry_invalid")
    if len({row["solver"] for row in trusted_licenses}) != len(trusted_licenses):
        _fail("level2_promotion_trust_registry_invalid")
    if not isinstance(trusted_licenses, list) or {
        str(row.get("solver")): {
            key: row.get(key)
            for key in (
                "license_id",
                "local_execution_allowed",
                "commercial_use_allowed",
                "redistribution_allowed",
                "evidence_sha256",
            )
        }
        for row in trusted_licenses
        if isinstance(row, Mapping)
    } != submitted_licenses:
        _fail("level2_promotion_trusted_license_decision_invalid")
    observed_runtime_sets = []
    for receipt in child_receipts:
        assets = receipt.get("external_assets")
        if not isinstance(assets, list) or any(
            not isinstance(row, Mapping)
            or not isinstance(row.get("distribution"), str)
            or not isinstance(row.get("version"), str)
            or not isinstance(row.get("sha256"), str)
            or SHA256_RE.fullmatch(row["sha256"]) is None
            or not isinstance(row.get("authority_url"), str)
            for row in assets
        ):
            _fail("level2_promotion_trusted_runtime_binding_invalid")
        if len({row["distribution"] for row in assets}) != len(assets):
            _fail("level2_promotion_trusted_runtime_binding_invalid")
        observed_runtime_sets.append(
            {
                row["distribution"]: {
                    "version": row["version"],
                    "sha256": row["sha256"],
                    "authority_url": row["authority_url"],
                }
                for row in assets
            }
        )
    if not observed_runtime_sets or any(
        row != observed_runtime_sets[0] for row in observed_runtime_sets[1:]
    ):
        _fail("level2_promotion_trusted_runtime_binding_invalid")
    observed_runtime = observed_runtime_sets[0]
    trusted_runtime = trusted.get("runtime_assets")
    runtime_fields = {"distribution", "version", "sha256", "authority_url"}
    if not isinstance(trusted_runtime, list) or any(
        not isinstance(row, Mapping)
        or set(row) != runtime_fields
        or not isinstance(row.get("distribution"), str)
        or not isinstance(row.get("version"), str)
        or not isinstance(row.get("sha256"), str)
        or SHA256_RE.fullmatch(row["sha256"]) is None
        or not isinstance(row.get("authority_url"), str)
        for row in trusted_runtime
    ):
        _fail("level2_promotion_trust_registry_invalid")
    if len({row["distribution"] for row in trusted_runtime}) != len(trusted_runtime):
        _fail("level2_promotion_trust_registry_invalid")
    if not isinstance(trusted_runtime, list) or {
        str(row.get("distribution")): {
            "version": row.get("version"),
            "sha256": row.get("sha256"),
            "authority_url": row.get("authority_url"),
        }
        for row in trusted_runtime
        if isinstance(row, Mapping)
    } != observed_runtime:
        _fail("level2_promotion_trusted_runtime_binding_invalid")
    return {
        "registry_epoch": epoch,
        "public_key_sha256": key_hash,
        "source_commit_sha": promotion["source_commit_sha"],
    }


def _validate_identity_review(promotion: Mapping[str, Any], bundle_root: Path) -> None:
    identity = promotion["identity_review"]
    assert isinstance(identity, Mapping)
    _check_file_descriptor(
        identity["credential_evidence"], bundle_root, json_artifact=False
    )


def _validate_verification_matrix(
    promotion: Mapping[str, Any],
    *,
    bundle_root: Path,
    repo_root: Path,
    intake: Mapping[str, Any],
    attestation: Mapping[str, Any],
    openssl: str,
) -> dict[str, Any]:
    descriptor = promotion["verification_matrix"]
    assert isinstance(descriptor, Mapping)
    path, matrix = _check_file_descriptor(descriptor, bundle_root, json_artifact=True)
    assert matrix is not None
    try:
        expected_matrix = operator_matrix.build_operator_attested_matrix(
            attestation,
            bundle_root=bundle_root,
            expected_source_commit_sha=str(promotion["source_commit_sha"]),
            repo_root=repo_root,
            openssl=openssl,
        )
    except Exception as exc:
        raise ExternalVVLevel2PromotionError(
            "level2_promotion_verification_matrix_invalid"
        ) from exc
    if matrix != expected_matrix:
        _fail("level2_promotion_verification_matrix_replay_mismatch")
    source_commit = str(promotion["source_commit_sha"])
    summary = matrix.get("summary")
    claims = matrix.get("claims")
    rows = matrix.get("requirements")
    core_bindings = matrix.get("receipt_bindings")
    supplemental_bindings = matrix.get("supplemental_receipt_bindings")
    requirement_count = len(vv_matrix.REQUIREMENTS)
    if (
        matrix.get("source_commit_sha") != source_commit
        or matrix.get("contract_pass") is not True
        or not isinstance(summary, Mapping)
        or summary.get("requirement_count") != requirement_count
        or summary.get("technical_reference_present_count") != requirement_count
        or summary.get("fresh_current_source_technical_count") != requirement_count
        or summary.get("fresh_external_technical_count") != requirement_count - 1
        or summary.get("fresh_independent_preflight_technical_count") != 1
        or summary.get("current_product_replay_only_count") != 0
        or summary.get("missing_count") != 0
        or not isinstance(claims, Mapping)
        or claims.get("recommended_matrix_technical_coverage_complete") is not True
        or claims.get("fresh_current_source_technical_matrix_complete") is not True
        or claims.get("fresh_current_source_external_matrix_complete") is not True
        or not isinstance(rows, list)
        or not isinstance(core_bindings, list)
        or not core_bindings
        or not isinstance(supplemental_bindings, list)
    ):
        _fail("level2_promotion_verification_matrix_incomplete")
    bindings = [*core_bindings, *supplemental_bindings]
    if any(
        not isinstance(binding, Mapping)
        or binding.get("technical_contract_pass") is not True
        or binding.get("current_product_replay_pass") is not True
        or binding.get("fresh_current_source_external_execution") is not True
        for binding in bindings
    ):
        _fail("level2_promotion_verification_matrix_receipt_not_fresh")
    intake_binding = intake.get("bundle_binding")
    if not isinstance(intake_binding, Mapping):
        _fail("level2_promotion_operator_intake_not_passed")
    signed_artifact_hashes = {
        str(intake_binding.get("code_to_code_artifact_hash") or ""),
        str(intake_binding.get("modal_buckling_artifact_hash") or ""),
    }
    for key in (
        "bounded_planar_linear",
        "bounded_planar_modal_buckling",
        "bounded_planar_negative",
        "bounded_planar_scaling",
        "bounded_planar_nonlinear_material_recovery",
    ):
        dedicated_binding = intake_binding.get(key)
        if isinstance(dedicated_binding, Mapping):
            signed_artifact_hashes.add(
                str(dedicated_binding.get("technical_receipt_artifact_hash") or "")
            )
    additional = intake_binding.get("additional_receipts", [])
    if not isinstance(additional, list):
        _fail("level2_promotion_operator_intake_not_passed")
    signed_artifact_hashes.update(
        str(row.get("artifact_hash") or "")
        for row in additional
        if isinstance(row, Mapping)
    )
    for binding in bindings:
        assert isinstance(binding, Mapping)
        if binding["artifact_hash"] not in signed_artifact_hashes:
            _fail("level2_promotion_matrix_receipt_not_operator_signed")
        receipt_path = _bundle_file(bundle_root, str(binding["path"]))
        if file_sha256(receipt_path) != binding["file_sha256"]:
            _fail("level2_promotion_matrix_receipt_file_hash_mismatch")
        receipt = _load_json(receipt_path, "level2_promotion_matrix_receipt_invalid")
        if (
            artifact_hash(receipt) != binding["artifact_hash"]
            or receipt.get("source_commit_sha") != source_commit
            or receipt.get("technical_contract_pass") is not True
        ):
            _fail("level2_promotion_matrix_receipt_contract_invalid")
        receipt_cases = receipt.get("cases", receipt.get("comparisons"))
        if not isinstance(receipt_cases, list):
            _fail("level2_promotion_matrix_receipt_case_inventory_invalid")
        actual_case_ids = sorted(
            str(case.get("case_id") or "")
            for case in receipt_cases
            if isinstance(case, Mapping)
            and (
                case.get("technical_comparison_pass") is True
                or case.get("contract_pass") is True
                or case.get("technical_rejection_pass") is True
                or case.get("technical_contract_pass") is True
            )
            and str(case.get("case_id") or "")
        )
        if actual_case_ids != sorted(str(case_id) for case_id in binding["case_ids"]):
            _fail("level2_promotion_matrix_receipt_case_inventory_invalid")
    expected_case_ids = {
        str(requirement["requirement_id"]): [
            str(case_id) for case_id in requirement.get("case_ids", ())
        ]
        for requirement in vv_matrix.REQUIREMENTS
    }
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("level2_promotion_verification_matrix_row_invalid")
        requirement_id = str(row.get("requirement_id") or "")
        required_case_ids = row.get("required_external_case_ids")
        evidence = row.get("evidence")
        verification_method = row.get("verification_method")
        fresh_method_valid = row.get(
            "fresh_current_source_technical_validation"
        ) is True and (
            (
                verification_method == "external_solver_execution"
                and row.get("fresh_current_source_external_execution") is True
                and row.get("status")
                in {"fresh_external_technical", "promotion_eligible"}
            )
            or (
                verification_method == "independent_preflight"
                and row.get("fresh_current_source_external_execution") is False
                and row.get("status")
                in {
                    "fresh_independent_preflight_technical",
                    "promotion_eligible",
                }
            )
        )
        if (
            required_case_ids != expected_case_ids.get(requirement_id)
            or row.get("technical_reference_present") is not True
            or row.get("current_product_replay_pass") is not True
            or not fresh_method_valid
            or not isinstance(evidence, list)
            or not evidence
        ):
            _fail("level2_promotion_verification_matrix_row_incomplete")
        submitted_case_ids = {
            str(case_id)
            for evidence_row in evidence
            if isinstance(evidence_row, Mapping)
            for case_id in evidence_row.get("case_ids", [])
        }
        if submitted_case_ids != set(required_case_ids):
            _fail("level2_promotion_verification_matrix_case_binding_invalid")
    return {
        "path": path.relative_to(bundle_root.resolve()).as_posix(),
        "file_sha256": descriptor["file_sha256"],
        "artifact_hash": matrix["artifact_hash"],
        "requirement_count": requirement_count,
        "technical_reference_present_count": requirement_count,
        "fresh_current_source_technical_count": requirement_count,
        "fresh_external_technical_count": requirement_count - 1,
        "fresh_independent_preflight_technical_count": 1,
        "missing_count": 0,
        "source_commit_sha": source_commit,
    }


def _build_evidence_rows(
    promotion: Mapping[str, Any],
    *,
    bundle_root: Path,
    attestation: Mapping[str, Any],
    child_receipts: Sequence[Mapping[str, Any]],
    license_by_solver: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    reviews = promotion["scientific_reviews"]
    assert isinstance(reviews, list)
    by_category = {
        str(row["category"]): row for row in reviews if isinstance(row, Mapping)
    }
    if set(by_category) != set(CATEGORY_POLICY) or len(by_category) != len(reviews):
        _fail("level2_promotion_scientific_category_set_invalid")
    attestation_bundle = attestation["bundle"]
    assert isinstance(attestation_bundle, Mapping)
    expected_artifacts = {
        json.dumps(attestation_bundle["code_to_code"], sort_keys=True),
        json.dumps(attestation_bundle["modal_buckling"], sort_keys=True),
    }
    evidence_rows: list[dict[str, Any]] = []
    for category, policy in CATEGORY_POLICY.items():
        row = by_category[category]
        reference = row["reference"]
        source = row["source"]
        artifacts = row["artifacts"]
        decision = row["decision"]
        assert isinstance(reference, Mapping)
        assert isinstance(source, Mapping)
        assert isinstance(artifacts, list)
        assert isinstance(decision, Mapping)
        solver = str(policy["solver"])
        name = str(reference["name"])
        if category == "opensees_code_to_code" and "opensees" not in name.casefold():
            _fail("level2_promotion_opensees_reference_required")
        if category == "second_solver_code_to_code" and "opensees" in name.casefold():
            _fail("level2_promotion_second_solver_reference_required")
        runtime = _runtime_asset(child_receipts, str(policy["distribution"]))
        if (
            reference["version"] != runtime.get("version")
            or source["sha256"] != runtime.get("sha256")
            or source["url_or_doi"] != runtime.get("authority_url")
        ):
            _fail("level2_promotion_reference_runtime_binding_invalid")
        submitted_artifacts = {
            json.dumps(descriptor, sort_keys=True) for descriptor in artifacts
        }
        if submitted_artifacts != expected_artifacts:
            _fail("level2_promotion_scientific_artifact_set_invalid")
        checked_artifacts: list[dict[str, Any]] = []
        for descriptor in artifacts:
            assert isinstance(descriptor, Mapping)
            path, payload = _check_file_descriptor(
                descriptor, bundle_root, json_artifact=True
            )
            assert payload is not None
            if payload.get("technical_contract_pass") is not True:
                _fail("level2_promotion_technical_receipt_not_passed")
            checked_artifacts.append(
                {
                    "path": path.relative_to(bundle_root.resolve()).as_posix(),
                    "sha256": descriptor["file_sha256"],
                    "contract_pass": True,
                }
            )
        decision_status = inspect_benchmark_decision_receipt(
            decision,
            required_metric_families=[str(policy["required_metric_family"])],
            require_benchmark_credit=True,
            as_of=promotion["reviewed_at"],
        )
        if (
            not decision_status["contract_pass"]
            or decision_status["decision"] != "PASS"
        ):
            _fail("level2_promotion_scientific_decision_invalid")
        license_row = license_by_solver[solver]
        evidence = {
            "schema_version": VERIFICATION_EVIDENCE_SCHEMA_VERSION,
            "evidence_id": f"{promotion['promotion_id']}-{category}",
            "level": 2,
            "category": category,
            "truth_basis": "code_to_code",
            "declared_blockers": [],
            "source": {
                "url_or_doi": source["url_or_doi"],
                "sha256": source["sha256"],
                "license": {
                    "id": license_row["license_id"],
                    "approval_status": "approved",
                    "local_execution_allowed": True,
                    "commercial_use_allowed": True,
                },
            },
            "artifacts": checked_artifacts,
            "decision": dict(decision),
            "reference": dict(reference),
        }
        inspection = inspect_verification_evidence(evidence)
        if inspection["ready_for_hierarchy_credit"] is not True:
            _fail("level2_promotion_generated_evidence_invalid")
        evidence_rows.append(evidence)
    return evidence_rows


def promote_external_vv_level2(
    promotion: Mapping[str, Any],
    *,
    bundle_root: Path,
    expected_source_commit_sha: str,
    repo_root: Path = ROOT,
    openssl: str = "openssl",
) -> dict[str, Any]:
    """Validate the complete authority chain and return receipt plus manifest."""

    if not isinstance(promotion, Mapping):
        _fail("level2_promotion_object_required")
    _validate_schema(promotion, repo_root)
    if promotion["source_commit_sha"] != expected_source_commit_sha:
        _fail("level2_promotion_source_commit_mismatch")
    operator_descriptor = promotion["operator_attestation"]
    assert isinstance(operator_descriptor, Mapping)
    attestation_path, _ = _check_file_descriptor(
        operator_descriptor, bundle_root, json_artifact=False
    )
    attestation = _load_json(
        attestation_path, "level2_promotion_operator_attestation_json_invalid"
    )
    if artifact_hash(attestation) != operator_descriptor["artifact_hash"]:
        _fail("level2_promotion_operator_attestation_hash_mismatch")
    try:
        intake = validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=repo_root,
            openssl=openssl,
        )
    except ExternalVVOperatorAttestationError as exc:
        raise ExternalVVLevel2PromotionError(
            f"level2_promotion_operator_attestation_invalid:{exc.code}"
        ) from exc
    if (
        intake.get("intake_contract_pass") is not True
        or intake.get("source_commit_sha") != promotion["source_commit_sha"]
    ):
        _fail("level2_promotion_operator_intake_not_passed")
    matrix_binding = _validate_verification_matrix(
        promotion,
        bundle_root=bundle_root,
        repo_root=repo_root,
        intake=intake,
        attestation=attestation,
        openssl=openssl,
    )
    _validate_identity_review(promotion, bundle_root)
    license_by_solver = _validate_license_reviews(promotion, bundle_root)
    attestation_bundle = attestation["bundle"]
    assert isinstance(attestation_bundle, Mapping)
    child_receipts: list[Mapping[str, Any]] = []
    for key in ("code_to_code", "modal_buckling"):
        descriptor = attestation_bundle[key]
        assert isinstance(descriptor, Mapping)
        _, receipt = _check_file_descriptor(descriptor, bundle_root, json_artifact=True)
        assert receipt is not None
        child_receipts.append(receipt)
    evidence = _build_evidence_rows(
        promotion,
        bundle_root=bundle_root,
        attestation=attestation,
        child_receipts=child_receipts,
        license_by_solver=license_by_solver,
    )
    signature = _verify_project_signature(promotion, bundle_root, openssl)
    trust = _validate_repo_owned_trust(
        promotion,
        child_receipts=child_receipts,
        repo_root=repo_root,
    )
    promotion_hash = sha256_bytes(canonical_bytes(promotion))
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": promotion["reviewed_at"],
        "evidence": evidence,
        "verification_matrix": matrix_binding,
        "claim_boundary": (
            "This manifest grants only the two named Verification Level 2 hierarchy "
            "slots for the exact signed source commit and external evidence bundle. It "
            "does not grant Level 3+, design authority, commercial equivalence, release "
            "readiness, runtime redistribution permission, or general solver validity."
        ),
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "promotion_id": promotion["promotion_id"],
        "promotion_sha256": promotion_hash,
        "source_commit_sha": promotion["source_commit_sha"],
        "operator_attestation_sha256": operator_descriptor["file_sha256"],
        "verification_matrix": matrix_binding,
        "operator_intake_contract_pass": True,
        "operator_identity_authenticated": True,
        "conflict_review_passed": True,
        "legal_use_approved": True,
        "scientific_review_completed": True,
        "verification_matrix_complete": True,
        "project_signature": signature,
        "repository_trust_registry": trust,
        "verification_hierarchy_level_2_evidence_eligible": True,
        "evidence_ids": [row["evidence_id"] for row in evidence],
        "claims": {
            "verification_hierarchy_level_2_slots": True,
            "verification_hierarchy_level_3_or_higher": False,
            "commercial_equivalence": False,
            "design_authority": False,
            "release_readiness": False,
            "external_runtime_redistribution_approval": False,
        },
        "contract_pass": True,
        "claim_boundary": manifest["claim_boundary"],
    }
    return {"receipt": receipt, "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promotion", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--emit-signing-payload", type=Path)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args()
    promotion = _load_json(args.promotion, "level2_promotion_json_invalid")
    if args.emit_signing_payload is not None:
        if args.bundle_root is not None or args.manifest_out or args.receipt_out:
            parser.error(
                "--emit-signing-payload cannot be combined with validation outputs"
            )
        args.emit_signing_payload.parent.mkdir(parents=True, exist_ok=True)
        payload = promotion_signed_payload(promotion)
        args.emit_signing_payload.write_bytes(payload)
        print(sha256_bytes(payload))
        return 0
    if args.bundle_root is None:
        parser.error("--bundle-root is required for validation")
    try:
        result = promote_external_vv_level2(
            promotion,
            bundle_root=args.bundle_root,
            expected_source_commit_sha=args.expected_source_commit,
            openssl=args.openssl,
        )
    except ExternalVVLevel2PromotionError as exc:
        print(exc.code)
        return 1
    outputs = (
        (args.manifest_out, result["manifest"]),
        (args.receipt_out, result["receipt"]),
    )
    if all(path is None for path, _ in outputs):
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for path, payload in outputs:
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
