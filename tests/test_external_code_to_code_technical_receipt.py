"""Tests for the non-promoting external code-to-code execution receipt."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_external_code_to_code_technical_receipt.py"
RECEIPT = (
    ROOT
    / "implementation/phase1/release_evidence/productization/"
    "external_code_to_code_technical_execution_receipt.json"
)
SPEC = importlib.util.spec_from_file_location(
    "run_external_code_to_code_technical_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _stored_receipt() -> dict[str, object]:
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_stored_receipt_validates_and_records_actual_technical_execution() -> None:
    payload = _stored_receipt()
    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    module.validate_external_code_to_code_technical_receipt(
        payload,
        repo_root=ROOT,
        require_current_sources=True,
    )

    assert payload["status"] == "partial"
    assert payload["technical_contract_pass"] is True
    assert len(payload["external_assets"]) == 5
    assert all(not row["bundled_in_repository"] for row in payload["external_assets"])
    assert len(payload["comparisons"]) == 12
    source_checksums = payload["internal_source"]["input_checksums"]
    assert "src/structural_analysis/solvers/equation_scaling_6dof.py" in (
        source_checksums
    )
    assert "scripts/source_bound_python_inventory.py" in source_checksums
    assert "src/structural_analysis/assembly/linear_static.py" in source_checksums
    assert "src/structural_analysis/model_ir/validation.py" in source_checksums
    assert "tests/test_equation_scaling_6dof.py" in source_checksums
    assert (
        "src/structural_analysis/assembly/"
        "stateful_corotational_frame3d_sparse.py"
    ) in source_checksums
    assert "src/structural_analysis/api/frame3d_direct_control.py" in source_checksums
    assert (
        "src/structural_analysis/schemas/"
        "bounded_frame3d_direct_control_result_v2.schema.json"
        in source_checksums
    )
    assert (
        "src/structural_analysis/schemas/"
        "bounded_frame3d_direct_control_checkpoint_v2.schema.json"
        in source_checksums
    )
    assert (
        "src/structural_analysis/schemas/"
        "stateful_corotational_frame3d_displacement_control_resume_binding_v2.schema.json"
        in source_checksums
    )
    assert (
        "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"
        in source_checksums
    )
    assert (
        "examples/bounded_frame3d_direct_control_torsion.model-ir.v2.json"
        in source_checksums
    )
    assert (
        "examples/bounded_frame3d_direct_control_ry_bending.model-ir.v2.json"
        in source_checksums
    )
    assert (
        "examples/bounded_frame3d_direct_control_rz_bending.model-ir.v2.json"
        in source_checksums
    )
    assert all(row["contract_pass"] for row in payload["comparisons"])
    assert all(
        metric["contract_pass"]
        for case in payload["comparisons"]
        for metric in case["metrics"]
    )
    assert all(
        runtime["actual_external_execution"] and runtime["version_verified"]
        for runtime in payload["runtimes"].values()
    )
    replay = payload["replay_provenance"]
    assert replay["current_product_replay_pass"] is True
    fresh_execution = (
        replay["external_runtime_executed_in_this_generation"] is True
        and replay["external_execution_reused"] is False
    )
    reused_execution = (
        replay["external_runtime_executed_in_this_generation"] is False
        and replay["external_execution_reused"] is True
        and isinstance(replay["reuse_reason"], str)
        and bool(replay["reuse_reason"].strip())
    )
    assert fresh_execution or reused_execution
    assert (
        module.REUSED_EXECUTION_BLOCKER in payload["blockers_remaining"]
    ) is reused_execution
    portal = payload["comparisons"][2]
    assert portal["case_id"] == "public_corotational_portal_load_path"
    assert len(portal["metrics"]) == 12
    assert payload["claims"][
        "public_corotational_portal_technical_comparison"
    ] is True
    member_feature = payload["comparisons"][3]
    assert member_feature["case_id"] == (
        "bounded_planar_member_feature_load_path"
    )
    assert len(member_feature["metrics"]) == 8
    assert payload["claims"][
        "bounded_planar_member_feature_technical_comparison"
    ] is True
    assert {
        row["quantity"] for row in member_feature["metrics"]
    } == {
        "node_N2_UX_m",
        "node_N2_UY_m",
        "support_N1_UX_N",
        "support_N1_UY_N",
        "support_N1_RZ_N_m",
        "support_N2_RZ_N_m",
        "member_E1_end_i_MZ_N_m",
        "member_E1_end_j_MZ_N_m",
    }
    settlement = payload["comparisons"][4]
    assert settlement["case_id"] == (
        "bounded_planar_prescribed_settlement_load_path"
    )
    assert len(settlement["metrics"]) == 9
    assert payload["claims"][
        "bounded_planar_prescribed_settlement_technical_comparison"
    ] is True
    assert {
        row["quantity"] for row in settlement["metrics"]
    } == {
        "node_N2_UX_m",
        "node_N2_UY_m",
        "support_N1_UX_N",
        "support_N1_UY_N",
        "support_N1_RZ_N_m",
        "support_N2_UY_N",
        "support_N2_RZ_N_m",
        "member_E1_end_i_MZ_N_m",
        "member_E1_end_j_MZ_N_m",
    }
    spatial_frame3d = payload["comparisons"][5]
    assert spatial_frame3d["case_id"] == (
        "spatial_frame3d_cantilever_combined_load"
    )
    assert len(spatial_frame3d["metrics"]) == 10
    assert payload["claims"][
        "opensees_frame3d_technical_comparison"
    ] is True
    assert {
        metric["relative_tolerance"] for metric in spatial_frame3d["metrics"]
    } == {module.SPATIAL_FRAME3D_RELATIVE_TOLERANCE}
    assert {
        metric["absolute_tolerance"] for metric in spatial_frame3d["metrics"]
    } == {module.SPATIAL_FRAME3D_ABSOLUTE_TOLERANCE}
    direct_control = payload["comparisons"][6]
    assert direct_control["case_id"] == "frame3d_direct_control_axial_yield"
    assert len(direct_control["metrics"]) == 8
    assert payload["claims"][
        "opensees_frame3d_direct_control_material_yield_technical_comparison"
    ] is True
    assert [row["quantity"] for row in direct_control["metrics"]] == [
        quantity for quantity, _field in module.FRAME3D_DIRECT_CONTROL_METRIC_SPECS
    ]
    assert {
        metric["relative_tolerance"] for metric in direct_control["metrics"]
    } == {module.FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE}
    assert {
        metric["absolute_tolerance"] for metric in direct_control["metrics"]
    } == {module.FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE}
    plastic_strain = next(
        row for row in direct_control["metrics"] if row["quantity"] == "plastic_strain"
    )
    assert plastic_strain["product_value"] > 0.0
    assert plastic_strain["reference_value"] > 0.0
    cyclic_direct_control = payload["comparisons"][7]
    assert cyclic_direct_control["case_id"] == (
        "frame3d_direct_control_cyclic_axial_reversal"
    )
    assert cyclic_direct_control["analysis_type"] == (
        "corotational_frame3d_cyclic_direct_displacement_control_axial_reversal"
    )
    assert len(cyclic_direct_control["metrics"]) == 19
    assert payload["claims"][
        "opensees_frame3d_cyclic_direct_control_technical_comparison"
    ] is True
    assert [row["quantity"] for row in cyclic_direct_control["metrics"]] == [
        quantity
        for quantity, _target_index, _field in (
            module.FRAME3D_CYCLIC_DIRECT_CONTROL_METRIC_SPECS
        )
    ]
    assert {
        metric["relative_tolerance"]
        for metric in cyclic_direct_control["metrics"]
    } == {module.FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE}
    assert {
        metric["absolute_tolerance"]
        for metric in cyclic_direct_control["metrics"]
    } == {module.FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE}
    cyclic_by_quantity = {
        row["quantity"]: row for row in cyclic_direct_control["metrics"]
    }
    for target_index, target in enumerate(
        module.FRAME3D_CYCLIC_DIRECT_CONTROL_TARGETS_M,
        start=1,
    ):
        assert cyclic_by_quantity[
            f"target_{target_index}_tip_N2_UX_m"
        ]["reference_value"] == pytest.approx(target)
    assert cyclic_by_quantity["final_plastic_strain"][
        "reference_value"
    ] == pytest.approx(-0.0002718623004345328)
    assert cyclic_by_quantity["final_backstress_mpa"][
        "reference_value"
    ] == pytest.approx(-0.2718623004345328)
    assert cyclic_by_quantity["final_accumulated_plastic_strain"][
        "reference_value"
    ] == pytest.approx(0.00464432238734123)
    assert cyclic_by_quantity[
        "final_dissipated_energy_density_mj_per_m3"
    ]["reference_value"] == pytest.approx(1.1610805968353075)
    torsion_direct_control = payload["comparisons"][8]
    assert torsion_direct_control["case_id"] == (
        "frame3d_direct_control_torsion"
    )
    assert len(torsion_direct_control["metrics"]) == 3
    assert payload["claims"][
        "opensees_frame3d_rotational_direct_control_technical_comparison"
    ] is True
    assert [row["quantity"] for row in torsion_direct_control["metrics"]] == [
        quantity
        for quantity, _field in (
            module.FRAME3D_DIRECT_CONTROL_TORSION_METRIC_SPECS
        )
    ]
    assert {
        metric["relative_tolerance"]
        for metric in torsion_direct_control["metrics"]
    } == {module.FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE}
    assert {
        metric["absolute_tolerance"]
        for metric in torsion_direct_control["metrics"]
    } == {module.FRAME3D_DIRECT_CONTROL_ABSOLUTE_TOLERANCE}
    bending_direct_control = payload["comparisons"][9]
    assert bending_direct_control["case_id"] == (
        "frame3d_direct_control_bending_rotations"
    )
    assert len(bending_direct_control["metrics"]) == 6
    assert payload["claims"][
        "opensees_frame3d_bending_rotational_direct_control_technical_comparison"
    ] is True
    assert [row["quantity"] for row in bending_direct_control["metrics"]] == [
        quantity
        for quantity, _control_dof, _field in (
            module.FRAME3D_DIRECT_CONTROL_BENDING_METRIC_SPECS
        )
    ]
    assert {
        metric["relative_tolerance"]
        for metric in bending_direct_control["metrics"]
    } == {module.FRAME3D_DIRECT_CONTROL_RELATIVE_TOLERANCE}
    spatial_truss = payload["comparisons"][11]
    assert spatial_truss["case_id"] == (
        "tetrahedral_spatial_truss_combined_load"
    )
    assert len(spatial_truss["metrics"]) == 12
    assert payload["claims"][
        "calculix_spatial_truss_technical_comparison"
    ] is True
    assert payload["claims"]["second_solver_technical_comparison"] is True


def test_debian_metadata_parser_accepts_labeled_field_output(monkeypatch) -> None:
    completed = SimpleNamespace(
        returncode=0,
        stdout="Package: calculix-ccx\nVersion: 2.17-3\nArchitecture: amd64\n",
    )
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: completed)

    assert module._deb_metadata(Path("runtime.deb")) == (
        "calculix-ccx",
        "2.17-3",
        "amd64",
    )


def test_receipt_does_not_promote_legal_hierarchy_or_release_claims() -> None:
    payload = _stored_receipt()

    assert payload["verification_hierarchy_operator_manifest_attached"] is False
    assert payload["verification_hierarchy_credit"] is False
    assert payload["claims"]["product_legal_license_approval"] is False
    assert payload["claims"]["external_runtime_redistribution_approval"] is False
    assert payload["claims"]["verification_level_2"] is False
    assert payload["claims"]["commercial_equivalence"] is False
    assert payload["claims"]["release_readiness"] is False
    assert (
        "public_corotational_material_nonlinear_family_breadth_missing"
        in payload["blockers_remaining"]
    )
    assert len(payload["blockers_remaining"]) >= 8
    assert "does not achieve Verification Level 2" in payload["claim_boundary"]


def test_product_replay_migrates_only_the_known_prior_claim_boundary() -> None:
    stored = _stored_receipt()
    refreshed = module.refresh_external_code_to_code_product_replay(
        stored,
        repo_root=ROOT,
        reuse_reason="current-source settlement migration test",
    )

    assert refreshed["claim_boundary"] == module.CLAIM_BOUNDARY
    assert refreshed["replay_provenance"]["external_execution_reused"] is True
    settlement_attached = any(
        row["case_id"] == "bounded_planar_prescribed_settlement_load_path"
        for row in refreshed["comparisons"]
    )
    assert refreshed["claims"][
        "bounded_planar_prescribed_settlement_technical_comparison"
    ] is settlement_attached
    assert (
        module.SETTLEMENT_EXTERNAL_RERUN_BLOCKER
        in refreshed["blockers_remaining"]
    ) is (not settlement_attached)
    cyclic_direct_control_attached = any(
        row["case_id"] == "frame3d_direct_control_cyclic_axial_reversal"
        for row in refreshed["comparisons"]
    )
    assert refreshed["claims"][
        "opensees_frame3d_cyclic_direct_control_technical_comparison"
    ] is cyclic_direct_control_attached
    assert (
        module.FRAME3D_DIRECT_CONTROL_CYCLIC_EXTERNAL_RERUN_BLOCKER
        in refreshed["blockers_remaining"]
    ) is (not cyclic_direct_control_attached)

    forged = deepcopy(stored)
    forged["claim_boundary"] = (
        "Arbitrary migration text cannot be accepted even when it is long enough "
        "to satisfy the structural schema because it is not one of the exact known "
        "historical claim-boundary hashes approved for migration. " * 4
    )
    forged["artifact_hash"] = module._artifact_hash(forged)
    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_claim_boundary_invalid",
    ):
        module.refresh_external_code_to_code_product_replay(
            forged,
            repo_root=ROOT,
            reuse_reason="must fail",
        )


def test_validation_rejects_rehashed_comparison_tampering() -> None:
    tampered = deepcopy(_stored_receipt())
    tampered["comparisons"][0]["metrics"][0]["product_value"] += 0.25
    tampered["artifact_hash"] = module._artifact_hash(tampered)

    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_comparison_error_invalid",
    ):
        module.validate_external_code_to_code_technical_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_validation_rejects_frame3d_tolerance_tampering() -> None:
    tampered = deepcopy(_stored_receipt())
    frame3d = next(
        row
        for row in tampered["comparisons"]
        if row["case_id"] == "spatial_frame3d_cantilever_combined_load"
    )
    frame3d["metrics"][0]["relative_tolerance"] = 1.0e-10
    tampered["artifact_hash"] = module._artifact_hash(tampered)
    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_comparison_tolerance_invalid",
    ):
        module.validate_external_code_to_code_technical_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )

    tampered_cyclic = deepcopy(_stored_receipt())
    cyclic_direct_control = next(
        row
        for row in tampered_cyclic["comparisons"]
        if row["case_id"] == "frame3d_direct_control_cyclic_axial_reversal"
    )
    cyclic_direct_control["metrics"][0]["relative_tolerance"] = 1.0e-4
    tampered_cyclic["artifact_hash"] = module._artifact_hash(tampered_cyclic)
    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_comparison_tolerance_invalid",
    ):
        module.validate_external_code_to_code_technical_receipt(
            tampered_cyclic,
            repo_root=ROOT,
            require_current_sources=False,
        )

    tampered_bending = deepcopy(_stored_receipt())
    bending_direct_control = next(
        row
        for row in tampered_bending["comparisons"]
        if row["case_id"] == "frame3d_direct_control_bending_rotations"
    )
    bending_direct_control["metrics"][0]["relative_tolerance"] = 1.0e-4
    tampered_bending["artifact_hash"] = module._artifact_hash(
        tampered_bending
    )
    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_comparison_tolerance_invalid",
    ):
        module.validate_external_code_to_code_technical_receipt(
            tampered_bending,
            repo_root=ROOT,
            require_current_sources=False,
        )

    tampered_torsion = deepcopy(_stored_receipt())
    torsion_direct_control = next(
        row
        for row in tampered_torsion["comparisons"]
        if row["case_id"] == "frame3d_direct_control_torsion"
    )
    torsion_direct_control["metrics"][0]["relative_tolerance"] = 1.0e-4
    tampered_torsion["artifact_hash"] = module._artifact_hash(
        tampered_torsion
    )
    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_comparison_tolerance_invalid",
    ):
        module.validate_external_code_to_code_technical_receipt(
            tampered_torsion,
            repo_root=ROOT,
            require_current_sources=False,
        )

    tampered_direct = deepcopy(_stored_receipt())
    direct_control = next(
        row
        for row in tampered_direct["comparisons"]
        if row["case_id"] == "frame3d_direct_control_axial_yield"
    )
    direct_control["metrics"][0]["relative_tolerance"] = 1.0e-4
    tampered_direct["artifact_hash"] = module._artifact_hash(tampered_direct)
    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_comparison_tolerance_invalid",
    ):
        module.validate_external_code_to_code_technical_receipt(
            tampered_direct,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_validation_rejects_rehashed_claim_promotion() -> None:
    tampered = deepcopy(_stored_receipt())
    tampered["claims"]["verification_level_2"] = True
    tampered["artifact_hash"] = module._artifact_hash(tampered)

    with pytest.raises(module.ExternalCodeToCodeReceiptError, match="schema_invalid"):
        module.validate_external_code_to_code_technical_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_product_replay_comparison_allows_only_bounded_runtime_drift() -> None:
    stored = _stored_receipt()["comparisons"]
    current = deepcopy(stored)
    metric = current[0]["metrics"][0]
    metric.update(
        module._comparison(
            metric["quantity"],
            metric["product_value"] + 1.0e-13,
            metric["reference_value"],
        )
    )
    assert module._product_replay_values_match(stored, current)

    metric.update(
        module._comparison(
            metric["quantity"],
            metric["product_value"] + 1.0e-6,
            metric["reference_value"],
        )
    )
    assert not module._product_replay_values_match(stored, current)


def test_product_replay_refresh_does_not_invent_legacy_execution_source() -> None:
    stored = _stored_receipt()
    refreshed = module.refresh_external_code_to_code_product_replay(
        stored,
        repo_root=ROOT,
        reuse_reason="test_current_product_replay",
    )

    assert refreshed["status"] == "partial"
    assert refreshed["technical_contract_pass"] is True
    assert refreshed["replay_provenance"][
        "external_runtime_executed_in_this_generation"
    ] is False
    assert refreshed["replay_provenance"]["external_execution_reused"] is True
    assert refreshed["replay_provenance"][
        "external_execution_source_commit_sha"
    ] is None
    assert refreshed["replay_provenance"]["current_product_replay_pass"] is True
    assert refreshed["replay_provenance"]["reuse_reason"] == (
        "test_current_product_replay"
    )
    assert refreshed["blockers_remaining"][-1] == (
        module.REUSED_EXECUTION_BLOCKER
    )


def test_fresh_receipt_without_execution_source_fails_closed() -> None:
    tampered = deepcopy(_stored_receipt())
    replay = tampered["replay_provenance"]
    replay["external_runtime_executed_in_this_generation"] = True
    replay["external_execution_reused"] = False
    replay["reuse_reason"] = None
    replay.pop("external_execution_source_commit_sha", None)
    tampered["artifact_hash"] = module._artifact_hash(tampered)

    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_replay_execution_source_invalid",
    ):
        module.validate_external_code_to_code_technical_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_cli_offline_check_validates_stored_receipt() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "external_code_to_code_technical_receipt_consistent" in completed.stdout


def test_cli_refresh_can_use_a_validated_current_reference_receipt(
    tmp_path: Path,
) -> None:
    out = tmp_path / "embedded-code-receipt.json"
    reference = (
        ROOT
        / "implementation/phase1/release_evidence/productization/"
        "external_code_to_code_technical_execution_receipt.json"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--refresh-product-replay",
            "--reuse-reference-receipt",
            str(reference),
            "--reuse-reason",
            "test validated current reference synchronization",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["replay_provenance"]["external_execution_reused"] is True
    assert [row["case_id"] for row in payload["comparisons"]] == [
        row["case_id"] for row in _stored_receipt()["comparisons"]
    ]
