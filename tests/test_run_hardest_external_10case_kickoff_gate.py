from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_hardest_external_10case_kickoff_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _truthy_report(*, summary_line: str = "PASS", summary: dict | None = None, checks: dict | None = None) -> dict:
    return {
        "contract_pass": True,
        "reason_code": "PASS",
        "summary_line": summary_line,
        "summary": summary or {},
        "checks": checks or {},
    }


def test_hardest_external_10case_kickoff_gate_passes_with_ready_boundary(tmp_path: Path) -> None:
    out = tmp_path / "hardest_external_10case_kickoff_gate_report.json"
    solver_truthfulness = tmp_path / "solver_truthfulness_gate_report.json"
    solver_hip = tmp_path / "solver_hip_e2e_contract_report.json"
    nonlinear = tmp_path / "nonlinear_generalization_gate_report.json"
    workflow = tmp_path / "workflow_productization_gate_report.json"
    commercial = tmp_path / "commercial_readiness_report.json"
    real_source_multi = tmp_path / "real_source_multi_gate_report.json"

    report_paths = {
        "material": tmp_path / "material_constitutive_gate_report.json",
        "surface": tmp_path / "surface_interaction_benchmark_gate_report.json",
        "wind": tmp_path / "wind_time_history_gate_report.json",
        "ssi": tmp_path / "ssi_boundary_gate_report.json",
        "damper": tmp_path / "damper_validation_gate_report.json",
        "construction": tmp_path / "construction_sequence_gate_report.json",
        "pushover": tmp_path / "nonlinear_pushover_stress_report.json",
        "ndtha": tmp_path / "nonlinear_ndtha_stress_report.json",
        "buckling": tmp_path / "buckling_contract_report.json",
        "track": tmp_path / "track_lf_solver_report.json",
        "moving": tmp_path / "moving_load_integrator_report.json",
        "vti": tmp_path / "vti_coupled_solver_report.json",
        "tunnel": tmp_path / "tunnel_dynamics_dataset_report.json",
        "foundation": tmp_path / "foundation_soil_link_gate_report.json",
    }

    _write_json(
        solver_truthfulness,
        _truthy_report(
            summary_line="Solver truthfulness: PASS",
            summary={
                "top_level_production_seeded_runtime_count": 4,
                "top_level_runtime_policy_satisfied_count": 4,
                "surrogate_marker_count": 0,
                "cpu_fallback_count": 0,
            },
        ),
    )
    _write_json(
        solver_hip,
        _truthy_report(
            summary_line="Solver HIP e2e: PASS",
            summary={
                "production_kernel_solver_count": 20,
                "surrogate_runtime_free_solver_count": 20,
                "hazard_family_count": 20,
                "topology_family_count": 17,
                "load_path_family_count": 15,
            },
        ),
    )
    _write_json(
        nonlinear,
        _truthy_report(
            summary_line="Nonlinear generalization: PASS",
            summary={
                "beam_family_count": 6,
                "fiber_family_count": 6,
                "layered_family_count": 6,
                "joint_panel_family_count": 4,
                "foundation_section_family_count": 4,
                "device_section_family_count": 4,
                "isolation_section_family_count": 4,
                "soil_interface_section_family_count": 4,
            },
        ),
    )
    _write_json(
        workflow,
        _truthy_report(
            summary_line="Workflow/interoperability productization: PASS",
            summary={
                "audit_queue_count": 2,
                "approve_all_preview_reason_code": "PASS_START_NOW_FULL",
                "generated_signed_submission_bundle_count": 7,
            },
            checks={
                "signed_submission_bundle_pass": True,
                "auto_approved_subset_pass": True,
            },
        ),
    )
    _write_json(
        commercial,
        _truthy_report(
            summary_line="Commercial readiness: PASS",
            checks={"real_source_pass": True, "gpu_strict_pass": True},
            summary={"measured_source_family_count": 8, "measured_case_count": 120},
        ),
    )
    _write_json(real_source_multi, _truthy_report(summary_line="Real-source multi: PASS"))
    for path in report_paths.values():
        _write_json(path, _truthy_report(summary_line="PASS"))

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--solver-truthfulness-report",
            str(solver_truthfulness),
            "--solver-hip-e2e-report",
            str(solver_hip),
            "--nonlinear-generalization-report",
            str(nonlinear),
            "--workflow-productization-report",
            str(workflow),
            "--commercial-readiness-report",
            str(commercial),
            "--real-source-multi-report",
            str(real_source_multi),
            "--material-constitutive-report",
            str(report_paths["material"]),
            "--surface-interaction-benchmark-report",
            str(report_paths["surface"]),
            "--wind-benchmark-report",
            str(report_paths["wind"]),
            "--ssi-boundary-report",
            str(report_paths["ssi"]),
            "--damper-validation-report",
            str(report_paths["damper"]),
            "--construction-sequence-report",
            str(report_paths["construction"]),
            "--pushover-stress-report",
            str(report_paths["pushover"]),
            "--ndtha-stress-report",
            str(report_paths["ndtha"]),
            "--buckling-contract-report",
            str(report_paths["buckling"]),
            "--track-lf-solver-report",
            str(report_paths["track"]),
            "--moving-load-integrator-report",
            str(report_paths["moving"]),
            "--vti-coupled-solver-report",
            str(report_paths["vti"]),
            "--tunnel-dynamics-dataset-report",
            str(report_paths["tunnel"]),
            "--foundation-soil-link-gate-report",
            str(report_paths["foundation"]),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["ready_case_count"] == 10
    assert payload["summary"]["ready_to_start_now"] is True
    assert payload["summary"]["recommended_start_mode"] == "start_now_limited_external_benchmark"
    assert payload["summary"]["ready_to_start_full_submission_now"] is False
    assert payload["summary_line"].startswith("Hardest external 10-case kickoff: PASS")
    assert "ready=10/10" in payload["summary_line"]


def test_hardest_external_10case_kickoff_gate_fails_when_solver_truthfulness_is_blocked(tmp_path: Path) -> None:
    out = tmp_path / "hardest_external_10case_kickoff_gate_report.json"
    solver_truthfulness = tmp_path / "solver_truthfulness_gate_report.json"
    solver_hip = tmp_path / "solver_hip_e2e_contract_report.json"
    nonlinear = tmp_path / "nonlinear_generalization_gate_report.json"
    workflow = tmp_path / "workflow_productization_gate_report.json"
    commercial = tmp_path / "commercial_readiness_report.json"
    real_source_multi = tmp_path / "real_source_multi_gate_report.json"

    report_paths = {
        "material": tmp_path / "material_constitutive_gate_report.json",
        "surface": tmp_path / "surface_interaction_benchmark_gate_report.json",
        "wind": tmp_path / "wind_time_history_gate_report.json",
        "ssi": tmp_path / "ssi_boundary_gate_report.json",
        "damper": tmp_path / "damper_validation_gate_report.json",
        "construction": tmp_path / "construction_sequence_gate_report.json",
        "pushover": tmp_path / "nonlinear_pushover_stress_report.json",
        "ndtha": tmp_path / "nonlinear_ndtha_stress_report.json",
        "buckling": tmp_path / "buckling_contract_report.json",
        "track": tmp_path / "track_lf_solver_report.json",
        "moving": tmp_path / "moving_load_integrator_report.json",
        "vti": tmp_path / "vti_coupled_solver_report.json",
        "tunnel": tmp_path / "tunnel_dynamics_dataset_report.json",
        "foundation": tmp_path / "foundation_soil_link_gate_report.json",
    }

    _write_json(
        solver_truthfulness,
        _truthy_report(
            summary_line="Solver truthfulness: GAP",
            summary={
                "top_level_production_seeded_runtime_count": 3,
                "top_level_runtime_policy_satisfied_count": 3,
                "surrogate_marker_count": 1,
                "cpu_fallback_count": 0,
            },
        ),
    )
    _write_json(
        solver_hip,
        _truthy_report(
            summary={"production_kernel_solver_count": 20, "surrogate_runtime_free_solver_count": 20, "hazard_family_count": 20, "topology_family_count": 17, "load_path_family_count": 15}
        ),
    )
    _write_json(
        nonlinear,
        _truthy_report(
            summary={
                "beam_family_count": 6,
                "fiber_family_count": 6,
                "layered_family_count": 6,
                "joint_panel_family_count": 4,
                "foundation_section_family_count": 4,
                "device_section_family_count": 4,
                "isolation_section_family_count": 4,
                "soil_interface_section_family_count": 4,
            }
        ),
    )
    _write_json(
        workflow,
        _truthy_report(
            summary={"audit_queue_count": 2, "approve_all_preview_reason_code": "PASS_START_NOW_FULL", "generated_signed_submission_bundle_count": 7},
            checks={"signed_submission_bundle_pass": True, "auto_approved_subset_pass": True},
        ),
    )
    _write_json(commercial, _truthy_report(checks={"real_source_pass": True, "gpu_strict_pass": True}))
    _write_json(real_source_multi, _truthy_report())
    for path in report_paths.values():
        _write_json(path, _truthy_report())

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--solver-truthfulness-report",
            str(solver_truthfulness),
            "--solver-hip-e2e-report",
            str(solver_hip),
            "--nonlinear-generalization-report",
            str(nonlinear),
            "--workflow-productization-report",
            str(workflow),
            "--commercial-readiness-report",
            str(commercial),
            "--real-source-multi-report",
            str(real_source_multi),
            "--material-constitutive-report",
            str(report_paths["material"]),
            "--surface-interaction-benchmark-report",
            str(report_paths["surface"]),
            "--wind-benchmark-report",
            str(report_paths["wind"]),
            "--ssi-boundary-report",
            str(report_paths["ssi"]),
            "--damper-validation-report",
            str(report_paths["damper"]),
            "--construction-sequence-report",
            str(report_paths["construction"]),
            "--pushover-stress-report",
            str(report_paths["pushover"]),
            "--ndtha-stress-report",
            str(report_paths["ndtha"]),
            "--buckling-contract-report",
            str(report_paths["buckling"]),
            "--track-lf-solver-report",
            str(report_paths["track"]),
            "--moving-load-integrator-report",
            str(report_paths["moving"]),
            "--vti-coupled-solver-report",
            str(report_paths["vti"]),
            "--tunnel-dynamics-dataset-report",
            str(report_paths["tunnel"]),
            "--foundation-soil-link-gate-report",
            str(report_paths["foundation"]),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOLVER_TRUTHFULNESS"
    assert payload["summary"]["ready_to_start_now"] is False
    assert payload["checks"]["solver_truthfulness_pass"] is False
