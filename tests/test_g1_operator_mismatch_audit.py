"""Hermetic tests for the non-promoting G1 global operator mismatch audit.

These tests build synthetic probe/tangent payloads so they do NOT depend on
untracked ``*.local.json`` evidence or on the long-running solver probe.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


PHASE1 = Path(__file__).resolve().parents[1] / "implementation" / "phase1"
MODULE_PATH = PHASE1 / "run_g1_global_operator_mismatch_audit.py"


def _load_module():
    if str(PHASE1) not in sys.path:
        sys.path.insert(0, str(PHASE1))
    spec = importlib.util.spec_from_file_location(
        "run_g1_global_operator_mismatch_audit", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_probe() -> dict:
    """A probe payload that reproduces the recorded mismatch signature."""
    return {
        "source_commit_sha": "deadbeef",
        "status": "partial",
        "checkpoint": {"load_scale": 0.656},
        "base_direct_residual": {
            "direct_residual_inf_n": 1.3092276661494922,
            "linear_correction_regularization": 515.4025311317521,
            "regularized_residual_inf_n": 12052.548204805724,
        },
        "newton_direction": {
            "regularization": 515.4025311317521,
            "linearized_tangent": "current service-material frame tangent plus geometric delta",
        },
        "residual_contract": {
            "definition": "R(u, lambda) = F_int(u) - lambda * F_ext",
            "physical_internal_force_model": "corotational_force_based_6dof_plus_shell",
            "direct_residual_uses_solver_regularization": False,
            "regularization_used_only_for_linear_correction_direction": True,
            "service_material_tangent_used_for_newton_direction_only": True,
            "frame_geometric_equilibrium_included": True,
            "quasi_tangent_residual_inf_n": 12052.65528749118,
        },
        "mesh_fingerprint": {
            "frame_geometric_delta_stiffness_nnz": 44913,
            "frame_material_meta": {
                "min_solver_tangent_ratio": 4.7619047619047615e-06,
                "tangent_reduction_element_count": 1763,
            },
            "service_material_meta": {
                "service_min_tangent_ratio": 0.09534355234715897,
                "service_mean_tangent_ratio": 0.936112317032684,
            },
            "service_shell_material_meta": {
                "nonlinear_tangent_surface_element_count": 0,
                "min_tangent_ratio": 0.9992733831574389,
                "mean_tangent_ratio": 0.999991442470334,
                "max_abs_strain": 2.555136149665333e-06,
                "state_tag_counts": {"concrete_compression_hardening": 4252},
            },
        },
        "trust_region_line_search": {
            "iterations": [
                {
                    "iteration": 1,
                    "start_direct_residual_inf_n": 1.3092276661494922,
                    "directional_residual_jacobian": {"jacobian_action_inf_n": 8268.459103885107},
                    "candidate_rows": [
                        {"alpha": 0.001, "direct_residual_inf_n": 8.230590455666515},
                        {"alpha": 0.0005, "direct_residual_inf_n": 4.0963615594346265},
                        {"alpha": 0.00025, "direct_residual_inf_n": 2.0292471629850297},
                        {"alpha": 0.000125, "direct_residual_inf_n": 1.3090640127442061},
                        {"alpha": 6.25e-05, "direct_residual_inf_n": 1.3091458394616293},
                    ],
                },
            ]
        },
    }


def _synthetic_tangent() -> dict:
    return {
        "status": "ready",
        "local_constitutive_tangent_fd_consistency": {
            "constitutive_tangent_fd_consistency_pass": True,
            "max_relative_error": 2.427464242549056e-11,
            "relative_error_tolerance": 1.0e-4,
            "bounded_solver_tangent_row_count": 3500,
            "bounded_solver_state_tag_counts": {
                "concrete_compression_softening": 2108,
                "steel_plastic_hardening": 1690,
            },
            "sample_worst_rows": [
                {
                    "state_tag": "concrete_compression_softening",
                    "constitutive_tangent_mpa": -100.0,
                    "solver_tangent_mpa": 420.0,
                },
                {
                    "state_tag": "steel_plastic_hardening",
                    "constitutive_tangent_mpa": 3000.0,
                    "solver_tangent_mpa": 3150.0,
                },
            ],
        },
    }


@pytest.fixture()
def written_inputs(tmp_path: Path):
    probe = tmp_path / "probe.local.json"
    tangent = tmp_path / "tangent.local.json"
    probe.write_text(json.dumps(_synthetic_probe()), encoding="utf-8")
    tangent.write_text(json.dumps(_synthetic_tangent()), encoding="utf-8")
    return probe, tangent


def test_audit_is_non_promoting(written_inputs, tmp_path):
    module = _load_module()
    probe, tangent = written_inputs
    out = tmp_path / "audit.local.json"
    payload = module.run_g1_global_operator_mismatch_audit(
        probe_json=probe, tangent_json=tangent, output_json=out
    )
    assert payload["is_audit_only"] is True
    assert payload["promotes_g1_closure"] is False
    assert "does NOT" in payload["claim_boundary"]
    assert out.is_file()


def test_termination_criteria_all_met(written_inputs, tmp_path):
    module = _load_module()
    probe, tangent = written_inputs
    payload = module.run_g1_global_operator_mismatch_audit(
        probe_json=probe, tangent_json=tangent, output_json=tmp_path / "a.json"
    )
    tc = payload["termination_criteria"]
    assert tc["normalization_factor_named"] is True
    assert tc["frame_geometric_scaling_differs_from_physical_residual_named"] is True
    assert tc["shell_material_tangent_elastic_passive_evidence_present"] is True
    assert tc["tiny_alpha_descent_only_reproduced"] is True
    assert payload["audit_complete"] is True


def test_lambda_is_named(written_inputs, tmp_path):
    module = _load_module()
    probe, tangent = written_inputs
    payload = module.run_g1_global_operator_mismatch_audit(
        probe_json=probe, tangent_json=tangent, output_json=tmp_path / "a.json"
    )
    op = payload["current_corrector_operator"]
    assert op["normalization_lambda"] == pytest.approx(515.4025311317521)
    assert op["normalization_lambda_named"] is True
    assert op["direct_residual_uses_solver_regularization"] is False


def test_shell_is_passive_not_stall_driver(written_inputs, tmp_path):
    module = _load_module()
    probe, tangent = written_inputs
    payload = module.run_g1_global_operator_mismatch_audit(
        probe_json=probe, tangent_json=tangent, output_json=tmp_path / "a.json"
    )
    shell = payload["shell_material_state"]
    assert shell["shell_material_tangent_elastic_passive_at_checkpoint"] is True
    assert shell["shell_material_tangent_is_stall_driver"] is False


def test_alpha_scan_tiny_descent_only(written_inputs, tmp_path):
    module = _load_module()
    probe, tangent = written_inputs
    payload = module.run_g1_global_operator_mismatch_audit(
        probe_json=probe, tangent_json=tangent, output_json=tmp_path / "a.json"
    )
    scan = payload["alpha_scan_descent_audit"]
    assert scan["tiny_alpha_descent_only_reproduced"] is True
    it0 = scan["iterations"][0]
    # only alpha <= 1.25e-4 is a descent direction; larger alphas increase residual
    assert it0["largest_descent_alpha"] == pytest.approx(0.000125)
    assert it0["smallest_increasing_alpha"] == pytest.approx(0.00025)
    assert it0["predicted_over_actual_mismatch_ratio"] > 1000.0


def test_physical_tangent_is_fd_consistent(written_inputs, tmp_path):
    module = _load_module()
    probe, tangent = written_inputs
    payload = module.run_g1_global_operator_mismatch_audit(
        probe_json=probe, tangent_json=tangent, output_json=tmp_path / "a.json"
    )
    phys = payload["physical_residual_operator"]
    assert phys["physical_material_tangent_is_fd_consistent"] is True
    ratios = phys["per_state_class_solver_over_consistent_tangent_ratio_samples"]
    # softening state: solver clamps the (negative) consistent tangent to a positive
    # bounded value, so solver/consistent ratio is negative -> named divergence.
    assert "concrete_compression_softening" in ratios


def test_missing_input_raises(tmp_path):
    module = _load_module()
    with pytest.raises(FileNotFoundError):
        module.run_g1_global_operator_mismatch_audit(
            probe_json=tmp_path / "nope.json",
            tangent_json=tmp_path / "nope2.json",
            output_json=tmp_path / "a.json",
        )
