from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_element_material_breadth_gate.py")
SPEC = importlib.util.spec_from_file_location("run_element_material_breadth_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_element_material_breadth_gate_passes_with_direct_shell_wall_contact_and_material_evidence(
    tmp_path: Path,
) -> None:
    topology = tmp_path / "topology.json"
    diaphragm = tmp_path / "diaphragm.json"
    pushover = tmp_path / "pushover.json"
    ndtha = tmp_path / "ndtha.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    wind = tmp_path / "wind.json"
    special_link = tmp_path / "special_link_library.py"
    structural_contact_validation = tmp_path / "structural_contact_validation_report.json"
    structural_contact_gate = tmp_path / "structural_contact_gate_report.json"
    rc_benchmark_lock = tmp_path / "rc_benchmark_lock_report.json"
    construction_sequence = tmp_path / "construction_sequence_report.json"
    damper_validation = tmp_path / "damper_validation_report.json"
    foundation_soil_link_gate = tmp_path / "foundation_soil_link_gate_report.json"
    cases = tmp_path / "cases.json"
    out = tmp_path / "element_material_breadth.json"

    _write(
        topology,
        {
            "contract_pass": True,
            "checks": {"shell_beam_mix_pass": True},
            "metrics": {"shell_element_count": 5},
        },
    )
    _write(
        diaphragm,
        {
            "contract_pass": True,
            "checks": {
                "flexible_diaphragm_modeled": True,
                "shell_beam_mix_topology_pass": True,
                "slab_shear_stress_pass": True,
            },
        },
    )
    _write(
        pushover,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True, "section_family_pass": True},
            "summary": {"material_model": "rc_composite"},
            "rows": [
                {
                    "case_id": "wall-1",
                    "topology_type": "wall-frame",
                    "summary": {
                        "material_model": "rc_composite",
                        "section_family_counts": {"wall_boundary": 6, "wall_web": 9},
                        "material_indices": {"compression_damage_mean": 1.0},
                    },
                }
            ],
        },
    )
    _write(
        ndtha,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True, "section_family_pass": True},
            "summary": {"material_model": "rc_composite"},
            "rows": [
                {
                    "case_id": "wall-1",
                    "topology_type": "wall-frame",
                    "hazard_type": "seismic",
                    "summary": {
                        "material_model": "rc_composite",
                        "section_family_counts": {"wall_boundary": 6, "wall_web": 9},
                        "material_indices": {"compression_damage_mean": 1.0},
                    },
                }
            ],
        },
    )
    _write(
        ssi,
        {
            "contract_pass": True,
            "checks": {
                "ssi_nonlinear_boundary_active": True,
                "ssi_transfer_finite": True,
                "section_family_pass": True,
                "material_model_pass": True,
            },
            "rows": [{"material_model": "steel_elastic_plastic"}],
        },
    )
    _write(
        substructuring,
        {
            "contract_pass": True,
            "checks": {"finite_transfer": True, "coupling_stability": True},
            "metrics": {"mean_transfer_ratio_building_to_track": 0.45},
        },
    )
    _write(
        wind,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True},
            "summary": {"material_model_types": ["steel_elastic_plastic"]},
        },
    )
    special_link.write_text(
        'SUPPORTED_LINKS = ["gap", "uplift", "compression-only", "bearing", "friction", "pounding"]\n',
        encoding="utf-8",
    )
    _write(
        structural_contact_validation,
        {
            "contract_pass": True,
            "checks": {
                "support_search_family_surface_pass": True,
                "node_to_surface_proxy_family_surface_pass": True,
            },
            "summary": {
                "contact_uplift_event_sequence_mismatch": 0,
                "link_model_types": [
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                    "compression_only_penalty",
                    "bearing_bilinear",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                ],
                "foundation_support_model_types": ["p-y", "q-z"],
                "device_model_types": ["friction_pendulum"],
                "support_search_model_types": [
                    "friction_pendulum",
                    "lead_rubber_bearing",
                    "p-y",
                    "pile_head",
                    "q-z",
                    "t-z",
                    "tmd",
                    "viscoelastic_damper",
                    "viscous_damper",
                ],
                "node_to_surface_proxy_model_types": [
                    "friction_pendulum",
                    "lead_rubber_bearing",
                    "p-y",
                    "q-z",
                    "viscoelastic_damper",
                ],
                "support_search_family_types": ["device_support_search", "foundation_support_search"],
                "node_to_surface_proxy_family_types": ["device_support_search", "foundation_support_search"],
                "support_depth_score": 21,
            },
        },
    )
    _write(
        structural_contact_gate,
        {
            "contract_pass": True,
            "checks": {
                "all_structural_contact_categories_ready": True,
                "structural_contact_event_sequence_zero_pass": True,
            },
        },
    )
    _write(
        rc_benchmark_lock,
        {
            "contract_pass": True,
            "checks": {
                "cracking_case_pass": True,
                "bond_slip_case_pass": True,
                "creep_case_pass": True,
                "slab_wall_case_pass": True,
            },
        },
    )
    _write(
        construction_sequence,
        {
            "contract_pass": True,
            "checks": {"creep_shrinkage_applied": True},
        },
    )
    _write(
        damper_validation,
        {
            "contract_pass": True,
            "checks": {
                "damper_type_diversity_pass": True,
                "waveform_corr_pass": True,
                "phase_error_pass": True,
                "residual_drift_pass": True,
            },
        },
    )
    _write(
        foundation_soil_link_gate,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_artifact_ready": True,
                "ssi_boundary_ready": True,
                "soil_tunnel_ready": True,
                "impedance_schema_ready": True,
                "foundation_link_models_ready": True,
                "support_search_family_surface_ready": True,
                "node_to_surface_proxy_family_surface_ready": True,
            },
            "summary": {
                "foundation_support_model_types": ["p-y"],
                "device_model_types": ["friction_pendulum"],
                "support_search_family_types": ["foundation_support_search"],
                "node_to_surface_proxy_family_types": ["foundation_support_search"],
                "support_depth_score": 21,
            },
        },
    )
    _write(
        cases,
        {
            "cases": [
                {
                    "case_id": "A-001",
                    "topology_type": "wall-frame",
                    "element_mix": "shell_beam_mix",
                },
                {
                    "case_id": "A-002",
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
            "--topology-report",
            str(topology),
            "--flexible-diaphragm-report",
            str(diaphragm),
            "--pushover-stress-report",
            str(pushover),
            "--ndtha-stress-report",
            str(ndtha),
            "--ssi-boundary-report",
            str(ssi),
            "--substructuring-interface-report",
            str(substructuring),
            "--wind-time-history-report",
            str(wind),
            "--special-link-library",
            str(special_link),
            "--structural-contact-validation-report",
            str(structural_contact_validation),
            "--structural-contact-gate-report",
            str(structural_contact_gate),
            "--rc-benchmark-lock-report",
            str(rc_benchmark_lock),
            "--construction-sequence-report",
            str(construction_sequence),
            "--damper-validation-report",
            str(damper_validation),
            "--foundation-soil-link-gate-report",
            str(foundation_soil_link_gate),
            "--benchmark-cases",
            str(cases),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["shell_direct_contract_pass"] is True
    assert payload["checks"]["wall_direct_contract_pass"] is True
    assert payload["checks"]["contact_interface_compression_surrogate_pass"] is True
    assert payload["checks"]["structural_contact_direct_contract_pass"] is True
    assert payload["checks"]["foundation_soil_link_direct_contract_pass"] is True
    assert payload["checks"]["material_model_breadth_pass"] is True
    assert payload["checks"]["link_model_breadth_pass"] is True
    assert payload["checks"]["material_capability_breadth_pass"] is True
    assert payload["checks"]["panel_rc_cyclic_surface_present"] is True
    assert payload["checks"]["beam_column_global_surface_present"] is True
    assert payload["checks"]["beam_column_global_equilibrium_pass"] is True
    assert payload["checks"]["layered_panel_assembled_surface_present"] is True
    assert payload["checks"]["layered_panel_force_balance_pass"] is True
    assert payload["checks"]["assembled_global_depth_surface_present"] is True
    assert payload["checks"]["section_family_demand_surface_present"] is True
    assert payload["checks"]["beam_shell_contact_coupling_surface_present"] is True
    assert payload["summary"]["contact_surface_status"] == "full_structural_contact"
    assert payload["summary"]["panel_rc_cyclic_surface_status"] == "pass"
    assert payload["summary"]["panel_rc_cyclic_section_count"] == 2
    assert payload["summary"]["panel_rc_cyclic_section_families"] == ["slab", "wall"]
    assert payload["summary"]["panel_rc_cyclic_section_names"] == ["layered_slab", "layered_wall"]
    assert payload["summary"]["panel_rc_cyclic_reversal_count_min"] >= 1
    assert payload["summary"]["panel_rc_cyclic_reversal_count_max"] >= payload["summary"]["panel_rc_cyclic_reversal_count_min"]
    assert payload["summary"]["panel_rc_cyclic_min_pinching_ratio"] < 1.0
    assert payload["summary"]["panel_rc_cyclic_max_crushing_ratio"] > 0.0
    assert payload["summary"]["panel_rc_cyclic_total_energy_like"] > 0.0
    assert "pinching" in payload["summary"]["panel_rc_cyclic_evidence_tags"]
    assert "crushing" in payload["summary"]["panel_rc_cyclic_evidence_tags"]
    assert payload["summary"]["assembled_global_depth_surface_status"] == "pass"
    assert payload["summary"]["assembled_global_depth_signal_count"] >= 5
    assert payload["summary"]["beam_column_global_case_count"] == 1
    assert payload["summary"]["beam_column_global_iteration_count"] >= 1
    assert payload["summary"]["beam_column_global_yielded_end_count"] == 1
    assert payload["summary"]["beam_column_global_tangent_scale_min"] < 1.0
    assert payload["summary"]["beam_column_global_max_trial_end_moment_ratio"] > 1.0
    assert payload["summary"]["beam_column_global_stability_index"] > 0.0
    assert payload["summary"]["beam_column_global_strain_energy_n_m"] > 0.0
    assert payload["summary"]["beam_column_global_free_dof_residual_max"] < 1.0e-6
    assert payload["summary"]["beam_column_global_displacement_max_m"] > 0.0
    assert payload["summary"]["section_family_demand_surface_status"] == "pass"
    assert payload["summary"]["section_family_story_count"] == 5
    assert payload["summary"]["section_family_beam_yielded_story_count"] >= 1
    assert payload["summary"]["section_family_beam_max_trial_end_moment_ratio"] > 1.0
    assert payload["summary"]["section_family_beam_stability_index_max"] > 0.0
    assert payload["summary"]["section_family_beam_strain_energy_total_n_m"] > 0.0
    assert payload["summary"]["layered_panel_assembled_case_count"] == 2
    assert payload["summary"]["layered_panel_assembled_section_families"] == ["slab", "wall"]
    assert payload["summary"]["layered_panel_assembled_force_balance_error_max_n"] < 1.0e-6
    assert payload["summary"]["layered_panel_assembled_corner_force_max_n"] > 0.0
    assert payload["summary"]["layered_panel_assembled_torsional_case_count"] == 1
    assert payload["summary"]["layered_panel_assembled_diaphragm_coupling_case_count"] == 1
    assert payload["summary"]["beam_shell_contact_coupling_surface_status"] == "pass"
    assert payload["summary"]["beam_shell_contact_coupling_signal_count"] == 21
    assert payload["summary"]["beam_shell_contact_support_depth_score"] == 21
    assert payload["summary"]["beam_shell_contact_support_search_count"] == 9
    assert payload["summary"]["beam_shell_contact_node_surface_proxy_count"] == 5
    assert payload["summary"]["beam_shell_contact_support_family_count"] == 2
    assert payload["summary"]["beam_shell_contact_proxy_family_count"] == 2
    assert payload["summary"]["material_model_types"] == ["rc_composite", "steel_elastic_plastic"]
    assert payload["summary"]["link_model_types"] == [
        "bearing_bilinear",
        "compression_only_penalty",
        "coulomb_friction",
        "kelvin_voigt_pounding",
        "normal_gap_unilateral",
        "uplift_seat_unilateral",
    ]
    assert payload["summary"]["foundation_support_model_types"] == ["p-y", "pile_head", "q-z", "t-z"]
    assert payload["summary"]["device_model_types"] == [
        "friction_pendulum",
        "lead_rubber_bearing",
        "tmd",
        "viscoelastic_damper",
        "viscous_damper",
    ]
    assert payload["summary"]["support_link_group_counts"] == {"contact": 6, "foundation": 4, "device": 5}
    assert payload["summary"]["support_link_family_count"] == 15
    assert payload["summary"]["missing_material_models"] == []
    assert payload["summary"]["missing_link_models"] == []
    assert payload["summary"]["material_capability_types"] == [
        "contact_bearing_friction_impact",
        "contact_gap_uplift_unilateral",
        "dissipative_device_response",
        "foundation_soil_link_nonlinear",
        "interface_transfer_finite",
        "rc_bond_slip",
        "rc_cracking",
        "rc_creep_shrinkage",
        "shell_surface_transfer",
        "slab_wall_interaction",
        "soil_boundary_nonlinear",
        "wall_compression_damage",
    ]
    assert payload["summary"]["missing_material_capabilities"] == []
    assert payload["summary"]["material_capability_group_counts"] == {
        "device_contact": 3,
        "foundation_soil": 2,
        "rc": 5,
        "shell_interface": 2,
    }
    assert payload["summary_line"].startswith("Element/material breadth: PASS")
    assert "panel_cyclic=yes(sections=2," in payload["summary_line"]
    assert "assembled_depth=yes(beam_iter=" in payload["summary_line"]
    assert "family_demand=yes(stories=5," in payload["summary_line"]
    assert "coupling=yes(beam=1,panel=2,support=21,search=9,proxy=5)" in payload["summary_line"]
    assert "support=15(contact=6,foundation=4,device=5)" in payload["summary_line"]
    assert any("shell=pass" in reason for reason in payload["reasons"])
    assert any("panel_rc_cyclic=pass" in reason for reason in payload["reasons"])
    assert any("assembled_global_depth=pass" in reason for reason in payload["reasons"])
    assert any("section_family_demand=pass" in reason for reason in payload["reasons"])
    assert any("beam_shell_contact_coupling=pass" in reason for reason in payload["reasons"])
    assert any("support_link_surface=pass" in reason for reason in payload["reasons"])
    assert any("Structural-contact breadth is measured" in item for item in payload["limitations"])
    assert any("Panel RC cyclic surface is a bounded library-backed wall/slab helper summary" in item for item in payload["limitations"])
    assert any("Assembled/global depth is a bounded helper-backed surface" in item for item in payload["limitations"])
    assert any("Beam/shell-contact coupling is a bounded rollup" in item for item in payload["limitations"])


def test_beam_shell_contact_coupling_surface_stays_additive_when_support_depth_is_missing() -> None:
    summary = MODULE._beam_shell_contact_coupling_surface_summary(
        assembled_global_depth_summary={
            "beam_case_count": 1,
            "beam_equilibrium_pass": True,
            "panel_case_count": 2,
            "panel_force_balance_pass": True,
        },
        structural_contact_summary={
            "support_search_model_types": [],
            "node_to_surface_proxy_model_types": [],
            "support_search_family_types": [],
            "node_to_surface_proxy_family_types": [],
            "support_depth_score": 0,
        },
        structural_contact_validation_checks={
            "support_search_family_surface_pass": False,
            "node_to_surface_proxy_family_surface_pass": False,
        },
        foundation_soil_link_summary={},
        foundation_soil_link_checks={
            "support_search_family_surface_ready": False,
            "node_to_surface_proxy_family_surface_ready": False,
        },
    )

    assert summary["beam_signal_present"] is True
    assert summary["panel_signal_present"] is True
    assert summary["support_signal_present"] is False
    assert summary["present"] is False
    assert summary["support_depth_score"] == 0
    assert summary["coupling_signal_count"] == 3


def test_element_material_breadth_gate_fails_honestly_when_material_breadth_is_only_rc(tmp_path: Path) -> None:
    topology = tmp_path / "topology.json"
    diaphragm = tmp_path / "diaphragm.json"
    pushover = tmp_path / "pushover.json"
    ndtha = tmp_path / "ndtha.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    wind = tmp_path / "wind.json"
    special_link = tmp_path / "special_link_library.py"
    structural_contact_validation = tmp_path / "structural_contact_validation_report.json"
    structural_contact_gate = tmp_path / "structural_contact_gate_report.json"
    rc_benchmark_lock = tmp_path / "rc_benchmark_lock_report.json"
    construction_sequence = tmp_path / "construction_sequence_report.json"
    damper_validation = tmp_path / "damper_validation_report.json"
    foundation_soil_link_gate = tmp_path / "foundation_soil_link_gate_report.json"
    cases = tmp_path / "cases.json"
    out = tmp_path / "element_material_breadth.json"

    _write(topology, {"contract_pass": True, "checks": {"shell_beam_mix_pass": True}, "metrics": {"shell_element_count": 2}})
    _write(
        diaphragm,
        {
            "contract_pass": True,
            "checks": {
                "flexible_diaphragm_modeled": True,
                "shell_beam_mix_topology_pass": True,
                "slab_shear_stress_pass": True,
            },
        },
    )
    rc_row = {
        "case_id": "wall-1",
        "topology_type": "wall-frame",
        "summary": {
            "material_model": "rc_composite",
            "section_family_counts": {"wall_boundary": 4, "wall_web": 6},
            "material_indices": {"compression_damage_mean": 0.5},
        },
    }
    _write(
        pushover,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True, "section_family_pass": True},
            "summary": {"material_model": "rc_composite"},
            "rows": [rc_row],
        },
    )
    _write(
        ndtha,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True, "section_family_pass": True},
            "summary": {"material_model": "rc_composite"},
            "rows": [rc_row],
        },
    )
    _write(
        ssi,
        {
            "contract_pass": True,
            "checks": {
                "ssi_nonlinear_boundary_active": True,
                "ssi_transfer_finite": True,
                "section_family_pass": True,
                "material_model_pass": True,
            },
            "rows": [{"material_model": "rc_composite"}],
        },
    )
    _write(
        substructuring,
        {
            "contract_pass": True,
            "checks": {"finite_transfer": True, "coupling_stability": True},
            "metrics": {"mean_transfer_ratio_building_to_track": 0.51},
        },
    )
    _write(
        wind,
        {
            "contract_pass": False,
            "checks": {"material_model_pass": False},
            "summary": {"material_model_types": []},
        },
    )
    special_link.write_text(
        'SUPPORTED_LINKS = ["gap", "uplift", "compression-only", "bearing", "friction", "pounding"]\n',
        encoding="utf-8",
    )
    _write(
        structural_contact_validation,
        {
            "contract_pass": False,
            "summary": {
                "contact_uplift_event_sequence_mismatch": 2,
                "link_model_types": ["normal_gap_unilateral"],
            },
        },
    )
    _write(
        structural_contact_gate,
        {
            "contract_pass": False,
            "checks": {
                "all_structural_contact_categories_ready": False,
                "structural_contact_event_sequence_zero_pass": False,
            },
        },
    )
    _write(
        rc_benchmark_lock,
        {
            "contract_pass": False,
            "checks": {
                "cracking_case_pass": False,
                "bond_slip_case_pass": False,
                "creep_case_pass": False,
                "slab_wall_case_pass": False,
            },
        },
    )
    _write(
        construction_sequence,
        {
            "contract_pass": False,
            "checks": {"creep_shrinkage_applied": False},
        },
    )
    _write(
        damper_validation,
        {
            "contract_pass": False,
            "checks": {
                "damper_type_diversity_pass": False,
                "waveform_corr_pass": False,
                "phase_error_pass": False,
                "residual_drift_pass": False,
            },
        },
    )
    _write(
        foundation_soil_link_gate,
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
        },
    )
    _write(cases, {"cases": [{"case_id": "A-001", "topology_type": "wall-frame", "element_mix": "shell_beam_mix"}]})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--topology-report",
            str(topology),
            "--flexible-diaphragm-report",
            str(diaphragm),
            "--pushover-stress-report",
            str(pushover),
            "--ndtha-stress-report",
            str(ndtha),
            "--ssi-boundary-report",
            str(ssi),
            "--substructuring-interface-report",
            str(substructuring),
            "--wind-time-history-report",
            str(wind),
            "--special-link-library",
            str(special_link),
            "--structural-contact-validation-report",
            str(structural_contact_validation),
            "--structural-contact-gate-report",
            str(structural_contact_gate),
            "--rc-benchmark-lock-report",
            str(rc_benchmark_lock),
            "--construction-sequence-report",
            str(construction_sequence),
            "--damper-validation-report",
            str(damper_validation),
            "--foundation-soil-link-gate-report",
            str(foundation_soil_link_gate),
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
    assert payload["reason_code"] == "ERR_STRUCTURAL_CONTACT_DIRECT_COVERAGE"
    assert payload["checks"]["shell_direct_contract_pass"] is True
    assert payload["checks"]["wall_direct_contract_pass"] is True
    assert payload["checks"]["contact_interface_compression_surrogate_pass"] is True
    assert payload["checks"]["structural_contact_direct_contract_pass"] is False
    assert payload["checks"]["support_link_surface_present"] is True
    assert payload["checks"]["material_model_breadth_pass"] is False
    assert payload["checks"]["link_model_breadth_pass"] is False
    assert payload["checks"]["material_capability_breadth_pass"] is False
    assert payload["checks"]["panel_rc_cyclic_surface_present"] is True
    assert payload["checks"]["assembled_global_depth_surface_present"] is True
    assert payload["checks"]["section_family_demand_surface_present"] is True
    assert payload["summary"]["material_model_types"] == ["rc_composite"]
    assert payload["summary"]["panel_rc_cyclic_surface_status"] == "pass"
    assert payload["summary"]["assembled_global_depth_surface_status"] == "pass"
    assert payload["summary"]["beam_column_global_yielded_end_count"] == 1
    assert payload["summary"]["beam_column_global_max_trial_end_moment_ratio"] > 1.0
    assert payload["summary"]["section_family_demand_surface_status"] == "pass"
    assert payload["summary"]["section_family_story_count"] == 5
    assert payload["summary"]["layered_panel_assembled_torsional_case_count"] == 1
    assert payload["summary"]["foundation_support_model_types"] == ["p-y", "pile_head", "q-z", "t-z"]
    assert payload["summary"]["device_model_types"] == [
        "friction_pendulum",
        "lead_rubber_bearing",
        "tmd",
        "viscoelastic_damper",
        "viscous_damper",
    ]
    assert payload["summary"]["missing_material_models"] == ["steel_elastic_plastic"]
    assert payload["summary_line"].startswith("Element/material breadth: CHECK")
    assert "panel_cyclic=yes(sections=2," in payload["summary_line"]
    assert "assembled_depth=yes(beam_iter=" in payload["summary_line"]
    assert "family_demand=yes(stories=5," in payload["summary_line"]
    assert any("material_models=partial" in reason for reason in payload["reasons"])
    assert any("panel_rc_cyclic=pass" in reason for reason in payload["reasons"])
    assert any("assembled_global_depth=pass" in reason for reason in payload["reasons"])
    assert any("section_family_demand=pass" in reason for reason in payload["reasons"])
