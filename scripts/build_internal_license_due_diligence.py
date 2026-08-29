#!/usr/bin/env python3
"""Build a non-promoting internal license due-diligence manifest."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import (  # noqa: E402
    engine_version,
    git_head,
    input_checksums,
    now_utc_iso,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(
    "artifacts/manifests/internal_license_due_diligence.current.v1.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "internal_license_due_diligence_v1.schema.json"
)
REPOSITORY_LICENSE = Path("LICENSE")
DATASET_LICENSE_MANIFEST = Path(
    "implementation/phase1/release_evidence/productization/"
    "developer_preview_dataset_license_manifest.json"
)
OPENSEES_SOURCE_LICENSE = Path(
    "implementation/phase1/release_evidence/productization/"
    "phase3_opensees_medium_source_license_receipt.json"
)
IFC_SOURCE_LICENSE = Path(
    "implementation/phase1/release_evidence/productization/"
    "phase3_ifc_source_license_receipt.json"
)
EXTERNAL_CODE_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "external_code_to_code_technical_execution_receipt.json"
)
EXTERNAL_MODAL_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "external_modal_buckling_technical_execution_receipt.json"
)
BUILDER_PATH = Path("scripts/build_internal_license_due_diligence.py")
SCHEMA_VERSION = "internal-license-due-diligence.v1"
REPOSITORY_DEFAULT_LICENSE_REF = "LicenseRef-Repository-Default-No-License"
REPOSITORY_RIGHTS_HOLDER_APPROVAL = "signed_rights_holder_decision_required"
REUSE_POLICY = (
    "current-source aggregation of existing license identities and restrictive "
    "use boundaries; no legal or redistribution approval is inferred"
)
INPUT_PATHS = (
    REPOSITORY_LICENSE,
    DATASET_LICENSE_MANIFEST,
    OPENSEES_SOURCE_LICENSE,
    IFC_SOURCE_LICENSE,
    EXTERNAL_CODE_RECEIPT,
    EXTERNAL_MODAL_RECEIPT,
    BUILDER_PATH,
    SCHEMA_PATH,
)
REQUIRED_INVENTORY_IDS = (
    "repository_default_license",
    "developer_preview_repo_generated_seed_corpus",
    "opensees_runtime",
    "calculix_runtime",
    "opensees_scbf16b_benchmark_source",
    "ifc_public_source_candidates",
    "commercial_operator_reference_imports",
)
EXTERNAL_ACTIONS = (
    "obtain_product_or_legal_approval_before_commercial_distribution",
    "obtain_or_confirm_opensees_runtime_redistribution_terms_before_bundling",
    "review_calculix_gpl_compliance_before_bundling_or_customer_delivery",
    "review_or_remove_repository_attached_opensees_benchmark_sources_before_distribution",
    "complete_ifc_per_file_license_review_before_acquisition_or_bundling",
    "obtain_operator_permission_before_ingesting_commercial_reference_exports",
)


class InternalLicenseDueDiligenceError(ValueError):
    """Raised when the stored due-diligence manifest is stale or tampered."""


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_git_sha(value: Any) -> bool:
    text = _text(value).lower()
    return len(text) == 40 and all(character in "0123456789abcdef" for character in text)


def _artifact_hash(payload: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"artifact_hash", "generated_at"}
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _inventory_row(
    *,
    inventory_id: str,
    category: str,
    source_evidence_path: Path,
    source_evidence_sha256: str,
    material_presence: str,
    declared_license_posture: str,
    spdx_or_license_ref: str,
    use_scope: str,
    redistribution_boundary: str,
    redistribution_allowed: bool,
    source_use_declaration: str,
    review_status: str,
) -> dict[str, Any]:
    return {
        "inventory_id": inventory_id,
        "category": category,
        "source_evidence_path": source_evidence_path.as_posix(),
        "source_evidence_sha256": source_evidence_sha256,
        "material_presence": material_presence,
        "declared_license_posture": declared_license_posture,
        "spdx_or_license_ref": spdx_or_license_ref,
        "use_scope": use_scope,
        "redistribution_boundary": redistribution_boundary,
        "redistribution_allowed": bool(redistribution_allowed),
        "commercial_use_approved": False,
        "product_legal_approval": False,
        "source_use_declaration": source_use_declaration,
        "review_status": review_status,
    }


def build_internal_license_due_diligence(
    repo_root: Path = ROOT,
    *,
    generated_at: str | None = None,
    external_code_receipt: Path = EXTERNAL_CODE_RECEIPT,
    external_modal_receipt: Path = EXTERNAL_MODAL_RECEIPT,
) -> dict[str, Any]:
    input_paths = (
        REPOSITORY_LICENSE,
        DATASET_LICENSE_MANIFEST,
        OPENSEES_SOURCE_LICENSE,
        IFC_SOURCE_LICENSE,
        external_code_receipt,
        external_modal_receipt,
        BUILDER_PATH,
        SCHEMA_PATH,
    )
    checksums = input_checksums(input_paths, repo_root=repo_root)
    head = git_head(repo_root)
    repository_license_text = (
        (repo_root / REPOSITORY_LICENSE).read_text(encoding="utf-8")
        if (repo_root / REPOSITORY_LICENSE).exists()
        else ""
    )
    dataset = _load_json(repo_root, DATASET_LICENSE_MANIFEST)
    opensees_source = _load_json(repo_root, OPENSEES_SOURCE_LICENSE)
    ifc_source = _load_json(repo_root, IFC_SOURCE_LICENSE)
    external_code = _load_json(repo_root, external_code_receipt)
    external_modal = _load_json(repo_root, external_modal_receipt)
    code_runtimes = _as_dict(external_code.get("runtimes"))
    modal_runtimes = _as_dict(external_modal.get("runtimes"))
    opensees_runtime = _as_dict(code_runtimes.get("opensees"))
    calculix_runtime = _as_dict(code_runtimes.get("calculix"))
    opensees_runtime_license = _as_dict(opensees_runtime.get("license"))
    calculix_runtime_license = _as_dict(calculix_runtime.get("license"))
    dataset_sources = [
        row for row in _as_list(dataset.get("sources")) if isinstance(row, dict)
    ]
    dataset_by_id = {
        _text(row.get("source_id")): row
        for row in dataset_sources
        if _text(row.get("source_id"))
    }
    analytic_seed = _as_dict(dataset_by_id.get("analytic-small"))
    operator_imports = _as_dict(
        dataset_by_id.get("commercial-cross-solver-imports")
    )
    ifc_sources = [
        row for row in _as_list(ifc_source.get("sources")) if isinstance(row, dict)
    ]

    blockers: list[str] = []

    def require(condition: bool, blocker: str) -> None:
        if not condition:
            blockers.append(blocker)

    require(bool(head) and len(head) == 40, "source_commit_sha_invalid")
    require(
        "No permission is granted" in repository_license_text
        and "default no-license posture" in repository_license_text,
        "repository_default_no_license_boundary_missing",
    )
    require(
        dataset.get("contract_pass") is True,
        "developer_preview_dataset_license_manifest_not_ready",
    )
    require(
        analytic_seed.get("license") == REPOSITORY_DEFAULT_LICENSE_REF
        and analytic_seed.get("local_execution_allowed") is False
        and analytic_seed.get("redistribution_allowed") is False
        and analytic_seed.get("commercial_use_allowed") is False
        and analytic_seed.get("rights_holder_approval_status")
        == REPOSITORY_RIGHTS_HOLDER_APPROVAL
        and analytic_seed.get("developer_preview_bundle_policy")
        == "not_bundled_signed_rights_holder_decision_required",
        "repo_generated_seed_license_boundary_invalid",
    )
    require(
        operator_imports.get("redistribution_allowed") is False,
        "commercial_operator_import_boundary_invalid",
    )
    for receipt_id, receipt in (
        ("code_to_code", external_code),
        ("modal_buckling", external_modal),
    ):
        require(
            receipt.get("technical_contract_pass") is True,
            f"external_{receipt_id}_technical_receipt_not_ready",
        )
        require(
            _is_git_sha(receipt.get("source_commit_sha")),
            f"external_{receipt_id}_source_commit_invalid",
        )
        require(
            _as_dict(receipt.get("replay_provenance")).get(
                "current_product_replay_pass"
            )
            is True,
            f"external_{receipt_id}_product_replay_not_passed",
        )
    require(
        _as_dict(modal_runtimes.get("opensees")).get("license")
        == opensees_runtime_license,
        "opensees_runtime_license_receipt_drift",
    )
    require(
        _as_dict(modal_runtimes.get("calculix")).get("license")
        == calculix_runtime_license,
        "calculix_runtime_license_receipt_drift",
    )
    for runtime_id, runtime, license_row in (
        ("opensees", opensees_runtime, opensees_runtime_license),
        ("calculix", calculix_runtime, calculix_runtime_license),
    ):
        require(
            runtime.get("actual_external_execution") is True,
            f"{runtime_id}_runtime_execution_missing",
        )
        require(
            _text(license_row.get("declared_license_posture")) != "",
            f"{runtime_id}_declared_license_posture_missing",
        )
        require(
            _text(license_row.get("license_file_sha256")).startswith("sha256:"),
            f"{runtime_id}_license_file_hash_missing",
        )
        require(
            license_row.get("product_legal_approval") is False
            and license_row.get("commercial_redistribution_approved") is False,
            f"{runtime_id}_unsupported_license_approval_claim",
        )
    opensees_license_evidence = _as_dict(opensees_source.get("license_evidence"))
    require(
        _text(opensees_license_evidence.get("spdx")) == "GPL-3.0"
        and opensees_source.get("redistribution_allowed") is False,
        "opensees_benchmark_source_license_boundary_invalid",
    )
    require(
        bool(ifc_sources)
        and all(
            row.get("redistribution_allowed") is False
            and row.get("commercial_use_allowed") is False
            and _text(row.get("declared_license"))
            for row in ifc_sources
        ),
        "ifc_source_license_boundaries_invalid",
    )
    require(
        all(value.startswith("sha256:") for value in checksums.values()),
        "input_checksum_missing",
    )

    inventory = [
        _inventory_row(
            inventory_id="repository_default_license",
            category="repository_source",
            source_evidence_path=REPOSITORY_LICENSE,
            source_evidence_sha256=checksums[REPOSITORY_LICENSE.as_posix()],
            material_presence="repository_tracked",
            declared_license_posture=(
                "default_no_license_separate_written_agreement_required"
            ),
            spdx_or_license_ref="LicenseRef-Repository-Default-No-License",
            use_scope="controlled_worktree_development_and_internal_validation",
            redistribution_boundary=(
                "no_distribution_or_commercial_use_without_separate_written_agreement"
            ),
            redistribution_allowed=False,
            source_use_declaration=(
                "Repository code is used only for controlled development and internal "
                "validation; distribution requires a separate written agreement."
            ),
            review_status="boundary_identified_no_approval",
        ),
        _inventory_row(
            inventory_id="developer_preview_repo_generated_seed_corpus",
            category="repo_generated_dataset",
            source_evidence_path=DATASET_LICENSE_MANIFEST,
            source_evidence_sha256=checksums[
                DATASET_LICENSE_MANIFEST.as_posix()
            ],
            material_presence="repository_generated_seed_only",
            declared_license_posture=(
                "repository_default_no_license_signed_rights_holder_decision_required"
            ),
            spdx_or_license_ref=REPOSITORY_DEFAULT_LICENSE_REF,
            use_scope="internal_technical_provenance_only",
            redistribution_boundary=(
                "no seed-case bundling, redistribution, or commercial use without a "
                "signed rights-holder decision"
            ),
            redistribution_allowed=False,
            source_use_declaration=(
                "Repository-generated analytic, element-patch, and material-mesh seed "
                "cases are inventoried for internal technical provenance only."
            ),
            review_status=REPOSITORY_RIGHTS_HOLDER_APPROVAL,
        ),
        _inventory_row(
            inventory_id="opensees_runtime",
            category="external_runtime",
            source_evidence_path=external_code_receipt,
            source_evidence_sha256=checksums[external_code_receipt.as_posix()],
            material_presence="executed_from_pinned_assets_not_bundled",
            declared_license_posture=_text(
                opensees_runtime_license.get("declared_license_posture")
            ),
            spdx_or_license_ref="LicenseRef-OpenSees-Software-License",
            use_scope="internal_technical_vv_execution_only",
            redistribution_boundary=(
                "runtime wheels are not bundled; redistribution requires separate review"
            ),
            redistribution_allowed=False,
            source_use_declaration=(
                "Pinned OpenSeesPy assets were executed locally for technical V&V only "
                "and are not part of the product package."
            ),
            review_status="license_hash_recorded_product_legal_review_pending",
        ),
        _inventory_row(
            inventory_id="calculix_runtime",
            category="external_runtime",
            source_evidence_path=external_code_receipt,
            source_evidence_sha256=checksums[external_code_receipt.as_posix()],
            material_presence="executed_from_pinned_assets_not_bundled",
            declared_license_posture=_text(
                calculix_runtime_license.get("declared_license_posture")
            ),
            spdx_or_license_ref="GPL-2.0-only",
            use_scope="internal_technical_vv_execution_only",
            redistribution_boundary=(
                "runtime packages are not bundled; GPL compliance review is required"
            ),
            redistribution_allowed=False,
            source_use_declaration=(
                "Pinned CalculiX packages were executed locally for technical V&V only "
                "and are not part of the product package."
            ),
            review_status="license_hash_recorded_product_legal_review_pending",
        ),
        _inventory_row(
            inventory_id="opensees_scbf16b_benchmark_source",
            category="external_benchmark_source",
            source_evidence_path=OPENSEES_SOURCE_LICENSE,
            source_evidence_sha256=checksums[OPENSEES_SOURCE_LICENSE.as_posix()],
            material_presence="repository_candidate_present_restricted",
            declared_license_posture=_text(
                opensees_source.get("license_review_status")
            ),
            spdx_or_license_ref=(
                _text(opensees_license_evidence.get("spdx")) or "NOASSERTION"
            ),
            use_scope="parser_and_topology_candidate_evidence_only",
            redistribution_boundary=(
                "no customer delivery or product bundling before legal review"
            ),
            redistribution_allowed=False,
            source_use_declaration=(
                "SCBF16B source is retained only as restricted parser/topology evidence "
                "and receives no Phase 3 or redistribution credit."
            ),
            review_status="repository_presence_requires_legal_review_or_removal",
        ),
        _inventory_row(
            inventory_id="ifc_public_source_candidates",
            category="external_benchmark_source",
            source_evidence_path=IFC_SOURCE_LICENSE,
            source_evidence_sha256=checksums[IFC_SOURCE_LICENSE.as_posix()],
            material_presence="source_identity_only_not_bundled",
            declared_license_posture="mixed_declared_and_per_file_review_pending",
            spdx_or_license_ref="LicenseRef-IFC-Per-File-Review-Pending",
            use_scope="acquisition_contract_and_source_identity_only",
            redistribution_boundary=(
                "no acquisition or bundling before per-file review and checksums"
            ),
            redistribution_allowed=False,
            source_use_declaration=(
                "IFC candidates remain source identities and acquisition contracts only; "
                "no candidate files are bundled or granted quantity credit."
            ),
            review_status="product_legal_and_per_file_review_pending",
        ),
        _inventory_row(
            inventory_id="commercial_operator_reference_imports",
            category="operator_supplied_reference",
            source_evidence_path=DATASET_LICENSE_MANIFEST,
            source_evidence_sha256=checksums[
                DATASET_LICENSE_MANIFEST.as_posix()
            ],
            material_presence="operator_files_not_attached",
            declared_license_posture="operator_supplied_not_bundled",
            spdx_or_license_ref=(
                "LicenseRef-Operator-Supplied-No-Public-Redistribution"
            ),
            use_scope="local_operator_import_after_explicit_permission_only",
            redistribution_boundary=(
                "no ingestion, bundling, or reuse without operator permission"
            ),
            redistribution_allowed=False,
            source_use_declaration=(
                "Commercial reference exports may be ingested locally only after an "
                "operator supplies files, permission, and checksums."
            ),
            review_status="operator_permission_and_files_missing",
        ),
    ]
    inventory_ids = [row["inventory_id"] for row in inventory]
    require(
        inventory_ids == list(REQUIRED_INVENTORY_IDS),
        "license_inventory_incomplete",
    )
    spdx_complete = all(_text(row["spdx_or_license_ref"]) for row in inventory)
    redistribution_complete = all(
        _text(row["redistribution_boundary"]) for row in inventory
    )
    source_use_complete = all(
        _text(row["source_use_declaration"]) for row in inventory
    )
    require(spdx_complete, "spdx_or_license_ref_missing")
    require(redistribution_complete, "redistribution_boundary_missing")
    require(source_use_complete, "source_use_declaration_missing")
    blockers = sorted(dict.fromkeys(blockers))
    contract_pass = not blockers
    claims = {
        "internal_due_diligence_complete": contract_pass,
        "license_inventory_complete": contract_pass,
        "spdx_notices_complete": contract_pass and spdx_complete,
        "redistribution_boundaries_explicit": (
            contract_pass and redistribution_complete
        ),
        "source_use_declarations_complete": contract_pass and source_use_complete,
        "repo_generated_preview_seed_bundle_policy_ready": False,
        "third_party_material_clearance_complete": False,
        "external_runtime_redistribution_approved": False,
        "external_benchmark_redistribution_approved": False,
        "product_commercial_redistribution_approved": False,
        "product_legal_approval": False,
        "formal_verification_level_2": False,
        "release_authority": False,
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_hash": "",
        "generated_at": generated_at or now_utc_iso(),
        "source_commit_sha": head,
        "engine_version": engine_version(repo_root),
        "input_checksums": checksums,
        "reused_evidence": True,
        "reuse_policy": REUSE_POLICY,
        "status": "complete" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "components": {
            "license_inventory": {
                "contract_pass": contract_pass,
                "inventory_count": len(inventory),
                "required_inventory_count": len(REQUIRED_INVENTORY_IDS),
            },
            "spdx_notices": {
                "contract_pass": contract_pass and spdx_complete,
                "notice_count": len(inventory),
            },
            "redistribution_boundary": {
                "contract_pass": contract_pass and redistribution_complete,
                "explicit_boundary_count": len(inventory),
                "bounded_preview_redistribution_allowed_count": sum(
                    row["redistribution_allowed"] for row in inventory
                ),
            },
            "source_use_declarations": {
                "contract_pass": contract_pass and source_use_complete,
                "declaration_count": len(inventory),
            },
        },
        "inventory": inventory,
        "claims": claims,
        "blockers": blockers,
        "external_actions": list(EXTERNAL_ACTIONS),
        "claim_boundary": (
            "This manifest proves only that current-source license identities, "
            "SPDX/LicenseRef notices, restrictive redistribution boundaries, and "
            "source-use declarations were inventoried. Internal due diligence is not "
            "legal advice or product/legal approval. It does not approve commercial "
            "redistribution, third-party bundling, customer delivery, Verification "
            "Level 2, release authority, or any external promotion claim. External "
            "receipt source-currentness remains a numerical V&V and Product State "
            "responsibility rather than a license-inventory completion criterion."
        ),
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def validate_internal_license_due_diligence(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    external_code_receipt: Path = EXTERNAL_CODE_RECEIPT,
    external_modal_receipt: Path = EXTERNAL_MODAL_RECEIPT,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InternalLicenseDueDiligenceError(
            "internal_license_due_diligence_not_object"
        )
    generated_at = _text(payload.get("generated_at"))
    try:
        timestamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InternalLicenseDueDiligenceError(
            "internal_license_due_diligence_generated_at_invalid"
        ) from exc
    if timestamp.tzinfo is None:
        raise InternalLicenseDueDiligenceError(
            "internal_license_due_diligence_generated_at_timezone_missing"
        )
    expected = build_internal_license_due_diligence(
        repo_root,
        generated_at=generated_at,
        external_code_receipt=external_code_receipt,
        external_modal_receipt=external_modal_receipt,
    )
    if payload != expected:
        raise InternalLicenseDueDiligenceError(
            "internal_license_due_diligence_mismatch"
        )
    if payload.get("artifact_hash") != _artifact_hash(payload):
        raise InternalLicenseDueDiligenceError(
            "internal_license_due_diligence_artifact_hash_mismatch"
        )
    return payload


def check_internal_license_due_diligence(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    external_code_receipt: Path = EXTERNAL_CODE_RECEIPT,
    external_modal_receipt: Path = EXTERNAL_MODAL_RECEIPT,
) -> tuple[bool, str]:
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"internal_license_due_diligence_missing:{out_path.as_posix()}"
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        validate_internal_license_due_diligence(
            payload,
            repo_root=repo_root,
            external_code_receipt=external_code_receipt,
            external_modal_receipt=external_modal_receipt,
        )
    except Exception as exc:
        return False, f"internal_license_due_diligence_invalid:{exc}"
    return True, "internal_license_due_diligence_consistent"


def write_internal_license_due_diligence(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    external_code_receipt: Path = EXTERNAL_CODE_RECEIPT,
    external_modal_receipt: Path = EXTERNAL_MODAL_RECEIPT,
) -> dict[str, Any]:
    payload = build_internal_license_due_diligence(
        repo_root,
        external_code_receipt=external_code_receipt,
        external_modal_receipt=external_modal_receipt,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--external-code-receipt", type=Path, default=EXTERNAL_CODE_RECEIPT
    )
    parser.add_argument(
        "--external-modal-receipt", type=Path, default=EXTERNAL_MODAL_RECEIPT
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        ok, message = check_internal_license_due_diligence(
            repo_root=args.repo_root,
            out_path=args.out,
            external_code_receipt=args.external_code_receipt,
            external_modal_receipt=args.external_modal_receipt,
        )
        print(message)
        return 0 if ok else 1
    payload = write_internal_license_due_diligence(
        repo_root=args.repo_root,
        out_path=args.out,
        external_code_receipt=args.external_code_receipt,
        external_modal_receipt=args.external_modal_receipt,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "Internal license due diligence: "
            f"{payload['status']} | inventory={len(payload['inventory'])} | "
            f"legal_approval={payload['claims']['product_legal_approval']}"
        )
    if args.fail_blocked and payload["contract_pass"] is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
