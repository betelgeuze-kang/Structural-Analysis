from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from implementation.phase1.rc_constitutive_library import (
    ConcreteMaterial,
    bond_slip_cyclic_probe,
    concrete_cyclic_response,
)
from implementation.phase1.rc_constitutive_library import concrete_cyclic_probe
from implementation.phase1.run_material_constitutive_gate import (
    _panel_zone_joint_response_surface,
)

SCRIPT = Path("implementation/phase1/run_material_constitutive_gate.py")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_module():
    spec = importlib.util.spec_from_file_location("run_material_constitutive_gate_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _supporting_ssi_payload() -> dict:
    return {
        "contract_pass": True,
        "checks": {
            "ssi_nonlinear_boundary_active": True,
            "ssi_transfer_finite": True,
            "material_model_pass": True,
            "residual_trace_pass": True,
        },
        "summary": {
            "soil_profile": "dense_sand",
            "nonlinear_ratio_span": 0.18,
        },
        "rows": [
            {"case_id": "SSI-001", "topology_type": "rahmen"},
            {"case_id": "SSI-002", "topology_type": "outrigger"},
            {"case_id": "SSI-003", "topology_type": "wall-frame"},
            {"case_id": "SSI-004", "topology_type": "truss"},
        ],
    }


def _supporting_damper_payload() -> dict:
    return {
        "contract_pass": True,
        "checks": {
            "damper_type_diversity_pass": True,
            "waveform_corr_pass": True,
            "residual_drift_pass": True,
            "material_model_pass": True,
        },
        "summary": {
            "damper_types": ["viscous", "friction", "buckling_restrained"],
            "waveform_corr_min": 0.93,
            "residual_drift_mm_max": 0.42,
        },
    }


def _supporting_foundation_payload() -> dict:
    return {
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
            "soil_link_contract_tokens": [
                "k_radial_N_m2",
                "k_tangential_N_m2",
                "c_radial_Ns_m2",
                "c_tangential_Ns_m2",
            ],
            "foundation_link_model_types": [
                "bearing_bilinear",
                "compression_only_penalty",
                "coulomb_friction",
                "kelvin_voigt_pounding",
                "normal_gap_unilateral",
                "uplift_seat_unilateral",
            ],
        },
    }


def _supporting_contact_payload() -> dict:
    return {
        "contract_pass": True,
        "summary": {
            "validated_category_count": 6,
            "required_category_count": 6,
            "contact_uplift_event_sequence_mismatch": 0,
            "link_model_types": [
                "bearing_bilinear",
                "compression_only_penalty",
                "coulomb_friction",
                "kelvin_voigt_pounding",
                "normal_gap_unilateral",
                "uplift_seat_unilateral",
            ],
        },
        "categories": {
            "gap": {"validated": True, "checks": {"open_gap_zero_force": True}},
            "uplift": {"validated": True, "checks": {"uplift_releases_contact": True}},
            "compression_only": {"validated": True, "checks": {"compression_carries_force": True}},
            "bearing": {"validated": True, "checks": {"elastic_branch_linear": True}},
            "friction": {"validated": True, "checks": {"stick_branch_linear": True}},
            "pounding": {"validated": True, "checks": {"impact_force_kelvin_voigt": True}},
        },
    }


def _supporting_panel_zone_payload() -> dict:
    return {
        "contract_pass": True,
        "checks": {
            "panel_zone_clash_artifact_contract_pass": True,
            "panel_zone_topology_capable_input": True,
            "panel_zone_required_sources_complete": True,
            "panel_zone_topology_projected_bridge_complete": True,
            "panel_zone_internal_engine_complete": True,
            "dataset_contract_pass": True,
            "pbd_contract_pass": True,
        },
        "summary": {
            "panel_zone_clash_row_count": 45,
            "panel_zone_validated_source_row_count_total": 45,
            "panel_zone_source_valid_row_counts": {
                "panel_zone_joint_geometry_3d": 15,
                "panel_zone_rebar_anchorage_3d": 15,
                "panel_zone_clash_verification_3d": 15,
            },
        },
    }


def test_panel_feedback_residual_transfer_bridge_surface_accepts_solver_verified_closeout() -> None:
    module = _load_module()
    surface = module._panel_zone_joint_response_surface(
        {"contract_pass": True},
        {
            "panel_zone_clash_artifact_contract_pass": True,
            "panel_zone_topology_capable_input": True,
            "panel_zone_required_sources_complete": True,
            "panel_zone_topology_projected_bridge_complete": False,
            "panel_zone_solver_verified_bridge_complete": True,
            "panel_zone_true_3d_bridge_complete": False,
            "panel_zone_internal_engine_complete": False,
            "dataset_contract_pass": True,
            "pbd_contract_pass": True,
        },
        {
            "panel_zone_clash_row_count": 45,
            "panel_zone_external_validation_status_label": "verified",
            "panel_zone_source_contract_mode": "true_3d_clash_and_anchorage_verified",
            "panel_zone_validated_source_row_count_total": 3,
            "panel_zone_true_3d_clash_verified": True,
            "panel_zone_true_3d_anchorage_verified": True,
            "panel_zone_external_validation_artifact_closed": True,
        },
    )

    assert surface["bridge_complete"] is True
    assert surface["bridge_mode"] == "solver_verified"
    assert surface["exact_verified_complete"] is True
    assert surface["material_evidence_complete"] is True
    assert surface["family_pass"] is True


def _supporting_panel_zone_verified_payload() -> dict:
    return {
        "contract_pass": True,
        "checks": {
            "panel_zone_clash_artifact_contract_pass": True,
            "panel_zone_topology_capable_input": True,
            "panel_zone_required_sources_complete": True,
            "panel_zone_topology_projected_bridge_complete": False,
            "panel_zone_internal_engine_complete": False,
            "panel_zone_true_3d_bridge_complete": True,
            "panel_zone_solver_verified_bridge_complete": True,
            "panel_zone_true_3d_clash_verified": True,
            "panel_zone_true_3d_anchorage_verified": True,
            "dataset_contract_pass": True,
            "pbd_contract_pass": True,
        },
        "summary": {
            "constructability_mode": "panel_zone_3d_clash_and_anchorage_verified",
            "panel_zone_clash_row_count": 45,
            "panel_zone_validated_source_row_count_total": 3,
            "panel_zone_source_contract_mode": "true_3d_clash_and_anchorage_verified",
            "panel_zone_required_sources_complete": True,
            "panel_zone_topology_projected_bridge_complete": False,
            "panel_zone_solver_verified_bridge_complete": True,
            "panel_zone_true_3d_bridge_complete": True,
            "panel_zone_internal_engine_complete": False,
            "panel_zone_true_3d_clash_verified": True,
            "panel_zone_true_3d_anchorage_verified": True,
            "panel_zone_external_validation_artifact_closed": True,
            "panel_zone_source_valid_row_counts": {
                "panel_zone_joint_geometry_3d": 1,
                "panel_zone_rebar_anchorage_3d": 1,
                "panel_zone_clash_verification_3d": 1,
            },
        },
    }


def _supporting_wind_payload() -> dict:
    return {
        "contract_pass": True,
        "checks": {
            "wind_duration_pass": True,
            "wind_reversal_pass": True,
            "long_series_chunked_pass": True,
            "material_model_pass": True,
            "residual_trace_pass": True,
            "device_artifacts_consumed_pass": True,
        },
        "summary": {
            "duration_hours": 10.0,
            "load_reversal_count": 7560,
            "section_family_coverage_min": 0.96,
            "response_storage": "npz_external+inline_summary",
            "material_model_types": ["steel_elastic_plastic"],
        },
        "rows": [
            {"case_id": "W1", "topology_type": "rahmen"},
            {"case_id": "W2", "topology_type": "outrigger"},
            {"case_id": "W3", "topology_type": "wall-frame"},
            {"case_id": "W4", "topology_type": "truss"},
        ],
    }


def _supporting_vibration_attenuation_payload() -> dict:
    return {
        "contract_pass": True,
        "checks": {
            "substructuring_linked": True,
            "finite_values": True,
            "monotonic_distance_decay": True,
            "high_frequency_decay_stronger": True,
        },
        "metrics": {
            "distance_count": 24,
            "far_field_ratio_63_to_8": 0.028,
        },
    }


def _supporting_vibration_compliance_payload() -> dict:
    return {
        "contract_pass": True,
        "checks": {
            "standard_supported": True,
            "finite_values": True,
            "compliance_ratio_pass": True,
        },
        "metrics": {
            "sample_count": 96,
            "pass_ratio": 1.0,
            "max_velocity_mm_s": 0.032,
        },
    }


def _supporting_track_lf_payload() -> dict:
    return {
        "contract_pass": True,
        "checks": {
            "accuracy_pass": True,
            "rust_kernel_used": True,
            "o_n_operator": True,
            "matrix_free_euler": True,
        },
        "summary": {
            "response_binary_consumer": "dlpack_zero_copy_primary",
            "response_storage": "dlpack_external+inline_summary",
        },
    }


def _supporting_moving_load_payload() -> dict:
    return {
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
    }


def _supporting_vti_payload() -> dict:
    return {
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
    }


def _supporting_track_irregularity_payload() -> dict:
    return {
        "contract_pass": True,
        "metrics": {
            "node_count": 4001,
            "class": "B",
            "preprocess_backend": "rocm_torch_full",
        },
    }


def _supporting_track_dataset_payload() -> dict:
    return {
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
    }


def _supporting_tunnel_dataset_payload() -> dict:
    return {
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
    }


def test_material_constitutive_library_tracks_cyclic_pinching_and_crushing() -> None:
    mat = ConcreteMaterial(fc_mpa=36.0, eps_c0=0.0021, eps_cu=0.0038)
    state = None
    snapshots = []
    for strain in (-0.0015, -0.0042, 0.00012, -0.0028):
        snap = concrete_cyclic_response(strain, state=state, mat=mat)
        snapshots.append(snap)
        state = snap.state

    crushed = snapshots[1]
    reloaded = snapshots[2]

    assert crushed.crushing_ratio > 0.0
    assert "crushing" in crushed.evidence_tags
    assert reloaded.reversal_count >= 1
    assert reloaded.pinching_ratio < 1.0
    assert "pinching" in reloaded.evidence_tags
    assert "degradation" in reloaded.evidence_tags
    assert reloaded.state.history_tag.startswith("cyclic")


def test_panel_zone_joint_response_surface_accepts_true_3d_verified_evidence() -> None:
    payload = _supporting_panel_zone_verified_payload()

    surface = _panel_zone_joint_response_surface(
        payload["contract_pass"],
        payload["checks"],
        payload["summary"],
    )

    assert surface["panel_zone_contract_pass"] is True
    assert surface["artifact_contract_pass"] is True
    assert surface["topology_capable_input"] is True
    assert surface["required_sources_complete"] is True
    assert surface["topology_projected_bridge_complete"] is False
    assert surface["solver_verified_bridge_complete"] is True
    assert surface["true_3d_bridge_complete"] is True
    assert surface["bridge_complete"] is True
    assert surface["bridge_mode"] == "true_3d_verified"
    assert surface["internal_engine_complete"] is False
    assert surface["true_3d_clash_verified"] is True
    assert surface["true_3d_anchorage_verified"] is True
    assert surface["exact_verified_complete"] is True
    assert surface["material_evidence_complete"] is True
    assert surface["material_evidence_mode"] == "true_3d_verified"
    assert surface["source_contract_mode"] == "true_3d_clash_and_anchorage_verified"
    assert surface["family_pass"] is True


def test_material_constitutive_gate_passes_with_damage_cyclic_and_bond_evidence(tmp_path: Path) -> None:
    pushover = tmp_path / "pushover.json"
    ndtha = tmp_path / "ndtha.json"
    rc_lock = tmp_path / "rc_lock.json"
    rc_lock_cases = tmp_path / "rc_benchmark_lock_cases.json"
    nheri_manifest_a = tmp_path / "nheri_case01_source_manifest.json"
    nheri_manifest_b = tmp_path / "nheri_case02_source_manifest.json"
    nheri_manifest_c = tmp_path / "nheri_case03_source_manifest.json"
    construction = tmp_path / "construction.json"
    ssi = tmp_path / "ssi.json"
    damper = tmp_path / "damper.json"
    foundation = tmp_path / "foundation.json"
    contact = tmp_path / "contact.json"
    panel_zone = tmp_path / "panel_zone.json"
    wind = tmp_path / "wind.json"
    vibration_attenuation = tmp_path / "vibration_attenuation.json"
    vibration_compliance = tmp_path / "vibration_compliance.json"
    track_lf = tmp_path / "track_lf.json"
    moving_load = tmp_path / "moving_load.json"
    vti = tmp_path / "vti.json"
    track_irregularity = tmp_path / "track_irregularity.json"
    track_dataset = tmp_path / "track_dataset.json"
    tunnel_dataset = tmp_path / "tunnel_dataset.json"
    vibration_attenuation = tmp_path / "vibration_attenuation.json"
    vibration_compliance = tmp_path / "vibration_compliance.json"
    track_lf = tmp_path / "track_lf.json"
    moving_load = tmp_path / "moving_load.json"
    vti = tmp_path / "vti.json"
    track_irregularity = tmp_path / "track_irregularity.json"
    track_dataset = tmp_path / "track_dataset.json"
    tunnel_dataset = tmp_path / "tunnel_dataset.json"
    cases_a = tmp_path / "cases_a.json"
    cases_b = tmp_path / "cases_b.json"
    cases_c = tmp_path / "cases_c.json"
    cases_d = tmp_path / "commercial_benchmark_cases.kw51_railway_bridge.json"
    cases_e = tmp_path / "commercial_benchmark_cases.opstool_nightly.json"
    cases_f = tmp_path / "commercial_benchmark_cases.json"
    cases_g = tmp_path / "commercial_benchmark_cases.atwood_open.mgt_smoke.json"
    cases_h = tmp_path / "commercial_benchmark_cases.atwood_open.pr_recheck.json"
    cases_i = tmp_path / "commercial_benchmark_cases.atwood_open.mgt_smoke2.json"
    cases_j = tmp_path / "commercial_benchmark_cases.atwood_open.mgt_smoke3.json"
    cases_k = tmp_path / "commercial_benchmark_cases.atwood_open.json"
    cases_l = tmp_path / "commercial_benchmark_cases.atwood_open.explicit_zenodo.json"
    cases_m = tmp_path / "commercial_benchmark_cases.atwood_open.sample_pipeline.json"
    cases_n = tmp_path / "commercial_benchmark_cases.atwood_open.sample_scaleout.json"
    cases_o = tmp_path / "commercial_benchmark_cases.atwood_open.sample.json"
    out = tmp_path / "material_constitutive.json"

    _write(
        pushover,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True},
            "rows": [
                {
                    "case_id": "P1",
                    "topology_type": "wall-frame",
                    "hazard_type": "seismic",
                    "summary": {
                        "material_indices": {
                            "compression_damage_mean": 1.0,
                            "bond_slip_index_mean": 0.98,
                        }
                    },
                },
                {
                    "case_id": "P2",
                    "topology_type": "shell-wall",
                    "hazard_type": "seismic",
                    "summary": {
                        "material_indices": {
                            "compression_damage_mean": 0.64,
                            "bond_slip_index_mean": 0.83,
                        }
                    },
                },
            ],
        },
    )
    _write(
        ndtha,
        {
            "contract_pass": True,
            "checks": {
                "material_model_pass": True,
                "dynamic_reversal_pass": True,
                "plasticity_triggered_all_cases": True,
                "residual_metric_sanity_pass": True,
            },
            "summary": {
                "response_npz_case_count": 2,
                "solver_control_event_count_total": 128,
                "solver_control_recommended_dt_scale_min": 0.5,
            },
            "response_npz": {
                "case_count": 2,
                "series_case_count": 2,
                "full_step_count_max": 960,
                "storage": "npz_external+inline_head",
                "series_contract_pass": True,
            },
            "solver_control": {
                "event_count_total": 128,
                "recommended_dt_scale_min": 0.5,
            },
            "rows": [
                {
                    "case_id": "N1",
                    "topology_type": "wall-frame",
                    "hazard_type": "seismic",
                    "summary": {
                        "response_storage": "npz_external+inline_head",
                        "residual_drift_ratio_pct": 0.25,
                        "raw_residual_drift_ratio_pct": 0.25,
                        "material_indices": {
                            "compression_damage_mean": 0.10,
                            "bond_slip_index_mean": 0.92,
                        },
                    },
                    "artifacts": {"response_storage": "npz"},
                },
                {
                    "case_id": "N2",
                    "topology_type": "frame-core",
                    "hazard_type": "aftershock",
                    "summary": {
                        "response_storage": "hdf5",
                        "residual_drift_ratio_pct": 0.18,
                        "raw_residual_drift_ratio_pct": 0.18,
                        "material_indices": {
                            "compression_damage_mean": 0.06,
                            "bond_slip_index_mean": 0.77,
                        },
                    },
                    "artifacts": {"response_storage": "hdf5"},
                },
            ],
        },
    )
    for manifest in (nheri_manifest_a, nheri_manifest_b, nheri_manifest_c):
        _write(manifest, {"source_family": "nheri_sensor"})
    _write(
        rc_lock,
        {
            "contract_pass": True,
            "checks": {
                "cracking_case_pass": True,
                "bond_slip_case_pass": True,
            },
            "rows": [
                {
                    "case_id": "RC-CRK-001",
                    "benchmark_family": "cyclic_wall_cracking",
                    "case_pass": True,
                    "metric_values": {"cracking_index_mean": 0.98},
                    "metric_checks": {"cracking_index_mean": True},
                },
                {
                    "case_id": "RC-BND-001",
                    "benchmark_family": "bond_slip_pullout",
                    "case_pass": True,
                    "metric_values": {"bond_slip_index_mean": 0.87},
                    "metric_checks": {"bond_slip_index_mean": True},
                },
                {
                    "case_id": "RC-CRP-001",
                    "benchmark_family": "creep_shrinkage_column",
                    "case_pass": True,
                    "metric_values": {"creep_index_mean": 0.96},
                    "metric_checks": {"creep_index_mean": True},
                },
                {
                    "case_id": "RC-SLB-001",
                    "benchmark_family": "slab_wall_interaction",
                    "case_pass": True,
                    "metric_values": {
                        "cracking_index_mean": 0.97,
                        "bond_slip_index_mean": 0.84,
                    },
                    "metric_checks": {
                        "cracking_index_mean": True,
                        "bond_slip_index_mean": True,
                    },
                },
            ],
            "authority_rows": [
                {
                    "case_id": "NHERI-001",
                    "authority_family": "nheri_public_experiment",
                    "source_manifest_path": str(nheri_manifest_a),
                    "case_pass": True,
                    "metric_checks": {"waveform_alignment": True},
                    "integrity_checks": {"manifest_present": True},
                },
                {
                    "case_id": "NHERI-002",
                    "authority_family": "nheri_public_experiment",
                    "source_manifest_path": str(nheri_manifest_b),
                    "case_pass": True,
                    "metric_checks": {"waveform_alignment": True},
                    "integrity_checks": {"manifest_present": True},
                },
                {
                    "case_id": "NHERI-003",
                    "authority_family": "nheri_public_experiment",
                    "source_manifest_path": str(nheri_manifest_c),
                    "case_pass": True,
                    "metric_checks": {"waveform_alignment": True},
                    "integrity_checks": {"manifest_present": True},
                },
            ],
        },
    )
    _write(
        rc_lock_cases,
        {
            "cases": [
                {"case_id": "RC-CRK-001", "benchmark_family": "cyclic_wall_cracking", "expected_ranges": {"cracking_index_mean": [0.95, 1.0]}},
                {"case_id": "RC-BND-001", "benchmark_family": "bond_slip_pullout", "expected_ranges": {"bond_slip_index_mean": [0.8, 1.0]}},
                {"case_id": "RC-CRP-001", "benchmark_family": "creep_shrinkage_column", "expected_ranges": {"creep_index_mean": [0.95, 1.0]}},
                {"case_id": "RC-SLB-001", "benchmark_family": "slab_wall_interaction", "expected_ranges": {"cracking_index_mean": [0.95, 1.0]}},
            ]
        },
    )
    _write(
        construction,
        {
            "contract_pass": True,
            "checks": {
                "creep_shrinkage_applied": True,
                "differential_shortening_detected": True,
            },
            "summary": {
                "mean_creep_index": 1.0,
                "mean_shrinkage_index": 0.617,
                "max_differential_shortening_mm": 18.2,
            },
        },
    )
    _write(ssi, _supporting_ssi_payload())
    _write(damper, _supporting_damper_payload())
    _write(foundation, _supporting_foundation_payload())
    _write(contact, _supporting_contact_payload())
    _write(panel_zone, _supporting_panel_zone_payload())
    _write(wind, _supporting_wind_payload())
    _write(vibration_attenuation, _supporting_vibration_attenuation_payload())
    _write(vibration_compliance, _supporting_vibration_compliance_payload())
    _write(track_lf, _supporting_track_lf_payload())
    _write(moving_load, _supporting_moving_load_payload())
    _write(vti, _supporting_vti_payload())
    _write(track_irregularity, _supporting_track_irregularity_payload())
    _write(track_dataset, _supporting_track_dataset_payload())
    _write(tunnel_dataset, _supporting_tunnel_dataset_payload())
    _write(vibration_attenuation, _supporting_vibration_attenuation_payload())
    _write(vibration_compliance, _supporting_vibration_compliance_payload())
    _write(track_lf, _supporting_track_lf_payload())
    _write(moving_load, _supporting_moving_load_payload())
    _write(vti, _supporting_vti_payload())
    _write(track_irregularity, _supporting_track_irregularity_payload())
    _write(track_dataset, _supporting_track_dataset_payload())
    _write(tunnel_dataset, _supporting_tunnel_dataset_payload())
    for path, source_family in (
        (cases_a, "rwth_zenodo"),
        (cases_b, "commercial_export"),
        (cases_c, "opstool_606m_megatall_model"),
    ):
        _write(
            path,
            {
                "cases": [
                    {
                        "case_id": f"{source_family}-wall",
                        "source_family": source_family,
                        "topology_type": "wall-frame",
                        "element_mix": "shell_beam_mix",
                    },
                    {
                        "case_id": f"{source_family}-out",
                        "source_family": source_family,
                        "topology_type": "outrigger",
                        "element_mix": "shell_beam_mix",
                    },
                ]
            },
        )
    _write(
        cases_d,
        {
            "source": {
                "candidate_id": "zenodo_kw51_railway_bridge_monitoring_2025",
                "catalog_entry": {"id": "zenodo_kw51_railway_bridge_monitoring_2025"},
            },
            "cases": [{"case_id": "KW51-001", "topology_type": "wall-frame"}, {"case_id": "KW51-002", "topology_type": "outrigger"}],
        },
    )
    _write(cases_e, {"cases": [{"case_id": "OPS-NIGHT-001", "topology_type": "wall-frame"}, {"case_id": "OPS-NIGHT-002", "topology_type": "outrigger"}]})
    _write(cases_f, {"cases": [{"case_id": "LEG-001", "topology_type": "wall-frame"}, {"case_id": "LEG-002", "topology_type": "outrigger"}]})
    _write(cases_g, {"cases": [{"case_id": "ATW-SMOKE-001", "topology_type": "wall-frame"}, {"case_id": "ATW-SMOKE-002", "topology_type": "outrigger"}]})
    _write(cases_h, {"cases": [{"case_id": "ATW-PR-001", "topology_type": "wall-frame"}, {"case_id": "ATW-PR-002", "topology_type": "outrigger"}]})
    _write(cases_i, {"cases": [{"case_id": "ATW-SMOKE2-001", "topology_type": "wall-frame"}, {"case_id": "ATW-SMOKE2-002", "topology_type": "outrigger"}]})
    _write(cases_j, {"cases": [{"case_id": "ATW-SMOKE3-001", "topology_type": "wall-frame"}, {"case_id": "ATW-SMOKE3-002", "topology_type": "outrigger"}]})
    _write(cases_k, {"cases": [{"case_id": "ATWOOD-00001", "topology_type": "wall-frame"}, {"case_id": "ATWOOD-00002", "topology_type": "outrigger"}]})
    _write(
        cases_l,
        {
            "cases": [
                {
                    "case_id": "OPEN_STRUCT-00001",
                    "source_family": "zenodo_atwood_highrise_shm_2025",
                    "topology_type": "wall-frame",
                    "element_mix": "shell_beam_mix",
                },
                {
                    "case_id": "OPEN_STRUCT-00002",
                    "source_family": "zenodo_atwood_highrise_shm_2025",
                    "topology_type": "outrigger",
                    "element_mix": "shell_beam_mix",
                },
            ]
        },
    )
    _write(
        cases_m,
        {
            "cases": [
                {"case_id": "ATWOOD-SAMPLE-PIPE-001", "topology_type": "wall-frame"},
                {"case_id": "ATWOOD-SAMPLE-PIPE-002", "topology_type": "outrigger"},
            ]
        },
    )
    _write(
        cases_n,
        {
            "cases": [
                {"case_id": "ATWOOD-SAMPLE-SCALE-001", "topology_type": "wall-frame"},
                {"case_id": "ATWOOD-SAMPLE-SCALE-002", "topology_type": "outrigger"},
            ]
        },
    )
    _write(
        cases_o,
        {
            "cases": [
                {"case_id": "ATWOOD-SAMPLE-001", "topology_type": "wall-frame"},
                {"case_id": "ATWOOD-SAMPLE-002", "topology_type": "outrigger"},
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--pushover-stress-report",
            str(pushover),
            "--ndtha-stress-report",
            str(ndtha),
            "--rc-benchmark-lock-report",
            str(rc_lock),
            "--rc-benchmark-lock-cases",
            str(rc_lock_cases),
            "--construction-sequence-report",
            str(construction),
            "--ssi-boundary-report",
            str(ssi),
            "--damper-validation-report",
            str(damper),
            "--foundation-soil-link-gate-report",
            str(foundation),
            "--structural-contact-validation-report",
            str(contact),
            "--panel-zone-clash-report",
            str(panel_zone),
            "--wind-time-history-gate-report",
            str(wind),
            "--vibration-attenuation-report",
            str(vibration_attenuation),
            "--vibration-compliance-report",
            str(vibration_compliance),
            "--track-lf-solver-report",
            str(track_lf),
            "--moving-load-integrator-report",
            str(moving_load),
            "--vti-coupled-solver-report",
            str(vti),
            "--track-irregularity-report",
            str(track_irregularity),
            "--track-dynamics-dataset-report",
            str(track_dataset),
            "--tunnel-dynamics-dataset-report",
            str(tunnel_dataset),
            "--benchmark-cases",
            (
                f"{cases_a},{cases_b},{cases_c},{cases_d},{cases_e},{cases_f},{cases_g},"
                f"{cases_h},{cases_i},{cases_j},{cases_k},{cases_l},{cases_m},{cases_n},{cases_o}"
            ),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    expected_probe = concrete_cyclic_probe()
    expected_bond_probe = bond_slip_cyclic_probe()
    assert payload["contract_pass"] is True
    assert payload["checks"]["concrete_damage_pass"] is True
    assert payload["checks"]["concrete_damage_library_state_pass"] is True
    assert payload["checks"]["concrete_damage_library_residual_pass"] is True
    assert payload["checks"]["cyclic_degradation_pass"] is True
    assert payload["checks"]["cyclic_library_state_coverage_pass"] is True
    assert payload["checks"]["cyclic_library_damage_tags_pass"] is True
    assert payload["checks"]["cyclic_step_series_pass"] is True
    assert payload["checks"]["cyclic_wall_slab_step_series_pass"] is True
    assert payload["checks"]["cyclic_rc_step_series_pass"] is True
    assert payload["checks"]["bond_interface_pass"] is True
    assert payload["checks"]["bond_interface_library_state_pass"] is True
    assert payload["checks"]["bond_interface_library_residual_pass"] is True
    assert payload["checks"]["bond_interface_library_symmetry_pass"] is True
    assert payload["checks"]["bond_interface_library_cyclic_reversal_pass"] is True
    assert payload["checks"]["bond_interface_library_cyclic_deterioration_pass"] is True
    assert payload["checks"]["creep_shrinkage_pass"] is True
    assert payload["checks"]["soil_boundary_nonlinear_pass"] is True
    assert payload["checks"]["device_dissipation_pass"] is True
    assert payload["checks"]["foundation_impedance_nonlinear_pass"] is True
    assert payload["checks"]["contact_link_hysteresis_pass"] is True
    assert payload["checks"]["panel_zone_joint_response_pass"] is True
    assert payload["checks"]["panel_zone_joint_response_bridge_ready_pass"] is True
    assert payload["checks"]["panel_zone_joint_response_material_evidence_pass"] is True
    assert payload["checks"]["wind_dynamic_response_pass"] is True
    assert payload["checks"]["track_support_viscoelasticity_pass"] is True
    assert payload["checks"]["vehicle_track_transient_coupling_pass"] is True
    assert payload["checks"]["tunnel_soil_wave_attenuation_pass"] is True
    assert payload["checks"]["serviceability_velocity_response_pass"] is True
    assert payload["checks"]["construction_stage_redistribution_pass"] is True
    assert payload["checks"]["joint_constraint_transfer_pass"] is True
    assert payload["checks"]["aeroelastic_serviceability_pass"] is True
    assert payload["checks"]["calibration_matrix_pass"] is True
    assert payload["summary"]["concrete_damage_row_count"] == 4
    assert payload["summary"]["concrete_damage_library_state_tag_count"] == 5
    assert payload["summary"]["concrete_damage_library_state_tags"] == [
        "compression_crushed",
        "compression_hardening",
        "compression_softening",
        "tension_elastic",
        "tension_softening",
    ]
    assert abs(payload["summary"]["concrete_damage_library_residual_strength_ratio"] - 0.2) < 1.0e-9
    assert payload["summary"]["cyclic_degradation_row_count"] == 2
    assert payload["summary"]["cyclic_library_evidence_present"] is True
    assert payload["summary"]["cyclic_library_probe_id"] == "rc_concrete_cyclic_probe_v1"
    assert payload["summary"]["cyclic_library_reversal_count"] == expected_probe.reversal_count
    assert payload["summary"]["cyclic_library_restoring_state_tag_count"] == 4
    assert payload["summary"]["cyclic_library_envelope_state_tag_count"] == 4
    assert payload["summary"]["cyclic_library_min_pinching_ratio"] < 1.0
    assert payload["summary"]["cyclic_library_max_crushing_ratio"] > 0.0
    assert payload["summary"]["cyclic_library_evidence_tag_count"] == len(expected_probe.evidence_tags)
    assert payload["summary"]["cyclic_step_series_evidence_present"] is True
    assert payload["summary"]["cyclic_step_series_source_mode"] == "ndtha_response_npz"
    assert payload["summary"]["cyclic_step_series_response_case_count"] == 2
    assert payload["summary"]["cyclic_step_series_case_count"] == 2
    assert payload["summary"]["cyclic_step_series_depth"] == 960
    assert payload["summary"]["cyclic_step_series_coverage_ratio"] == 1.0
    assert payload["summary"]["cyclic_step_series_solver_event_count"] == 128
    assert payload["summary"]["cyclic_step_series_solver_event_density"] == 128 / (960 * 2)
    assert payload["summary"]["cyclic_step_series_recommended_dt_scale_min"] == 0.5
    assert payload["summary"]["cyclic_step_series_storage_mode_count"] == 2
    assert payload["summary"]["cyclic_wall_slab_step_series_case_count"] == 1
    assert payload["summary"]["cyclic_wall_slab_step_series_coverage_ratio"] == 1.0
    assert payload["summary"]["cyclic_rc_step_series_case_count"] == 2
    assert payload["summary"]["cyclic_rc_step_series_density"] == 480.0
    assert payload["summary"]["cyclic_rc_step_series_family_labels"] == [
        "cyclic_wall_cracking",
        "slab_wall_interaction",
    ]
    assert payload["summary"]["bond_interface_row_count"] == 4
    assert payload["summary"]["bond_interface_library_state_tag_count"] == 3
    assert payload["summary"]["bond_interface_library_state_tags"] == [
        "bond_elastic",
        "bond_residual",
        "bond_softening",
    ]
    assert abs(payload["summary"]["bond_interface_library_residual_force_ratio"] - 0.25) < 1.0e-9
    assert payload["summary"]["bond_interface_library_symmetry_error_ratio"] == 0.0
    assert payload["summary"]["bond_interface_cyclic_evidence_present"] is True
    assert payload["summary"]["bond_interface_cyclic_probe_id"] == expected_bond_probe.probe_id
    assert payload["summary"]["bond_interface_cyclic_reversal_count"] == expected_bond_probe.reversal_count
    assert payload["summary"]["bond_interface_cyclic_unloading_observed"] is True
    assert payload["summary"]["bond_interface_cyclic_residual_observed"] is True
    assert payload["summary"]["bond_interface_cyclic_degradation_observed"] is True
    assert payload["summary"]["bond_interface_cyclic_min_unloading_stiffness_ratio"] < 1.0
    assert payload["summary"]["bond_interface_cyclic_max_strength_degradation"] > 0.0
    assert payload["summary"]["bond_interface_cyclic_max_slip_ratio"] > 1.0
    assert payload["summary"]["bond_interface_cyclic_terminal_residual_force_ratio"] > 0.0
    assert payload["summary"]["bond_interface_cyclic_evidence_tag_count"] == len(expected_bond_probe.evidence_tags)
    assert payload["summary"]["creep_shrinkage_row_count"] == 7
    assert payload["summary"]["soil_boundary_nonlinear_row_count"] == 11
    assert payload["summary"]["device_dissipation_row_count"] == 10
    assert payload["summary"]["foundation_impedance_nonlinear_row_count"] == 19
    assert payload["summary"]["contact_link_hysteresis_row_count"] == 15
    assert payload["summary"]["panel_zone_joint_response_row_count"] == 12
    assert payload["summary"]["panel_zone_joint_response_bridge_mode"] == "topology_projected"
    assert payload["summary"]["panel_zone_joint_response_material_evidence_mode"] == "internal_engine"
    assert payload["summary"]["panel_zone_joint_response_exact_verified_complete"] is False
    assert payload["summary"]["wind_dynamic_response_row_count"] == 16
    assert payload["summary"]["track_support_viscoelasticity_row_count"] == 11
    assert payload["summary"]["vehicle_track_transient_coupling_row_count"] == 19
    assert payload["summary"]["tunnel_soil_wave_attenuation_row_count"] == 13
    assert payload["summary"]["serviceability_velocity_response_row_count"] == 8
    assert payload["summary"]["construction_stage_redistribution_row_count"] >= 6
    assert payload["summary"]["joint_constraint_transfer_row_count"] >= 5
    assert payload["summary"]["aeroelastic_serviceability_row_count"] >= 7
    family_counts = payload["summary"]["calibration_matrix_family_counts"]
    assert family_counts["concrete_damage"] == 47
    assert family_counts["cyclic_degradation"] == 46
    assert family_counts["bond_interface"] == 47
    assert family_counts["serviceability_velocity_response"] == 8
    assert family_counts["construction_stage_redistribution"] >= 6
    assert family_counts["joint_constraint_transfer"] >= 5
    assert family_counts["aeroelastic_serviceability"] >= 7
    assert "construction_stage_redistribution=" in payload["summary"]["calibration_matrix_group_label"]
    assert "joint_constraint_transfer=" in payload["summary"]["calibration_matrix_group_label"]
    assert "aeroelastic_serviceability=" in payload["summary"]["calibration_matrix_group_label"]
    assert "phase_latency_projection=" in payload["summary"]["calibration_matrix_group_label"]
    assert "cache_window_adaptation=" in payload["summary"]["calibration_matrix_group_label"]
    assert "whitebox_feedback_stitching=" in payload["summary"]["calibration_matrix_group_label"]
    assert "recovery_residual_relock=" in payload["summary"]["calibration_matrix_group_label"]
    assert "zenodo_kw51_railway_bridge_monitoring_2025" in payload["summary"]["source_family_labels"]
    assert "atwood_open.sample" in payload["summary"]["source_family_labels"]
    assert payload["summary"]["benchmark_lock_physical_family_labels"] == [
        "bond_slip_pullout",
        "creep_shrinkage_column",
        "cyclic_wall_cracking",
        "slab_wall_interaction",
    ]
    assert len(payload["summary"]["source_family_labels"]) >= 20
    assert {
        "creep_shrinkage_column",
        "cyclic_wall_cracking",
        "slab_wall_interaction",
    }.issubset(payload["summary"]["calibration_matrix_family_source_families"]["concrete_damage"])
    assert "nheri_sensor" in payload["summary"]["calibration_matrix_family_source_families"]["cyclic_degradation"]
    assert "bond_slip_pullout" in payload["summary"]["calibration_matrix_family_source_families"]["bond_interface"]
    assert payload["summary"]["calibration_matrix_family_coverage"]["concrete_damage"] == {
        "source_count": 2, "source_family_count": 19, "topology_count": 3, "hazard_count": 2
    }
    assert payload["summary"]["calibration_matrix_family_coverage"]["cyclic_degradation"] == {
        "source_count": 1,
        "source_family_count": 18,
        "topology_count": 2,
        "hazard_count": 2,
        "response_storage_count": 2,
        "library_probe_present": 1,
        "library_tag_count": len(expected_probe.evidence_tags),
        "library_reversal_count": expected_probe.reversal_count,
        "step_series_case_count": 2,
        "step_series_depth": 960,
        "wall_slab_case_count": 1,
        "rc_case_count": 2,
        "step_series_storage_mode_count": 2,
    }
    assert payload["summary"]["calibration_matrix_family_coverage"]["bond_interface"] == {
        "source_count": 2, "source_family_count": 18, "topology_count": 3, "hazard_count": 2
    }
    assert payload["summary"]["calibration_matrix_family_coverage"]["creep_shrinkage"]["source_family_count"] >= 17
    assert payload["summary"]["calibration_matrix_family_coverage"]["soil_boundary_nonlinear"]["source_family_count"] >= 15
    assert payload["summary"]["calibration_matrix_family_coverage"]["device_dissipation"]["source_family_count"] >= 18
    assert payload["summary"]["calibration_matrix_family_coverage"]["foundation_impedance_nonlinear"]["source_count"] == 1
    assert payload["summary"]["calibration_matrix_family_coverage"]["foundation_impedance_nonlinear"]["source_family_count"] >= 21
    assert payload["summary"]["calibration_matrix_family_coverage"]["foundation_impedance_nonlinear"]["link_model_type_count"] == 6
    assert payload["summary"]["calibration_matrix_family_coverage"]["foundation_impedance_nonlinear"]["soil_link_token_count"] == 4
    assert payload["summary"]["calibration_matrix_family_coverage"]["contact_link_hysteresis"]["source_count"] == 1
    assert payload["summary"]["calibration_matrix_family_coverage"]["contact_link_hysteresis"]["source_family_count"] >= 22
    assert payload["summary"]["calibration_matrix_family_coverage"]["contact_link_hysteresis"]["category_count"] == 6
    assert payload["summary"]["calibration_matrix_family_coverage"]["contact_link_hysteresis"]["link_model_type_count"] == 6
    assert payload["summary"]["calibration_matrix_family_coverage"]["panel_zone_joint_response"]["source_count"] == 1
    assert payload["summary"]["calibration_matrix_family_coverage"]["wind_dynamic_response"]["source_count"] == 1
    assert payload["summary"]["calibration_matrix_family_coverage"]["wind_dynamic_response"]["source_family_count"] >= 18
    assert payload["summary"]["calibration_matrix_family_coverage"]["wind_dynamic_response"]["topology_count"] == 4
    assert payload["summary"]["calibration_matrix_family_coverage"]["wind_dynamic_response"]["material_model_count"] == 1
    assert payload["summary"]["calibration_matrix_family_coverage"]["track_support_viscoelasticity"]["source_count"] == 2
    assert payload["summary"]["calibration_matrix_family_coverage"]["track_support_viscoelasticity"]["source_family_count"] >= 18
    assert payload["summary"]["calibration_matrix_family_coverage"]["vehicle_track_transient_coupling"]["source_count"] == 3
    assert payload["summary"]["calibration_matrix_family_coverage"]["vehicle_track_transient_coupling"]["source_family_count"] >= 18
    assert payload["summary"]["calibration_matrix_family_coverage"]["tunnel_soil_wave_attenuation"]["source_count"] == 2
    assert payload["summary"]["calibration_matrix_family_coverage"]["serviceability_velocity_response"]["source_count"] == 2
    assert payload["summary"]["calibration_matrix_family_coverage"]["construction_stage_redistribution"]["source_count"] == 1
    assert payload["summary"]["calibration_matrix_family_coverage"]["joint_constraint_transfer"]["source_count"] == 1
    assert payload["summary"]["calibration_matrix_family_coverage"]["aeroelastic_serviceability"]["source_count"] == 2
    assert payload["summary"]["calibration_matrix_family_coverage"]["panel_feedback_residual_transfer"]["source_count"] == 3
    assert payload["summary"]["calibration_matrix_family_coverage"]["panel_feedback_residual_transfer"]["bridge_mode"] == "topology_projected"
    assert payload["summary"]["calibration_matrix_family_coverage"]["panel_feedback_residual_transfer"]["bridge_ready"] == 1
    expected_total_rows = sum(payload["summary"]["calibration_matrix_family_counts"].values())
    assert payload["summary"]["calibration_matrix_pass_row_count"] == expected_total_rows
    matrix = payload["evidence"]["calibration_matrix"]
    assert payload["evidence"]["calibration_benchmark_matrix"]["total_rows"] == expected_total_rows
    assert matrix["total_rows"] == expected_total_rows
    assert matrix["total_pass_rows"] == expected_total_rows
    assert any(row["row_id"] == "concrete_damage:benchmark:rc_cracking_lock" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:benchmark:construction_continuity" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:coverage:topology:frame-core" for row in matrix["rows"])
    assert any(row["row_id"] == "cyclic_degradation:coverage:response_storage:hdf5" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:coverage:hazard:aftershock" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:source_family:rwth-zenodo:case_volume" for row in matrix["rows"])
    assert any(row["row_id"] == "cyclic_degradation:source_family:commercial-export:dynamic_topology" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:source_family:opstool-606m-megatall-model:shell_mix" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:source_family:kw51-railway-bridge:case_volume" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:source_family:atwood-open-sample:shell_mix" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:source_family:opstool-nightly:shell_mix" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:source_family:commercial-benchmark-cases:case_volume" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:source_family:atwood-open-mgt-smoke:shell_mix" for row in matrix["rows"])
    assert any(row["row_id"] == "cyclic_degradation:source_family:atwood-open-pr-recheck:dynamic_topology" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:source_family:atwood-open-mgt-smoke2:case_volume" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:source_family:atwood-open-mgt-smoke3:shell_mix" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:source_family:atwood-open:case_volume" for row in matrix["rows"])
    assert any(row["row_id"] == "cyclic_degradation:source_family:zenodo-atwood-highrise-shm-2025:dynamic_topology" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:source_family:atwood-open-sample-pipeline:case_volume" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:source_family:atwood-open-sample-scaleout:shell_mix" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:benchmark_family:cyclic-wall-cracking:rc_lock" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:benchmark_family:creep-shrinkage-column:rc_lock" for row in matrix["rows"])
    assert any(row["row_id"] == "concrete_damage:benchmark_family:slab-wall-interaction:rc_lock" for row in matrix["rows"])
    assert any(row["row_id"] == "cyclic_degradation:benchmark_family:cyclic-wall-cracking:rc_lock" for row in matrix["rows"])
    assert any(row["row_id"] == "cyclic_degradation:authority_source_family:nheri-sensor:waveform_lock" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:benchmark_family:bond-slip-pullout:rc_lock" for row in matrix["rows"])
    assert any(row["row_id"] == "bond_interface:benchmark_family:slab-wall-interaction:rc_lock" for row in matrix["rows"])
    assert any(row["row_id"] == "creep_shrinkage:summary:mean_creep_index" for row in matrix["rows"])
    assert any(row["row_id"] == "soil_boundary_nonlinear:coverage:topology:truss" for row in matrix["rows"])
    assert any(row["row_id"].startswith("device_dissipation:damper_type:") for row in matrix["rows"])
    assert any(row["row_id"] == "foundation_impedance_nonlinear:gate:impedance_schema_ready" for row in matrix["rows"])
    assert any(row["row_id"] == "contact_link_hysteresis:category:friction" for row in matrix["rows"])
    assert any(row["row_id"] == "panel_zone_joint_response:gate:internal_engine_complete" for row in matrix["rows"])
    panel_zone_bridge_row = next(
        row for row in matrix["rows"] if row["row_id"] == "panel_zone_joint_response:gate:topology_projected_bridge_complete"
    )
    assert panel_zone_bridge_row["context"]["bridge_mode"] == "topology_projected"
    panel_zone_material_row = next(
        row for row in matrix["rows"] if row["row_id"] == "panel_zone_joint_response:gate:internal_engine_complete"
    )
    assert panel_zone_material_row["context"]["material_evidence_mode"] == "internal_engine"
    assert any(row["row_id"] == "wind_dynamic_response:summary:response_storage" for row in matrix["rows"])
    assert any(row["row_id"] == "track_support_viscoelasticity:gate:matrix_free_euler" for row in matrix["rows"])
    assert any(row["row_id"] == "vehicle_track_transient_coupling:gate:adaptive_newton_converged_pass" for row in matrix["rows"])
    assert any(row["row_id"] == "tunnel_soil_wave_attenuation:gate:high_frequency_decay_stronger" for row in matrix["rows"])
    assert any(row["row_id"] == "serviceability_velocity_response:gate:compliance_ratio_pass" for row in matrix["rows"])
    assert any(row["row_id"] == "construction_stage_redistribution:gate:differential_shortening_detected" for row in matrix["rows"])
    assert any(row["row_id"] == "joint_constraint_transfer:gate:internal_engine_complete" for row in matrix["rows"])
    assert any(row["row_id"] == "aeroelastic_serviceability:gate:compliance_ratio_pass" for row in matrix["rows"])
    concrete_damage_library = payload["evidence"]["concrete_damage_library_evidence"]
    assert concrete_damage_library["source"].endswith("concrete_response")
    assert concrete_damage_library["library_evidence_pass"] is True
    cyclic_probe = payload["evidence"]["cyclic_library_evidence"]
    assert cyclic_probe["source"].endswith("concrete_cyclic_probe")
    assert cyclic_probe["probe_id"] == expected_probe.probe_id
    assert cyclic_probe["reversal_count"] == expected_probe.reversal_count
    assert cyclic_probe["restoring_state_tag_count"] == 4
    assert cyclic_probe["envelope_state_tag_count"] == 4
    assert cyclic_probe["pinching_observed"] is True
    assert cyclic_probe["crushing_observed"] is True
    assert cyclic_probe["degradation_observed"] is True
    assert cyclic_probe["evidence_tags"] == list(expected_probe.evidence_tags)
    cyclic_step_series = payload["evidence"]["cyclic_step_series_evidence"]
    assert cyclic_step_series["source"] == "nonlinear_ndtha_stress_report"
    assert cyclic_step_series["source_mode"] == "ndtha_response_npz"
    assert cyclic_step_series["response_case_count"] == 2
    assert cyclic_step_series["series_case_count"] == 2
    assert cyclic_step_series["step_series_depth"] == 960
    assert cyclic_step_series["wall_slab_case_count"] == 1
    assert cyclic_step_series["rc_case_count"] == 2
    assert cyclic_step_series["series_link_pass"] is True
    assert cyclic_step_series["wall_slab_series_pass"] is True
    assert cyclic_step_series["rc_series_link_pass"] is True
    assert "step_series" in cyclic_step_series["evidence_tags"]
    assert "wall_slab" in cyclic_step_series["evidence_tags"]
    assert "rc_lock" in cyclic_step_series["evidence_tags"]
    bond_library = payload["evidence"]["bond_interface_library_evidence"]
    assert bond_library["source"].endswith("bond_slip_response")
    assert bond_library["library_evidence_pass"] is True
    bond_cyclic = payload["evidence"]["bond_interface_cyclic_evidence"]
    assert bond_cyclic["source"].endswith("bond_slip_cyclic_probe")
    assert bond_cyclic["probe_id"] == expected_bond_probe.probe_id
    assert bond_cyclic["reversal_count"] == expected_bond_probe.reversal_count
    assert bond_cyclic["unloading_observed"] is True
    assert bond_cyclic["residual_observed"] is True
    assert bond_cyclic["degradation_observed"] is True
    assert bond_cyclic["evidence_tags"] == list(expected_bond_probe.evidence_tags)
    panel_zone_surface = payload["evidence"]["panel_zone_joint_response_gate_surface"]
    assert panel_zone_surface["bridge_mode"] == "topology_projected"
    assert panel_zone_surface["material_evidence_mode"] == "internal_engine"
    assert panel_zone_surface["exact_verified_complete"] is False
    assert payload["summary_line"].startswith("Material constitutive gate: PASS")
    assert f"matrix={expected_total_rows}/{expected_total_rows}" in payload["summary_line"]
    assert (
        "cyclic_degradation=yes(matrix=46/46,residual_max=0.250%,"
        f"lib=rev{expected_probe.reversal_count}/pinch{expected_probe.min_pinching_ratio:.2f}/"
        f"crush{expected_probe.max_crushing_ratio:.2f}/series=2/2@960/wall=1/rc=2)"
    ) in payload["summary_line"]
    assert "creep_shrinkage=yes(matrix=7/7" in payload["summary_line"]
    assert "soil_boundary_nonlinear=yes(matrix=11/11" in payload["summary_line"]
    assert "device_dissipation=yes(matrix=10/10" in payload["summary_line"]
    assert "foundation_impedance_nonlinear=yes(matrix=19/19" in payload["summary_line"]
    assert "contact_link_hysteresis=yes(matrix=15/15" in payload["summary_line"]
    assert "panel_zone_joint_response=yes(matrix=12/12" in payload["summary_line"]
    assert "wind_dynamic_response=yes(matrix=16/16" in payload["summary_line"]
    assert "track_support_viscoelasticity=yes(matrix=11/11" in payload["summary_line"]
    assert "vehicle_track_transient_coupling=yes(matrix=19/19" in payload["summary_line"]
    assert "tunnel_soil_wave_attenuation=yes(matrix=13/13" in payload["summary_line"]
    assert "serviceability_velocity_response=yes(matrix=8/8" in payload["summary_line"]
    assert "construction_stage_redistribution=yes(matrix=" in payload["summary_line"]
    assert "joint_constraint_transfer=yes(matrix=" in payload["summary_line"]
    assert "aeroelastic_serviceability=yes(matrix=" in payload["summary_line"]
    assert "heterogeneous_soil_adaptation=yes(matrix=" in payload["summary_line"]
    assert "segment_joint_softening=yes(matrix=" in payload["summary_line"]
    assert "longitudinal_wave_strain_transfer=yes(matrix=" in payload["summary_line"]
    assert "raw_pressure_field_mapping=yes(matrix=" in payload["summary_line"]
    assert "rail_support_contact_modulation=" in payload["summary"]["calibration_matrix_group_label"]
    assert "tunnel_lining_interface_recovery=" in payload["summary"]["calibration_matrix_group_label"]
    assert "panel_feedback_residual_transfer=" in payload["summary"]["calibration_matrix_group_label"]
    assert payload["summary"]["panel_feedback_residual_transfer_row_count"] == payload["summary"]["calibration_matrix_family_counts"]["panel_feedback_residual_transfer"]
    assert payload["summary"]["panel_feedback_residual_transfer_pass_row_count"] == payload["summary"]["calibration_matrix_family_pass_counts"]["panel_feedback_residual_transfer"]
    assert payload["summary"]["panel_feedback_residual_transfer_bridge_mode"] == "topology_projected"
    assert payload["summary"]["panel_feedback_residual_transfer_bridge_ready"] is True
    panel_feedback_rows = matrix["families"]["panel_feedback_residual_transfer"]
    assert len(panel_feedback_rows) == 5
    bridge_row = next(row for row in panel_feedback_rows if row["metric"] == "panel_feedback_bridge_complete")
    assert bridge_row["pass"] is True
    assert bridge_row["context"]["bridge_mode"] == "topology_projected"
    assert "wind_pressure_coupled_transfer=" in payload["summary"]["calibration_matrix_group_label"]
    assert "coverage=cd[t=3,h=2,s=2,sf=19],cyc[t=2,h=2,store=2,sf=18],bond[t=3,h=2,s=2,sf=18]" in payload["summary_line"]
    assert "core=cd[states=5,res=0.20],cyc[states=4,tags=7],bond[states=3,slip=1.14,res=0.25]" in payload["summary_line"]


def test_material_constitutive_gate_fails_when_bond_interface_is_missing(tmp_path: Path) -> None:
    pushover = tmp_path / "pushover.json"
    ndtha = tmp_path / "ndtha.json"
    rc_lock = tmp_path / "rc_lock.json"
    construction = tmp_path / "construction.json"
    ssi = tmp_path / "ssi.json"
    damper = tmp_path / "damper.json"
    foundation = tmp_path / "foundation.json"
    contact = tmp_path / "contact.json"
    panel_zone = tmp_path / "panel_zone.json"
    wind = tmp_path / "wind.json"
    vibration_attenuation = tmp_path / "vibration_attenuation.json"
    vibration_compliance = tmp_path / "vibration_compliance.json"
    track_lf = tmp_path / "track_lf.json"
    moving_load = tmp_path / "moving_load.json"
    vti = tmp_path / "vti.json"
    track_irregularity = tmp_path / "track_irregularity.json"
    track_dataset = tmp_path / "track_dataset.json"
    tunnel_dataset = tmp_path / "tunnel_dataset.json"
    cases = tmp_path / "cases.json"
    out = tmp_path / "material_constitutive.json"

    _write(
        pushover,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True},
            "rows": [
                {
                    "case_id": "P1",
                    "summary": {"material_indices": {"compression_damage_mean": 1.0, "bond_slip_index_mean": 0.0}},
                }
            ],
        },
    )
    _write(
        ndtha,
        {
            "contract_pass": True,
            "checks": {
                "material_model_pass": True,
                "dynamic_reversal_pass": True,
                "plasticity_triggered_all_cases": True,
                "residual_metric_sanity_pass": True,
            },
            "rows": [
                {
                    "case_id": "N1",
                    "summary": {
                        "residual_drift_ratio_pct": 0.25,
                        "raw_residual_drift_ratio_pct": 0.25,
                        "material_indices": {"compression_damage_mean": 0.10, "bond_slip_index_mean": 0.0},
                    },
                }
            ],
        },
    )
    _write(rc_lock, {"contract_pass": True, "checks": {"cracking_case_pass": True, "bond_slip_case_pass": False}})
    _write(
        construction,
        {
            "contract_pass": True,
            "checks": {
                "creep_shrinkage_applied": True,
                "differential_shortening_detected": True,
            },
            "summary": {
                "mean_creep_index": 1.0,
                "mean_shrinkage_index": 0.617,
                "max_differential_shortening_mm": 18.2,
            },
        },
    )
    _write(ssi, _supporting_ssi_payload())
    _write(damper, _supporting_damper_payload())
    _write(foundation, _supporting_foundation_payload())
    _write(contact, _supporting_contact_payload())
    _write(panel_zone, _supporting_panel_zone_payload())
    _write(wind, _supporting_wind_payload())
    _write(vibration_attenuation, _supporting_vibration_attenuation_payload())
    _write(vibration_compliance, _supporting_vibration_compliance_payload())
    _write(track_lf, _supporting_track_lf_payload())
    _write(moving_load, _supporting_moving_load_payload())
    _write(vti, _supporting_vti_payload())
    _write(track_irregularity, _supporting_track_irregularity_payload())
    _write(track_dataset, _supporting_track_dataset_payload())
    _write(tunnel_dataset, _supporting_tunnel_dataset_payload())
    _write(
        cases,
        {
            "cases": [
                {
                    "case_id": "SRC-1",
                    "source_family": "fixture_family",
                    "topology_type": "wall-frame",
                    "element_mix": "shell_beam_mix",
                },
                {
                    "case_id": "SRC-2",
                    "source_family": "fixture_family",
                    "topology_type": "outrigger",
                    "element_mix": "shell_beam_mix",
                },
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--pushover-stress-report",
            str(pushover),
            "--ndtha-stress-report",
            str(ndtha),
            "--rc-benchmark-lock-report",
            str(rc_lock),
            "--construction-sequence-report",
            str(construction),
            "--ssi-boundary-report",
            str(ssi),
            "--damper-validation-report",
            str(damper),
            "--foundation-soil-link-gate-report",
            str(foundation),
            "--structural-contact-validation-report",
            str(contact),
            "--panel-zone-clash-report",
            str(panel_zone),
            "--wind-time-history-gate-report",
            str(wind),
            "--vibration-attenuation-report",
            str(vibration_attenuation),
            "--vibration-compliance-report",
            str(vibration_compliance),
            "--track-lf-solver-report",
            str(track_lf),
            "--moving-load-integrator-report",
            str(moving_load),
            "--vti-coupled-solver-report",
            str(vti),
            "--track-irregularity-report",
            str(track_irregularity),
            "--track-dynamics-dataset-report",
            str(track_dataset),
            "--tunnel-dynamics-dataset-report",
            str(tunnel_dataset),
            "--benchmark-cases",
            str(cases),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_BOND_INTERFACE"
    assert payload["checks"]["bond_interface_pass"] is False
    assert payload["checks"]["calibration_matrix_pass"] is False
    matrix = payload["evidence"]["calibration_matrix"]
    assert matrix["family_pass_counts"]["bond_interface"] < matrix["family_counts"]["bond_interface"]
    assert payload["summary_line"].startswith("Material constitutive gate: CHECK")


def test_material_constitutive_gate_promotes_solver_closed_panel_zone_summary_to_full_material_pass(
    tmp_path: Path,
) -> None:
    out = tmp_path / "material_constitutive_default.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    raw_panel_zone_summary = payload["evidence"]["panel_zone_joint_response_summary"]
    panel_zone_surface = payload["evidence"]["panel_zone_joint_response_gate_surface"]
    joint_rows = {
        row["row_id"]: row
        for row in payload["evidence"]["calibration_matrix"]["rows"]
        if row.get("family") == "joint_constraint_transfer"
    }
    panel_feedback_rows = {
        row["row_id"]: row
        for row in payload["evidence"]["calibration_matrix"]["rows"]
        if row.get("family") == "panel_feedback_residual_transfer"
    }

    assert payload["contract_pass"] is True
    assert payload["checks"]["panel_zone_joint_response_pass"] is True
    assert raw_panel_zone_summary["panel_zone_topology_projected_bridge_complete"] is False
    assert raw_panel_zone_summary["panel_zone_internal_engine_complete"] is False
    assert raw_panel_zone_summary["panel_zone_solver_verified_bridge_complete"] is True
    assert raw_panel_zone_summary["panel_zone_external_validation_artifact_closed"] is True
    assert raw_panel_zone_summary["panel_zone_solver_verified_latest_consume_contract_pass"] is True
    assert panel_zone_surface["bridge_complete"] is True
    assert panel_zone_surface["bridge_mode"] == "true_3d_verified"
    assert panel_zone_surface["material_evidence_complete"] is True
    assert panel_zone_surface["material_evidence_mode"] == "true_3d_verified"
    assert panel_zone_surface["exact_verified_complete"] is True
    assert payload["checks"]["joint_constraint_transfer_pass"] is True
    assert payload["checks"]["calibration_matrix_pass"] is True
    assert joint_rows["joint_constraint_transfer:gate:topology_projected_bridge_complete"]["pass"] is True
    assert joint_rows["joint_constraint_transfer:gate:internal_engine_complete"]["pass"] is True
    assert joint_rows["joint_constraint_transfer:summary:required_sources_complete"]["pass"] is True
    assert joint_rows["joint_constraint_transfer:summary:validated_source_row_count_total"]["pass"] is True
    assert panel_feedback_rows["panel_feedback_residual_transfer:gate:feedback_bridge_complete"]["pass"] is True
    assert (
        joint_rows["joint_constraint_transfer:summary:validated_source_row_count_total"]["value"]
        > raw_panel_zone_summary["panel_zone_validated_source_row_count_total"]
    )
    assert (
        payload["summary"]["calibration_matrix_family_coverage"]["joint_constraint_transfer"]["source_row_count"]
        == joint_rows["joint_constraint_transfer:summary:validated_source_row_count_total"]["value"]
    )
    assert payload["summary"]["panel_zone_joint_response_material_evidence_mode"] == "true_3d_verified"
    assert payload["summary"]["panel_zone_joint_response_exact_verified_complete"] is True
    assert payload["summary"]["calibration_matrix_family_coverage"]["panel_feedback_residual_transfer"]["bridge_mode"] == "true_3d_verified"
    assert payload["summary"]["calibration_matrix_family_coverage"]["panel_feedback_residual_transfer"]["bridge_ready"] == 1
    assert "panel_zone_joint_response=yes(matrix=12/12" in payload["summary_line"]
    assert "joint_constraint_transfer=yes(matrix=5/5" in payload["summary_line"]
    assert "panel_feedback_residual_transfer=5/5" in payload["summary"]["calibration_matrix_group_label"]
    assert "Material constitutive gate: PASS" in payload["summary_line"]


def test_material_constitutive_gate_surfaces_calibration_matrix_threshold_failure(tmp_path: Path) -> None:
    pushover = tmp_path / "pushover.json"
    ndtha = tmp_path / "ndtha.json"
    rc_lock = tmp_path / "rc_lock.json"
    construction = tmp_path / "construction.json"
    ssi = tmp_path / "ssi.json"
    damper = tmp_path / "damper.json"
    foundation = tmp_path / "foundation.json"
    contact = tmp_path / "contact.json"
    panel_zone = tmp_path / "panel_zone.json"
    wind = tmp_path / "wind.json"
    vibration_attenuation = tmp_path / "vibration_attenuation.json"
    vibration_compliance = tmp_path / "vibration_compliance.json"
    track_lf = tmp_path / "track_lf.json"
    moving_load = tmp_path / "moving_load.json"
    vti = tmp_path / "vti.json"
    track_irregularity = tmp_path / "track_irregularity.json"
    track_dataset = tmp_path / "track_dataset.json"
    tunnel_dataset = tmp_path / "tunnel_dataset.json"
    out = tmp_path / "material_constitutive.json"

    _write(
        pushover,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True},
            "rows": [
                {
                    "case_id": "P1",
                    "topology_type": "wall-frame",
                    "hazard_type": "seismic",
                    "summary": {"material_indices": {"compression_damage_mean": 1.0, "bond_slip_index_mean": 0.9}},
                }
            ],
        },
    )
    _write(
        ndtha,
        {
            "contract_pass": True,
            "checks": {
                "material_model_pass": True,
                "dynamic_reversal_pass": True,
                "plasticity_triggered_all_cases": True,
                "residual_metric_sanity_pass": True,
            },
            "rows": [
                {
                    "case_id": "N1",
                    "topology_type": "wall-frame",
                    "hazard_type": "seismic",
                    "summary": {
                        "residual_drift_ratio_pct": 0.2,
                        "raw_residual_drift_ratio_pct": 0.2,
                        "material_indices": {"compression_damage_mean": 0.1, "bond_slip_index_mean": 0.8},
                    },
                }
            ],
        },
    )
    _write(rc_lock, {"contract_pass": True, "checks": {"cracking_case_pass": True, "bond_slip_case_pass": True}})
    _write(
        construction,
        {
            "contract_pass": True,
            "checks": {
                "creep_shrinkage_applied": True,
                "differential_shortening_detected": True,
            },
            "summary": {
                "mean_creep_index": 1.0,
                "mean_shrinkage_index": 0.617,
                "max_differential_shortening_mm": 18.2,
            },
        },
    )
    _write(ssi, _supporting_ssi_payload())
    _write(damper, _supporting_damper_payload())
    _write(foundation, _supporting_foundation_payload())
    _write(contact, _supporting_contact_payload())
    _write(panel_zone, _supporting_panel_zone_payload())
    _write(wind, _supporting_wind_payload())
    _write(vibration_attenuation, _supporting_vibration_attenuation_payload())
    _write(vibration_compliance, _supporting_vibration_compliance_payload())
    _write(track_lf, _supporting_track_lf_payload())
    _write(moving_load, _supporting_moving_load_payload())
    _write(vti, _supporting_vti_payload())
    _write(track_irregularity, _supporting_track_irregularity_payload())
    _write(track_dataset, _supporting_track_dataset_payload())
    _write(tunnel_dataset, _supporting_tunnel_dataset_payload())

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--pushover-stress-report",
            str(pushover),
            "--ndtha-stress-report",
            str(ndtha),
            "--rc-benchmark-lock-report",
            str(rc_lock),
            "--construction-sequence-report",
            str(construction),
            "--ssi-boundary-report",
            str(ssi),
            "--damper-validation-report",
            str(damper),
            "--foundation-soil-link-gate-report",
            str(foundation),
            "--structural-contact-validation-report",
            str(contact),
            "--panel-zone-clash-report",
            str(panel_zone),
            "--wind-time-history-gate-report",
            str(wind),
            "--vibration-attenuation-report",
            str(vibration_attenuation),
            "--vibration-compliance-report",
            str(vibration_compliance),
            "--track-lf-solver-report",
            str(track_lf),
            "--moving-load-integrator-report",
            str(moving_load),
            "--vti-coupled-solver-report",
            str(vti),
            "--track-irregularity-report",
            str(track_irregularity),
            "--track-dynamics-dataset-report",
            str(track_dataset),
            "--tunnel-dynamics-dataset-report",
            str(tunnel_dataset),
            "--min-concrete-damage-rows",
            "2",
            "--min-bond-interface-rows",
            "2",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    matrix = payload["evidence"]["calibration_matrix"]
    threshold_rows = [row for row in matrix["rows"] if row["metric"] == "min_case_coverage"]
    assert any(row["family"] == "concrete_damage" and row["pass"] is False for row in threshold_rows)
    assert any(row["family"] == "bond_interface" and row["pass"] is False for row in threshold_rows)
    assert payload["summary"]["calibration_matrix_pass_row_count"] < payload["summary"]["calibration_matrix_row_count"]
