from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts" / "build_bounded_planar_external_vv_matrix_from_operator_bundle.py"
)
OPERATOR_FIXTURE = ROOT / "tests/test_validate_external_vv_operator_attestation.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load("operator_attested_matrix_tests", SCRIPT)
operator_fixture = _load("operator_attested_matrix_fixture", OPERATOR_FIXTURE)


def test_signed_fresh_core_bundle_builds_nine_fresh_rows_without_promotion(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )

    assert matrix["summary"] == {
        "requirement_count": 25,
        "technical_reference_present_count": 9,
        "fresh_current_source_technical_count": 9,
        "current_product_replay_only_count": 0,
        "fresh_external_technical_count": 9,
        "fresh_independent_preflight_technical_count": 0,
        "promotion_eligible_count": 0,
        "missing_count": 16,
        "execution_package_available_count": 16,
        "current_source_execution_prepared_count": 9,
    }
    assert matrix["operator_intake_binding"]["status"] == "available"
    assert matrix["operator_intake_binding"]["cryptographic_signature_verified"] is True
    assert (
        matrix["operator_intake_binding"]["operator_identity_credentials_verified"]
        is False
    )
    assert matrix["claims"]["fresh_current_source_external_matrix_complete"] is False
    assert matrix["claims"]["independent_operator_attested"] is False
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False
    assert all(
        row["independent_operator_attested"] is False
        and row["level2_eligible"] is False
        for row in matrix["requirements"]
    )
    with pytest.raises(
        builder.matrix_builder.BoundedPlanarVVMatrixError,
        match="matrix_status_operator_intake_revalidation_required",
    ):
        builder.matrix_builder._validate_status(matrix, ROOT)


def test_signed_linear_supplement_adds_only_its_two_exact_cases(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    operator_fixture._attach_linear_supplement(attestation, bundle_root)

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )
    rows = {row["requirement_id"]: row for row in matrix["requirements"]}

    assert matrix["summary"]["fresh_external_technical_count"] == 11
    assert matrix["summary"]["missing_count"] == 14
    assert rows["linear.portal"]["status"] == "fresh_external_technical"
    assert rows["linear.multistory"]["status"] == "fresh_external_technical"
    assert rows["modal.rigid_mode"]["status"] == "missing"
    assert matrix["supplemental_receipt_bindings"][0]["case_ids"] == [
        "bounded_planar_linear_multistory",
        "bounded_planar_linear_portal",
    ]
    assert (
        matrix["supplemental_receipt_bindings"][0][
            "external_execution_reused"
        ]
        is False
    )
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False


def test_signed_modal_buckling_supplement_adds_only_three_exact_cases(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    operator_fixture._attach_modal_buckling_supplement(attestation, bundle_root)

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )
    rows = {row["requirement_id"]: row for row in matrix["requirements"]}

    assert matrix["summary"]["fresh_external_technical_count"] == 12
    assert matrix["summary"]["missing_count"] == 13
    for requirement_id in (
        "modal.rigid_mode",
        "modal.repeated_mode",
        "buckling.portal",
    ):
        assert rows[requirement_id]["status"] == "fresh_external_technical"
        assert rows[requirement_id]["level2_eligible"] is False
    assert rows["geometric_nonlinear.p_delta"]["status"] == "missing"
    assert rows["buckling.column"]["status"] == "fresh_external_technical"
    assert matrix["supplemental_receipt_bindings"][0]["receipt_id"] == (
        "bounded_planar_modal_buckling"
    )
    assert matrix["supplemental_receipt_bindings"][0]["case_ids"] == [
        "bounded_planar_buckling_portal",
        "bounded_planar_modal_repeated_mode",
        "bounded_planar_modal_rigid_mode",
    ]
    assert matrix["claims"]["independent_operator_attested"] is False
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False


def test_signed_linear_and_modal_buckling_supplements_add_five_exact_rows(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    operator_fixture._attach_linear_supplement(attestation, bundle_root)
    operator_fixture._attach_modal_buckling_supplement(attestation, bundle_root)

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )
    rows = {row["requirement_id"]: row for row in matrix["requirements"]}

    assert matrix["summary"]["fresh_external_technical_count"] == 14
    assert matrix["summary"]["missing_count"] == 11
    assert [
        binding["receipt_id"] for binding in matrix["supplemental_receipt_bindings"]
    ] == ["bounded_planar_linear", "bounded_planar_modal_buckling"]
    for requirement_id in (
        "linear.portal",
        "linear.multistory",
        "modal.rigid_mode",
        "modal.repeated_mode",
        "buckling.portal",
    ):
        assert rows[requirement_id]["status"] == "fresh_external_technical"
        assert rows[requirement_id]["level2_eligible"] is False
    assert matrix["claims"]["independent_operator_attested"] is False
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False


def test_signed_negative_supplement_adds_only_three_exact_rejection_cases(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    operator_fixture._attach_negative_supplement(attestation, bundle_root)

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )
    rows = {row["requirement_id"]: row for row in matrix["requirements"]}

    assert matrix["summary"]["fresh_current_source_technical_count"] == 12
    assert matrix["summary"]["fresh_external_technical_count"] == 11
    assert matrix["summary"]["fresh_independent_preflight_technical_count"] == 1
    assert matrix["summary"]["missing_count"] == 13
    for requirement_id in ("negative.mechanism", "negative.singular"):
        assert rows[requirement_id]["status"] == "fresh_external_technical"
        assert rows[requirement_id]["level2_eligible"] is False
    invalid_geometry = rows["negative.invalid_geometry"]
    assert invalid_geometry["status"] == "fresh_independent_preflight_technical"
    assert invalid_geometry["fresh_current_source_external_execution"] is False
    assert invalid_geometry["fresh_current_source_technical_validation"] is True
    assert invalid_geometry["level2_eligible"] is False
    assert rows["linear.portal"]["status"] == "missing"
    assert matrix["supplemental_receipt_bindings"][0]["receipt_id"] == (
        "bounded_planar_negative"
    )
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False


def test_signed_scaling_supplement_adds_only_two_exact_invariance_cases(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    operator_fixture._attach_scaling_supplement(attestation, bundle_root)

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )
    rows = {row["requirement_id"]: row for row in matrix["requirements"]}

    assert matrix["summary"]["fresh_external_technical_count"] == 11
    assert matrix["summary"]["missing_count"] == 14
    for requirement_id in (
        "scaling.unit_invariance",
        "scaling.characteristic_length_invariance",
    ):
        assert rows[requirement_id]["status"] == "fresh_external_technical"
        assert rows[requirement_id]["level2_eligible"] is False
    assert rows["negative.mechanism"]["status"] == "missing"
    assert matrix["supplemental_receipt_bindings"][0]["receipt_id"] == (
        "bounded_planar_scaling"
    )
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False


def test_signed_nonlinear_material_recovery_supplement_adds_six_exact_cases(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    operator_fixture._attach_nonlinear_material_recovery_supplement(
        attestation, bundle_root
    )

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )
    rows = {row["requirement_id"]: row for row in matrix["requirements"]}

    assert matrix["summary"]["fresh_external_technical_count"] == 15
    assert matrix["summary"]["missing_count"] == 10
    for requirement_id in (
        "geometric_nonlinear.p_delta",
        "geometric_nonlinear.snap_through",
        "material.steel_yield",
        "material.rc_fiber",
        "recovery.section",
        "recovery.fiber",
    ):
        assert rows[requirement_id]["status"] == "fresh_external_technical"
        assert rows[requirement_id]["level2_eligible"] is False
    assert rows["linear.portal"]["status"] == "missing"
    binding = matrix["supplemental_receipt_bindings"][0]
    assert binding["receipt_id"] == (
        "bounded_planar_nonlinear_material_recovery"
    )
    assert binding["case_ids"] == [
        "bounded_planar_fiber_recovery",
        "bounded_planar_p_delta",
        "bounded_planar_rc_fiber",
        "bounded_planar_section_recovery",
        "bounded_planar_snap_through",
        "bounded_planar_steel_yield",
    ]
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False


def test_legacy_four_dedicated_supplements_add_ten_rows_without_promotion(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    operator_fixture._attach_linear_supplement(attestation, bundle_root)
    operator_fixture._attach_modal_buckling_supplement(attestation, bundle_root)
    operator_fixture._attach_negative_supplement(attestation, bundle_root)
    operator_fixture._attach_scaling_supplement(attestation, bundle_root)

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )

    assert matrix["summary"]["fresh_current_source_technical_count"] == 19
    assert matrix["summary"]["fresh_external_technical_count"] == 18
    assert matrix["summary"]["fresh_independent_preflight_technical_count"] == 1
    assert matrix["summary"]["missing_count"] == 6
    assert [
        binding["receipt_id"] for binding in matrix["supplemental_receipt_bindings"]
    ] == [
        "bounded_planar_linear",
        "bounded_planar_modal_buckling",
        "bounded_planar_negative",
        "bounded_planar_scaling",
    ]
    assert all(
        row["independent_operator_attested"] is False
        and row["level2_eligible"] is False
        for row in matrix["requirements"]
    )
    assert matrix["claims"]["independent_operator_attested"] is False
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False


def test_all_five_dedicated_supplements_complete_technical_matrix_without_promotion(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    operator_fixture._attach_linear_supplement(attestation, bundle_root)
    operator_fixture._attach_modal_buckling_supplement(attestation, bundle_root)
    operator_fixture._attach_negative_supplement(attestation, bundle_root)
    operator_fixture._attach_scaling_supplement(attestation, bundle_root)
    operator_fixture._attach_nonlinear_material_recovery_supplement(
        attestation, bundle_root
    )

    matrix = builder.build_operator_attested_matrix(
        attestation,
        bundle_root=bundle_root,
        expected_source_commit_sha=attestation["source_commit_sha"],
        repo_root=ROOT,
    )

    assert matrix["summary"]["fresh_current_source_technical_count"] == 25
    assert matrix["summary"]["fresh_external_technical_count"] == 24
    assert matrix["summary"]["fresh_independent_preflight_technical_count"] == 1
    assert matrix["summary"]["technical_reference_present_count"] == 25
    assert matrix["summary"]["missing_count"] == 0
    assert [
        binding["receipt_id"] for binding in matrix["supplemental_receipt_bindings"]
    ] == [
        "bounded_planar_linear",
        "bounded_planar_modal_buckling",
        "bounded_planar_negative",
        "bounded_planar_scaling",
        "bounded_planar_nonlinear_material_recovery",
    ]
    assert matrix["claims"]["recommended_matrix_technical_coverage_complete"] is True
    assert matrix["claims"]["fresh_current_source_technical_matrix_complete"] is True
    assert matrix["claims"]["fresh_current_source_external_matrix_complete"] is True
    assert all(
        row["independent_operator_attested"] is False
        and row["level2_eligible"] is False
        for row in matrix["requirements"]
    )
    assert matrix["claims"]["independent_operator_attested"] is False
    assert matrix["claims"]["bounded_planar_profile_level_2"] is False


def test_reused_execution_or_signature_tamper_fails_closed(tmp_path: Path) -> None:
    reused, reused_root = operator_fixture._build_submission(
        tmp_path / "reused", fresh=False
    )
    with pytest.raises(
        builder.OperatorMatrixBuildError,
        match="operator_matrix_attestation_invalid:operator_attestation_fresh_external_runtime_required",
    ):
        builder.build_operator_attested_matrix(
            reused,
            bundle_root=reused_root,
            expected_source_commit_sha=reused["source_commit_sha"],
            repo_root=ROOT,
        )

    tampered, tampered_root = operator_fixture._build_submission(tmp_path / "tampered")
    signature_path = tampered_root / tampered["signature"]["signature_path"]
    signature_path.write_bytes(signature_path.read_bytes() + b"tamper")
    with pytest.raises(
        builder.OperatorMatrixBuildError,
        match="operator_matrix_attestation_invalid:operator_attestation_signature_artifact_hash_mismatch",
    ):
        builder.build_operator_attested_matrix(
            tampered,
            bundle_root=tampered_root,
            expected_source_commit_sha=tampered["source_commit_sha"],
            repo_root=ROOT,
        )


def test_cli_writes_source_bound_nonpromoting_matrix(tmp_path: Path) -> None:
    attestation, bundle_root = operator_fixture._build_submission(tmp_path / "bundle")
    attestation_path = bundle_root / "operator-attestation.json"
    out = tmp_path / "operator-matrix.json"
    attestation_path.write_text(
        json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--attestation",
            str(attestation_path),
            "--bundle-root",
            str(bundle_root),
            "--expected-source-commit",
            attestation["source_commit_sha"],
            "--out",
            str(out),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["fresh_external_technical_count"] == 9
    assert payload["operator_intake_binding"]["status"] == "available"
    assert payload["claims"]["bounded_planar_profile_level_2"] is False


def test_forged_available_operator_binding_is_rejected_by_schema() -> None:
    matrix = builder.matrix_builder.build_bounded_planar_external_vv_matrix(
        repo_root=ROOT
    )
    forged = deepcopy(matrix)
    forged["operator_intake_binding"] = {
        "status": "available",
        "attestation_id": "forged",
        "attestation_sha256": "sha256:" + "0" * 64,
        "source_commit_sha": forged["source_commit_sha"],
        "signed_payload_sha256": "sha256:" + "0" * 64,
        "public_key_sha256": "sha256:" + "0" * 64,
        "signature_sha256": "sha256:" + "0" * 64,
        "intake_contract_pass": True,
        "fresh_external_runtime_execution": True,
        "cryptographic_signature_verified": False,
        "operator_independence_declared": True,
        "operator_identity_credentials_verified": False,
        "verification_level_2": False,
    }
    forged["artifact_hash"] = builder.matrix_builder._artifact_hash(forged)

    with pytest.raises(
        builder.matrix_builder.BoundedPlanarVVMatrixError,
        match="matrix_status_schema_validation_failed",
    ):
        builder.matrix_builder._validate_status(forged, ROOT)
