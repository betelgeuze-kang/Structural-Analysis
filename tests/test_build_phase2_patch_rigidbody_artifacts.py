from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_phase2_patch_rigidbody_artifacts.py"

SPEC = importlib.util.spec_from_file_location("build_phase2_patch_rigidbody_artifacts", SCRIPT_PATH)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
assert SPEC.loader is not None
SPEC.loader.exec_module(module)

from structural_analysis.assembly.patch_static import AxialPatchRigidBodyProblem  # noqa: E402


def test_phase2_patch_rigidbody_builds_honest_seed_artifacts() -> None:
    artifacts = module.build_phase2_patch_rigidbody_artifacts(repo_root=REPO_ROOT)
    result = artifacts["result"]
    summary = artifacts["summary"]
    patch = result["patch_test"]
    rigid = result["rigid_body_test"]

    assert result["status"] == "ready"
    assert result["contract_pass"] is True
    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["patch_test_passed"] is True
    assert summary["rigid_body_test_passed"] is True
    assert result["g1_closure_claim"] is False
    assert result["patch_rigidbody_closure_claim"] is False
    assert result["full_mesh_closure_claim"] is False
    assert summary["g1_closure_claim"] is False
    assert summary["patch_rigidbody_closure_claim"] is False
    assert summary["full_mesh_closure_claim"] is False
    assert summary["blockers_remaining"] == [
        "general_frame_shell_patch_tests_not_closed",
        "full_mesh_full_load_nonlinear_equilibrium_not_closed",
        "general_mesh_load_step_nonlinear_convergence_suite_not_closed",
        "production_sparse_matrix_backend_not_closed",
        "production_rocm_hip_parity_not_closed",
    ]

    checksums = summary["input_checksums"]
    assert "src/structural_analysis/assembly/patch_static.py" in checksums
    assert "scripts/build_phase2_patch_rigidbody_artifacts.py" in checksums
    assert "tests/test_build_phase2_patch_rigidbody_artifacts.py" in checksums

    assert patch["truth_class"] == "analytic_component_patch_truth"
    assert patch["element_count"] == 2
    assert patch["residual_formula"] == "F_internal_minus_F_external"
    assert patch["max_total_residual_kn"] <= module.PATCH_TOLERANCE
    assert patch["max_interior_residual_kn"] <= module.PATCH_TOLERANCE
    assert patch["strain_spread"] <= module.PATCH_TOLERANCE
    assert patch["element_force_inf_norm_error_kn"] <= module.PATCH_TOLERANCE
    assert patch["stiffness_work_balance_error_kn_m"] <= module.PATCH_TOLERANCE
    assert patch["regularization_used"] is False
    assert patch["fallback_used"] is False

    assert rigid["pass"] is True
    assert rigid["element_strain_inf_norm"] <= module.RIGID_BODY_TOLERANCE
    assert rigid["element_force_inf_norm_kn"] <= module.RIGID_BODY_TOLERANCE
    assert rigid["dense_stiffness_times_translation_inf_norm_kn"] <= module.RIGID_BODY_TOLERANCE
    assert rigid["sparse_stiffness_times_translation_inf_norm_kn"] <= module.RIGID_BODY_TOLERANCE
    assert rigid["stiffness_storage"] == "dense_numpy_and_scipy_sparse_csr"
    assert "does not close general frame/shell patch tests" in result["claim_boundary"]


def test_phase2_patch_rigidbody_check_detects_missing_outputs(tmp_path: Path) -> None:
    ok, message = module.check_phase2_patch_rigidbody_artifacts(
        repo_root=REPO_ROOT,
        result_out=tmp_path / "missing_result.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_patch_rigidbody_missing:")


def test_phase2_patch_rigidbody_assembly_rejects_invalid_coordinates() -> None:
    problem = module.default_axial_patch_rigidbody_problem()
    invalid = AxialPatchRigidBodyProblem(
        case_id=problem.case_id,
        node_coordinates_m=(0.0, 1.0, 1.0),
        elastic_modulus_kn_per_m2=problem.elastic_modulus_kn_per_m2,
        area_m2=problem.area_m2,
        prescribed_strain=problem.prescribed_strain,
        rigid_translation_m=problem.rigid_translation_m,
    )

    try:
        module.assemble_axial_patch_state(invalid)
    except ValueError as exc:
        assert "strictly increasing" in str(exc)
    else:
        raise AssertionError("Expected invalid patch coordinates to be rejected.")
