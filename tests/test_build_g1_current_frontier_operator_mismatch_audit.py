from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_g1_current_frontier_operator_mismatch_audit.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_current_frontier_operator_mismatch_audit",
    SCRIPT_PATH,
)
assert SPEC is not None
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _frontier_probe_payload() -> dict:
    return {
        "schema_version": "mgt-direct-residual-newton-probe.v1",
        "status": "partial",
        "source_commit_sha": "fixture-frontier",
        "base_direct_residual": {
            "load_scale": 1.0,
            "direct_residual_inf_n": 5.0,
            "linear_correction_regularization": 515.0,
        },
        "final_direct_residual": {
            "direct_residual_inf_n": 5.0,
            "residual_gate_passed": False,
        },
        "output_final_checkpoint": {
            "written": False,
            "reason": "no_residual_descent",
            "path": "frontier_candidate.npz",
            "load_scale": 1.0,
        },
        "newton_direction": {
            "linearized_tangent": (
                "current service-material frame tangent plus frame geometric delta "
                "plus state shell material tangent plus finite springs"
            )
        },
        "live_g1_assembly_contract": {
            "contract_pass": True,
            "assembly_result_schema": "g1-assembly-result.v1",
            "residual_formula": "F_internal_minus_F_external",
            "residual_source": "physical_direct_residual",
            "tangent_definition": "dR_du_consistent",
            "residual_inf_norm": 5.0,
            "free_dof_count": 58998,
        },
        "residual_contract": {
            "definition": "R(u, lambda) = F_int(u) - lambda * F_ext",
            "direct_residual_uses_solver_regularization": False,
            "regularization_used_only_for_linear_correction_direction": True,
            "service_material_tangent_used_for_newton_direction_only": True,
            "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
            "hip_residual_engine_contract_passed": True,
            "hip_residual_engine_required_lane_count": 2,
            "hip_residual_engine_passed_lane_count": 2,
            "hip_residual_engine_backends": [
                "hip_full_residual",
                "hip_full_residual_resident",
            ],
        },
        "mesh_fingerprint": {
            "frame_geometric_delta_stiffness_nnz": 44913,
            "frame_material_meta": {
                "min_solver_tangent_ratio": 4.7619047619047615e-06,
                "tangent_reduction_element_count": 1763,
            },
            "service_material_meta": {
                "service_min_tangent_ratio": 0.02746524828006217,
                "service_mean_tangent_ratio": 0.9360619275141128,
            },
            "service_shell_material_meta": {
                "nonlinear_tangent_surface_element_count": 0,
                "min_tangent_ratio": 0.9988921983086817,
                "mean_tangent_ratio": 0.9999869549431114,
                "max_abs_strain": 3.89556638705355e-06,
                "state_tag_counts": {"concrete_compression_hardening": 4252},
            },
        },
        "matrix_free_global_krylov": {
            "attempted": True,
            "promoted_to_final_state": False,
            "trial_rows": [
                {"alpha": 1.0, "direct_residual_inf_n": 5.1},
                {"alpha": 0.5, "direct_residual_inf_n": 5.2},
            ],
            "best_candidate": {
                "alpha": -0.0625,
                "alpha_source": "matrix_free_global_krylov_negative",
                "direct_residual_inf_n": 5.1,
                "improvement_inf_n": -0.1,
                "residual_batch_backend": "hip_full_residual_resident",
            },
        },
        "current_tangent_residual_row_correction": {
            "attempted": True,
            "promoted_to_final_state": False,
            "trial_rows": [
                {"alpha": 0.5, "direct_residual_inf_n": 5.4},
                {"alpha": 0.25, "direct_residual_inf_n": 5.3},
            ],
            "best_candidate": {
                "alpha": 0.25,
                "alpha_source": "current_tangent_residual_row",
                "direct_residual_inf_n": 5.3,
                "improvement_inf_n": -0.3,
                "residual_batch_backend": "hip_full_residual",
            },
        },
    }


def test_current_frontier_audit_is_non_promoting_and_complete(tmp_path: Path) -> None:
    probe = tmp_path / "frontier.json"
    _write_json(probe, _frontier_probe_payload())

    payload = module.build_g1_current_frontier_operator_mismatch_audit(
        repo_root=tmp_path,
        frontier_probe_path=probe,
    )

    assert payload["audit_complete"] is True
    assert payload["is_audit_only"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["frontier_probe"]["full_load_no_descent"] is True
    assert payload["live_g1_assembly_contract"]["contract_pass"] is True
    assert (
        payload["current_frontier_no_descent"][
            "global_and_row_operator_family_no_descent"
        ]
        is True
    )
    assert payload["current_frontier_no_descent"]["scaled_global_krylov"][
        "best_direct_residual_inf_n"
    ] == 5.1
    assert payload["current_frontier_no_descent"][
        "current_tangent_residual_row_correction"
    ]["best_direct_residual_inf_n"] == 5.3
    assert "frame_service_material_tangent_reduced_below_elastic" in payload[
        "current_operator_mismatch"
    ]["mismatch_reasons"]
    assert payload["shell_material_state"][
        "shell_material_tangent_elastic_passive_at_checkpoint"
    ] is True
    assert payload["operator_mismatch_summary"]["next_required_operator"] == (
        "physical_consistent_frame_shell_material_geometric_with_state_"
        "updated_material_tangent_and_full_residual_globalization"
    )


def test_current_frontier_audit_blocks_when_probe_missing(tmp_path: Path) -> None:
    payload = module.build_g1_current_frontier_operator_mismatch_audit(
        repo_root=tmp_path,
        frontier_probe_path=tmp_path / "missing.json",
    )

    assert payload["audit_complete"] is False
    assert payload["status"] == "partial"
    assert payload["frontier_probe"]["full_load_no_descent"] is False
    assert payload["terminal_criteria"]["frontier_probe_present"] is False


def test_current_frontier_audit_write_json(tmp_path: Path) -> None:
    probe = tmp_path / "frontier.json"
    out = tmp_path / "audit.json"
    _write_json(probe, _frontier_probe_payload())

    payload = module.write_g1_current_frontier_operator_mismatch_audit(
        repo_root=tmp_path,
        frontier_probe_path=probe,
        out=out,
    )

    assert out.is_file()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["schema_version"] == module.SCHEMA_VERSION
    assert written["audit_complete"] == payload["audit_complete"]
