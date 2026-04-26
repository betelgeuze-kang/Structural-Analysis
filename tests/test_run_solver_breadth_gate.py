from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_solver_breadth_gate.py")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_solver_breadth_gate_passes_with_shell_wall_interface_evidence(tmp_path: Path) -> None:
    topology = tmp_path / "topology.json"
    pushover = tmp_path / "pushover.json"
    diaphragm = tmp_path / "diaphragm.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    ndtha = tmp_path / "ndtha.json"
    structural_contact = tmp_path / "structural_contact_gate.json"
    general_fe_contact = tmp_path / "general_fe_contact.json"
    element_material = tmp_path / "element_material.json"
    surface_interaction = tmp_path / "surface_interaction.json"
    cases_a = tmp_path / "cases_a.json"
    cases_b = tmp_path / "cases_b.json"
    out = tmp_path / "solver_breadth.json"

    _write(
        topology,
        {
            "contract_pass": True,
            "checks": {"shell_beam_mix_pass": True},
            "metrics": {"shell_element_count": 5},
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
                    "summary": {
                        "section_family_counts": {"wall_boundary": 6, "wall_web": 9},
                        "material_indices": {"compression_damage_mean": 1.0},
                    },
                },
                {"case_id": "frame-1", "summary": {"section_family_counts": {"mega_column": 3}}},
            ],
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
        ssi,
        {
            "contract_pass": True,
            "checks": {
                "ssi_nonlinear_boundary_active": True,
                "section_family_pass": True,
                "material_model_pass": True,
                "ssi_transfer_finite": True,
            },
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
        ndtha,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True, "section_family_pass": True},
            "summary": {"material_model": "rc_composite"},
            "rows": [
                {
                    "case_id": "ndtha-1",
                    "topology_type": "wall-frame",
                    "hazard_type": "seismic",
                    "summary": {"material_indices": {"compression_damage_mean": 1.0}},
                }
            ],
        },
    )
    _write(
        structural_contact,
        {
            "contract_pass": True,
            "checks": {
                "all_structural_contact_categories_ready": True,
                "structural_contact_event_sequence_zero_pass": True,
            },
        },
    )
    _write(
        general_fe_contact,
        {
            "contract_pass": True,
            "checks": {
                "direct_structural_contact_pass": True,
                "foundation_soil_link_pass": True,
                "interface_transfer_pass": True,
                "ssi_boundary_pass": True,
                "soil_tunnel_dynamic_pass": True,
                "support_search_family_surface_pass": True,
                "node_to_surface_proxy_family_surface_pass": True,
                "all_matrix_rows_ready": True,
            },
            "summary": {
                "ready_row_count": 10,
                "total_row_count": 10,
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
            },
            "summary_line": "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21 | coupling_depth=31 | support_families=2/2 | proxy_families=2/2",
        },
    )
    _write(
        element_material,
        {
            "contract_pass": True,
            "checks": {
                "beam_shell_contact_coupling_surface_present": True,
            },
            "summary": {
                "beam_shell_contact_coupling_signal_count": 21,
                "beam_shell_contact_support_depth_score": 21,
                "beam_shell_contact_support_search_count": 9,
                "beam_shell_contact_node_surface_proxy_count": 5,
                "beam_shell_contact_support_family_count": 2,
                "beam_shell_contact_proxy_family_count": 2,
            },
        },
    )
    _write(
        surface_interaction,
        {
            "contract_pass": True,
            "checks": {
                "shell_surface_coupling_pass": True,
                "interface_transfer_pass": True,
                "interface_gap_continuity_pass": True,
                "foundation_soil_impedance_pass": True,
                "ssi_boundary_interaction_pass": True,
                "soil_tunnel_dynamic_interaction_pass": True,
                "direct_structural_contact_family_pass": True,
                "interaction_family_matrix_pass": True,
                "all_matrix_rows_ready": True,
            },
            "summary": {
                "ready_row_count": 7,
                "total_row_count": 7,
                "interaction_family_ready_count": 53,
                "interaction_family_total_count": 53,
                "interaction_source_family_ready_count": 3,
                "interaction_source_family_total_count": 3,
                "interaction_family_group_label": "shell-shell=15/15,shell-wall=15/15,footing-soil=15/15,ssi=1/1,soil-tunnel=1/1,direct-contact=6/6",
            },
            "summary_line": "Surface interaction benchmark: PASS | ready=7/7 | family_matrix=53/53 | source_families=3/3 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | groups=shell-shell=15/15,shell-wall=15/15,footing-soil=15/15,ssi=1/1,soil-tunnel=1/1,direct-contact=6/6",
        },
    )
    _write(
        cases_a,
        {
            "cases": [
                {
                    "case_id": "A-001",
                    "topology_type": "wall-frame",
                    "element_mix": "shell_beam_mix",
                    "source_family": "rwth_zenodo",
                    "metric_source": "open_data_measurement",
                },
                {
                    "case_id": "A-002",
                    "topology_type": "rahmen",
                    "element_mix": "beam_only",
                    "source_family": "rwth_zenodo",
                    "metric_source": "open_data_measurement",
                },
            ]
        },
    )
    _write(
        cases_b,
        {
            "cases": [
                {
                    "case_id": "B-001",
                    "topology_type": "outrigger",
                    "element_mix": "shell_beam_mix",
                    "source_family": "atwood_open",
                    "metric_source": "open_data_measurement",
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--topology-report",
            str(topology),
            "--pushover-stress-report",
            str(pushover),
            "--flexible-diaphragm-report",
            str(diaphragm),
            "--ssi-boundary-report",
            str(ssi),
            "--substructuring-interface-report",
            str(substructuring),
            "--ndtha-stress-report",
            str(ndtha),
            "--structural-contact-gate-report",
            str(structural_contact),
            "--general-fe-contact-benchmark-report",
            str(general_fe_contact),
            "--element-material-breadth-report",
            str(element_material),
            "--surface-interaction-benchmark-report",
            str(surface_interaction),
            "--benchmark-cases",
            f"{cases_a},{cases_b}",
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
    assert payload["checks"]["shell_evidence_pass"] is True
    assert payload["checks"]["wall_evidence_pass"] is True
    assert payload["checks"]["interface_boundary_pass"] is True
    assert payload["checks"]["contact_surrogate_pass"] is True
    assert payload["checks"]["structural_contact_direct_pass"] is True
    assert payload["checks"]["general_fe_contact_matrix_pass"] is True
    assert payload["checks"]["surface_interaction_benchmark_pass"] is True
    assert payload["checks"]["benchmark_coverage_pass"] is True
    assert payload["checks"]["contact_surface_declared"] is True
    assert payload["summary"]["contact_surface_status"] == "full_structural_contact"
    assert payload["summary"]["general_fe_contact_ready_row_count"] == 10
    assert payload["summary"]["general_fe_contact_total_row_count"] == 10
    assert payload["summary"]["general_fe_contact_support_depth_score"] == 21
    assert payload["summary"]["general_fe_contact_coupling_depth_score"] == 31
    assert payload["summary"]["general_fe_contact_support_family_ready_count"] == 2
    assert payload["summary"]["general_fe_contact_support_family_total_count"] == 2
    assert payload["summary"]["general_fe_contact_proxy_family_ready_count"] == 2
    assert payload["summary"]["general_fe_contact_proxy_family_total_count"] == 2
    assert payload["summary"]["contact_coupling_surface_status"] == "pass"
    assert payload["summary"]["contact_coupling_depth_score"] == 31
    assert payload["summary"]["contact_support_depth_score"] == 21
    assert payload["summary"]["contact_support_search_count"] == 9
    assert payload["summary"]["contact_node_surface_proxy_count"] == 5
    assert payload["summary"]["contact_support_family_ready_count"] == 2
    assert payload["summary"]["contact_support_family_total_count"] == 2
    assert payload["summary"]["contact_proxy_family_ready_count"] == 2
    assert payload["summary"]["contact_proxy_family_total_count"] == 2
    assert payload["summary"]["contact_coupling_source_label"] == "general_fe+element_material"
    assert payload["summary"]["contact_coupling_summary_label"] == "depth=31,support=21,search=9,proxy=5"
    assert payload["summary"]["contact_family_readiness_label"] == "support=2/2,proxy=2/2"
    assert payload["summary"]["element_material_contact_coupling_present"] is True
    assert payload["summary"]["element_material_contact_coupling_signal_count"] == 21
    assert payload["summary"]["surface_interaction_ready_row_count"] == 7
    assert payload["summary"]["surface_interaction_total_row_count"] == 7
    assert payload["summary"]["surface_interaction_family_ready_count"] == 53
    assert payload["summary"]["surface_interaction_family_total_count"] == 53
    assert payload["summary"]["surface_interaction_source_family_ready_count"] == 3
    assert payload["summary"]["surface_interaction_source_family_total_count"] == 3
    assert payload["summary"]["surface_interaction_group_label"] == (
        "shell-shell=15/15,shell-wall=15/15,footing-soil=15/15,ssi=1/1,soil-tunnel=1/1,direct-contact=6/6"
    )
    assert payload["summary"]["pushover_compression_damage_row_count"] == 1
    assert payload["summary"]["ndtha_compression_damage_row_count"] == 1
    assert payload["summary"]["wall_frame_case_count"] == 1
    assert payload["summary"]["shell_beam_mix_case_count"] == 2
    assert "contact_coupling=yes(depth=31,support=21,search=9,proxy=5)" in payload["summary_line"]
    assert "contact_families=yes(support=2/2,proxy=2/2)" in payload["summary_line"]
    assert "interaction_family=yes(53/53)" in payload["summary_line"]
    assert "interaction_sources=3/3" in payload["summary_line"]
    assert "groups=shell-shell=15/15,shell-wall=15/15,footing-soil=15/15,ssi=1/1,soil-tunnel=1/1,direct-contact=6/6" in payload["summary_line"]
    assert payload["summary_line"].startswith("Solver breadth: PASS")


def test_solver_breadth_gate_keeps_general_fe_coupling_signal_when_element_material_report_is_absent(
    tmp_path: Path,
) -> None:
    topology = tmp_path / "topology.json"
    pushover = tmp_path / "pushover.json"
    diaphragm = tmp_path / "diaphragm.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    ndtha = tmp_path / "ndtha.json"
    structural_contact = tmp_path / "structural_contact_gate.json"
    general_fe_contact = tmp_path / "general_fe_contact.json"
    surface_interaction = tmp_path / "surface_interaction.json"
    cases = tmp_path / "cases.json"
    missing_element_material = tmp_path / "missing_element_material.json"
    out = tmp_path / "solver_breadth.json"

    _write(topology, {"contract_pass": True, "checks": {"shell_beam_mix_pass": True}, "metrics": {"shell_element_count": 2}})
    _write(
        pushover,
        {
            "contract_pass": True,
            "checks": {"material_model_pass": True, "section_family_pass": True},
            "summary": {"material_model": "rc_composite"},
            "rows": [
                {
                    "case_id": "wall-1",
                    "summary": {
                        "section_family_counts": {"wall_boundary": 2},
                        "material_indices": {"compression_damage_mean": 0.5},
                    },
                }
            ],
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
        ssi,
        {
            "contract_pass": True,
            "checks": {
                "ssi_nonlinear_boundary_active": True,
                "section_family_pass": True,
                "material_model_pass": True,
                "ssi_transfer_finite": True,
            },
        },
    )
    _write(
        substructuring,
        {
            "contract_pass": True,
            "checks": {"finite_transfer": True, "coupling_stability": True},
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
                    "case_id": "ndtha-1",
                    "summary": {"material_indices": {"compression_damage_mean": 0.5}},
                }
            ],
        },
    )
    _write(
        structural_contact,
        {
            "contract_pass": True,
            "checks": {
                "all_structural_contact_categories_ready": True,
                "structural_contact_event_sequence_zero_pass": True,
            },
        },
    )
    _write(
        general_fe_contact,
        {
            "contract_pass": True,
            "checks": {
                "direct_structural_contact_pass": True,
                "foundation_soil_link_pass": True,
                "interface_transfer_pass": True,
                "ssi_boundary_pass": True,
                "soil_tunnel_dynamic_pass": True,
                "support_search_family_surface_pass": True,
                "node_to_surface_proxy_family_surface_pass": True,
                "all_matrix_rows_ready": True,
            },
            "summary": {
                "ready_row_count": 10,
                "total_row_count": 10,
                "support_depth_score": 21,
                "coupling_depth_score": 31,
                "support_search_model_count": 9,
                "node_to_surface_proxy_model_count": 5,
                "support_search_family_count": 2,
                "node_to_surface_proxy_family_count": 2,
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
            },
        },
    )
    _write(
        surface_interaction,
        {
            "contract_pass": True,
            "checks": {
                "shell_surface_coupling_pass": True,
                "interface_transfer_pass": True,
                "interface_gap_continuity_pass": True,
                "foundation_soil_impedance_pass": True,
                "ssi_boundary_interaction_pass": True,
                "soil_tunnel_dynamic_interaction_pass": True,
                "direct_structural_contact_family_pass": True,
                "interaction_family_matrix_pass": True,
                "all_matrix_rows_ready": True,
            },
            "summary": {
                "ready_row_count": 7,
                "total_row_count": 7,
                "interaction_family_ready_count": 4,
                "interaction_family_total_count": 4,
                "interaction_source_family_ready_count": 2,
                "interaction_source_family_total_count": 2,
            },
        },
    )
    _write(
        cases,
        {
            "cases": [
                {
                    "case_id": "case-1",
                    "topology_type": "wall-frame",
                    "element_mix": "shell_beam_mix",
                    "source_family": "fixture",
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--topology-report",
            str(topology),
            "--pushover-stress-report",
            str(pushover),
            "--flexible-diaphragm-report",
            str(diaphragm),
            "--ssi-boundary-report",
            str(ssi),
            "--substructuring-interface-report",
            str(substructuring),
            "--ndtha-stress-report",
            str(ndtha),
            "--structural-contact-gate-report",
            str(structural_contact),
            "--general-fe-contact-benchmark-report",
            str(general_fe_contact),
            "--element-material-breadth-report",
            str(missing_element_material),
            "--surface-interaction-benchmark-report",
            str(surface_interaction),
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
    assert payload["summary"]["contact_coupling_source_label"] == "general_fe"
    assert payload["summary"]["contact_coupling_depth_score"] == 31
    assert payload["summary"]["contact_support_depth_score"] == 21
    assert payload["summary"]["contact_support_search_count"] == 9
    assert payload["summary"]["contact_node_surface_proxy_count"] == 5
    assert payload["summary"]["contact_support_family_ready_count"] == 2
    assert payload["summary"]["contact_support_family_total_count"] == 2
    assert payload["summary"]["contact_proxy_family_ready_count"] == 2
    assert payload["summary"]["contact_proxy_family_total_count"] == 2
    assert payload["summary"]["element_material_contact_coupling_present"] is False
    assert payload["summary"]["element_material_contact_coupling_signal_count"] == 0
    assert "contact_coupling=yes(depth=31,support=21,search=9,proxy=5)" in payload["summary_line"]
