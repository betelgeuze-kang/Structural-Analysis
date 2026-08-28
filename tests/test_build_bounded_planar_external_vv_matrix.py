from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_bounded_planar_external_vv_matrix.py"
SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_external_vv_matrix_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
matrix = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = matrix
SPEC.loader.exec_module(matrix)
SUPPLEMENTAL_RECEIPT = (
    ROOT / matrix.TRACKED_HISTORICAL_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT
)
requires_local_supplemental = pytest.mark.skipif(
    not SUPPLEMENTAL_RECEIPT.is_file(),
    reason="optional same-operator replay bundle is not source-controlled",
)


def _rows(payload: dict) -> dict[str, dict]:
    return {row["requirement_id"]: row for row in payload["requirements"]}


def _build_with_historical_supplemental(**kwargs):
    return matrix.build_bounded_planar_external_vv_matrix(
        repo_root=ROOT,
        same_operator_supplemental_receipt_path=(
            matrix.TRACKED_HISTORICAL_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT
        ),
        **kwargs,
    )


def test_matrix_schema_is_valid() -> None:
    schema = json.loads((ROOT / matrix.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_current_matrix_defaults_do_not_fall_back_to_tracked_snapshots() -> None:
    assert matrix.DEFAULT_CLEAN_RUNNER_SUMMARY.parts[:2] == (
        ".ci",
        "product-state-inputs",
    )
    assert matrix.DEFAULT_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT.parts[:2] == (
        ".ci",
        "product-state-inputs",
    )
    assert (
        matrix.DEFAULT_CLEAN_RUNNER_SUMMARY
        != matrix.TRACKED_HISTORICAL_CLEAN_RUNNER_SUMMARY
    )
    assert (
        matrix.DEFAULT_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT
        != matrix.TRACKED_HISTORICAL_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT
    )
    assert matrix.DEFAULT_CLEAN_RUNNER_EVIDENCE_ROOT == (
        matrix.DEFAULT_CLEAN_RUNNER_SUMMARY.parent
    )


def test_materialized_clean_runner_modal_vectors_do_not_fall_back_to_tracked_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = tmp_path / "materialized-clean-runner"
    evidence_root.mkdir()
    code_payload = json.loads((ROOT / matrix.DEFAULT_CODE_RECEIPT).read_text())
    modal_payload = json.loads((ROOT / matrix.DEFAULT_MODAL_RECEIPT).read_text())
    code_path = evidence_root / "code-receipt.json"
    modal_path = evidence_root / "modal-receipt.json"
    code_path.write_text(json.dumps(code_payload), encoding="utf-8")
    modal_path.write_text(json.dumps(modal_payload), encoding="utf-8")
    materialized_vectors: list[Path] = []
    for descriptor in modal_payload["mode_vector_artifacts"]:
        relative = Path(descriptor["artifact_path"])
        target = evidence_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
        materialized_vectors.append(target)
    observed_mode_vector_paths: dict[str, Path] = {}

    monkeypatch.setattr(
        matrix.code_receipt,
        "validate_external_code_to_code_technical_receipt",
        lambda *_args, **_kwargs: None,
    )

    def capture_modal_paths(*_args, **kwargs) -> None:
        observed_mode_vector_paths.update(kwargs["mode_vector_paths"])

    monkeypatch.setattr(
        matrix.modal_receipt,
        "validate_external_modal_buckling_technical_receipt",
        capture_modal_paths,
    )

    payloads, bindings = matrix._validated_receipts(
        ROOT,
        code_path,
        modal_path,
        modal_mode_vector_evidence_root=evidence_root,
    )

    assert set(payloads) == {"code_to_code", "modal_buckling"}
    assert bindings["modal_buckling"]["technical_contract_pass"] is True
    assert set(observed_mode_vector_paths) == {
        descriptor["name"] for descriptor in modal_payload["mode_vector_artifacts"]
    }
    assert all(
        path.is_relative_to(evidence_root)
        for path in observed_mode_vector_paths.values()
    )
    materialized_vectors[0].unlink()
    assert (ROOT / modal_payload["mode_vector_artifacts"][0]["artifact_path"]).is_file()
    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_clean_runner_mode_vector_missing_or_escape",
    ):
        matrix._materialized_modal_mode_vector_paths(
            evidence_root=evidence_root,
            modal_payload=modal_payload,
        )


@requires_local_supplemental
def test_current_matrix_uses_replay_only_receipts_without_promoting() -> None:
    payload = _build_with_historical_supplemental()
    rows = _rows(payload)

    assert payload["contract_pass"] is True
    assert payload["status"] == "blocked"
    assert payload["summary"] == {
        "requirement_count": 25,
        "technical_reference_present_count": 25,
        "fresh_current_source_technical_count": 0,
        "current_product_replay_only_count": 25,
        "fresh_external_technical_count": 0,
        "fresh_independent_preflight_technical_count": 0,
        "promotion_eligible_count": 0,
        "missing_count": 0,
        "execution_package_available_count": 16,
        "current_source_execution_prepared_count": 9,
    }
    assert payload["claims"] == {
        "recommended_matrix_technical_coverage_complete": True,
        "fresh_current_source_technical_matrix_complete": False,
        "fresh_current_source_external_matrix_complete": False,
        "independent_operator_attested": False,
        "legal_use_approved": False,
        "formal_promotion_receipt_attached": False,
        "bounded_planar_profile_level_2": False,
    }
    assert all(
        binding["current_product_replay_pass"] is True
        and binding["fresh_current_source_external_execution"] is False
        for binding in payload["receipt_bindings"]
    )
    assert payload["execution_package_binding"]["requirement_ids"] == [
        "linear.portal",
        "linear.multistory",
    ]
    assert payload["execution_package_binding"]["execution_workflow"] == {
        "repository_path": ".github/workflows/bounded-planar-opensees-technical.yml",
        "packaged_path": "workflow/bounded-planar-opensees-technical.yml",
        "file_sha256": matrix._file_sha256(
            ROOT / ".github/workflows/bounded-planar-opensees-technical.yml"
        ),
    }
    assert payload["execution_package_binding"]["contract_pass"] is True
    assert payload["execution_package_binding"]["external_solver_execution"] is False
    assert payload["execution_package_binding"]["verification_matrix_credit"] is False
    negative_binding = payload["supplemental_execution_package_bindings"][0]
    assert negative_binding["requirement_ids"] == [
        "negative.mechanism",
        "negative.singular",
        "negative.invalid_geometry",
    ]
    assert negative_binding["execution_workflow"] == {
        "repository_path": (
            ".github/workflows/bounded-planar-negative-opensees-technical.yml"
        ),
        "packaged_path": ("workflow/bounded-planar-negative-opensees-technical.yml"),
        "file_sha256": matrix._file_sha256(
            ROOT / ".github/workflows/bounded-planar-negative-opensees-technical.yml"
        ),
    }
    assert negative_binding["external_solver_execution"] is False
    assert negative_binding["verification_matrix_credit"] is False
    scaling_binding = payload["supplemental_execution_package_bindings"][1]
    assert scaling_binding["requirement_ids"] == [
        "scaling.unit_invariance",
        "scaling.characteristic_length_invariance",
    ]
    assert scaling_binding["execution_workflow"] == {
        "repository_path": (
            ".github/workflows/bounded-planar-scaling-opensees-technical.yml"
        ),
        "packaged_path": ("workflow/bounded-planar-scaling-opensees-technical.yml"),
        "file_sha256": matrix._file_sha256(
            ROOT / ".github/workflows/bounded-planar-scaling-opensees-technical.yml"
        ),
    }
    assert scaling_binding["external_solver_execution"] is False
    assert scaling_binding["verification_matrix_credit"] is False
    modal_buckling_binding = payload["supplemental_execution_package_bindings"][2]
    assert modal_buckling_binding["requirement_ids"] == [
        "modal.rigid_mode",
        "modal.repeated_mode",
        "buckling.portal",
    ]
    assert modal_buckling_binding["execution_workflow"] == {
        "repository_path": (
            ".github/workflows/bounded-planar-modal-buckling-technical.yml"
        ),
        "packaged_path": ("workflow/bounded-planar-modal-buckling-technical.yml"),
        "file_sha256": matrix._file_sha256(
            ROOT / ".github/workflows/bounded-planar-modal-buckling-technical.yml"
        ),
    }
    assert modal_buckling_binding["external_solver_execution"] is False
    assert modal_buckling_binding["verification_matrix_credit"] is False
    nonlinear_binding = payload["supplemental_execution_package_bindings"][3]
    assert nonlinear_binding["requirement_ids"] == [
        "geometric_nonlinear.p_delta",
        "geometric_nonlinear.snap_through",
        "material.steel_yield",
        "material.rc_fiber",
        "recovery.section",
        "recovery.fiber",
    ]
    assert nonlinear_binding["execution_workflow"] == {
        "repository_path": (
            ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml"
        ),
        "packaged_path": (
            "workflow/bounded-planar-nonlinear-material-recovery-technical.yml"
        ),
        "file_sha256": matrix._file_sha256(
            ROOT / ".github/workflows/"
            "bounded-planar-nonlinear-material-recovery-technical.yml"
        ),
    }
    assert nonlinear_binding["external_solver_execution"] is False
    assert nonlinear_binding["verification_matrix_credit"] is False
    assert payload["current_source_workflow_binding"] == {
        "workflow_id": "opensees-calculix-current-source-clean-runner",
        "repository_path": ".github/workflows/opensees-calculix-current-source.yml",
        "file_sha256": matrix._file_sha256(
            ROOT / ".github/workflows/opensees-calculix-current-source.yml"
        ),
        "trigger_branch": "main",
        "external_solver_ids": ["OpenSees", "CalculiX"],
        "prepared_requirement_ids": [
            "linear.cantilever",
            "member_feature.release",
            "member_feature.rigid_offset",
            "member_feature.distributed_load",
            "boundary.settlement",
            "boundary.prescribed_displacement",
            "buckling.column",
            "recovery.reaction",
            "recovery.member",
        ],
        "prepared_case_ids": [
            "bounded_planar_member_feature_load_path",
            "bounded_planar_prescribed_settlement_load_path",
            "cantilever_tip_load",
            "whole_model_frame_repeated_mode_linear_buckling",
        ],
        "contract_pass": True,
        "current_source_execution_attached": False,
        "same_operator_execution_attached": False,
        "attestation_required": True,
        "attestation_attached": False,
        "independent_operator_attested": False,
        "verification_matrix_credit": False,
        "verification_level_2": False,
    }
    same_operator = payload["same_operator_execution_binding"]
    assert same_operator == {
        "status": "unavailable",
        "reason": "current_source_clean_runner_cross_environment_parity_missing",
        "technical_contract_pass": False,
        "fresh_external_runtime_execution": False,
        "same_operator_container_isolated_reproduction": False,
        "actual_external_solver_execution": False,
        "independent_operator_attested": False,
        "product_legal_license_approval": False,
        "verification_level_2": False,
    }
    supplemental = payload["same_operator_supplemental_execution_binding"]
    assert supplemental["status"] == "attached_replay_only"
    assert supplemental["path"] == (
        "artifacts/vv/bounded_planar_same_operator_supplemental_execution/receipt.json"
    )
    assert supplemental["technical_contract_pass"] is True
    assert supplemental["current_product_replay_pass"] is True
    assert supplemental["historical_execution_input_binding_pass"] is True
    assert supplemental["external_runtime_executed_in_this_generation"] is False
    assert supplemental["external_execution_reused"] is True
    assert supplemental["fresh_current_source_external_execution"] is False
    assert supplemental["same_operator_local_execution"] is True
    assert supplemental["container_isolated_reproduction"] is False
    assert supplemental["actual_external_solver_execution"] is True
    assert supplemental["runtime_asset_bytes_attached"] is False
    assert supplemental["family_ids"] == [
        "linear",
        "negative",
        "scaling",
        "modal_buckling",
        "nonlinear_material_recovery",
    ]
    assert len(supplemental["case_ids"]) == 16
    assert supplemental["external_engine_invoked_case_count"] == 15
    assert supplemental["independent_preflight_case_ids"] == [
        "bounded_planar_negative_invalid_geometry"
    ]
    assert supplemental["independent_operator_attested"] is False
    assert supplemental["product_legal_license_approval"] is False
    assert supplemental["verification_level_2"] is False
    assert [
        binding["receipt_id"] for binding in payload["supplemental_receipt_bindings"]
    ] == [
        "same_operator_supplemental_linear",
        "same_operator_supplemental_negative",
        "same_operator_supplemental_scaling",
        "same_operator_supplemental_modal_buckling",
        "same_operator_supplemental_nonlinear_material_recovery",
    ]
    assert all(
        binding["technical_contract_pass"] is True
        and binding["current_product_replay_pass"] is True
        and binding["external_execution_reused"] is True
        and binding["fresh_current_source_external_execution"] is False
        for binding in payload["supplemental_receipt_bindings"]
    )
    assert payload["operator_intake_binding"] == {
        "status": "unavailable",
        "reason": "signed_operator_bundle_not_attached",
        "intake_contract_pass": False,
        "fresh_external_runtime_execution": False,
        "cryptographic_signature_verified": False,
        "operator_independence_declared": False,
        "operator_identity_credentials_verified": False,
        "verification_level_2": False,
    }
    assert all(
        row["status"] == "current_product_replay_only"
        and row["technical_reference_present"] is True
        and row["current_product_replay_pass"] is True
        and row["fresh_current_source_technical_validation"] is False
        and row["fresh_current_source_external_execution"] is False
        for row in rows.values()
    )
    invalid_geometry = rows["negative.invalid_geometry"]
    assert invalid_geometry["status"] == "current_product_replay_only"
    assert invalid_geometry["verification_method"] == "independent_preflight"
    assert invalid_geometry["fresh_current_source_technical_validation"] is False
    assert invalid_geometry["fresh_current_source_external_execution"] is False
    for requirement_id in (
        "geometric_nonlinear.p_delta",
        "geometric_nonlinear.snap_through",
        "material.steel_yield",
        "material.rc_fiber",
        "recovery.section",
        "recovery.fiber",
    ):
        assert rows[requirement_id]["status"] == "current_product_replay_only"
        assert rows[requirement_id]["execution_package_available"] is True
    prepared_ids = {
        "linear.cantilever",
        "member_feature.release",
        "member_feature.rigid_offset",
        "member_feature.distributed_load",
        "boundary.settlement",
        "boundary.prescribed_displacement",
        "buckling.column",
        "recovery.reaction",
        "recovery.member",
    }
    assert {
        requirement_id
        for requirement_id, row in rows.items()
        if row["current_source_execution_prepared"]
    } == prepared_ids
    assert all(
        rows[requirement_id]["execution_package_available"] is False
        for requirement_id in prepared_ids
    )
    assert payload["artifact_hash"] == matrix._artifact_hash(payload)


@requires_local_supplemental
def test_missing_clean_runner_preserves_replay_only_technical_coverage(
    tmp_path: Path,
) -> None:
    payload = _build_with_historical_supplemental(
        clean_runner_summary_path=tmp_path / "missing-clean-runner.json",
    )
    rows = _rows(payload)

    assert payload["summary"]["current_product_replay_only_count"] == 25
    assert payload["summary"]["fresh_current_source_technical_count"] == 0
    assert payload["summary"]["fresh_external_technical_count"] == 0
    assert payload["summary"]["fresh_independent_preflight_technical_count"] == 0
    assert payload["same_operator_execution_binding"] == {
        "status": "unavailable",
        "reason": "fresh_same_operator_clean_runner_receipt_not_attached",
        "technical_contract_pass": False,
        "fresh_external_runtime_execution": False,
        "same_operator_container_isolated_reproduction": False,
        "actual_external_solver_execution": False,
        "independent_operator_attested": False,
        "product_legal_license_approval": False,
        "verification_level_2": False,
    }
    assert rows["linear.cantilever"]["status"] == "current_product_replay_only"
    assert rows["buckling.column"]["status"] == "current_product_replay_only"
    assert rows["linear.portal"]["status"] == "current_product_replay_only"
    assert rows["buckling.portal"]["status"] == "current_product_replay_only"


def test_tampered_fresh_clean_runner_fails_closed(tmp_path: Path) -> None:
    source = ROOT / matrix.TRACKED_HISTORICAL_CLEAN_RUNNER_SUMMARY
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["claims"]["verification_level_2"] = True
    payload["artifact_hash"] = matrix._artifact_hash(payload)
    tampered = tmp_path / "tampered-clean-runner.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_clean_runner_summary_validation_failed",
    ):
        matrix.build_bounded_planar_external_vv_matrix(
            repo_root=ROOT,
            clean_runner_summary_path=tampered,
        )


def test_incompatible_receipts_do_not_fill_recommended_matrix_rows(
    tmp_path: Path,
) -> None:
    payload = matrix.build_bounded_planar_external_vv_matrix(
        repo_root=ROOT,
        same_operator_supplemental_receipt_path=(
            tmp_path / "missing-supplemental" / "receipt.json"
        ),
    )
    rows = _rows(payload)
    current_source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert payload["source_commit_sha"] == current_source_commit
    assert all(
        binding["source_commit_sha"] == current_source_commit
        and binding["external_execution_source_commit_sha"] != current_source_commit
        and binding["external_execution_reused"] is True
        and binding["fresh_current_source_external_execution"] is False
        for binding in payload["receipt_bindings"]
    )

    assert payload["same_operator_supplemental_execution_binding"] == {
        "status": "unavailable",
        "reason": "same_operator_supplemental_execution_receipt_not_attached",
        "technical_contract_pass": False,
        "current_product_replay_pass": False,
        "historical_execution_input_binding_pass": False,
        "external_runtime_executed_in_this_generation": False,
        "external_execution_reused": False,
        "fresh_current_source_external_execution": False,
        "same_operator_local_execution": False,
        "container_isolated_reproduction": False,
        "actual_external_solver_execution": False,
        "runtime_asset_bytes_attached": False,
        "independent_operator_attested": False,
        "product_legal_license_approval": False,
        "verification_level_2": False,
    }
    assert payload["supplemental_receipt_bindings"] == []
    assert payload["summary"]["technical_reference_present_count"] == 9
    assert payload["summary"]["missing_count"] == 16
    assert payload["summary"]["promotion_eligible_count"] == 0
    assert payload["status"] == "blocked"
    assert payload["claims"]["recommended_matrix_technical_coverage_complete"] is False

    assert rows["linear.portal"]["status"] == "missing"
    assert rows["linear.multistory"]["status"] == "missing"
    assert rows["linear.portal"]["required_external_case_ids"] == [
        "bounded_planar_linear_portal"
    ]
    assert rows["linear.multistory"]["required_external_case_ids"] == [
        "bounded_planar_linear_multistory"
    ]
    assert rows["linear.portal"]["execution_package_available"] is True
    assert rows["linear.multistory"]["execution_package_available"] is True
    assert (
        "external_execution_package_available_but_external_result_missing"
        in rows["linear.portal"]["blockers"]
    )
    assert (
        "external_execution_package_available_but_external_result_missing"
        in rows["linear.multistory"]["blockers"]
    )
    assert rows["modal.rigid_mode"]["status"] == "missing"
    assert rows["modal.repeated_mode"]["status"] == "missing"
    assert rows["buckling.portal"]["status"] == "missing"
    assert all(
        rows[requirement_id]["execution_package_available"] is True
        and "external_execution_package_available_but_external_result_missing"
        in rows[requirement_id]["blockers"]
        for requirement_id in (
            "modal.rigid_mode",
            "modal.repeated_mode",
            "buckling.portal",
        )
    )
    assert rows["geometric_nonlinear.p_delta"]["status"] == "missing"
    assert rows["geometric_nonlinear.snap_through"]["status"] == "missing"
    assert (
        "bounded_planar_public_p_delta_case_missing"
        in rows["geometric_nonlinear.p_delta"]["blockers"]
    )
    assert (
        "bounded_planar_public_snap_through_case_missing"
        in rows["geometric_nonlinear.snap_through"]["blockers"]
    )
    assert rows["material.steel_yield"]["status"] == "missing"
    assert rows["material.rc_fiber"]["status"] == "missing"
    assert rows["recovery.section"]["status"] == "missing"
    assert rows["recovery.fiber"]["status"] == "missing"
    assert rows["negative.mechanism"]["status"] == "missing"
    assert rows["negative.singular"]["status"] == "missing"
    assert rows["negative.invalid_geometry"]["status"] == "missing"
    assert rows["negative.mechanism"]["execution_package_available"] is True
    assert rows["negative.singular"]["execution_package_available"] is True
    assert rows["negative.invalid_geometry"]["execution_package_available"] is True
    assert all(
        "external_execution_package_available_but_external_result_missing"
        in rows[requirement_id]["blockers"]
        for requirement_id in (
            "negative.mechanism",
            "negative.singular",
            "negative.invalid_geometry",
        )
    )
    assert rows["scaling.unit_invariance"]["status"] == "missing"
    assert rows["scaling.characteristic_length_invariance"]["status"] == "missing"
    assert rows["scaling.unit_invariance"]["execution_package_available"] is True
    assert (
        rows["scaling.characteristic_length_invariance"]["execution_package_available"]
        is True
    )
    assert all(
        "external_execution_package_available_but_external_result_missing"
        in rows[requirement_id]["blockers"]
        for requirement_id in (
            "scaling.unit_invariance",
            "scaling.characteristic_length_invariance",
        )
    )
    assert all(
        row["execution_package_available"] is False
        for requirement_id, row in rows.items()
        if requirement_id
        not in {
            "linear.portal",
            "linear.multistory",
            "negative.mechanism",
            "negative.singular",
            "negative.invalid_geometry",
            "scaling.unit_invariance",
            "scaling.characteristic_length_invariance",
            "modal.rigid_mode",
            "modal.repeated_mode",
            "buckling.portal",
            "geometric_nonlinear.p_delta",
            "geometric_nonlinear.snap_through",
            "material.steel_yield",
            "material.rc_fiber",
            "recovery.section",
            "recovery.fiber",
        }
    )
    assert all(row["required_external_case_ids"] for row in rows.values())


def test_tampered_external_receipt_fails_closed(tmp_path: Path) -> None:
    source = ROOT / matrix.DEFAULT_CODE_RECEIPT
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["comparisons"][0]["contract_pass"] = False
    tampered = tmp_path / "external-code.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_code_receipt_validation_failed",
    ):
        matrix.build_bounded_planar_external_vv_matrix(
            repo_root=ROOT,
            code_receipt_path=tampered,
            clean_runner_summary_path=tmp_path / "missing-clean-runner.json",
        )


def test_forged_summary_or_level2_row_fails_closed() -> None:
    payload = matrix.build_bounded_planar_external_vv_matrix(repo_root=ROOT)
    forged_summary = deepcopy(payload)
    forged_summary["summary"]["missing_count"] += 1
    forged_summary["artifact_hash"] = matrix._artifact_hash(forged_summary)
    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_summary_invalid",
    ):
        matrix._validate_status(forged_summary, ROOT)

    forged_level2 = deepcopy(payload)
    row = forged_level2["requirements"][0]
    row["level2_eligible"] = True
    row["status"] = "promotion_eligible"
    forged_level2["summary"]["current_product_replay_only_count"] -= 1
    forged_level2["summary"]["promotion_eligible_count"] += 1
    forged_level2["artifact_hash"] = matrix._artifact_hash(forged_level2)
    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_level2_eligibility_invalid",
    ):
        matrix._validate_status(forged_level2, ROOT)


def test_forged_current_source_workflow_hash_fails_closed() -> None:
    payload = matrix.build_bounded_planar_external_vv_matrix(repo_root=ROOT)
    forged = deepcopy(payload)
    forged["current_source_workflow_binding"]["file_sha256"] = "sha256:" + "0" * 64
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_current_source_workflow_hash_invalid",
    ):
        matrix._validate_status(forged, ROOT)


def test_forged_core_receipt_freshness_fails_exact_revalidation() -> None:
    payload = matrix.build_bounded_planar_external_vv_matrix(repo_root=ROOT)
    forged = deepcopy(payload)
    forged["receipt_bindings"][0]["fresh_current_source_external_execution"] = True
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_core_receipt_bindings_invalid",
    ):
        matrix._validate_status(forged, ROOT)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("external_execution_source_commit_sha", "0" * 40),
        ("external_execution_reused", False),
    ),
)
def test_forged_core_replay_source_binding_fails_exact_revalidation(
    field: str,
    value: str | bool,
) -> None:
    payload = matrix.build_bounded_planar_external_vv_matrix(repo_root=ROOT)
    forged = deepcopy(payload)
    forged["receipt_bindings"][0][field] = value
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_core_receipt_bindings_invalid",
    ):
        matrix._validate_status(forged, ROOT)


def test_forged_current_source_workflow_coverage_fails_closed() -> None:
    payload = matrix.build_bounded_planar_external_vv_matrix(repo_root=ROOT)
    forged = deepcopy(payload)
    forged["current_source_workflow_binding"]["prepared_requirement_ids"].pop()
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_schema_validation_failed",
    ):
        matrix._validate_status(forged, ROOT)


def test_forged_unavailable_same_operator_binding_fails_closed() -> None:
    payload = matrix.build_bounded_planar_external_vv_matrix(repo_root=ROOT)
    forged = deepcopy(payload)
    forged["same_operator_execution_binding"]["actual_external_solver_execution"] = True
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_schema_validation_failed",
    ):
        matrix._validate_status(forged, ROOT)


@requires_local_supplemental
def test_forged_same_operator_supplemental_binding_fails_closed() -> None:
    payload = _build_with_historical_supplemental()
    forged = deepcopy(payload)
    forged["same_operator_supplemental_execution_binding"]["file_sha256"] = (
        "sha256:" + "0" * 64
    )
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match=("matrix_status_same_operator_supplemental_execution_binding_invalid"),
    ):
        matrix._validate_status(forged, ROOT)


@requires_local_supplemental
def test_forged_supplemental_child_receipt_binding_fails_closed() -> None:
    payload = _build_with_historical_supplemental()
    forged = deepcopy(payload)
    forged["supplemental_receipt_bindings"][0]["file_sha256"] = "sha256:" + "0" * 64
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_supplemental_receipt_bindings_invalid",
    ):
        matrix._validate_status(forged, ROOT)


@requires_local_supplemental
def test_reused_supplemental_binding_cannot_claim_fresh() -> None:
    payload = _build_with_historical_supplemental()
    forged = deepcopy(payload)
    forged["supplemental_receipt_bindings"][0][
        "fresh_current_source_external_execution"
    ] = True
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_schema_validation_failed",
    ):
        matrix._validate_status(forged, ROOT)


def test_forged_prepared_row_fails_closed() -> None:
    payload = matrix.build_bounded_planar_external_vv_matrix(repo_root=ROOT)
    forged = deepcopy(payload)
    forged["requirements"][0]["current_source_execution_prepared"] = False
    forged["summary"]["current_source_execution_prepared_count"] -= 1
    forged["artifact_hash"] = matrix._artifact_hash(forged)

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_status_current_source_execution_prepared_invalid",
    ):
        matrix._validate_status(forged, ROOT)


def test_tampered_execution_package_fails_closed(tmp_path: Path) -> None:
    source = ROOT / matrix.DEFAULT_LINEAR_CASE_PACKAGE.parent
    target = tmp_path / "linear-package"
    import shutil

    shutil.copytree(source, target)
    runner = target / "opensees" / "bounded_planar_linear_portal.py"
    runner.write_text(runner.read_text(encoding="utf-8") + "# tampered\n")

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_linear_execution_package_file_hash_invalid",
    ):
        matrix.build_bounded_planar_external_vv_matrix(
            repo_root=ROOT,
            linear_case_package_path=target / matrix.linear_package.MANIFEST_NAME,
        )


def test_tampered_packaged_execution_workflow_fails_closed(tmp_path: Path) -> None:
    source = ROOT / matrix.DEFAULT_LINEAR_CASE_PACKAGE.parent
    target = tmp_path / "linear-package"
    import shutil

    shutil.copytree(source, target)
    manifest = json.loads(
        (target / matrix.linear_package.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    workflow = target / manifest["execution_workflow"]["path"]
    workflow.write_text(
        workflow.read_text(encoding="utf-8") + "# tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_linear_execution_package_file_hash_invalid",
    ):
        matrix.build_bounded_planar_external_vv_matrix(
            repo_root=ROOT,
            linear_case_package_path=target / matrix.linear_package.MANIFEST_NAME,
        )


def test_tampered_negative_execution_package_fails_closed(tmp_path: Path) -> None:
    source = ROOT / matrix.DEFAULT_NEGATIVE_CASE_PACKAGE.parent
    target = tmp_path / "negative-package"
    import shutil

    shutil.copytree(source, target)
    runner = target / "opensees/bounded_planar_negative_mechanism.py"
    runner.write_text(runner.read_text(encoding="utf-8") + "# tampered\n")

    with pytest.raises(
        matrix.BoundedPlanarVVMatrixError,
        match="matrix_negative_execution_package_validation_failed",
    ):
        matrix.build_bounded_planar_external_vv_matrix(
            repo_root=ROOT,
            negative_case_package_path=(target / matrix.negative_package.MANIFEST_NAME),
        )


def test_committed_status_is_current_and_cli_check_passes() -> None:
    expected = matrix.build_bounded_planar_external_vv_matrix(repo_root=ROOT)
    actual = json.loads((ROOT / matrix.DEFAULT_OUT).read_text(encoding="utf-8"))

    assert actual == expected
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "status_consistent" in completed.stdout
