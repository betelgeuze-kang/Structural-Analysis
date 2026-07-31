from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_product_state.py"
SPEC = importlib.util.spec_from_file_location("build_product_state", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
product_state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = product_state
SPEC.loader.exec_module(product_state)
SUPPLEMENTAL_RECEIPT = (
    ROOT
    / "artifacts/vv/bounded_planar_same_operator_supplemental_execution/receipt.json"
)


def _nightly_event(
    head_sha: str,
    *,
    conclusion: str = "success",
) -> dict[str, object]:
    return {
        "workflow_run": {
            "id": 30207954772,
            "run_number": 42,
            "run_attempt": 1,
            "name": "Nightly Full Quality",
            "event": "schedule",
            "conclusion": conclusion,
            "head_branch": "main",
            "head_sha": head_sha,
            "html_url": "https://github.com/example/repository/actions/runs/30207954772",
        }
    }


@pytest.mark.skipif(
    not SUPPLEMENTAL_RECEIPT.is_file(),
    reason="optional same-operator replay bundle is not source-controlled",
)
def test_product_state_separates_current_source_from_historical_passes() -> None:
    current, history = product_state.build_product_state(ROOT)

    assert current["schema_version"] == "product-state.current.v1"
    assert current["source_commit_sha"] == current["observed_github_main_sha"]
    assert current["capability_registry"]["schema_version"] == (
        "structural-analysis-capabilities.v2"
    )
    assert current["capability_registry"]["capability_count"] == 31
    assert current["capability_registry"]["release_eligible_count"] == 0
    assert (
        current["bounded_planar_external_vv"]["source_commit_matches_current"] is True
    )
    assert current["bounded_planar_external_vv"]["validation_pass"] is True
    assert current["bounded_planar_external_vv"]["validation_reason"] == (
        "bounded_planar_external_vv_matrix_status_consistent"
    )
    assert current["bounded_planar_external_vv"]["status"] == "blocked"
    assert current["bounded_planar_external_vv"]["contract_pass"] is True
    expected_summary = {
        "requirement_count": 25,
        "technical_reference_present_count": 25,
        "fresh_current_source_technical_count": 25,
        "current_product_replay_only_count": 0,
        "fresh_external_technical_count": 24,
        "fresh_independent_preflight_technical_count": 1,
        "promotion_eligible_count": 0,
        "missing_count": 0,
        "execution_package_available_count": 16,
        "current_source_execution_prepared_count": 9,
    }
    assert current["bounded_planar_external_vv"]["summary"] == expected_summary
    assert current["bounded_planar_external_vv"]["stored_summary"] == expected_summary
    matrix = current["bounded_planar_external_vv"]
    for live_name, stored_name in (
        ("execution_package_binding", "stored_execution_package_binding"),
        (
            "supplemental_execution_package_bindings",
            "stored_supplemental_execution_package_bindings",
        ),
        (
            "current_source_workflow_binding",
            "stored_current_source_workflow_binding",
        ),
        (
            "same_operator_execution_binding",
            "stored_same_operator_execution_binding",
        ),
        (
            "same_operator_supplemental_execution_binding",
            "stored_same_operator_supplemental_execution_binding",
        ),
        ("operator_intake_binding", "stored_operator_intake_binding"),
    ):
        assert matrix[live_name] == matrix[stored_name]
    stored_execution_package = matrix["execution_package_binding"]
    assert stored_execution_package["requirement_ids"] == [
        "linear.portal",
        "linear.multistory",
    ]
    assert stored_execution_package["external_solver_execution"] is False
    negative_binding = matrix["supplemental_execution_package_bindings"][0]
    assert negative_binding["requirement_ids"] == [
        "negative.mechanism",
        "negative.singular",
        "negative.invalid_geometry",
    ]
    assert negative_binding["external_solver_execution"] is False
    assert negative_binding["verification_matrix_credit"] is False
    scaling_binding = matrix["supplemental_execution_package_bindings"][1]
    assert scaling_binding["requirement_ids"] == [
        "scaling.unit_invariance",
        "scaling.characteristic_length_invariance",
    ]
    assert scaling_binding["external_solver_execution"] is False
    assert scaling_binding["verification_matrix_credit"] is False
    workflow_binding = matrix["current_source_workflow_binding"]
    assert workflow_binding["workflow_id"] == (
        "opensees-calculix-current-source-clean-runner"
    )
    assert workflow_binding["current_source_execution_attached"] is False
    assert workflow_binding["attestation_attached"] is False
    assert workflow_binding["verification_matrix_credit"] is False
    assert workflow_binding["verification_level_2"] is False
    same_operator_binding = matrix["same_operator_execution_binding"]
    assert same_operator_binding["status"] == "unavailable"
    assert same_operator_binding["fresh_external_runtime_execution"] is False
    assert (
        same_operator_binding["same_operator_container_isolated_reproduction"] is False
    )
    assert same_operator_binding["reason"] == (
        "current_source_clean_runner_cross_environment_parity_missing"
    )
    assert same_operator_binding["independent_operator_attested"] is False
    assert same_operator_binding["product_legal_license_approval"] is False
    assert same_operator_binding["verification_level_2"] is False
    supplemental_binding = matrix["same_operator_supplemental_execution_binding"]
    assert supplemental_binding["status"] == "attached"
    assert supplemental_binding["fresh_current_source_external_execution"] is True
    assert supplemental_binding["same_operator_local_execution"] is True
    assert supplemental_binding["container_isolated_reproduction"] is False
    assert supplemental_binding["actual_external_solver_execution"] is True
    assert supplemental_binding["runtime_asset_bytes_attached"] is False
    assert len(supplemental_binding["case_ids"]) == 16
    assert supplemental_binding["external_engine_invoked_case_count"] == 15
    assert supplemental_binding["independent_preflight_case_ids"] == [
        "bounded_planar_negative_invalid_geometry"
    ]
    assert supplemental_binding["independent_operator_attested"] is False
    assert supplemental_binding["product_legal_license_approval"] is False
    assert supplemental_binding["verification_level_2"] is False
    assert matrix["operator_intake_binding"] == {
        "status": "unavailable",
        "reason": "signed_operator_bundle_not_attached",
        "intake_contract_pass": False,
        "fresh_external_runtime_execution": False,
        "cryptographic_signature_verified": False,
        "operator_independence_declared": False,
        "operator_identity_credentials_verified": False,
        "verification_level_2": False,
    }
    assert (
        current["bounded_planar_external_vv"]["claims"][
            "recommended_matrix_technical_coverage_complete"
        ]
        is True
    )
    assert (
        current["bounded_planar_external_vv"]["claims"][
            "fresh_current_source_technical_matrix_complete"
        ]
        is True
    )
    assert (
        current["bounded_planar_external_vv"]["stored_claims"][
            "recommended_matrix_technical_coverage_complete"
        ]
        is True
    )
    assert (
        current["bounded_planar_external_vv"]["claims"][
            "bounded_planar_profile_level_2"
        ]
        is False
    )
    assert current["historical_state"]["current_authority"] is False
    assert current["historical_state"]["record_count"] == 5
    assert current["historical_state"]["legacy_g1_record_count"] == 3
    assert current["historical_state"]["source_catalog_sha256"].startswith("sha256:")
    assert current["workstation_readiness"]["current_source_bound"] is True
    assert current["workstation_readiness"]["status"] == "blocked"
    assert current["workstation_readiness"]["contract_pass"] is False
    assert current["product_profile"] == "repository_integrity_developer_preview"
    assert current["release_authority"] is False
    assert current["release_eligible"] is False
    solo_track = current["authority_tracks"]["solo_developer_technical"]
    assert solo_track["status"] == "complete"
    assert solo_track["blockers"] == []
    assert solo_track["requires_independent_identity_authentication"] is False
    assert solo_track["requires_counsel_legal_approval"] is False
    assert solo_track["grants"] == ["bounded_developer_preview_technical_claims"]
    assert "release_authority" in solo_track["does_not_grant"]
    external_track = current["authority_tracks"]["external_promotion"]
    assert external_track["status"] == "unavailable"
    assert external_track["evidence"] == {
        "independent_operator_identity_authentication": {"status": "unavailable"},
        "product_legal_license_approval": {"status": "unavailable"},
        "formal_level_2_promotion": {"status": "unavailable"},
    }
    assert external_track["does_not_block"] == [
        "repository_integrity_developer_preview",
        "solo_developer_technical_track",
    ]
    license_track = current["authority_tracks"]["internal_license_due_diligence"]
    assert license_track["status"] == "complete"
    assert license_track["attainable_by_solo_developer"] is True
    assert license_track["blockers"] == []
    assert license_track["evidence"]["contract_pass"] is True
    assert license_track["evidence"]["source_commit_matches_current"] is True
    assert license_track["evidence"]["validation_reason"] == "PASS"
    assert license_track["claims"]["internal_due_diligence_complete"] is True
    assert license_track["claims"]["product_legal_approval"] is False
    assert (
        license_track["claims"]["product_commercial_redistribution_approved"] is False
    )
    assert license_track["claims"]["formal_verification_level_2"] is False
    assert license_track["claims"]["release_authority"] is False
    assert "release_authority" in license_track["does_not_grant"]
    assert current["quality_evidence"] == {
        "status": "unavailable",
        "authority": "github_actions_workflow_run_event",
    }
    assert "nightly_full_quality_evidence_unavailable" in current["blockers"]
    assert (
        "bounded_planar_external_vv_matrix_stale_or_invalid" not in current["blockers"]
    )
    assert current["legacy_readiness"] == {
        "path": (
            "implementation/phase1/release_evidence/productization/"
            "product_readiness_snapshot.json"
        ),
        "classification": "historical_only",
        "current_product_authority": False,
        "historical_record_id": "product_readiness_snapshot_legacy",
    }
    assert current["promotion_blockers"] == [
        "current_workstation_readiness_not_ready",
        "repository_hygiene_closure_open",
        "no_release_eligible_capability",
        "bounded_planar_profile_level2_not_achieved",
    ]
    assert current["result_authority"]["release_eligible_capability_count"] == 0
    assert history["schema_version"] == "product-state.history.v1"
    assert history["current_authority"] is False
    assert history["legacy_g1_record_count"] == 3
    assert history["source_catalog"]["schema_version"] == (
        "product-state.legacy-sources.v1"
    )
    assert all(row["classification"] == "historical_only" for row in history["records"])
    assert all(row["current_product_authority"] is False for row in history["records"])
    assert all(
        row["snapshot"]["storage_kind"] == "git_object" for row in history["records"]
    )
    assert all(
        row["snapshot"]["content_sha256"].startswith("sha256:")
        for row in history["records"]
    )
    legacy_workstation = next(
        row
        for row in history["records"]
        if row["id"] == "workstation_delivery_readiness_legacy_pass"
    )
    assert legacy_workstation["artifact"]["status"] == "ready"
    assert legacy_workstation["artifact"]["contract_pass"] is True
    assert (
        legacy_workstation["artifact"]["source_commit_sha"]
        != current["source_commit_sha"]
    )


def test_dirty_candidate_fails_closed_without_promoting_legacy_readiness() -> None:
    current_head = product_state._git(ROOT, "rev-parse", "HEAD")
    current, _ = product_state.build_product_state(
        ROOT,
        observed_main_sha=current_head,
        observed_main_source="test_exact_current_head",
    )

    assert current["source_matches_observed_github_main"] is True
    assert current["contract_pass"] is False
    assert current["status"] == "blocked"
    assert "candidate_worktree_not_committed" in current["blockers"]
    assert "readiness_snapshot_not_bound_to_current_source" not in current["blockers"]
    assert "current_readiness_not_ready" not in current["blockers"]
    assert "current_workstation_readiness_not_ready" not in current["blockers"]
    assert (
        "workstation_readiness_not_bound_to_current_source"
        in current["promotion_blockers"]
    )
    assert "do not promote" in current["claim_boundary"]


@pytest.mark.skipif(
    not SUPPLEMENTAL_RECEIPT.is_file(),
    reason="optional same-operator replay bundle is not source-controlled",
)
def test_stale_external_vv_matrix_claims_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        product_state,
        "check_bounded_planar_external_vv_matrix_status",
        lambda **_: (False, "test_matrix_source_drift"),
    )

    current, _ = product_state.build_product_state(ROOT)
    matrix = current["bounded_planar_external_vv"]

    assert matrix["validation_pass"] is False
    assert matrix["validation_reason"] == "test_matrix_source_drift"
    assert matrix["status"] == "stale_or_invalid"
    assert matrix["contract_pass"] is False
    assert matrix["summary"] is None
    assert matrix["stored_contract_pass"] is True
    assert matrix["stored_summary"]["technical_reference_present_count"] == 25
    assert (
        matrix["stored_claims"]["recommended_matrix_technical_coverage_complete"]
        is True
    )
    assert matrix["same_operator_supplemental_execution_binding"] is None
    assert (
        matrix["stored_same_operator_supplemental_execution_binding"]["status"]
        == "attached"
    )
    assert all(value is False for value in matrix["claims"].values())
    assert "bounded_planar_external_vv_matrix_stale_or_invalid" in current["blockers"]


def test_external_vv_claims_require_current_head_binding(monkeypatch) -> None:
    actual_git = product_state._git

    def fake_git(repo_root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "0" * 40
        return actual_git(repo_root, *args)

    monkeypatch.setattr(product_state, "_git", fake_git)
    monkeypatch.setattr(
        product_state,
        "check_bounded_planar_external_vv_matrix_status",
        lambda **_: (True, "test_matrix_status_consistent"),
    )

    current, _ = product_state.build_product_state(ROOT)
    matrix = current["bounded_planar_external_vv"]

    assert matrix["status_check_pass"] is True
    assert matrix["source_commit_matches_current"] is False
    assert matrix["validation_pass"] is False
    assert matrix["validation_reason"] == (
        "bounded_planar_external_vv_matrix_source_commit_mismatch"
    )
    assert matrix["summary"] is None
    assert all(value is False for value in matrix["claims"].values())
    assert current["authority_tracks"]["solo_developer_technical"]["status"] == (
        "in_progress"
    )


def test_missing_external_vv_matrix_emits_blocked_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    missing = tmp_path / "missing-matrix.json"
    monkeypatch.setattr(
        product_state,
        "BOUNDED_PLANAR_EXTERNAL_VV_MATRIX",
        missing,
    )

    current, _ = product_state.build_product_state(ROOT)
    matrix = current["bounded_planar_external_vv"]

    assert matrix["artifact_load_pass"] is False
    assert matrix["status_check_pass"] is False
    assert matrix["validation_pass"] is False
    assert matrix["validation_reason"] == (
        "bounded_planar_external_vv_matrix_load_failed:FileNotFoundError"
    )
    assert matrix["sha256"] == "missing"
    assert matrix["status"] == "stale_or_invalid"
    assert matrix["summary"] is None
    assert all(value is False for value in matrix["claims"].values())
    assert "bounded_planar_external_vv_matrix_stale_or_invalid" in current["blockers"]


def test_internal_license_due_diligence_tamper_blocks_product_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = json.loads(
        (ROOT / product_state.INTERNAL_LICENSE_DUE_DILIGENCE).read_text(
            encoding="utf-8"
        )
    )
    payload["claims"]["product_legal_approval"] = True
    tampered = tmp_path / "internal_license_due_diligence.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        product_state,
        "INTERNAL_LICENSE_DUE_DILIGENCE",
        tampered,
    )

    current, _ = product_state.build_product_state(ROOT)

    assert "internal_license_due_diligence_missing_or_invalid" in current["blockers"]
    license_track = current["authority_tracks"]["internal_license_due_diligence"]
    assert license_track["status"] == "blocked"
    assert license_track["blockers"] == [
        "internal_license_due_diligence_missing_or_invalid"
    ]
    assert license_track["evidence"]["contract_pass"] is False
    assert license_track["evidence"]["source_commit_matches_current"] is False
    assert license_track["claims"]["internal_due_diligence_complete"] is False
    assert license_track["claims"]["product_legal_approval"] is False
    assert license_track["claims"]["release_authority"] is False
    assert (
        "internal_license_due_diligence_mismatch"
        in license_track["evidence"]["validation_reason"]
    )
    assert current["release_authority"] is False
    assert current["release_eligible"] is False


def test_live_main_observation_source_is_recorded_without_promoting_release() -> None:
    head = product_state._git(ROOT, "rev-parse", "HEAD")
    current, _ = product_state.build_product_state(
        ROOT,
        observed_main_sha=head,
        observed_main_source="test_main_observation",
        nightly_workflow_run_event=_nightly_event(head),
    )

    assert current["observed_github_main_sha"] == head
    assert current["observed_github_main_source"] == "test_main_observation"
    assert current["source_matches_observed_github_main"] is True
    assert current["quality_evidence"]["status"] == "available"
    assert current["quality_evidence"]["head_sha"] == head
    assert current["release_authority"] is False


def test_legacy_git_object_snapshots_rehash_against_pinned_commit() -> None:
    head = product_state._git(ROOT, "rev-parse", "HEAD")
    current, history = product_state.build_product_state(
        ROOT,
        observed_main_sha=head,
        observed_main_source="test_main_observation",
        verify_legacy_git_objects=True,
        nightly_workflow_run_event=_nightly_event(head),
    )

    assert not any(
        blocker.startswith("legacy_record_") for blocker in current["blockers"]
    )
    assert current["historical_state"]["git_object_verification"] == "passed"
    assert history["source_catalog"]["git_object_verification"] == "passed"


def test_nightly_quality_evidence_rejects_detached_head_sha() -> None:
    head = product_state._git(ROOT, "rev-parse", "HEAD")
    event = _nightly_event("0" * 40)

    current, _ = product_state.build_product_state(
        ROOT,
        observed_main_sha=head,
        observed_main_source="github_nightly_full_quality_success",
        nightly_workflow_run_event=event,
    )

    assert current["quality_evidence"]["status"] == "invalid"
    assert "nightly_full_quality_evidence_invalid:head_sha" in current["blockers"]


def test_nightly_failure_is_available_evidence_and_blocks_quality() -> None:
    head = product_state._git(ROOT, "rev-parse", "HEAD")

    current, _ = product_state.build_product_state(
        ROOT,
        observed_main_sha=head,
        observed_main_source="github_nightly_full_quality_observation",
        nightly_workflow_run_event=_nightly_event(head, conclusion="failure"),
    )

    assert current["quality_evidence"]["status"] == "available"
    assert current["quality_evidence"]["conclusion"] == "failure"
    assert "nightly_full_quality_not_success:failure" in current["blockers"]
    assert not any(
        blocker.startswith("nightly_full_quality_evidence_invalid:")
        for blocker in current["blockers"]
    )


def test_unknown_nightly_conclusion_is_invalid_evidence() -> None:
    head = product_state._git(ROOT, "rev-parse", "HEAD")

    current, _ = product_state.build_product_state(
        ROOT,
        observed_main_sha=head,
        observed_main_source="github_nightly_full_quality_observation",
        nightly_workflow_run_event=_nightly_event(head, conclusion="unexpected"),
    )

    assert current["quality_evidence"]["status"] == "invalid"
    assert "nightly_full_quality_evidence_invalid:conclusion" in current["blockers"]
    assert not any(
        blocker.startswith("nightly_full_quality_not_success:")
        for blocker in current["blockers"]
    )
