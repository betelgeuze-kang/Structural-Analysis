from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts" / "build_phase2_state_updated_concrete_damage_artifacts.py"
)
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
    assert result["material_point"]["tension_finite_difference_tangent"][
        "pass"
    ] is True
    assert result["material_point"]["compression_finite_difference_tangent"][
        "pass"
    ] is True
    assert result["material_point"]["cyclic_path"][
        "energy_damage_gate_passed"
    ] is True
    assert result["element_benchmark"]["contract_pass"] is True
    assert result["structure_benchmark"]["contract_pass"] is True
    assert result["structure_benchmark"]["localization_observed"] is True
    assert result["structure_benchmark"]["mesh_objectivity_claim"] is False
    assert result["structure_benchmark"][
        "consistent_jacobian_finite_difference"
    ]["pass"] is True
    assert result["rollback_probe"]["exact"] is True
    assert result["verification"]["fallback_count"] == 0
    assert result["verification"]["regularization_count"] == 0

    tie_break = result["structure_benchmark"]["localization_tie_break"]
    assert tie_break["profile"] == module.LOCALIZATION_TIE_BREAK_PROFILE
    assert tie_break["area_imperfection_ratio"] == (
        module.LOCALIZATION_AREA_IMPERFECTION_RATIO
    )
    assert tie_break["weakened_element_id"] == "bar-1"
    assert tie_break["selected_localization_element_id"] == "bar-1"
    assert tie_break["deterministic_branch_selected"] is True
    assert result["structure_benchmark"]["final_element_compressive_damage"][0] > 0.9
    assert result["structure_benchmark"]["final_element_compressive_damage"][1] == 0.0

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
    assert summary["mesh_objectivity_claim"] is False
    assert "post_peak_mesh_objectivity_not_closed" in summary["blockers_remaining"]
    assert "counter-evidence for mesh objectivity" in summary["claim_boundary"]


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


def test_builder_check_reports_structured_json_path_difference(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "result.json"
    summary_path = tmp_path / "summary.json"
    payloads = module.build_phase2_state_updated_concrete_damage_artifacts(
        repo_root=ROOT,
        result_out=result_path,
        summary_out=summary_path,
    )
    result_path.write_text(module._json_text(payloads["result"]), encoding="utf-8")
    summary_path.write_text(module._json_text(payloads["summary"]), encoding="utf-8")

    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["structure_benchmark"]["localization_observed"] = False
    result_path.write_text(module._json_text(tampered), encoding="utf-8")

    ok, message = module.check_phase2_state_updated_concrete_damage_artifacts(
        repo_root=ROOT,
        result_out=result_path,
        summary_out=summary_path,
    )

    assert ok is False
    prefix, artifact_kind, diagnostic_text = message.split(":", 2)
    assert prefix == "phase2_state_updated_concrete_damage_mismatch"
    assert artifact_kind == "result"
    diagnostic = json.loads(diagnostic_text)
    assert diagnostic["difference_count"] >= 1
    assert diagnostic["first_difference"]["path"] == (
        "$.structure_benchmark.localization_observed"
    )
    assert diagnostic["first_difference"]["existing"] is False
    assert diagnostic["first_difference"]["expected"] is True


def test_builder_is_deterministic_across_isolated_python_processes(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "result.json"
    summary_path = tmp_path / "summary.json"
    env = os.environ.copy()
    env.update(
        {
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "PYTHONHASHSEED": "0",
        }
    )
    snapshots = []
    for _ in range(3):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--result-out",
                str(result_path),
                "--summary-out",
                str(summary_path),
            ],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "ready | localization=True" in completed.stdout
        snapshots.append(
            (
                module._strip_volatile(
                    json.loads(result_path.read_text(encoding="utf-8"))
                ),
                module._strip_volatile(
                    json.loads(summary_path.read_text(encoding="utf-8"))
                ),
            )
        )

    assert snapshots[1] == snapshots[0]
    assert snapshots[2] == snapshots[0]


def test_committed_concrete_damage_artifacts_match_builder() -> None:
    ok, message = module.check_phase2_state_updated_concrete_damage_artifacts(
        repo_root=ROOT
    )

    assert ok is True
    assert message == "phase2_state_updated_concrete_damage_consistent"
