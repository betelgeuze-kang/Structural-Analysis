#!/usr/bin/env python3
"""Build current and historical product-state manifests without claim promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_bounded_planar_external_vv_matrix import (  # noqa: E402
    check_status as check_bounded_planar_external_vv_matrix_status,
)
from build_internal_license_due_diligence import (  # noqa: E402
    InternalLicenseDueDiligenceError,
    validate_internal_license_due_diligence,
)


ROOT = Path(__file__).resolve().parents[1]
CURRENT_OUT = Path("artifacts/manifests/product_state.current.v1.json")
HISTORY_OUT = Path("artifacts/manifests/product_state.history.v1.json")
LEGACY_CATALOG = Path("artifacts/manifests/product_state.legacy-sources.v1.json")
REGISTRY = Path("artifacts/manifests/capabilities.yaml")
CANONICAL_VERIFICATION_RECEIPT = Path(
    "artifacts/manifests/canonical_verification_environment.current.v1.json"
)
BOUNDED_PLANAR_EXTERNAL_VV_MATRIX = Path(
    "artifacts/manifests/bounded_planar_external_vv_matrix.current.v1.json"
)
BOUNDED_PLANAR_EXTERNAL_VV_CLAIM_KEYS = (
    "recommended_matrix_technical_coverage_complete",
    "fresh_current_source_technical_matrix_complete",
    "fresh_current_source_external_matrix_complete",
    "independent_operator_attested",
    "legal_use_approved",
    "formal_promotion_receipt_attached",
    "bounded_planar_profile_level_2",
)
INTERNAL_LICENSE_DUE_DILIGENCE = Path(
    "artifacts/manifests/internal_license_due_diligence.current.v1.json"
)
INTERNAL_LICENSE_CLAIM_KEYS = (
    "internal_due_diligence_complete",
    "license_inventory_complete",
    "spdx_notices_complete",
    "redistribution_boundaries_explicit",
    "source_use_declarations_complete",
    "repo_generated_preview_seed_bundle_policy_ready",
    "third_party_material_clearance_complete",
    "external_runtime_redistribution_approved",
    "external_benchmark_redistribution_approved",
    "product_commercial_redistribution_approved",
    "product_legal_approval",
    "formal_verification_level_2",
    "release_authority",
)
HYGIENE = Path("artifacts/manifests/repository_hygiene_inventory.json")
READINESS = Path(
    "implementation/phase1/release_evidence/productization/"
    "product_readiness_snapshot.json"
)
WORKSTATION = Path("implementation/phase1/workstation_delivery_readiness.json")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
GITHUB_WORKFLOW_RUN_TERMINAL_CONCLUSIONS = frozenset(
    {
        "action_required",
        "cancelled",
        "failure",
        "neutral",
        "skipped",
        "stale",
        "success",
        "timed_out",
    }
)


def _load(repo_root: Path, path: Path) -> dict[str, Any]:
    payload = json.loads((repo_root / path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _load_path(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _sha256(repo_root: Path, path: Path) -> str:
    return "sha256:" + hashlib.sha256((repo_root / path).read_bytes()).hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _status_row_matches_exact_path(row: str, path: Path) -> bool:
    """Match one porcelain-v1 path without accepting rename destinations."""

    return len(row) >= 4 and row[2] == " " and row[3:] == path.as_posix()


def _verify_legacy_git_objects(
    repo_root: Path,
    legacy_catalog: dict[str, Any],
    legacy_records: list[object],
) -> list[str]:
    blockers: list[str] = []
    catalog_commit = str(legacy_catalog.get("snapshot_commit_sha") or "")
    if not GIT_SHA_PATTERN.fullmatch(catalog_commit):
        return ["legacy_source_catalog_snapshot_commit_invalid"]
    for row in legacy_records:
        if not isinstance(row, dict):
            continue
        record_id = str(row.get("id") or "unknown")
        repository_path = str(row.get("repository_path") or "")
        snapshot = row.get("snapshot")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        commit_sha = str(snapshot.get("git_commit_sha") or "")
        blob_oid = str(snapshot.get("git_blob_oid") or "")
        expected_sha256 = str(snapshot.get("content_sha256") or "")
        if commit_sha != catalog_commit:
            blockers.append(f"legacy_record_snapshot_commit_drift:{record_id}")
            continue
        try:
            observed_blob_oid = _git(
                repo_root,
                "rev-parse",
                f"{commit_sha}:{repository_path}",
            )
            content = subprocess.check_output(
                ["git", "cat-file", "blob", observed_blob_oid],
                cwd=repo_root,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            blockers.append(f"legacy_record_git_object_unavailable:{record_id}")
            continue
        if observed_blob_oid != blob_oid:
            blockers.append(f"legacy_record_git_blob_oid_drift:{record_id}")
        observed_sha256 = "sha256:" + hashlib.sha256(content).hexdigest()
        if observed_sha256 != expected_sha256:
            blockers.append(f"legacy_record_content_sha256_drift:{record_id}")
    return blockers


def _nightly_quality_evidence(
    payload: dict[str, Any] | None,
    *,
    expected_sha: str,
) -> tuple[dict[str, Any], list[str]]:
    if payload is None:
        return (
            {
                "status": "unavailable",
                "authority": "github_actions_workflow_run_event",
            },
            ["nightly_full_quality_evidence_unavailable"],
        )

    run = payload.get("workflow_run")
    if not isinstance(run, dict):
        return (
            {
                "status": "invalid",
                "authority": "github_actions_workflow_run_event",
                "reason": "workflow_run_missing",
            },
            ["nightly_full_quality_evidence_invalid:workflow_run_missing"],
        )

    workflow_name = str(run.get("name") or "")
    conclusion = str(run.get("conclusion") or "")
    head_branch = str(run.get("head_branch") or "")
    head_sha = str(run.get("head_sha") or "")
    trigger_event = str(run.get("event") or "")
    html_url = str(run.get("html_url") or "")
    run_id = run.get("id")
    run_number = run.get("run_number")
    run_attempt = run.get("run_attempt")
    invalid_fields: list[str] = []
    if workflow_name != "Nightly Full Quality":
        invalid_fields.append("workflow_name")
    if conclusion not in GITHUB_WORKFLOW_RUN_TERMINAL_CONCLUSIONS:
        invalid_fields.append("conclusion")
    if head_branch != "main":
        invalid_fields.append("head_branch")
    if head_sha != expected_sha:
        invalid_fields.append("head_sha")
    if trigger_event not in {"schedule", "workflow_dispatch"}:
        invalid_fields.append("trigger_event")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        invalid_fields.append("run_id")
    if (
        not isinstance(run_number, int)
        or isinstance(run_number, bool)
        or run_number <= 0
    ):
        invalid_fields.append("run_number")
    if (
        not isinstance(run_attempt, int)
        or isinstance(run_attempt, bool)
        or run_attempt <= 0
    ):
        invalid_fields.append("run_attempt")
    if not html_url.startswith("https://github.com/"):
        invalid_fields.append("html_url")

    status = "available" if not invalid_fields else "invalid"
    evidence = {
        "status": status,
        "authority": "github_actions_workflow_run_event",
        "workflow_name": workflow_name,
        "run_id": run_id,
        "run_number": run_number,
        "run_attempt": run_attempt,
        "trigger_event": trigger_event,
        "conclusion": conclusion,
        "head_branch": head_branch,
        "head_sha": head_sha,
        "html_url": html_url,
    }
    if invalid_fields:
        evidence["reason"] = "invalid fields: " + ", ".join(sorted(invalid_fields))
    blockers = [
        f"nightly_full_quality_evidence_invalid:{field}"
        for field in sorted(invalid_fields)
    ]
    if not invalid_fields and conclusion != "success":
        blockers.append(f"nightly_full_quality_not_success:{conclusion}")
    return evidence, blockers


def build_product_state(
    repo_root: Path = ROOT,
    *,
    observed_main_sha: str | None = None,
    observed_main_source: str | None = None,
    verify_legacy_git_objects: bool = False,
    nightly_workflow_run_event: dict[str, Any] | None = None,
    external_vv_code_receipt: Path | None = None,
    external_vv_modal_receipt: Path | None = None,
    external_vv_clean_runner_summary: Path | None = None,
    external_vv_same_operator_supplemental_receipt: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    head = _git(repo_root, "rev-parse", "HEAD")
    status_rows = [
        row
        for row in _git(
            repo_root, "status", "--short", "--untracked-files=normal"
        ).splitlines()
        if row.strip()
        and not _status_row_matches_exact_path(row, CURRENT_OUT)
        and not _status_row_matches_exact_path(row, HISTORY_OUT)
        and not _status_row_matches_exact_path(row, CANONICAL_VERIFICATION_RECEIPT)
    ]
    registry = _load(repo_root, REGISTRY)
    external_vv_matrix: dict[str, Any] = {}
    external_vv_matrix_sha256 = "unavailable"
    external_vv_matrix_load_pass = False
    external_vv_matrix_status_check_pass = False
    external_vv_matrix_validation_reason = (
        "bounded_planar_external_vv_matrix_validation_not_run"
    )
    try:
        external_vv_matrix_path = (
            BOUNDED_PLANAR_EXTERNAL_VV_MATRIX
            if BOUNDED_PLANAR_EXTERNAL_VV_MATRIX.is_absolute()
            else repo_root / BOUNDED_PLANAR_EXTERNAL_VV_MATRIX
        )
        external_vv_matrix_bytes = external_vv_matrix_path.read_bytes()
        external_vv_matrix_sha256 = (
            "sha256:" + hashlib.sha256(external_vv_matrix_bytes).hexdigest()
        )
        loaded_external_vv_matrix = json.loads(external_vv_matrix_bytes)
        if not isinstance(loaded_external_vv_matrix, dict):
            raise ValueError("expected external V&V matrix JSON object")
        external_vv_matrix = loaded_external_vv_matrix
        external_vv_matrix_load_pass = True
    except FileNotFoundError as exc:
        external_vv_matrix_sha256 = "missing"
        external_vv_matrix_validation_reason = (
            "bounded_planar_external_vv_matrix_load_failed:"
            f"{exc.__class__.__name__}"
        )
    except (OSError, UnicodeError, ValueError) as exc:
        external_vv_matrix_validation_reason = (
            "bounded_planar_external_vv_matrix_load_failed:"
            f"{exc.__class__.__name__}"
        )
    if external_vv_matrix_load_pass:
        try:
            matrix_check_kwargs: dict[str, Any] = {
                "repo_root": repo_root,
                "out_path": BOUNDED_PLANAR_EXTERNAL_VV_MATRIX,
            }
            if external_vv_code_receipt is not None:
                matrix_check_kwargs["code_receipt_path"] = (
                    external_vv_code_receipt
                )
            if external_vv_modal_receipt is not None:
                matrix_check_kwargs["modal_receipt_path"] = (
                    external_vv_modal_receipt
                )
            if external_vv_clean_runner_summary is not None:
                matrix_check_kwargs["clean_runner_summary_path"] = (
                    external_vv_clean_runner_summary
                )
            if external_vv_same_operator_supplemental_receipt is not None:
                matrix_check_kwargs[
                    "same_operator_supplemental_receipt_path"
                ] = external_vv_same_operator_supplemental_receipt
            (
                external_vv_matrix_status_check_pass,
                external_vv_matrix_validation_reason,
            ) = check_bounded_planar_external_vv_matrix_status(
                **matrix_check_kwargs
            )
        except (
            OSError,
            UnicodeError,
            ValueError,
            subprocess.SubprocessError,
        ) as exc:
            external_vv_matrix_validation_reason = (
                str(exc) or exc.__class__.__name__
            )
    external_vv_matrix_schema_valid = external_vv_matrix.get(
        "schema_version"
    ) == "bounded-planar-external-vv-matrix-status.v1"
    external_vv_matrix_source_commit_matches_current = (
        external_vv_matrix.get("source_commit_sha") == head
    )
    external_vv_matrix_stored_contract_pass = (
        external_vv_matrix.get("contract_pass") is True
    )
    external_vv_matrix_validation_pass = bool(
        external_vv_matrix_status_check_pass
        and external_vv_matrix_schema_valid
        and external_vv_matrix_source_commit_matches_current
        and external_vv_matrix_stored_contract_pass
    )
    if (
        external_vv_matrix_status_check_pass
        and not external_vv_matrix_validation_pass
    ):
        if not external_vv_matrix_schema_valid:
            external_vv_matrix_validation_reason = (
                "bounded_planar_external_vv_matrix_schema_invalid"
            )
        elif not external_vv_matrix_source_commit_matches_current:
            external_vv_matrix_validation_reason = (
                "bounded_planar_external_vv_matrix_source_commit_mismatch"
            )
        else:
            external_vv_matrix_validation_reason = (
                "bounded_planar_external_vv_matrix_contract_not_passed"
            )
    raw_matrix_claims = external_vv_matrix.get("claims")
    raw_matrix_claims = (
        raw_matrix_claims if isinstance(raw_matrix_claims, dict) else {}
    )
    matrix_claims = {
        key: (
            external_vv_matrix_validation_pass
            and raw_matrix_claims.get(key) is True
        )
        for key in BOUNDED_PLANAR_EXTERNAL_VV_CLAIM_KEYS
    }
    hygiene = _load(repo_root, HYGIENE)
    workstation = _load(repo_root, WORKSTATION)
    legacy_catalog = _load(repo_root, LEGACY_CATALOG)
    internal_license_due_diligence: dict[str, Any] = {}
    internal_license_validation_reason = "PASS"
    internal_license_blockers: list[str] = []
    try:
        internal_license_due_diligence = _load(
            repo_root,
            INTERNAL_LICENSE_DUE_DILIGENCE,
        )
        license_validation_kwargs: dict[str, Any] = {
            "repo_root": repo_root,
        }
        if external_vv_code_receipt is not None:
            license_validation_kwargs["external_code_receipt"] = (
                external_vv_code_receipt
            )
        if external_vv_modal_receipt is not None:
            license_validation_kwargs["external_modal_receipt"] = (
                external_vv_modal_receipt
            )
        validate_internal_license_due_diligence(
            internal_license_due_diligence,
            **license_validation_kwargs,
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
        InternalLicenseDueDiligenceError,
    ) as exc:
        internal_license_validation_reason = str(exc) or exc.__class__.__name__
        internal_license_blockers.append(
            "internal_license_due_diligence_missing_or_invalid"
        )
    raw_internal_license_claims = internal_license_due_diligence.get("claims")
    raw_internal_license_claims = (
        raw_internal_license_claims
        if isinstance(raw_internal_license_claims, dict)
        else {}
    )
    internal_license_claims = {
        key: (
            raw_internal_license_claims.get(key) is True
            if not internal_license_blockers
            else False
        )
        for key in INTERNAL_LICENSE_CLAIM_KEYS
    }
    rows = registry.get("capabilities", [])
    if not isinstance(rows, list):
        rows = []
    inventory_main = str(hygiene.get("observed_default_branch_head", ""))
    official_main = observed_main_sha or inventory_main
    main_observation_source = (
        observed_main_source
        if observed_main_sha is not None
        else "repository_hygiene_inventory"
    )

    blockers: list[str] = []
    blockers.extend(internal_license_blockers)
    if not GIT_SHA_PATTERN.fullmatch(official_main):
        blockers.append("observed_main_sha_invalid")
    elif official_main != head:
        blockers.append("source_commit_does_not_match_observed_github_main")
    if status_rows:
        blockers.append("candidate_worktree_not_committed")
    if registry.get("schema_version") != "structural-analysis-capabilities.v2":
        blockers.append("capability_registry_not_v2")
    if not external_vv_matrix_schema_valid:
        blockers.append("bounded_planar_external_vv_matrix_schema_invalid")
    if not external_vv_matrix_source_commit_matches_current:
        blockers.append("bounded_planar_external_vv_matrix_source_commit_mismatch")
    if not external_vv_matrix_stored_contract_pass:
        blockers.append("bounded_planar_external_vv_matrix_contract_not_passed")
    if not external_vv_matrix_validation_pass:
        blockers.append("bounded_planar_external_vv_matrix_stale_or_invalid")
    quality_evidence, quality_blockers = _nightly_quality_evidence(
        nightly_workflow_run_event,
        expected_sha=official_main,
    )
    blockers.extend(quality_blockers)

    legacy_records = legacy_catalog.get("records", [])
    if legacy_catalog.get("schema_version") != "product-state.legacy-sources.v1":
        blockers.append("legacy_source_catalog_schema_invalid")
    if not isinstance(legacy_records, list):
        blockers.append("legacy_source_catalog_records_invalid")
        legacy_records = []
    legacy_record_ids: list[str] = []
    for row in legacy_records:
        if not isinstance(row, dict):
            blockers.append("legacy_source_catalog_record_invalid")
            continue
        record_id = str(row.get("id") or "")
        legacy_record_ids.append(record_id)
        snapshot = row.get("snapshot")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        if not record_id:
            blockers.append("legacy_source_catalog_record_id_missing")
        if row.get("classification") != "historical_only":
            blockers.append(f"legacy_record_not_historical:{record_id}")
        if row.get("current_product_authority") is not False:
            blockers.append(f"legacy_record_authority_not_false:{record_id}")
        if snapshot.get("storage_kind") != "git_object":
            blockers.append(f"legacy_record_storage_not_immutable:{record_id}")
        if not str(snapshot.get("content_sha256") or "").startswith("sha256:"):
            blockers.append(f"legacy_record_content_sha256_missing:{record_id}")
        if len(str(snapshot.get("git_blob_oid") or "")) != 40:
            blockers.append(f"legacy_record_git_blob_oid_invalid:{record_id}")
    if len(legacy_record_ids) != len(set(legacy_record_ids)):
        blockers.append("legacy_source_catalog_duplicate_record_id")
    legacy_git_object_blockers = (
        _verify_legacy_git_objects(repo_root, legacy_catalog, legacy_records)
        if verify_legacy_git_objects
        else []
    )
    blockers.extend(legacy_git_object_blockers)

    legacy_g1_count = sum(
        isinstance(row, dict) and row.get("category") == "g1_readiness"
        for row in legacy_records
    )
    promotion_blockers: list[str] = []
    if workstation.get("source_commit_sha") != head:
        promotion_blockers.append("workstation_readiness_not_bound_to_current_source")
    if (
        workstation.get("status") != "ready"
        or workstation.get("contract_pass") is not True
    ):
        promotion_blockers.append("current_workstation_readiness_not_ready")
    if not bool(hygiene.get("closure_pass")):
        promotion_blockers.append("repository_hygiene_closure_open")
    if not any(
        bool(row.get("release_eligible")) for row in rows if isinstance(row, dict)
    ):
        promotion_blockers.append("no_release_eligible_capability")
    if matrix_claims.get("recommended_matrix_technical_coverage_complete") is not True:
        promotion_blockers.append("bounded_planar_external_vv_matrix_incomplete")
    if matrix_claims.get("fresh_current_source_external_matrix_complete") is not True:
        promotion_blockers.append(
            "bounded_planar_fresh_current_source_external_matrix_incomplete"
        )
    if matrix_claims.get("bounded_planar_profile_level_2") is not True:
        promotion_blockers.append("bounded_planar_profile_level2_not_achieved")

    authority_counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        authority = str(row.get("numerical_authority") or "unavailable")
        authority_counts[authority] = authority_counts.get(authority, 0) + 1

    technical_track_blockers = [
        *(
            []
            if matrix_claims.get("recommended_matrix_technical_coverage_complete")
            is True
            else ["bounded_planar_external_vv_matrix_incomplete"]
        ),
        *(
            []
            if matrix_claims.get("fresh_current_source_technical_matrix_complete")
            is True
            else ["bounded_planar_fresh_current_source_technical_matrix_incomplete"]
        ),
    ]

    def external_authority_evidence(available: bool) -> dict[str, Any]:
        return (
            {"status": "available", "value": True}
            if available
            else {"status": "unavailable"}
        )

    history = {
        "schema_version": "product-state.history.v1",
        "current_authority": False,
        "source_catalog": {
            "path": LEGACY_CATALOG.as_posix(),
            "sha256": _sha256(repo_root, LEGACY_CATALOG),
            "schema_version": legacy_catalog.get("schema_version"),
            "snapshot_commit_sha": legacy_catalog.get("snapshot_commit_sha"),
            "git_object_verification": (
                "passed"
                if verify_legacy_git_objects and not legacy_git_object_blockers
                else ("failed" if verify_legacy_git_objects else "not_requested")
            ),
        },
        "legacy_g1_record_count": legacy_g1_count,
        "records": legacy_records,
        "claim_boundary": (
            "Historical records preserve provenance and their original bounded "
            "claims. They cannot establish current readiness, release authority, "
            "or current-source numerical authority."
        ),
    }
    current = {
        "schema_version": "product-state.current.v1",
        "source_commit_sha": head,
        "observed_github_main_sha": official_main,
        "observed_github_main_source": main_observation_source,
        "inventory_observed_main_sha": inventory_main,
        "source_matches_observed_github_main": head == official_main,
        "candidate_worktree_dirty": bool(status_rows),
        "candidate_worktree_change_count": len(status_rows),
        "status": "ready" if not blockers else "blocked",
        "contract_pass": not blockers,
        "blockers": blockers,
        "product_profile": "repository_integrity_developer_preview",
        "release_authority": False,
        "release_eligible": False,
        "authority_tracks": {
            "solo_developer_technical": {
                "status": (
                    "complete" if not technical_track_blockers else "in_progress"
                ),
                "scope": [
                    "repository_integrity",
                    "current_source_execution_packages",
                    "same_operator_technical_vv",
                    "deterministic_replay_and_result_integrity",
                ],
                "requires_independent_identity_authentication": False,
                "requires_counsel_legal_approval": False,
                "blockers": technical_track_blockers,
                "grants": ["bounded_developer_preview_technical_claims"],
                "does_not_grant": [
                    "independent_verification_level_2",
                    "commercial_equivalence",
                    "design_authority",
                    "release_authority",
                ],
            },
            "external_promotion": {
                "status": (
                    "complete"
                    if matrix_claims.get("bounded_planar_profile_level_2") is True
                    else "unavailable"
                ),
                "evidence": {
                    "independent_operator_identity_authentication": (
                        external_authority_evidence(
                            matrix_claims.get("independent_operator_attested") is True
                        )
                    ),
                    "product_legal_license_approval": external_authority_evidence(
                        matrix_claims.get("legal_use_approved") is True
                    ),
                    "formal_level_2_promotion": external_authority_evidence(
                        matrix_claims.get("bounded_planar_profile_level_2") is True
                    ),
                },
                "required_for": [
                    "independent_verification_level_2",
                    "external_promotion_claims",
                ],
                "does_not_block": [
                    "repository_integrity_developer_preview",
                    "solo_developer_technical_track",
                ],
            },
            "internal_license_due_diligence": {
                "status": (
                    "complete"
                    if not internal_license_blockers
                    and internal_license_due_diligence.get("contract_pass") is True
                    else "blocked"
                ),
                "attainable_by_solo_developer": True,
                "components": [
                    "license_inventory",
                    "spdx_notices",
                    "redistribution_boundary",
                    "source_use_declarations",
                ],
                "evidence": {
                    "path": INTERNAL_LICENSE_DUE_DILIGENCE.as_posix(),
                    "sha256": (
                        _sha256(repo_root, INTERNAL_LICENSE_DUE_DILIGENCE)
                        if (repo_root / INTERNAL_LICENSE_DUE_DILIGENCE).exists()
                        else "missing"
                    ),
                    "schema_version": internal_license_due_diligence.get(
                        "schema_version"
                    ),
                    "artifact_hash": internal_license_due_diligence.get(
                        "artifact_hash"
                    ),
                    "source_commit_sha": internal_license_due_diligence.get(
                        "source_commit_sha"
                    ),
                    "source_commit_matches_current": (
                        not internal_license_blockers
                        and
                        internal_license_due_diligence.get("source_commit_sha")
                        == head
                    ),
                    "contract_pass": (
                        not internal_license_blockers
                        and internal_license_due_diligence.get("contract_pass")
                        is True
                    ),
                    "validation_reason": internal_license_validation_reason,
                },
                "claims": internal_license_claims,
                # Keep the actionable details in the authenticated due-diligence
                # artifact referenced above.  Product State records only their
                # non-promoting state so imperative phrases such as "obtain ...
                # approval before ..." cannot be mistaken for granted authority.
                "external_actions": {
                    "status": (
                        "pending"
                        if not internal_license_blockers
                        and bool(
                            internal_license_due_diligence.get(
                                "external_actions", []
                            )
                        )
                        else "unavailable"
                    )
                },
                "blockers": internal_license_blockers,
                "does_not_grant": [
                    "product_legal_license_approval",
                    "commercial_redistribution_approval",
                    "independent_verification_level_2",
                    "release_authority",
                ],
                "claim_boundary": (
                    internal_license_due_diligence.get("claim_boundary")
                    if not internal_license_blockers
                    else (
                        "Internal due diligence is not counsel legal approval and "
                        "cannot promote the external authority track."
                    )
                ),
            },
        },
        "promotion_blockers": promotion_blockers,
        "quality_evidence": quality_evidence,
        "capability_registry": {
            "path": REGISTRY.as_posix(),
            "sha256": _sha256(repo_root, REGISTRY),
            "schema_version": registry.get("schema_version"),
            "capability_count": len(rows),
            "public_count": sum(
                bool(row.get("public")) for row in rows if isinstance(row, dict)
            ),
            "release_eligible_count": sum(
                bool(row.get("release_eligible"))
                for row in rows
                if isinstance(row, dict)
            ),
        },
        "bounded_planar_external_vv": {
            "path": BOUNDED_PLANAR_EXTERNAL_VV_MATRIX.as_posix(),
            "sha256": external_vv_matrix_sha256,
            "schema_version": external_vv_matrix.get("schema_version"),
            "source_commit_sha": external_vv_matrix.get("source_commit_sha"),
            "source_commit_matches_current": (
                external_vv_matrix_source_commit_matches_current
            ),
            "artifact_load_pass": external_vv_matrix_load_pass,
            "status_check_pass": external_vv_matrix_status_check_pass,
            "validation_pass": external_vv_matrix_validation_pass,
            "validation_reason": external_vv_matrix_validation_reason,
            "status": (
                external_vv_matrix.get("status")
                if external_vv_matrix_validation_pass
                else "stale_or_invalid"
            ),
            "contract_pass": (
                external_vv_matrix_validation_pass
                and external_vv_matrix.get("contract_pass") is True
            ),
            "summary": (
                external_vv_matrix.get("summary")
                if external_vv_matrix_validation_pass
                else None
            ),
            "stored_status": external_vv_matrix.get("status"),
            "stored_contract_pass": external_vv_matrix.get("contract_pass"),
            "stored_summary": external_vv_matrix.get("summary"),
            "execution_package_binding": (
                external_vv_matrix.get("execution_package_binding")
                if external_vv_matrix_validation_pass
                else None
            ),
            "supplemental_execution_package_bindings": (
                external_vv_matrix.get("supplemental_execution_package_bindings")
                if external_vv_matrix_validation_pass
                else None
            ),
            "current_source_workflow_binding": (
                external_vv_matrix.get("current_source_workflow_binding")
                if external_vv_matrix_validation_pass
                else None
            ),
            "same_operator_execution_binding": (
                external_vv_matrix.get("same_operator_execution_binding")
                if external_vv_matrix_validation_pass
                else None
            ),
            "same_operator_supplemental_execution_binding": (
                external_vv_matrix.get(
                    "same_operator_supplemental_execution_binding"
                )
                if external_vv_matrix_validation_pass
                else None
            ),
            "operator_intake_binding": (
                external_vv_matrix.get("operator_intake_binding")
                if external_vv_matrix_validation_pass
                else None
            ),
            "stored_execution_package_binding": external_vv_matrix.get(
                "execution_package_binding"
            ),
            "stored_supplemental_execution_package_bindings": (
                external_vv_matrix.get("supplemental_execution_package_bindings")
            ),
            "stored_current_source_workflow_binding": external_vv_matrix.get(
                "current_source_workflow_binding"
            ),
            "stored_same_operator_execution_binding": external_vv_matrix.get(
                "same_operator_execution_binding"
            ),
            "stored_same_operator_supplemental_execution_binding": (
                external_vv_matrix.get(
                    "same_operator_supplemental_execution_binding"
                )
            ),
            "stored_operator_intake_binding": external_vv_matrix.get(
                "operator_intake_binding"
            ),
            "claims": matrix_claims,
            "stored_claims": raw_matrix_claims,
            "claim_boundary": (
                "Stored matrix fields are diagnostic only until the matrix is "
                "rebuilt and exactly revalidated against current source inputs. "
                "Failed validation forces all effective claims false."
            ),
        },
        "legacy_readiness": {
            "path": READINESS.as_posix(),
            "classification": "historical_only",
            "current_product_authority": False,
            "historical_record_id": "product_readiness_snapshot_legacy",
        },
        "workstation_readiness": {
            "path": WORKSTATION.as_posix(),
            "sha256": _sha256(repo_root, WORKSTATION),
            "source_commit_sha": workstation.get("source_commit_sha"),
            "status": workstation.get("status"),
            "contract_pass": workstation.get("contract_pass"),
            "current_source_bound": workstation.get("source_commit_sha") == head,
        },
        "result_authority": {
            "source": REGISTRY.as_posix(),
            "numerical_authority_counts": dict(sorted(authority_counts.items())),
            "release_eligible_capability_count": sum(
                bool(row.get("release_eligible"))
                for row in rows
                if isinstance(row, dict)
            ),
        },
        "historical_state": {
            "path": HISTORY_OUT.as_posix(),
            "record_count": len(history["records"]),
            "legacy_g1_record_count": legacy_g1_count,
            "source_catalog_path": LEGACY_CATALOG.as_posix(),
            "source_catalog_sha256": _sha256(repo_root, LEGACY_CATALOG),
            "git_object_verification": history["source_catalog"][
                "git_object_verification"
            ],
            "current_authority": False,
        },
        "claim_boundary": (
            "This current-state manifest separates repository/source integrity from "
            "product promotion. A matching GitHub-main SHA, a successful source-bound "
            "Nightly Full Quality workflow-run event, and an internally consistent "
            "manifest can establish only the bounded Developer Preview profile; they do "
            "not promote a historical readiness receipt, blocked workstation gate, "
            "bounded capability, or historical PASS into release authority."
            " Unavailable independent identity or counsel review blocks only the "
            "external promotion track, not truthful solo-developer technical completion."
        ),
    }
    return current, history


def _write(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = repo_root / path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--observed-main-sha")
    parser.add_argument("--observed-main-source")
    parser.add_argument("--verify-legacy-git-objects", action="store_true")
    parser.add_argument("--nightly-workflow-run-event", type=Path)
    parser.add_argument("--external-vv-code-receipt", type=Path)
    parser.add_argument("--external-vv-modal-receipt", type=Path)
    parser.add_argument("--external-vv-clean-runner-summary", type=Path)
    parser.add_argument(
        "--external-vv-same-operator-supplemental-receipt", type=Path
    )
    args = parser.parse_args(argv)
    current, history = build_product_state(
        args.repo_root,
        observed_main_sha=args.observed_main_sha,
        observed_main_source=args.observed_main_source,
        verify_legacy_git_objects=args.verify_legacy_git_objects,
        nightly_workflow_run_event=(
            _load_path(args.nightly_workflow_run_event)
            if args.nightly_workflow_run_event is not None
            else None
        ),
        external_vv_code_receipt=args.external_vv_code_receipt,
        external_vv_modal_receipt=args.external_vv_modal_receipt,
        external_vv_clean_runner_summary=(
            args.external_vv_clean_runner_summary
        ),
        external_vv_same_operator_supplemental_receipt=(
            args.external_vv_same_operator_supplemental_receipt
        ),
    )
    if args.write:
        _write(args.repo_root, CURRENT_OUT, current)
        _write(args.repo_root, HISTORY_OUT, history)
    if args.json:
        print(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"product state: {current['status']} | "
            f"source={current['source_commit_sha'][:12]} | "
            f"blockers={len(current['blockers'])}"
        )
    return 0 if current["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
