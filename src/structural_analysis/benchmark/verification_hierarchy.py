"""Evidence contract for the five-level structural verification hierarchy.

The hierarchy separates intrinsic evidence at a level from promotion through
all lower levels.  It never treats a template, source URL, parser receipt, or
readiness packet as completed scientific verification.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import re
from typing import Any
from urllib.parse import urlparse

from .acceptance import inspect_benchmark_decision_receipt


VERIFICATION_EVIDENCE_SCHEMA_VERSION = "structural-verification-evidence.v1"
VERIFICATION_HIERARCHY_SCHEMA_VERSION = "structural-verification-hierarchy.v1"
REPOSITORY_DEFAULT_LICENSE_REF = "LicenseRef-Repository-Default-No-License"
REPOSITORY_RIGHTS_HOLDER_APPROVAL = "signed_rights_holder_decision_required"
_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


@dataclass(frozen=True)
class VerificationSlot:
    category: str
    label: str
    minimum_evidence_count: int = 1


@dataclass(frozen=True)
class VerificationLevel:
    level: int
    level_id: str
    label: str
    truth_basis: str
    slots: tuple[VerificationSlot, ...]
    claim_boundary: str


VERIFICATION_LEVELS = (
    VerificationLevel(
        level=1,
        level_id="analytic",
        label="Analytic",
        truth_basis="analytic_closed_form",
        slots=(
            VerificationSlot("single_bar", "Single bar"),
            VerificationSlot("cantilever_beam", "Cantilever beam"),
            VerificationSlot("simply_supported_beam", "Simply supported beam"),
            VerificationSlot("portal_frame", "Portal frame"),
            VerificationSlot("patch_tests", "Element and rigid-body patch tests"),
        ),
        claim_boundary=(
            "Each generated analytic case proves only its named closed-form family and "
            "declared modeling assumptions; case volume cannot substitute for another "
            "structural family or a higher verification level."
        ),
    ),
    VerificationLevel(
        level=2,
        level_id="code_to_code",
        label="Code-to-code",
        truth_basis="code_to_code",
        slots=(
            VerificationSlot("opensees_code_to_code", "OpenSees comparison"),
            VerificationSlot(
                "second_solver_code_to_code",
                "Second independent open-source or commercial solver",
            ),
        ),
        claim_boundary=(
            "Requires version-verified independent solver outputs; parser compatibility "
            "and solver input generation do not count."
        ),
    ),
    VerificationLevel(
        level=3,
        level_id="published_benchmark",
        label="Published benchmark",
        truth_basis="published_benchmark",
        slots=(
            VerificationSlot("nafems", "NAFEMS benchmark"),
            VerificationSlot("shell_patch", "Published shell patch"),
            VerificationSlot("nonlinear_snap_through", "Nonlinear snap-through"),
            VerificationSlot("material_cyclic", "Material cyclic benchmark"),
        ),
        claim_boundary=(
            "A publication URL or submission-readiness packet is not a passed published "
            "benchmark without checksum-bound outputs and a scientific decision."
        ),
    ),
    VerificationLevel(
        level=4,
        level_id="experimental",
        label="Experimental",
        truth_basis="experimental",
        slots=(
            VerificationSlot("load_displacement", "Load-displacement response"),
            VerificationSlot("failure_mode", "Failure mode"),
            VerificationSlot("strain_distribution", "Strain distribution"),
        ),
        claim_boundary=(
            "Experimental credit requires measurement data and publication/dataset "
            "provenance, not a numerical model labeled as experimental."
        ),
    ),
    VerificationLevel(
        level=5,
        level_id="customer_shadow",
        label="Customer shadow",
        truth_basis="customer_shadow",
        slots=(
            VerificationSlot(
                "completed_customer_shadow",
                "Reviewed completed-project shadow case",
                minimum_evidence_count=3,
            ),
        ),
        claim_boundary=(
            "Only privacy-safe derived metadata is stored. Raw customer data remains "
            "customer-held and three distinct reviewed completed projects are required."
        ),
    ),
)


def verification_hierarchy_policy() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for level in VERIFICATION_LEVELS:
        row = asdict(level)
        row["slots"] = [asdict(slot) for slot in level.slots]
        rows.append(row)
    return rows


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return ()
    return value


def _valid_sha256(value: Any) -> bool:
    return bool(_SHA256.fullmatch(_text(value).lower()))


def _valid_source_reference(value: Any, *, level: int) -> bool:
    parsed = urlparse(_text(value))
    allowed = {"http", "https", "doi"}
    if level == 1:
        allowed.add("generated")
    if level == 5:
        allowed.add("customer-shadow")
    return parsed.scheme in allowed and bool(parsed.netloc or parsed.path)


def _artifact_blockers(artifacts: Any) -> list[str]:
    values = _sequence(artifacts)
    if not values:
        return ["verification_evidence_artifacts_missing"]
    blockers: list[str] = []
    for index, value in enumerate(values):
        artifact = _mapping(value)
        if not _text(artifact.get("path")):
            blockers.append(f"verification_evidence_artifact_path_missing:{index}")
        if not _valid_sha256(artifact.get("sha256")):
            blockers.append(f"verification_evidence_artifact_sha256_invalid:{index}")
        if artifact.get("contract_pass") is not True:
            blockers.append(
                f"verification_evidence_artifact_contract_not_passed:{index}"
            )
    return blockers


def inspect_verification_evidence(value: Any) -> dict[str, Any]:
    """Inspect one hierarchy evidence row without promoting malformed input."""

    payload = _mapping(value)
    evidence_id = _text(payload.get("evidence_id"))
    category = _text(payload.get("category"))
    level_value = payload.get("level")
    level = (
        level_value
        if isinstance(level_value, int) and not isinstance(level_value, bool)
        else 0
    )
    policy_by_level = {row.level: row for row in VERIFICATION_LEVELS}
    policy = policy_by_level.get(level)
    blockers = [
        _text(item)
        for item in _sequence(payload.get("declared_blockers"))
        if _text(item)
    ]
    if payload.get("schema_version") != VERIFICATION_EVIDENCE_SCHEMA_VERSION:
        blockers.append("verification_evidence_schema_invalid")
    if not evidence_id:
        blockers.append("verification_evidence_id_missing")
    if policy is None:
        blockers.append("verification_evidence_level_invalid")
    else:
        valid_categories = {slot.category for slot in policy.slots}
        if category not in valid_categories:
            blockers.append("verification_evidence_category_invalid")
        if _text(payload.get("truth_basis")) != policy.truth_basis:
            blockers.append("verification_evidence_truth_basis_invalid")

    source = _mapping(payload.get("source"))
    if not _valid_source_reference(source.get("url_or_doi"), level=level):
        blockers.append("verification_evidence_source_reference_invalid")
    if not _valid_sha256(source.get("sha256")):
        blockers.append("verification_evidence_source_sha256_invalid")
    license_receipt = _mapping(source.get("license"))
    source_scheme = urlparse(_text(source.get("url_or_doi"))).scheme
    technical_provenance_only = source_scheme == "generated"
    if not _text(license_receipt.get("id")):
        blockers.append("verification_evidence_license_id_missing")
    if technical_provenance_only:
        if license_receipt.get("id") != REPOSITORY_DEFAULT_LICENSE_REF:
            blockers.append(
                "verification_evidence_repo_generated_license_boundary_invalid"
            )
        if (
            license_receipt.get("approval_status")
            != REPOSITORY_RIGHTS_HOLDER_APPROVAL
        ):
            blockers.append(
                "verification_evidence_repo_generated_rights_holder_decision_invalid"
            )
        if license_receipt.get("local_execution_allowed") is not False:
            blockers.append(
                "verification_evidence_repo_generated_local_use_boundary_invalid"
            )
        if license_receipt.get("commercial_use_allowed") is not False:
            blockers.append(
                "verification_evidence_repo_generated_commercial_boundary_invalid"
            )
        if license_receipt.get("redistribution_allowed") is not False:
            blockers.append(
                "verification_evidence_repo_generated_redistribution_boundary_invalid"
            )
    elif license_receipt.get("approval_status") != "approved":
        blockers.append("verification_evidence_license_not_approved")
    elif level == 5:
        if license_receipt.get("derived_metadata_use_allowed") is not True:
            blockers.append("verification_evidence_derived_metadata_use_not_approved")
    else:
        if license_receipt.get("local_execution_allowed") is not True:
            blockers.append("verification_evidence_local_execution_not_approved")
        if license_receipt.get("commercial_use_allowed") is not True:
            blockers.append("verification_evidence_commercial_use_not_approved")

    blockers.extend(_artifact_blockers(payload.get("artifacts")))
    decision_status = inspect_benchmark_decision_receipt(payload.get("decision"))
    blockers.extend(
        f"verification_evidence_decision:{blocker}"
        for blocker in decision_status["blockers"]
    )

    if level == 2:
        reference = _mapping(payload.get("reference"))
        if not _text(reference.get("name")):
            blockers.append("verification_evidence_reference_solver_name_missing")
        if not _text(reference.get("version")):
            blockers.append("verification_evidence_reference_solver_version_missing")
        if reference.get("version_verified") is not True:
            blockers.append("verification_evidence_reference_solver_version_unverified")
        if reference.get("independent_from_product") is not True:
            blockers.append("verification_evidence_reference_solver_not_independent")
        name = _text(reference.get("name")).casefold()
        if category == "opensees_code_to_code" and "opensees" not in name:
            blockers.append("verification_evidence_opensees_reference_required")
        if category == "second_solver_code_to_code" and "opensees" in name:
            blockers.append("verification_evidence_second_reference_solver_required")
    elif level == 3:
        publication = _mapping(payload.get("publication"))
        if not _text(publication.get("benchmark_name")):
            blockers.append("verification_evidence_published_benchmark_name_missing")
        if not _text(publication.get("publisher")):
            blockers.append("verification_evidence_publisher_missing")
    elif level == 4:
        experiment = _mapping(payload.get("experiment"))
        if not _text(experiment.get("dataset_id")):
            blockers.append("verification_evidence_experiment_dataset_id_missing")
        measurements = {
            _text(item)
            for item in _sequence(experiment.get("measurement_categories"))
            if _text(item)
        }
        if category not in measurements:
            blockers.append("verification_evidence_measurement_category_missing")
    elif level == 5:
        shadow = _mapping(payload.get("customer_shadow"))
        case_id_hash = _text(shadow.get("case_id_hash"))
        if not _valid_sha256(case_id_hash):
            blockers.append("verification_evidence_customer_case_id_hash_invalid")
        if shadow.get("project_status") != "completed":
            blockers.append("verification_evidence_customer_project_not_completed")
        if shadow.get("raw_data_retained_by_customer") is not True:
            blockers.append("verification_evidence_customer_raw_data_policy_invalid")
        if shadow.get("redistribution_allowed") is not False:
            blockers.append(
                "verification_evidence_customer_redistribution_policy_invalid"
            )
        if not _text(shadow.get("reviewer_id")):
            blockers.append("verification_evidence_customer_reviewer_id_missing")

    blockers = sorted(set(blockers))
    return {
        "schema_version": VERIFICATION_EVIDENCE_SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "level": level,
        "level_id": policy.level_id if policy else "",
        "category": category,
        "truth_basis": _text(payload.get("truth_basis")),
        "source_url_or_doi": _text(source.get("url_or_doi")),
        "source_sha256": _text(source.get("sha256")),
        "source_license_id": _text(license_receipt.get("id")),
        "source_license_approval_status": _text(
            license_receipt.get("approval_status")
        ),
        "technical_provenance_only": technical_provenance_only,
        "source_local_execution_allowed": (
            license_receipt.get("local_execution_allowed") is True
        ),
        "source_commercial_use_allowed": (
            license_receipt.get("commercial_use_allowed") is True
        ),
        "source_redistribution_allowed": (
            license_receipt.get("redistribution_allowed") is True
        ),
        "decision": decision_status,
        "ready_for_hierarchy_credit": not blockers,
        "blockers": blockers,
        "claim_boundary": (
            "This row validates declared evidence metadata and artifact hashes. It does "
            "not independently rerun a solver, authenticate a reviewer, or fetch source bytes."
        ),
    }


def build_verification_hierarchy_readiness(
    evidence: Any,
    *,
    input_blockers: Sequence[str] = (),
) -> dict[str, Any]:
    """Aggregate evidence while enforcing contiguous Level 1→5 promotion."""

    values = _sequence(evidence)
    evidence_rows = [inspect_verification_evidence(value) for value in values]
    normalized_input_blockers = sorted(
        {_text(item) for item in input_blockers if _text(item)}
    )
    blockers: list[str] = list(normalized_input_blockers)
    evidence_ids = [row["evidence_id"] for row in evidence_rows if row["evidence_id"]]
    duplicate_ids = sorted(
        evidence_id
        for evidence_id in set(evidence_ids)
        if evidence_ids.count(evidence_id) > 1
    )
    blockers.extend(
        f"verification_hierarchy_duplicate_evidence_id:{evidence_id}"
        for evidence_id in duplicate_ids
    )

    previous_promotion_pass = True
    highest_verified_level = 0
    level_rows: list[dict[str, Any]] = []
    for policy in VERIFICATION_LEVELS:
        selected = [row for row in evidence_rows if row["level"] == policy.level]
        ready = [row for row in selected if row["ready_for_hierarchy_credit"]]
        slot_rows: list[dict[str, Any]] = []
        level_blockers: list[str] = []
        for slot in policy.slots:
            matching = [row for row in ready if row["category"] == slot.category]
            slot_pass = len(matching) >= slot.minimum_evidence_count
            slot_blockers = (
                []
                if slot_pass
                else [
                    (
                        "verification_hierarchy_slot_count_below_minimum:"
                        f"level={policy.level}:category={slot.category}:"
                        f"current={len(matching)}:required={slot.minimum_evidence_count}"
                    )
                ]
            )
            level_blockers.extend(slot_blockers)
            slot_rows.append(
                {
                    "category": slot.category,
                    "label": slot.label,
                    "minimum_evidence_count": slot.minimum_evidence_count,
                    "ready_evidence_count": len(matching),
                    "ready_evidence_ids": [row["evidence_id"] for row in matching],
                    "contract_pass": slot_pass,
                    "blockers": slot_blockers,
                }
            )
        invalid_row_blockers = [
            f"verification_hierarchy_invalid_evidence:{row['evidence_id'] or '<missing>'}:{blocker}"
            for row in selected
            for blocker in row["blockers"]
        ]
        level_blockers.extend(invalid_row_blockers)
        intrinsic_pass = (
            all(row["contract_pass"] for row in slot_rows) and not invalid_row_blockers
        )
        promotion_pass = intrinsic_pass and previous_promotion_pass
        if intrinsic_pass and not previous_promotion_pass:
            level_blockers.append(
                f"verification_hierarchy_prerequisite_level_not_passed:{policy.level - 1}"
            )
        if promotion_pass:
            status = "ready"
            highest_verified_level = policy.level
        elif intrinsic_pass:
            status = "blocked_by_prerequisite"
        elif selected or ready:
            status = "partial"
        else:
            status = "missing"
        level_blockers = sorted(set(level_blockers))
        blockers.extend(level_blockers)
        level_rows.append(
            {
                "level": policy.level,
                "level_id": policy.level_id,
                "label": policy.label,
                "truth_basis": policy.truth_basis,
                "evidence_count": len(selected),
                "ready_evidence_count": len(ready),
                "intrinsic_contract_pass": intrinsic_pass,
                "promotion_contract_pass": promotion_pass,
                "status": status,
                "slot_rows": slot_rows,
                "blockers": level_blockers,
                "claim_boundary": policy.claim_boundary,
            }
        )
        previous_promotion_pass = promotion_pass

    blockers = sorted(set(blockers))
    contract_pass = highest_verified_level == len(VERIFICATION_LEVELS) and not blockers
    return {
        "schema_version": VERIFICATION_HIERARCHY_SCHEMA_VERSION,
        "status": "pass" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "highest_verified_level": highest_verified_level,
        "required_level_count": len(VERIFICATION_LEVELS),
        "evidence_count": len(evidence_rows),
        "ready_evidence_count": sum(
            1 for row in evidence_rows if row["ready_for_hierarchy_credit"]
        ),
        "product_commercial_use_authority": False,
        "product_redistribution_authority": False,
        "release_authority": False,
        "input_blockers": normalized_input_blockers,
        "policy": verification_hierarchy_policy(),
        "level_rows": level_rows,
        "evidence_rows": evidence_rows,
        "blockers": blockers,
        "summary_line": (
            "Structural verification hierarchy: "
            f"{'PASS' if contract_pass else 'BLOCKED'} | "
            f"highest_level={highest_verified_level}/5 | "
            f"evidence={sum(1 for row in evidence_rows if row['ready_for_hierarchy_credit'])}/"
            f"{len(evidence_rows)}"
        ),
        "claim_boundary": (
            "Hierarchy promotion is contiguous: higher-level evidence remains visible but "
            "cannot bypass an incomplete lower level. This readiness report does not create "
            "published, experimental, customer, license, or engineer-review evidence. "
            "Repository-generated rows provide technical provenance only and this report "
            "grants no product commercial-use, redistribution, or release authority."
        ),
    }
