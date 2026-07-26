#!/usr/bin/env python3
"""Build or validate the fail-closed P2 engineering-review package."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "structural-analysis-engineering-review-package.v1"
ASSERTION_SCHEMA_VERSION = "structural-analysis-engineering-review-assertion.v1"
REGISTRY_SCHEMA_VERSION = "structural-analysis-engineering-reviewer-registry.v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/engineering_review_package_v1.schema.json"
)
REGISTRY_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/engineering_reviewer_registry_v1.schema.json"
)
REGISTRY_PATH = Path("artifacts/manifests/engineering_reviewers.json")
OUTPUT_PATH = Path("artifacts/review/engineering_review_package.candidate.json")
ROADMAP_STATUS_PATH = Path("artifacts/manifests/product_roadmap_status.json")
HIERARCHY_STATUS_PATH = Path(
    "implementation/phase1/release_evidence/productization/"
    "verification_hierarchy_status.json"
)

REQUIRED_DECISION_IDS = (
    "numerical_results_accepted",
    "result_and_evidence_authority_boundary_accepted",
    "level2_external_vv_accepted",
    "level3_published_benchmarks_accepted",
    "frame3d_external_comparison_accepted",
    "checkpoint_resume_job_service_accepted",
    "known_limitations_and_blockers_accepted",
)

REVIEW_SCOPE = (
    "P0-P2 repository and source provenance",
    "public result and evidence authority boundaries",
    "independent Level 2 code-to-code evidence",
    "published Level 3 material and snap-through evidence",
    "bounded 3D frame formulation and external comparison",
    "checkpoint and resume job-service integrity",
    "known limitations, counter-evidence, and release blockers",
)

PREREQUISITE_EVIDENCE_IDS = (
    "product_license_approved",
    "repository_hygiene_closed",
    "committed_current_head_ci_receipt",
    "opensees_level2_promoted",
    "second_solver_level2_promoted",
    "published_material_cyclic_level3",
    "published_snap_through_level3",
    "frame3d_external_comparison",
    "checkpoint_resume_job_service_promoted",
)

EVIDENCE_PATHS = (
    Path("docs/repository-architecture-and-product-roadmap.md"),
    Path("docs/product-roadmap-closure-matrix.md"),
    Path("docs/engineering-review-package.md"),
    ROADMAP_STATUS_PATH,
    Path("artifacts/manifests/capabilities.yaml"),
    Path("artifacts/manifests/core_quality.json"),
    Path("artifacts/manifests/repository_hygiene_inventory.json"),
    REGISTRY_PATH,
    HIERARCHY_STATUS_PATH,
    Path(
        "implementation/phase1/release_evidence/productization/"
        "external_code_to_code_technical_execution_receipt.json"
    ),
    Path(
        "implementation/phase1/release_evidence/productization/"
        "external_modal_buckling_technical_execution_receipt.json"
    ),
    Path("artifacts/vv/opensees_calculix_clean_runner/clean_runner_receipt.json"),
    Path("artifacts/benchmarks/fracture_energy_concrete_mesh_objectivity.json"),
    Path(
        "implementation/phase1/release_evidence/productization/"
        "verification_candidates/lee_frame/source_receipt.json"
    ),
    Path(
        "implementation/phase1/release_evidence/productization/"
        "verification_candidates/lee_frame/execution_receipt.json"
    ),
    Path(
        "implementation/phase1/release_evidence/productization/"
        "verification_candidates/lee_frame/scientific_decision.json"
    ),
    Path(
        "implementation/phase1/release_evidence/productization/"
        "verification_hierarchy_evidence.candidate.json"
    ),
    Path("src/structural_analysis/assembly/__init__.py"),
    Path("src/structural_analysis/assembly/corotational_frame3d_global.py"),
    Path("src/structural_analysis/assembly/corotational_frame3d_graph.py"),
    Path("src/structural_analysis/assembly/stateful_corotational_frame3d_sparse.py"),
    Path("src/structural_analysis/elements/corotational_frame3d.py"),
    Path(
        "src/structural_analysis/elements/"
        "stateful_corotational_fiber_frame3d.py"
    ),
    Path(
        "src/structural_analysis/elements/"
        "stateful_corotational_partial_composite_frame3d.py"
    ),
    Path("src/structural_analysis/materials/concrete_damage.py"),
    Path("src/structural_analysis/materials/composite_section.py"),
    Path("src/structural_analysis/materials/confined_concrete.py"),
    Path("src/structural_analysis/materials/bond_slip.py"),
    Path("src/structural_analysis/materials/partial_composite.py"),
    Path("src/structural_analysis/materials/stateful_biaxial_fiber_section.py"),
    Path(
        "src/structural_analysis/schemas/"
        "corotational_frame3d_global_checkpoint_v1.schema.json"
    ),
    Path(
        "src/structural_analysis/schemas/"
        "stateful_corotational_frame3d_sparse_checkpoint_v1.schema.json"
    ),
    Path("tests/test_corotational_frame3d_global.py"),
    Path("tests/test_stateful_corotational_frame3d_sparse.py"),
    Path("tests/test_stateful_corotational_frame3d_materials.py"),
    Path("tests/test_stateful_biaxial_fiber_section.py"),
    Path("tests/test_stateful_corotational_fiber_frame3d.py"),
    Path("tests/test_stateful_corotational_partial_composite_frame3d.py"),
    Path("tests/test_corotational_frame3d_scalable_graph.py"),
    Path("docs/p2-frame3d-candidates.md"),
    Path("docs/p2-material-candidates.md"),
    Path(
        "src/structural_analysis/solvers/nonlinear/"
        "scalable_sparse_factorization.py"
    ),
    Path(
        "src/structural_analysis/schemas/"
        "scalable_sparse_factorization_diagnostic_v1.schema.json"
    ),
    Path("tests/test_scalable_sparse_factorization.py"),
    Path("docs/sparse-factorization-conditioning-diagnostics.md"),
    Path("src/structural_analysis/execution/job_service.py"),
    Path("src/structural_analysis/execution/nonlinear_frame_worker.py"),
    Path("src/structural_analysis/schemas/job_completion_evidence_v1.schema.json"),
    Path("tests/test_durable_job_service.py"),
    Path("scripts/build_engineering_review_package.py"),
    SCHEMA_PATH,
    REGISTRY_SCHEMA_PATH,
    Path("tests/test_engineering_review_package.py"),
)

CLAIM_BOUNDARY = (
    "This package checksum-binds the named implementation, test, benchmark, and "
    "external-execution evidence for an engineering reviewer. An unsigned package, "
    "an untrusted key, a dirty or non-current source tree, an incomplete prerequisite, "
    "or a signed rejection cannot satisfy the P2 signed-engineering-review criterion. "
    "A verified review signature authenticates only the exact reviewer assertion and "
    "review-material hash. It does not by itself create solver truth, legal approval, "
    "Verification Level 2 or 3, deployment authority, design authority, or release "
    "readiness. Private signing keys must never enter the repository."
)


class EngineeringReviewPackageError(ValueError):
    """Raised when a review package, reviewer registry, or signature is invalid."""


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


def _hash_value(value: object) -> str:
    return _hash_bytes(_canonical_bytes(value))


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _package_hash(payload: Mapping[str, Any]) -> str:
    material = dict(payload)
    material.pop("package_hash", None)
    return _hash_value(material)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EngineeringReviewPackageError(f"cannot_read_json:{path}") from exc
    if not isinstance(value, dict):
        raise EngineeringReviewPackageError(f"json_object_required:{path}")
    return value


def _git_head(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or len(value) != 40:
        raise EngineeringReviewPackageError("git_head_unavailable")
    return value


def _worktree_clean(repo_root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise EngineeringReviewPackageError("git_status_unavailable")
    return not completed.stdout.strip()


def _inventory_rows(
    repo_root: Path,
    paths: Iterable[Path],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative in paths:
        key = relative.as_posix()
        if key in seen:
            raise EngineeringReviewPackageError(f"duplicate_evidence_path:{key}")
        seen.add(key)
        path = repo_root / relative
        if not path.is_file():
            raise EngineeringReviewPackageError(f"evidence_file_missing:{key}")
        rows.append(
            {
                "path": key,
                "sha256": _file_hash(path),
                "byte_length": path.stat().st_size,
            }
        )
    return sorted(rows, key=lambda row: str(row["path"]))


def validate_reviewer_registry(
    registry: Mapping[str, Any],
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    schema = _read_object(repo_root / REGISTRY_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(registry)
    rows = registry["reviewers"]
    ids = [str(row["reviewer_id"]) for row in rows]
    keys = [str(row["public_key_sha256"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise EngineeringReviewPackageError("reviewer_registry_duplicate_id")
    if len(keys) != len(set(keys)):
        raise EngineeringReviewPackageError("reviewer_registry_duplicate_key")
    return dict(registry)


def _authorized_reviewers(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["reviewer_id"]): row
        for row in registry["reviewers"]
        if row["authorization_status"] == "approved"
        and row["independent_from_implementation_team"] is True
        and "P2" in row["authorized_review_scopes"]
    }


def _source_state(
    *,
    repo_root: Path,
    roadmap_status: Mapping[str, Any],
) -> dict[str, Any]:
    remote_raw = roadmap_status.get("remote_repository_observation")
    remote = remote_raw if isinstance(remote_raw, dict) else {}
    remote_head = str(remote.get("default_branch_head") or "")
    if len(remote_head) != 40:
        remote_head = "0" * 40
    return {
        "source_commit_sha": _git_head(repo_root),
        "remote_default_branch_head": remote_head,
        "worktree_clean": _worktree_clean(repo_root),
        "authoritative_release_snapshot": bool(
            roadmap_status.get("authoritative_release_snapshot") is True
        ),
        "assessment_scope": str(roadmap_status.get("assessment_scope") or "unknown"),
    }


def _prerequisite_checks(
    roadmap_status: Mapping[str, Any],
    hierarchy_status: Mapping[str, Any],
) -> list[dict[str, Any]]:
    evidence_raw = roadmap_status.get("required_external_evidence")
    evidence = evidence_raw if isinstance(evidence_raw, dict) else {}
    checks = [
        {
            "id": evidence_id,
            "required": True,
            "observed": evidence.get(evidence_id),
            "pass": evidence.get(evidence_id) is True,
        }
        for evidence_id in PREREQUISITE_EVIDENCE_IDS
    ]
    highest = hierarchy_status.get("highest_verified_level")
    checks.append(
        {
            "id": "verification_hierarchy_level_3_promoted",
            "required": True,
            "observed": highest,
            "pass": isinstance(highest, int) and highest >= 3,
        }
    )
    return checks


def _unsigned_signature() -> dict[str, Any]:
    return {
        "state": "unsigned",
        "algorithm": None,
        "signer_id": None,
        "public_key_spki_base64": None,
        "public_key_sha256": None,
        "signature_base64": None,
        "signed_payload_hash": None,
    }


def _reviewer_assertion_approved(assertion: object) -> bool:
    if not isinstance(assertion, dict):
        return False
    decisions = assertion.get("decisions")
    return bool(
        assertion.get("disposition") == "approved_for_p2_closure"
        and assertion.get("independent_review_attested") is True
        and isinstance(decisions, dict)
        and set(decisions) == set(REQUIRED_DECISION_IDS)
        and all(decisions.get(key) is True for key in REQUIRED_DECISION_IDS)
    )


def _claims(payload: Mapping[str, Any]) -> dict[str, bool]:
    material = payload["review_material"]
    source = material["source"]
    exact_current_head = bool(
        source["worktree_clean"] is True
        and source["source_commit_sha"] == source["remote_default_branch_head"]
    )
    authoritative = source["authoritative_release_snapshot"] is True
    prerequisites = all(row["pass"] is True for row in material["prerequisite_checks"])
    trusted = payload["reviewer_authority"]["matched_reviewer_id"] is not None
    signed = payload["signature"]["state"] == "verified"
    decisions = _reviewer_assertion_approved(payload["reviewer_assertion"])
    review_ready = exact_current_head and authoritative and prerequisites
    approved = review_ready and trusted and signed and decisions
    return {
        "evidence_inventory_current": True,
        "exact_current_head": exact_current_head,
        "authoritative_release_snapshot": authoritative,
        "prerequisite_evidence_pass": prerequisites,
        "ready_for_external_review": review_ready,
        "trusted_reviewer": trusted,
        "signature_verified": signed,
        "required_decisions_approved": decisions,
        "signed_engineering_review": approved,
        "release_authority": False,
    }


def _blockers(payload: Mapping[str, Any]) -> list[str]:
    claims = _claims(payload)
    source = payload["review_material"]["source"]
    blockers: list[str] = []
    if source["worktree_clean"] is not True:
        blockers.append("candidate_worktree_not_clean")
    if source["source_commit_sha"] != source["remote_default_branch_head"]:
        blockers.append("candidate_source_commit_not_remote_default_head")
    if not claims["authoritative_release_snapshot"]:
        blockers.append("authoritative_release_snapshot_missing")
    blockers.extend(
        f"prerequisite_missing:{row['id']}"
        for row in payload["review_material"]["prerequisite_checks"]
        if row["pass"] is not True
    )
    if payload["reviewer_assertion"] is None:
        blockers.append("reviewer_assertion_not_attached")
    if not claims["trusted_reviewer"]:
        blockers.append("trusted_engineering_reviewer_not_attached")
    if not claims["signature_verified"]:
        blockers.append("engineering_review_signature_not_verified")
    if not claims["required_decisions_approved"]:
        blockers.append("required_engineering_decisions_not_approved")
    return blockers


def build_engineering_review_package(
    *,
    repo_root: Path = ROOT,
    evidence_paths: Iterable[Path] = EVIDENCE_PATHS,
    roadmap_status: Mapping[str, Any] | None = None,
    hierarchy_status: Mapping[str, Any] | None = None,
    trusted_registry: Mapping[str, Any] | None = None,
    source_state: Mapping[str, Any] | None = None,
    require_current_sources: bool = True,
) -> dict[str, Any]:
    roadmap = (
        dict(roadmap_status)
        if roadmap_status is not None
        else _read_object(repo_root / ROADMAP_STATUS_PATH)
    )
    hierarchy = (
        dict(hierarchy_status)
        if hierarchy_status is not None
        else _read_object(repo_root / HIERARCHY_STATUS_PATH)
    )
    registry = (
        dict(trusted_registry)
        if trusted_registry is not None
        else _read_object(repo_root / REGISTRY_PATH)
    )
    validate_reviewer_registry(registry, repo_root=repo_root)
    inventory = _inventory_rows(repo_root, evidence_paths)
    evidence_set_hash = _hash_value(inventory)
    selected_source = (
        dict(source_state)
        if source_state is not None
        else _source_state(repo_root=repo_root, roadmap_status=roadmap)
    )
    material = {
        "package_id": f"p2-engineering-review-{evidence_set_hash[7:23]}",
        "source": selected_source,
        "evidence_inventory": inventory,
        "evidence_set_hash": evidence_set_hash,
        "review_scope": list(REVIEW_SCOPE),
        "required_decision_ids": list(REQUIRED_DECISION_IDS),
        "prerequisite_checks": _prerequisite_checks(roadmap, hierarchy),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    registry_bytes = _canonical_bytes(registry)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "package_hash": "sha256:" + "0" * 64,
        "generated_at": str(roadmap.get("assessed_at") or "1970-01-01T00:00:00Z"),
        "status": "blocked",
        "contract_pass": True,
        "review_material": material,
        "review_material_hash": _hash_value(material),
        "reviewer_authority": {
            "registry_path": REGISTRY_PATH.as_posix(),
            "registry_sha256": _hash_bytes(registry_bytes),
            "authorized_reviewer_count": len(_authorized_reviewers(registry)),
            "matched_reviewer_id": None,
        },
        "reviewer_assertion": None,
        "signature": _unsigned_signature(),
        "claims": {},
        "blockers_remaining": [],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["claims"] = _claims(payload)
    payload["blockers_remaining"] = _blockers(payload)
    payload["status"] = (
        "approved" if payload["claims"]["signed_engineering_review"] else "blocked"
    )
    payload["package_hash"] = _package_hash(payload)
    return validate_engineering_review_package(
        payload,
        repo_root=repo_root,
        require_current_sources=require_current_sources,
        trusted_registry=registry,
    )


def reviewer_assertion_bytes(assertion: Mapping[str, Any]) -> bytes:
    """Return the exact canonical bytes that an external reviewer must sign."""

    return _canonical_bytes(assertion)


def build_reviewer_assertion(
    package: Mapping[str, Any],
    *,
    reviewer_id: str,
    reviewed_at: str,
    disposition: str,
    decisions: Mapping[str, bool],
    review_notes: str,
) -> dict[str, Any]:
    return {
        "schema_version": ASSERTION_SCHEMA_VERSION,
        "review_material_hash": package["review_material_hash"],
        "reviewer_id": reviewer_id.strip(),
        "reviewed_at": reviewed_at,
        "disposition": disposition,
        "decisions": {
            key: bool(decisions.get(key, False)) for key in REQUIRED_DECISION_IDS
        },
        "review_notes": review_notes,
        "independent_review_attested": True,
    }


def _load_ed25519_public_key(public_der: bytes):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("engineering_review_cryptography_missing") from exc
    key = serialization.load_der_public_key(public_der)
    if not isinstance(key, Ed25519PublicKey):
        raise EngineeringReviewPackageError("review_public_key_not_ed25519")
    return key


def attach_engineering_review(
    package: Mapping[str, Any],
    *,
    assertion: Mapping[str, Any],
    signature_bytes: bytes,
    public_key_pem: bytes,
    repo_root: Path = ROOT,
    trusted_registry: Mapping[str, Any] | None = None,
    require_current_sources: bool = True,
) -> dict[str, Any]:
    registry = (
        dict(trusted_registry)
        if trusted_registry is not None
        else _read_object(repo_root / REGISTRY_PATH)
    )
    validate_reviewer_registry(registry, repo_root=repo_root)
    validate_engineering_review_package(
        dict(package),
        repo_root=repo_root,
        require_current_sources=require_current_sources,
        trusted_registry=registry,
    )
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("engineering_review_cryptography_missing") from exc
    public_key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(public_key, Ed25519PublicKey):
        raise EngineeringReviewPackageError("review_public_key_not_ed25519")
    assertion_bytes = reviewer_assertion_bytes(assertion)
    try:
        public_key.verify(signature_bytes, assertion_bytes)
    except Exception as exc:
        raise EngineeringReviewPackageError("review_signature_invalid") from exc
    public_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_hash = _hash_bytes(public_der)
    reviewer_id = str(assertion.get("reviewer_id") or "")
    reviewer = _authorized_reviewers(registry).get(reviewer_id)
    if reviewer is None:
        raise EngineeringReviewPackageError("reviewer_not_authorized")
    if reviewer["public_key_sha256"] != public_hash:
        raise EngineeringReviewPackageError("reviewer_public_key_mismatch")
    if assertion.get("review_material_hash") != package["review_material_hash"]:
        raise EngineeringReviewPackageError("review_material_binding_mismatch")

    updated = deepcopy(package)
    updated["reviewer_authority"] = {
        "registry_path": REGISTRY_PATH.as_posix(),
        "registry_sha256": _hash_bytes(_canonical_bytes(registry)),
        "authorized_reviewer_count": len(_authorized_reviewers(registry)),
        "matched_reviewer_id": reviewer_id,
    }
    updated["reviewer_assertion"] = dict(assertion)
    updated["signature"] = {
        "state": "verified",
        "algorithm": "ed25519",
        "signer_id": reviewer_id,
        "public_key_spki_base64": base64.b64encode(public_der).decode("ascii"),
        "public_key_sha256": public_hash,
        "signature_base64": base64.b64encode(signature_bytes).decode("ascii"),
        "signed_payload_hash": _hash_bytes(assertion_bytes),
    }
    updated["claims"] = _claims(updated)
    updated["blockers_remaining"] = _blockers(updated)
    updated["status"] = (
        "approved" if updated["claims"]["signed_engineering_review"] else "blocked"
    )
    updated["package_hash"] = _package_hash(updated)
    return validate_engineering_review_package(
        updated,
        repo_root=repo_root,
        require_current_sources=require_current_sources,
        trusted_registry=registry,
    )


def validate_engineering_review_package(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    require_current_sources: bool,
    trusted_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    schema = _read_object(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    registry = (
        dict(trusted_registry)
        if trusted_registry is not None
        else _read_object(repo_root / REGISTRY_PATH)
    )
    validate_reviewer_registry(registry, repo_root=repo_root)
    if payload["package_hash"] != _package_hash(payload):
        raise EngineeringReviewPackageError("review_package_hash_mismatch")
    material = payload["review_material"]
    if payload["review_material_hash"] != _hash_value(material):
        raise EngineeringReviewPackageError("review_material_hash_mismatch")
    inventory = material["evidence_inventory"]
    if material["evidence_set_hash"] != _hash_value(inventory):
        raise EngineeringReviewPackageError("review_evidence_set_hash_mismatch")
    if payload["claim_boundary"] != CLAIM_BOUNDARY:
        raise EngineeringReviewPackageError("review_claim_boundary_mismatch")
    if material["claim_boundary"] != CLAIM_BOUNDARY:
        raise EngineeringReviewPackageError("review_material_claim_boundary_mismatch")
    if tuple(material["required_decision_ids"]) != REQUIRED_DECISION_IDS:
        raise EngineeringReviewPackageError("required_review_decisions_mismatch")
    if payload["reviewer_authority"]["registry_sha256"] != _hash_bytes(
        _canonical_bytes(registry)
    ):
        raise EngineeringReviewPackageError("reviewer_registry_hash_mismatch")
    authorized = _authorized_reviewers(registry)
    if payload["reviewer_authority"]["authorized_reviewer_count"] != len(authorized):
        raise EngineeringReviewPackageError("authorized_reviewer_count_mismatch")

    if require_current_sources:
        current_rows = _inventory_rows(
            repo_root,
            (Path(str(row["path"])) for row in inventory),
        )
        if inventory != current_rows:
            raise EngineeringReviewPackageError("review_evidence_inventory_stale")
        source = material["source"]
        if source["source_commit_sha"] != _git_head(repo_root):
            raise EngineeringReviewPackageError("review_source_commit_stale")
        if source["worktree_clean"] is not _worktree_clean(repo_root):
            raise EngineeringReviewPackageError("review_worktree_state_stale")

    signature = payload["signature"]
    assertion = payload["reviewer_assertion"]
    signed = signature["state"] == "verified"
    matched_id = payload["reviewer_authority"]["matched_reviewer_id"]
    if signed:
        if not isinstance(assertion, dict):
            raise EngineeringReviewPackageError("signed_review_assertion_missing")
        if signature["signer_id"] != assertion["reviewer_id"]:
            raise EngineeringReviewPackageError("review_signer_id_mismatch")
        if assertion["review_material_hash"] != payload["review_material_hash"]:
            raise EngineeringReviewPackageError("review_material_binding_mismatch")
        try:
            public_der = base64.b64decode(
                signature["public_key_spki_base64"], validate=True
            )
            signature_bytes = base64.b64decode(
                signature["signature_base64"], validate=True
            )
        except Exception as exc:
            raise EngineeringReviewPackageError(
                "review_signature_encoding_invalid"
            ) from exc
        if signature["public_key_sha256"] != _hash_bytes(public_der):
            raise EngineeringReviewPackageError("review_public_key_hash_mismatch")
        assertion_bytes = reviewer_assertion_bytes(assertion)
        if signature["signed_payload_hash"] != _hash_bytes(assertion_bytes):
            raise EngineeringReviewPackageError("review_signed_payload_hash_mismatch")
        try:
            _load_ed25519_public_key(public_der).verify(
                signature_bytes,
                assertion_bytes,
            )
        except Exception as exc:
            raise EngineeringReviewPackageError("review_signature_invalid") from exc
        reviewer = authorized.get(str(matched_id))
        if reviewer is None or matched_id != assertion["reviewer_id"]:
            raise EngineeringReviewPackageError("reviewer_not_authorized")
        if reviewer["public_key_sha256"] != signature["public_key_sha256"]:
            raise EngineeringReviewPackageError("reviewer_public_key_mismatch")
    elif assertion is not None or matched_id is not None:
        raise EngineeringReviewPackageError("unsigned_review_contains_authority")

    expected_claims = _claims(payload)
    if payload["claims"] != expected_claims:
        raise EngineeringReviewPackageError("review_claims_mismatch")
    expected_blockers = _blockers(payload)
    if payload["blockers_remaining"] != expected_blockers:
        raise EngineeringReviewPackageError("review_blockers_mismatch")
    expected_status = (
        "approved" if expected_claims["signed_engineering_review"] else "blocked"
    )
    if payload["status"] != expected_status:
        raise EngineeringReviewPackageError("review_status_mismatch")
    return payload


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--attach-assertion", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--canonicalize-assertion", type=Path)
    parser.add_argument("--canonical-out", type=Path)
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else ROOT / args.out

    if args.canonicalize_assertion is not None:
        if args.canonical_out is None:
            parser.error("--canonicalize-assertion requires --canonical-out")
        assertion = _read_object(args.canonicalize_assertion)
        args.canonical_out.write_bytes(reviewer_assertion_bytes(assertion))
        return 0
    if args.check:
        payload = _read_object(out)
        validate_engineering_review_package(
            payload,
            repo_root=ROOT,
            require_current_sources=True,
        )
        print("engineering_review_package_current")
        return 0

    attaching = any(
        path is not None
        for path in (args.attach_assertion, args.signature, args.public_key)
    )
    if attaching:
        if not all(
            path is not None
            for path in (args.attach_assertion, args.signature, args.public_key)
        ):
            parser.error(
                "--attach-assertion, --signature, and --public-key are required together"
            )
        payload = attach_engineering_review(
            _read_object(out),
            assertion=_read_object(args.attach_assertion),
            signature_bytes=args.signature.read_bytes(),
            public_key_pem=args.public_key.read_bytes(),
            repo_root=ROOT,
        )
    else:
        payload = build_engineering_review_package(repo_root=ROOT)
    if args.write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "engineering-review-package: "
            f"status={payload['status']} "
            f"signed={payload['claims']['signed_engineering_review']} "
            f"evidence={len(payload['review_material']['evidence_inventory'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
