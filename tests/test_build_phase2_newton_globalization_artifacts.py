from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase2_newton_globalization_artifacts.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_phase2_newton_globalization_artifacts",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ZeroResidualSingularScalar:
    case_id = "phase2_zero_residual_singular_scalar"
    external_force_kn = 0.0
    initial_displacement_m = 0.0

    def internal_force(self, displacement_m: float) -> float:
        return 0.0

    def tangent_stiffness(self, displacement_m: float) -> float:
        return 0.0

    def residual(self, displacement_m: float) -> float:
        return 0.0

    def reference_force_scale(self) -> float:
        return 1.0


class ZeroResidualSingularVector:
    case_id = "phase2_zero_residual_singular_vector"

    def reference_force_scale(self) -> float:
        return 1.0

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.array([0.0])

    def assemble(self, free_displacements_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return np.array([0.0]), np.array([[0.0]])


def test_phase2_newton_globalization_builds_honest_seed_artifacts() -> None:
    artifacts = module.build_newton_globalization_artifacts(repo_root=REPO_ROOT)
    summary = artifacts["summary"]
    result = artifacts["result"]
    metrics = result["metrics"]
    verification = result["verification"]

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["g1_closure_claim"] is False
    assert summary["nonlinear_newton_closure_claim"] is False
    assert summary["residual_contract"] == "F_internal_minus_F_external"
    assert summary["residual_gate_passed"] is True
    assert summary["increment_gate_passed"] is True
    assert summary["line_search_used"] is True
    assert summary["line_search_step_count"] >= 1
    assert summary["tangent_gate_passed"] is True
    assert summary["displacement_gate_passed"] is True
    assert summary["regularization_used"] is False
    assert summary["fallback_used"] is False
    assert summary["unsupported_backend_guard_passed"] is True
    assert summary["singular_tangent_guard_passed"] is True
    assert summary["unsupported_backend_guard"] == {
        "configured_matrix_backend": "scipy_sparse_spsolve_cpu",
        "status": "blocked",
        "contract_pass": False,
        "detail": "unsupported_matrix_backend",
        "regularization_used": False,
        "fallback_used": False,
        "unsupported_feature_kinds": ["newton_scalar_reference_blocked"],
    }
    assert summary["singular_tangent_guard"] == {
        "scalar": {
            "status": "blocked",
            "contract_pass": False,
            "detail": "singular_tangent_stiffness_at_residual_gate",
            "regularization_used": False,
            "fallback_used": False,
            "unsupported_feature_kinds": ["newton_scalar_reference_blocked"],
        },
        "vector": {
            "status": "blocked",
            "contract_pass": False,
            "detail": "singular_tangent_stiffness_at_residual_gate",
            "regularization_used": False,
            "fallback_used": False,
            "unsupported_feature_kinds": ["newton_vector_reference_blocked"],
        },
    }
    assert summary["sparse_backend_used"] is False
    assert summary["matrix_backend"] == "numpy_linalg_solve_scalar"
    assert summary["blockers_remaining"] == [
        "full_mesh_full_load_nonlinear_equilibrium_not_closed",
        "frame_shell_material_coupling_not_closed",
        "mesh_load_step_nonlinear_convergence_suite_not_closed",
        "sparse_matrix_backend_not_closed",
        "production_rocm_hip_parity_not_closed",
        "general_newton_jacobian_assembly_not_closed",
    ]

    assert result["status"] == "ready"
    assert result["contract_pass"] is True
    assert result["g1_closure_claim"] is False
    assert result["nonlinear_newton_closure_claim"] is False
    assert result["residual_formula"] == "F_internal_minus_F_external"
    assert result["globalization"] == "backtracking_line_search"
    assert result["regularization_used"] is False
    assert result["fallback_used"] is False
    assert metrics["residual_gate_passed"] is True
    assert metrics["increment_gate_passed"] is True
    assert metrics["line_search_used"] is True
    assert metrics["regularization_used"] is False
    assert metrics["fallback_used"] is False
    assert metrics["relative_residual"] <= 1.0e-10
    assert metrics["final_increment_abs_m"] <= 1.0e-12
    assert verification["displacement_gate_passed"] is True
    assert verification["tangent_gate_passed"] is True
    assert verification["displacement_abs_error_m"] <= 1.0e-10

    assert len(result["convergence_history"]) >= 2
    assert result["convergence_history"][-2]["residual_gate_passed"] is True
    assert result["convergence_history"][-2]["increment_gate_passed"] is False
    assert result["convergence_history"][-1]["residual_gate_passed"] is True
    assert result["convergence_history"][-1]["increment_gate_passed"] is True
    assert len(result["line_search_history"]) >= 1
    first_line_search = result["line_search_history"][0]
    assert first_line_search["attempt_count"] >= 1
    assert len(first_line_search["attempts"]) >= 1
    assert any(not attempt["accepted"] for attempt in first_line_search["attempts"])
    assert any(attempt["accepted"] for attempt in first_line_search["attempts"])
    assert result["convergence_history"][-1]["residual_gate_passed"] is True


def test_phase2_newton_globalization_check_detects_stale_outputs(tmp_path: Path) -> None:
    ok, message = module.check_newton_globalization_artifacts(
        repo_root=REPO_ROOT,
        result_out=tmp_path / "missing_result.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_newton_globalization_missing:")


def test_phase2_newton_requires_residual_and_increment_gates() -> None:
    problem = module.ScalarNonlinearAxialReference()
    config = module.NewtonRaphsonConfig(max_iterations=5)

    solution = module.newton_raphson_scalar(problem, config=config)

    assert solution.status == "blocked"
    assert solution.metrics["contract_pass"] is False
    assert solution.metrics["detail"] == "max_iterations_exceeded"
    assert solution.convergence_history[-1]["residual_gate_passed"] is True
    assert solution.convergence_history[-1]["increment_gate_passed"] is False


def test_phase2_scalar_newton_blocks_unsupported_matrix_backend() -> None:
    problem = module.ScalarNonlinearAxialReference()
    config = module.NewtonRaphsonConfig(matrix_backend="scipy_sparse_spsolve_cpu")

    solution = module.newton_raphson_scalar(problem, config=config)

    assert solution.status == "blocked"
    assert solution.metrics["contract_pass"] is False
    assert solution.metrics["detail"] == "unsupported_matrix_backend"
    assert solution.metrics["matrix_backend"] == "scipy_sparse_spsolve_cpu"
    assert solution.metrics["regularization_used"] is False
    assert solution.metrics["fallback_used"] is False
    assert solution.convergence_history == []
    assert solution.unsupported_features == [
        {
            "kind": "newton_scalar_reference_blocked",
            "detail": "unsupported_matrix_backend",
            "guard_outcome": "blocked",
            "regularization_used": False,
            "fallback_used": False,
        }
    ]


def test_phase2_scalar_newton_blocks_singular_tangent_even_when_residual_is_zero() -> None:
    solution = module.newton_raphson_scalar(
        ZeroResidualSingularScalar(),
        config=module.NewtonRaphsonConfig(),
    )

    assert solution.status == "blocked"
    assert solution.metrics["contract_pass"] is False
    assert solution.metrics["detail"] == "singular_tangent_stiffness_at_residual_gate"
    assert solution.metrics["regularization_used"] is False
    assert solution.metrics["fallback_used"] is False
    assert solution.convergence_history == []
    assert solution.unsupported_features == [
        {
            "kind": "newton_scalar_reference_blocked",
            "detail": "singular_tangent_stiffness_at_residual_gate",
            "guard_outcome": "blocked",
            "regularization_used": False,
            "fallback_used": False,
        }
    ]


def test_phase2_vector_newton_blocks_singular_jacobian_even_when_residual_is_zero() -> None:
    solution = module.newton_raphson_vector(
        ZeroResidualSingularVector(),
        config=module.NewtonRaphsonConfig(),
    )

    assert solution.status == "blocked"
    assert solution.metrics["contract_pass"] is False
    assert solution.metrics["detail"] == "singular_tangent_stiffness_at_residual_gate"
    assert solution.metrics["regularization_used"] is False
    assert solution.metrics["fallback_used"] is False
    assert solution.convergence_history == []
    assert solution.unsupported_features == [
        {
            "kind": "newton_vector_reference_blocked",
            "detail": "singular_tangent_stiffness_at_residual_gate",
            "guard_outcome": "blocked",
            "regularization_used": False,
            "fallback_used": False,
        }
    ]
