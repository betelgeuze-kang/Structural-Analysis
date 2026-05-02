from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_surface_interaction_benchmark_gate.py")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_inputs(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "diaphragm": tmp_path / "flexible_diaphragm.json",
        "substructuring": tmp_path / "substructuring.json",
        "sync": tmp_path / "sync.json",
        "foundation": tmp_path / "foundation.json",
        "moving_load": tmp_path / "moving_load.json",
        "vti": tmp_path / "vti.json",
        "track_dataset": tmp_path / "track_dataset.json",
        "tunnel_dataset": tmp_path / "tunnel_dataset.json",
        "panel_zone": tmp_path / "panel_zone.json",
        "ssi": tmp_path / "ssi.json",
        "soil_tunnel": tmp_path / "soil_tunnel.json",
        "structural_contact": tmp_path / "structural_contact.json",
        "cases_a": tmp_path / "cases_a.json",
        "cases_b": tmp_path / "cases_b.json",
        "cases_c": tmp_path / "cases_c.json",
        "cases_d": tmp_path / "commercial_benchmark_cases.kw51_railway_bridge.json",
        "cases_e": tmp_path / "commercial_benchmark_cases.opstool_nightly.json",
        "cases_f": tmp_path / "commercial_benchmark_cases.atwood_open.mgt_smoke.json",
        "cases_g": tmp_path / "commercial_benchmark_cases.atwood_open.mgt_smoke2.json",
        "cases_h": tmp_path / "commercial_benchmark_cases.atwood_open.mgt_smoke3.json",
        "cases_i": tmp_path / "commercial_benchmark_cases.atwood_open.pr_recheck.json",
        "cases_j": tmp_path / "commercial_benchmark_cases.opstool_pr.json",
        "out": tmp_path / "surface_interaction.json",
    }
    _write(
        paths["diaphragm"],
        {
            "contract_pass": True,
            "checks": {
                "shell_beam_mix_topology_pass": True,
                "flexible_diaphragm_modeled": True,
                "slab_shear_stress_pass": True,
                "all_cases_converged": True,
                "rust_backend_used_pass": True,
                "flex_amplification_band_pass": True,
                "max_flexible_drift_pass": True,
            },
            "summary": {
                "case_count": 31,
                "flex_amplification_max": 1.12,
                "slab_shear_stress_mpa_max": 0.83,
                "max_flexible_drift_pct": 1.48,
            },
            "rows": [
                {
                    "case_id": "C-TRN-001",
                    "topology_type": "rahmen",
                    "rigid": {"converged": True, "rust_backend_ok": True},
                    "flexible": {"amplification_ratio": 1.08, "slab_shear_stress_mpa": 0.41},
                },
                {
                    "case_id": "C-TRN-002",
                    "topology_type": "truss",
                    "rigid": {"converged": True, "rust_backend_ok": True},
                    "flexible": {"amplification_ratio": 1.11, "slab_shear_stress_mpa": 0.37},
                },
                {
                    "case_id": "C-TRN-003",
                    "topology_type": "wall-frame",
                    "rigid": {"converged": True, "rust_backend_ok": True},
                    "flexible": {"amplification_ratio": 1.12, "slab_shear_stress_mpa": 0.52},
                },
                {
                    "case_id": "C-TRN-004",
                    "topology_type": "rahmen",
                    "rigid": {"converged": True, "rust_backend_ok": True},
                    "flexible": {"amplification_ratio": 1.05, "slab_shear_stress_mpa": 0.29},
                },
            ],
        },
    )
    _write(
        paths["substructuring"],
        {
            "contract_pass": True,
            "checks": {
                "finite_transfer": True,
                "coupling_stability": True,
                "interface_dof_match": True,
            },
            "metrics": {
                "mean_transfer_ratio_building_to_track": 0.45,
                "max_condition_number": 8.2,
            },
            "curve_head": [
                {
                    "f_hz": 4.0,
                    "track_disp_m": 4.2e-05,
                    "tunnel_disp_m": 1.0e-05,
                    "soil_disp_m": 1.6e-05,
                    "building_disp_m": 8.1e-06,
                    "coupled_total_disp_m": 7.6e-05,
                },
                {
                    "f_hz": 18.0,
                    "track_disp_m": 4.5e-05,
                    "tunnel_disp_m": 1.2e-05,
                    "soil_disp_m": 2.0e-05,
                    "building_disp_m": 1.0e-05,
                    "coupled_total_disp_m": 8.4e-05,
                },
                {
                    "f_hz": 32.0,
                    "track_disp_m": 4.9e-05,
                    "tunnel_disp_m": 1.5e-05,
                    "soil_disp_m": 6.3e-05,
                    "building_disp_m": 2.4e-05,
                    "coupled_total_disp_m": 1.4e-04,
                },
            ],
        },
    )
    _write(
        paths["sync"],
        {
            "contract_pass": True,
            "checks": {
                "topology_gate_pass": True,
                "required_levels_present": True,
                "required_levels_sync_pass": True,
                "sync_stall_budget_pass": True,
                "backend_policy_pass": True,
                "inline_native_smoke_pass": True,
            },
            "inline_native_smoke_result": {
                "max_gap_norm": 0.00041,
                "mean_gap_abs_m": 0.00012,
            },
            "level_rows": [
                {
                    "node_count": 1000000,
                    "contract_pass": True,
                    "backend": "feti_lite_boundary_sync",
                    "sync_stall_ratio": 0.0,
                    "p99_step_ms": 0.34,
                },
                {
                    "node_count": 3000000,
                    "contract_pass": True,
                    "backend": "feti_lite_boundary_sync",
                    "sync_stall_ratio": 0.0,
                    "p99_step_ms": 0.35,
                },
                {
                    "node_count": 10000000,
                    "contract_pass": True,
                    "backend": "feti_lite_boundary_sync",
                    "sync_stall_ratio": 0.0,
                    "p99_step_ms": 0.36,
                },
            ],
        },
    )
    _write(
        paths["foundation"],
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_artifact_ready": True,
                "ssi_boundary_ready": True,
                "soil_tunnel_ready": True,
                "impedance_schema_ready": True,
                "foundation_link_models_ready": True,
            },
            "summary": {
                "foundation_member_type_count": 76,
                "optimized_foundation_group_count": 2,
                "foundation_link_model_types": [
                    "bearing_bilinear",
                    "compression_only_penalty",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                ],
                "required_foundation_link_models": [
                    "bearing_bilinear",
                    "compression_only_penalty",
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                ],
                "soil_link_contract_tokens": [
                    "k_radial_N_m2",
                    "k_tangential_N_m2",
                    "c_radial_Ns_m2",
                    "c_tangential_Ns_m2",
                ],
                "missing_foundation_link_models": [],
            },
        },
    )
    _write(
        paths["moving_load"],
        {
            "contract_pass": True,
            "checks": {
                "finite_response": True,
                "non_divergent_response": True,
                "linear_solver_converged": True,
                "equilibrium_residual_pass": True,
                "energy_balance_pass": True,
            },
            "metrics": {
                "residual_ratio": 1.2e-13,
                "energy_balance_relative_error": 0.0236,
                "max_acceleration_mps2": 47.77,
            },
        },
    )
    _write(
        paths["vti"],
        {
            "contract_pass": True,
            "checks": {
                "finite_response": True,
                "coupling_converged_ratio_pass": True,
                "dynamic_disp_pass": True,
                "adaptive_newton_converged_pass": True,
            },
            "metrics": {
                "mean_coupling_iters": 1.64,
            },
        },
    )
    _write(
        paths["track_dataset"],
        {
            "contract_pass": True,
            "checks": {
                "dataset_nonempty": True,
                "split_has_val_test": True,
                "finite_response": True,
                "equilibrium_residual_pass": True,
            },
            "metrics": {
                "max_equilibrium_residual": 0.386,
            },
        },
    )
    _write(
        paths["tunnel_dataset"],
        {
            "contract_pass": True,
            "checks": {
                "dataset_nonempty": True,
                "split_has_val_test": True,
                "finite_response": True,
                "equilibrium_residual_pass": True,
            },
            "metrics": {
                "max_equilibrium_residual": 0.386,
            },
        },
    )
    _write(
        paths["panel_zone"],
        {
            "contract_pass": True,
            "checks": {
                "panel_zone_clash_artifact_contract_pass": True,
                "panel_zone_topology_capable_input": True,
                "panel_zone_required_sources_complete": True,
                "panel_zone_topology_projected_bridge_complete": True,
                "panel_zone_internal_engine_complete": True,
            },
            "summary": {
                "panel_zone_clash_row_count": 45,
            },
        },
    )
    _write(
        paths["ssi"],
        {
            "contract_pass": True,
            "checks": {
                "ssi_nonlinear_boundary_active": True,
                "ssi_transfer_finite": True,
                "material_model_pass": True,
                "section_family_pass": True,
                "shear_delta_pass": True,
                "residual_trace_pass": True,
                "device_artifacts_consumed_pass": True,
            },
            "summary": {
                "selected_case_count": 4,
                "nonlinear_ratio_span": 0.18,
                "soil_profile": "dense_sand",
            },
            "rows": [
                {
                    "case_id": "C-TRN-003",
                    "topology_type": "rahmen",
                    "fixed": {"converged_all_steps": True, "collapsed": False},
                    "ssi": {"converged_all_steps": True, "collapsed": False},
                    "material_model": "steel_elastic_plastic",
                    "material_model_pass": True,
                    "residual_trace_pass": True,
                    "shear_delta_ratio": 0.68,
                },
                {
                    "case_id": "C-TRN-005",
                    "topology_type": "outrigger",
                    "fixed": {"converged_all_steps": True, "collapsed": False},
                    "ssi": {"converged_all_steps": True, "collapsed": False},
                    "material_model": "steel_elastic_plastic",
                    "material_model_pass": True,
                    "residual_trace_pass": True,
                    "shear_delta_ratio": 0.73,
                },
                {
                    "case_id": "C-TRN-007",
                    "topology_type": "wall-frame",
                    "fixed": {"converged_all_steps": True, "collapsed": False},
                    "ssi": {"converged_all_steps": True, "collapsed": False},
                    "material_model": "steel_elastic_plastic",
                    "material_model_pass": True,
                    "residual_trace_pass": True,
                    "shear_delta_ratio": 0.71,
                },
            ],
        },
    )
    _write(
        paths["soil_tunnel"],
        {
            "contract_pass": True,
            "checks": {
                "finite_response": True,
                "monotonic_stiffness": True,
                "positive_damping": True,
                "high_freq_attenuation": True,
            },
            "metrics": {
                "k_min": 9.8e7,
                "c_min": 1.7e5,
                "amp_low_band_median": 8.6e-9,
                "amp_high_band_median": 6.8e-9,
            },
            "curve_head": [
                {"f_hz": 0.5, "k_n_m": 9.8e7, "c_n_s_m": 1.67e5, "transfer_amp": 1.01e-8},
                {"f_hz": 5.0, "k_n_m": 1.36e8, "c_n_s_m": 2.28e5, "transfer_amp": 7.88e-9},
                {"f_hz": 15.0, "k_n_m": 1.67e8, "c_n_s_m": 3.39e5, "transfer_amp": 9.89e-9},
                {"f_hz": 30.0, "k_n_m": 1.95e8, "c_n_s_m": 5.63e5, "transfer_amp": 6.81e-9},
            ],
        },
    )
    _write(
        paths["structural_contact"],
        {
            "contract_pass": True,
            "checks": {
                "bounded_contact_evidence_pass": True,
                "special_link_library_present": True,
                "special_link_categories_present": True,
                "structural_contact_validation_present": True,
                "all_structural_contact_categories_ready": True,
                "structural_contact_event_sequence_zero_pass": True,
                "bearing_design_rule_present": True,
                "friction_design_rule_present": True,
            },
            "category_readiness": [
                {"category": "gap", "implementation_present": True, "validated": True, "ready": True},
                {"category": "uplift", "implementation_present": True, "validated": True, "ready": True},
                {"category": "compression-only", "implementation_present": True, "validated": True, "ready": True},
                {"category": "bearing", "implementation_present": True, "validated": True, "ready": True},
                {"category": "friction", "implementation_present": True, "validated": True, "ready": True},
                {"category": "pounding", "implementation_present": True, "validated": True, "ready": True},
            ],
        },
    )
    for key, source_family in (("cases_a", "rwth_zenodo"), ("cases_b", "commercial_export"), ("cases_c", "opstool_606m_megatall_model")):
        _write(
            paths[key],
            {
                "cases": [
                    {
                        "case_id": f"{source_family}-wall",
                        "source_family": source_family,
                        "topology_type": "wall-frame",
                        "element_mix": "shell_beam_mix",
                        "hazard_type": "wind",
                        "split": "train",
                        "ood_tag": "in_distribution",
                        "metric_source": "open_data_measurement",
                    },
                    {
                        "case_id": f"{source_family}-out",
                        "source_family": source_family,
                        "topology_type": "outrigger",
                        "element_mix": "shell_beam_mix",
                        "hazard_type": "seismic" if source_family == "rwth_zenodo" else ("wind" if source_family == "commercial_export" else "combined"),
                        "split": "train" if source_family != "commercial_export" else "holdout",
                        "ood_tag": "in_distribution" if source_family != "commercial_export" else "stress_probe",
                        "metric_source": "open_data_measurement" if source_family != "commercial_export" else "commercial_solver_export",
                    },
                ]
            },
        )
    _write(paths["cases_d"], {"cases": [{"case_id": "KW51-001", "topology_type": "wall-frame"}, {"case_id": "KW51-002", "topology_type": "outrigger"}]})
    _write(paths["cases_e"], {"cases": [{"case_id": "OPS-NIGHT-001", "topology_type": "wall-frame"}, {"case_id": "OPS-NIGHT-002", "topology_type": "outrigger"}]})
    _write(paths["cases_f"], {"cases": [{"case_id": "ATW-SMOKE-001", "topology_type": "wall-frame"}, {"case_id": "ATW-SMOKE-002", "topology_type": "outrigger"}]})
    _write(paths["cases_g"], {"cases": [{"case_id": "ATW-SMOKE2-001", "topology_type": "wall-frame"}, {"case_id": "ATW-SMOKE2-002", "topology_type": "outrigger"}]})
    _write(paths["cases_h"], {"cases": [{"case_id": "ATW-SMOKE3-001", "topology_type": "wall-frame"}, {"case_id": "ATW-SMOKE3-002", "topology_type": "outrigger"}]})
    _write(paths["cases_i"], {"cases": [{"case_id": "ATW-PR-001", "topology_type": "wall-frame"}, {"case_id": "ATW-PR-002", "topology_type": "outrigger"}]})
    _write(paths["cases_j"], {"cases": [{"case_id": "OPS-PR-001", "topology_type": "wall-frame"}, {"case_id": "OPS-PR-002", "topology_type": "outrigger"}]})
    return paths


def test_surface_interaction_benchmark_gate_passes_with_complete_evidence(tmp_path: Path) -> None:
    paths = _base_inputs(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--flexible-diaphragm-report",
            str(paths["diaphragm"]),
            "--substructuring-interface-report",
            str(paths["substructuring"]),
            "--sync-stress-report",
            str(paths["sync"]),
            "--foundation-soil-link-gate-report",
            str(paths["foundation"]),
            "--moving-load-integrator-report",
            str(paths["moving_load"]),
            "--vti-coupled-solver-report",
            str(paths["vti"]),
            "--track-dynamics-dataset-report",
            str(paths["track_dataset"]),
            "--tunnel-dynamics-dataset-report",
            str(paths["tunnel_dataset"]),
            "--panel-zone-clash-report",
            str(paths["panel_zone"]),
            "--ssi-boundary-report",
            str(paths["ssi"]),
            "--soil-tunnel-ssi-report",
            str(paths["soil_tunnel"]),
            "--structural-contact-gate-report",
            str(paths["structural_contact"]),
            "--benchmark-cases",
            f"{paths['cases_a']},{paths['cases_b']},{paths['cases_c']},{paths['cases_d']},{paths['cases_e']},"
            f"{paths['cases_f']},{paths['cases_g']},{paths['cases_h']},{paths['cases_i']},{paths['cases_j']}",
            "--out",
            str(paths["out"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["shell_surface_coupling_pass"] is True
    assert payload["checks"]["interface_transfer_pass"] is True
    assert payload["checks"]["interface_gap_continuity_pass"] is True
    assert payload["checks"]["foundation_soil_impedance_pass"] is True
    assert payload["checks"]["ssi_boundary_interaction_pass"] is True
    assert payload["checks"]["soil_tunnel_dynamic_interaction_pass"] is True
    assert payload["checks"]["direct_structural_contact_family_pass"] is True
    assert payload["checks"]["interaction_family_matrix_pass"] is True
    assert payload["checks"]["all_matrix_rows_ready"] is True
    assert payload["summary"]["ready_row_count"] == 7
    assert payload["summary"]["total_row_count"] == 7
    assert payload["summary"]["interaction_family_ready_count"] == payload["summary"]["interaction_family_total_count"]
    assert payload["summary"]["interaction_family_total_count"] == len(payload["interaction_family_rows"])
    assert payload["summary"]["interaction_source_family_ready_count"] == 10
    assert payload["summary"]["interaction_source_family_total_count"] == 10
    assert payload["summary"]["interaction_source_families"] == [
        "atwood_open.mgt_smoke",
        "atwood_open.mgt_smoke2",
        "atwood_open.mgt_smoke3",
        "atwood_open.pr_recheck",
        "commercial_export",
        "kw51_railway_bridge",
        "opstool_606m_megatall_model",
        "opstool_nightly",
        "opstool_pr",
        "rwth_zenodo",
    ]
    group_counts = payload["summary"]["interaction_family_group_counts"]
    group_ready_counts = payload["summary"]["interaction_family_group_ready_counts"]
    assert {
        "modal_transfer",
        "kinematic_coupling",
        "constraint_bridge",
        "wave_radiation",
        "shell_shell",
        "shell_wall",
        "footing_soil",
        "track_slab",
        "vehicle_track",
        "tunnel_lining_soil",
        "joint_panel",
        "ssi",
        "soil_tunnel",
        "direct_structural_contact",
    }.issubset(set(group_counts))
    assert group_ready_counts == group_counts
    assert sum(group_counts.values()) == payload["summary"]["interaction_family_total_count"]
    assert payload["summary"]["direct_contact_ready_count"] == 6
    assert len(payload["interaction_family_rows"]) == payload["summary"]["interaction_family_total_count"]
    assert any(row["label"] == "shell_shell_surface_transfer" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_shell_diaphragm_case_c_trn_001" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_shell_metric_source_open_data_measurement" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_shell_surface_to_surface_contact_patch" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_shell_surface_to_surface_augmented_lagrange" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_shell_surface_to_surface_dual_lagrange" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_wall_interface_frequency_4hz" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_wall_sync_scale_1e_06nodes" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_wall_surface_to_surface_pressure_recovery" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_wall_surface_to_surface_segment_to_segment" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "shell_wall_surface_to_surface_contact_stabilization" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "footing_soil_link_model_coulomb_friction" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "footing_soil_impedance_token_k_radial_n_m2" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "footing_soil_surface_to_surface_normal_projection" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "footing_soil_surface_to_surface_energy_consistency" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "footing_soil_surface_to_surface_projection_consistency" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "track_slab_surface_to_surface_normal_projection" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "vehicle_track_surface_to_surface_contact_stabilization" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "tunnel_lining_soil_surface_to_surface_mortar_pairing" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "joint_panel_surface_to_surface_constraint_projection" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "modal_transfer_shell_modal_consistency" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "kinematic_coupling_joint_panel_bridge" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "constraint_bridge_direct_contact_projection" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "wave_radiation_tunnel_soil_decay" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "direct_contact_gap" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "direct_contact_design_rule_surface" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "ssi_case_c_trn_003" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "ssi_topology_wall_frame" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "soil_tunnel_frequency_15hz" for row in payload["interaction_family_rows"])
    assert any(row["label"] == "soil_tunnel_monotonic_stiffness_surface" for row in payload["interaction_family_rows"])
    assert not any("source_family" in row["label"] for row in payload["interaction_family_rows"])
    assert "modal-transfer=" in payload["summary"]["interaction_family_group_label"]
    assert "kinematic-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "constraint-bridge=" in payload["summary"]["interaction_family_group_label"]
    assert "wave-radiation=" in payload["summary"]["interaction_family_group_label"]
    assert "multiphysics-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "explicit-shear-transfer=" in payload["summary"]["interaction_family_group_label"]
    assert "phase-latency-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "cache-window-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "whitebox-feedback-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "recovery-residual-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "track-slab=" in payload["summary"]["interaction_family_group_label"]
    assert "vehicle-track=" in payload["summary"]["interaction_family_group_label"]
    assert "tunnel-lining-soil=" in payload["summary"]["interaction_family_group_label"]
    assert "joint-panel=" in payload["summary"]["interaction_family_group_label"]
    assert "support-contact-modulation-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "lining-recovery-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "panel-feedback-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "pressure-mapping-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert (
        f"family_matrix={payload['summary']['interaction_family_ready_count']}/{payload['summary']['interaction_family_total_count']}"
        in payload["summary_line"]
    )
    assert "source_families=10/10" in payload["summary_line"]
    assert f"groups={payload['summary']['interaction_family_group_label']}" in payload["summary_line"]
    assert payload["summary_line"].startswith("Surface interaction benchmark: PASS")


def test_surface_interaction_benchmark_accepts_solver_verified_true_3d_panel_zone_bridge(
    tmp_path: Path,
) -> None:
    paths = _base_inputs(tmp_path)
    panel_zone = json.loads(paths["panel_zone"].read_text(encoding="utf-8"))
    panel_zone["checks"].update(
        {
            "panel_zone_true_3d_bridge_complete": True,
            "panel_zone_solver_verified_bridge_complete": True,
            "panel_zone_topology_projected_bridge_complete": False,
            "panel_zone_internal_engine_complete": False,
        }
    )
    panel_zone["summary"].update(
        {
            "panel_zone_true_3d_bridge_complete": True,
            "panel_zone_solver_verified_bridge_complete": True,
            "panel_zone_topology_projected_bridge_complete": False,
            "panel_zone_internal_engine_complete": False,
            "panel_zone_external_validation_closure_mode": "closed_exact_validated",
        }
    )
    _write(paths["panel_zone"], panel_zone)

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--flexible-diaphragm-report",
            str(paths["diaphragm"]),
            "--substructuring-interface-report",
            str(paths["substructuring"]),
            "--sync-stress-report",
            str(paths["sync"]),
            "--foundation-soil-link-gate-report",
            str(paths["foundation"]),
            "--moving-load-integrator-report",
            str(paths["moving_load"]),
            "--vti-coupled-solver-report",
            str(paths["vti"]),
            "--track-dynamics-dataset-report",
            str(paths["track_dataset"]),
            "--tunnel-dynamics-dataset-report",
            str(paths["tunnel_dataset"]),
            "--panel-zone-clash-report",
            str(paths["panel_zone"]),
            "--ssi-boundary-report",
            str(paths["ssi"]),
            "--soil-tunnel-ssi-report",
            str(paths["soil_tunnel"]),
            "--structural-contact-gate-report",
            str(paths["structural_contact"]),
            "--benchmark-cases",
            f"{paths['cases_a']},{paths['cases_b']},{paths['cases_c']},{paths['cases_d']},{paths['cases_e']},"
            f"{paths['cases_f']},{paths['cases_g']},{paths['cases_h']},{paths['cases_i']},{paths['cases_j']}",
            "--out",
            str(paths["out"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["joint_panel_interaction_pass"] is True
    assert payload["summary"]["interaction_family_group_ready_counts"]["joint_panel"] == 8
    assert payload["summary"]["interaction_family_group_ready_counts"]["panel_feedback_coupling"] == 4


def test_surface_interaction_benchmark_gate_fails_with_gap_semantics_when_direct_contact_is_incomplete(
    tmp_path: Path,
) -> None:
    paths = _base_inputs(tmp_path)
    _write(
        paths["structural_contact"],
        {
            "contract_pass": False,
            "checks": {
                "bounded_contact_evidence_pass": False,
                "special_link_library_present": False,
                "special_link_categories_present": False,
                "structural_contact_validation_present": False,
                "all_structural_contact_categories_ready": False,
                "structural_contact_event_sequence_zero_pass": False,
                "bearing_design_rule_present": False,
                "friction_design_rule_present": False,
            },
            "category_readiness": [
                {"category": "gap", "implementation_present": True, "validated": True, "ready": True},
                {"category": "uplift", "implementation_present": True, "validated": True, "ready": True},
                {"category": "compression-only", "implementation_present": True, "validated": True, "ready": True},
                {"category": "bearing", "implementation_present": True, "validated": False, "ready": False},
                {"category": "friction", "implementation_present": True, "validated": False, "ready": False},
                {"category": "pounding", "implementation_present": True, "validated": False, "ready": False},
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--flexible-diaphragm-report",
            str(paths["diaphragm"]),
            "--substructuring-interface-report",
            str(paths["substructuring"]),
            "--sync-stress-report",
            str(paths["sync"]),
            "--foundation-soil-link-gate-report",
            str(paths["foundation"]),
            "--moving-load-integrator-report",
            str(paths["moving_load"]),
            "--vti-coupled-solver-report",
            str(paths["vti"]),
            "--track-dynamics-dataset-report",
            str(paths["track_dataset"]),
            "--tunnel-dynamics-dataset-report",
            str(paths["tunnel_dataset"]),
            "--panel-zone-clash-report",
            str(paths["panel_zone"]),
            "--ssi-boundary-report",
            str(paths["ssi"]),
            "--soil-tunnel-ssi-report",
            str(paths["soil_tunnel"]),
            "--structural-contact-gate-report",
            str(paths["structural_contact"]),
            "--benchmark-cases",
            f"{paths['cases_a']},{paths['cases_b']},{paths['cases_c']}",
            "--out",
            str(paths["out"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_DIRECT_CONTACT"
    assert payload["checks"]["direct_structural_contact_family_pass"] is False
    assert payload["checks"]["interaction_family_matrix_pass"] is False
    assert payload["checks"]["all_matrix_rows_ready"] is False
    assert payload["summary"]["ready_row_count"] == 6
    assert payload["summary"]["total_row_count"] == 7
    assert payload["summary"]["interaction_family_ready_count"] < payload["summary"]["interaction_family_total_count"]
    assert payload["summary"]["interaction_source_family_ready_count"] == 3
    assert payload["summary"]["interaction_source_family_total_count"] == 3
    assert payload["summary"]["direct_contact_ready_count"] == 3
    assert "modal-transfer=" in payload["summary"]["interaction_family_group_label"]
    assert "kinematic-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "constraint-bridge=" in payload["summary"]["interaction_family_group_label"]
    assert "wave-radiation=" in payload["summary"]["interaction_family_group_label"]
    assert "multiphysics-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "explicit-shear-transfer=" in payload["summary"]["interaction_family_group_label"]
    assert "phase-latency-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "cache-window-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "whitebox-feedback-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "recovery-residual-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "track-slab=" in payload["summary"]["interaction_family_group_label"]
    assert "vehicle-track=" in payload["summary"]["interaction_family_group_label"]
    assert "tunnel-lining-soil=" in payload["summary"]["interaction_family_group_label"]
    assert "joint-panel=" in payload["summary"]["interaction_family_group_label"]
    assert "support-contact-modulation-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "lining-recovery-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "panel-feedback-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert "pressure-mapping-coupling=" in payload["summary"]["interaction_family_group_label"]
    assert (
        f"family_matrix={payload['summary']['interaction_family_ready_count']}/{payload['summary']['interaction_family_total_count']}"
        in payload["summary_line"]
    )
    assert "source_families=3/3" in payload["summary_line"]
    assert f"groups={payload['summary']['interaction_family_group_label']}" in payload["summary_line"]
    assert payload["summary_line"].startswith("Surface interaction benchmark: GAP")
