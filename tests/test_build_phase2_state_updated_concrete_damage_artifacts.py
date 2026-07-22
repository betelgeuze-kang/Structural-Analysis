from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_phase2_state_updated_concrete_damage_artifacts.py"
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_state_updated_concrete_damage_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_concrete_damage_and_post_peak_localization_honestly() -> None:
    payloads = module.build_phase2_state_updated_concrete_damage_artifacts(
        repo_root=ROOT
    )
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "ready"
    assert result["contract_pass"] is True
    assert result["state_updated_concrete_seed_contract_pass"] is True
    assert result["mesh_objectivity_claim"] is False
    assert result["material_newton_breadth_closure_claim"] is False
    assert result["g1_material_newton_breadth_claim"] is False
    assert result["production_nonlinear_closure_claim"] is False
    assert result["residual_formula"] == "F_internal_minus_F_external"
    assert result["damage_algorithm"] == (
        "history_max_exponential_tension_compression_damage"
    )
    assert result["material_point"]["contract_pass"] is True
    assert result["material_point"]["tension_finite_difference_tangent"]["pass"] is True
    assert (
        result["material_point"]["compression_finite_difference_tangent"]["pass"]
        is True
    )
    assert result["material_point"]["cyclic_path"]["energy_damage_gate_passed"] is True
    assert result["element_benchmark"]["contract_pass"] is True
    assert result["element_benchmark"]["expected_force_kn"] == (
        result["element_benchmark"]["assembly"]["element_responses"][0][
            "internal_force_kn"
        ]
    )
    assert result["element_benchmark"]["force_abs_error_kn"] == 0.0
    assert result["structure_benchmark"]["contract_pass"] is True
    assert result["structure_benchmark"]["localization_observed"] is True
    assert result["structure_benchmark"]["mesh_objectivity_claim"] is False
    tie_break = result["structure_benchmark"]["localization_tie_break"]
    assert tie_break["profile"] == module.LOCALIZATION_TIE_BREAK_PROFILE
    assert tie_break["area_imperfection_ratio"] == (
        module.LOCALIZATION_AREA_IMPERFECTION_RATIO
    )
    assert tie_break["nondominant_damage_tolerance"] == (
        module.LOCALIZATION_NONDOMINANT_DAMAGE_TOLERANCE
    )
    assert tie_break["perturbed_element_id"] == (
        module.LOCALIZATION_PERTURBED_ELEMENT_ID
    )
    assert tie_break["selected_localization_element_id"] == (
        module.LOCALIZATION_SELECTED_ELEMENT_ID
    )
    assert tie_break["deterministic_branch_selected"] is True
    final_damage = result["structure_benchmark"]["final_element_compressive_damage"]
    assert final_damage[1] > 0.9
    assert final_damage[0] <= module.LOCALIZATION_NONDOMINANT_DAMAGE_TOLERANCE
    assert (
        result["structure_benchmark"]["consistent_jacobian_finite_difference"]["pass"]
        is True
    )
    assert result["rollback_probe"]["exact"] is True
    assert result["verification"]["fallback_count"] == 0
    assert result["verification"]["regularization_count"] == 0

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["tension_damage_tangent_gate_passed"] is True
    assert summary["compression_damage_tangent_gate_passed"] is True
    assert summary["cyclic_energy_damage_gate_passed"] is True
    assert summary["damage_irreversibility_gate_passed"] is True
    assert summary["element_benchmark_gate_passed"] is True
    assert summary["structure_benchmark_gate_passed"] is True
    assert summary["structure_jacobian_gate_passed"] is True
    assert summary["rollback_exact_gate_passed"] is True
    assert summary["deterministic_replay_exact_gate_passed"] is True
    assert summary["localization_observed"] is True
    assert summary["localization_tie_break_profile"] == (
        module.LOCALIZATION_TIE_BREAK_PROFILE
    )
    assert summary["localization_area_imperfection_ratio"] == (
        module.LOCALIZATION_AREA_IMPERFECTION_RATIO
    )
    assert summary["localization_nondominant_damage_tolerance"] == (
        module.LOCALIZATION_NONDOMINANT_DAMAGE_TOLERANCE
    )
    assert summary["perturbed_localization_element_id"] == (
        module.LOCALIZATION_PERTURBED_ELEMENT_ID
    )
    assert summary["selected_localization_element_id"] == (
        module.LOCALIZATION_SELECTED_ELEMENT_ID
    )
    assert summary["mesh_objectivity_claim"] is False
    assert "post_peak_mesh_objectivity_not_closed" in summary["blockers_remaining"]
    assert "counter-evidence for mesh objectivity" in summary["claim_boundary"]
    assert "solely to select one of two symmetric" in summary["claim_boundary"]


def test_difference_diagnostic_reports_path_scale_and_signed_zero() -> None:
    diagnostic = module._difference_diagnostic(
        {"nested": {"a_signed_zero": -0.0, "b_float": 1.25}},
        {"nested": {"a_signed_zero": 0.0, "b_float": 1.0}},
    )

    assert diagnostic == {
        "difference_count": 2,
        "first_difference": {
            "path": "$.nested.a_signed_zero",
            "existing": -0.0,
            "expected": 0.0,
            "kind": "signed_zero",
            "absolute_difference": 0.0,
        },
        "maximum_float_absolute_difference": 0.25,
        "signed_zero_difference_count": 1,
    }


def test_builder_is_exact_across_isolated_single_thread_processes(
    tmp_path: Path,
) -> None:
    result_out = tmp_path / "result.json"
    summary_out = tmp_path / "summary.json"
    environment = os.environ.copy()
    environment.update(
        {
            "MKL_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_CORETYPE": "Haswell",
            "OPENBLAS_NUM_THREADS": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    snapshots = []

    for _ in range(3):
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--result-out",
                str(result_out),
                "--summary-out",
                str(summary_out),
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        snapshots.append(
            {
                "result": module._strip_volatile(
                    json.loads(result_out.read_text(encoding="utf-8"))
                ),
                "summary": module._strip_volatile(
                    json.loads(summary_out.read_text(encoding="utf-8"))
                ),
            }
        )

    assert snapshots[1:] == snapshots[:-1]


def test_builder_check_reports_missing_concrete_damage_artifacts(
    tmp_path: Path,
) -> None:
    ok, message = module.check_phase2_state_updated_concrete_damage_artifacts(
        repo_root=ROOT,
        result_out=tmp_path / "missing-result.json",
        summary_out=tmp_path / "missing-summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_state_updated_concrete_damage_missing:")


def test_committed_concrete_damage_artifacts_match_builder() -> None:
    ok, message = module.check_phase2_state_updated_concrete_damage_artifacts(
        repo_root=ROOT
    )

    assert ok is True
    assert message == "phase2_state_updated_concrete_damage_consistent"
