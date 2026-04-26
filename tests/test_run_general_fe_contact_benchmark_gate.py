from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_general_fe_contact_benchmark_gate.py")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_gate(
    validation: Path,
    structural_gate: Path,
    foundation: Path,
    ssi: Path,
    substructuring: Path,
    soil_tunnel: Path,
    out: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--structural-contact-validation-report",
            str(validation),
            "--structural-contact-gate-report",
            str(structural_gate),
            "--foundation-soil-link-gate-report",
            str(foundation),
            "--ssi-boundary-report",
            str(ssi),
            "--substructuring-interface-report",
            str(substructuring),
            "--soil-tunnel-ssi-report",
            str(soil_tunnel),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_general_fe_contact_benchmark_gate_passes_with_direct_and_interface_evidence(tmp_path: Path) -> None:
    validation = tmp_path / "validation.json"
    structural_gate = tmp_path / "structural_contact_gate.json"
    foundation = tmp_path / "foundation.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    soil_tunnel = tmp_path / "soil_tunnel.json"
    out = tmp_path / "general_fe_contact.json"

    _write(
        validation,
        {
            "contract_pass": True,
            "summary": {
                "link_model_types": [
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                    "compression_only_penalty",
                    "bearing_bilinear",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                ],
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
                    "t-z",
                ],
                "search_surface_mode_counts": {
                    "node_to_soil_surface_proxy": 1,
                    "node_to_shaft_surface_proxy": 1,
                    "node_to_tip_surface_proxy": 1,
                    "support_head_rotation_search": 1,
                    "brace_end_support_search": 2,
                    "node_to_surface_isolation_proxy": 2,
                    "tuned_mass_attachment_search": 1,
                },
                "search_family_counts": {
                    "foundation_support_search": 4,
                    "device_support_search": 5,
                },
                "support_depth_score": 21,
            },
            "categories": {
                "gap": {"validated": True, "link_model_type": "normal_gap_unilateral", "implementation_class": "unilateral_gap"},
                "uplift": {"validated": True, "link_model_type": "uplift_seat_unilateral", "implementation_class": "unilateral_uplift"},
                "compression_only": {"validated": True, "link_model_type": "compression_only_penalty", "implementation_class": "compression_only"},
                "bearing": {"validated": True, "link_model_type": "bearing_bilinear", "implementation_class": "bearing"},
                "friction": {"validated": True, "link_model_type": "coulomb_friction", "implementation_class": "friction"},
                "pounding": {"validated": True, "link_model_type": "kelvin_voigt_pounding", "implementation_class": "impact"},
            },
        },
    )
    _write(
        structural_gate,
        {
            "contract_pass": True,
            "checks": {
                "gap_ready": True,
                "uplift_ready": True,
                "compression_only_ready": True,
                "bearing_ready": True,
                "friction_ready": True,
                "pounding_ready": True,
                "all_structural_contact_categories_ready": True,
                "support_search_surface_present": True,
                "node_to_surface_proxy_surface_present": True,
                "support_depth_surface_present": True,
                "support_search_family_surface_present": True,
                "node_to_surface_proxy_family_surface_present": True,
            },
            "support_surface_evidence": {
                "support_link_group_counts": {
                    "contact": 6,
                    "foundation": 4,
                    "device": 5,
                },
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
                    "t-z",
                ],
                "search_surface_mode_counts": {
                    "node_to_soil_surface_proxy": 1,
                    "node_to_shaft_surface_proxy": 1,
                    "node_to_tip_surface_proxy": 1,
                    "support_head_rotation_search": 1,
                    "brace_end_support_search": 2,
                    "node_to_surface_isolation_proxy": 2,
                    "tuned_mass_attachment_search": 1,
                },
                "search_family_counts": {
                    "foundation_support_search": 4,
                    "device_support_search": 5,
                },
                "support_search_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 21,
            },
            "category_readiness": [
                {"category": "gap", "ready": True},
                {"category": "uplift", "ready": True},
                {"category": "compression-only", "ready": True},
                {"category": "bearing", "ready": True},
                {"category": "friction", "ready": True},
                {"category": "pounding", "ready": True},
            ],
        },
    )
    _write(
        foundation,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_artifact_ready": True,
                "foundation_link_models_ready": True,
            },
            "summary": {
                "foundation_member_type_count": 76,
                "optimized_foundation_group_count": 2,
                "foundation_support_model_types": ["p-y", "pile_head", "q-z", "t-z"],
                "device_model_types": [
                    "friction_pendulum",
                    "lead_rubber_bearing",
                    "tmd",
                    "viscoelastic_damper",
                    "viscous_damper",
                ],
                "support_library_group_counts": {
                    "contact": 6,
                    "foundation": 4,
                    "device": 5,
                },
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
                    "t-z",
                ],
                "support_search_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 21,
            },
        },
    )
    _write(
        ssi,
        {
            "contract_pass": True,
            "checks": {
                "ssi_nonlinear_boundary_active": True,
                "ssi_transfer_finite": True,
                "material_model_pass": True,
                "section_family_pass": True,
            },
        },
    )
    _write(
        substructuring,
        {
            "contract_pass": True,
            "checks": {
                "finite_transfer": True,
                "coupling_stability": True,
            },
            "metrics": {"mean_transfer_ratio_building_to_track": 0.45},
        },
    )
    _write(
        soil_tunnel,
        {
            "contract_pass": True,
            "checks": {
                "finite_response": True,
                "monotonic_stiffness": True,
                "positive_damping": True,
                "high_freq_attenuation": True,
            },
            "metrics": {
                "k_min": 1.2,
                "k_max": 4.8,
                "c_min": 0.11,
                "c_max": 0.37,
            },
        },
    )

    proc = _run_gate(validation, structural_gate, foundation, ssi, substructuring, soil_tunnel, out)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["direct_structural_contact_pass"] is True
    assert payload["checks"]["foundation_soil_link_pass"] is True
    assert payload["checks"]["interface_transfer_pass"] is True
    assert payload["checks"]["ssi_boundary_pass"] is True
    assert payload["checks"]["soil_tunnel_dynamic_pass"] is True
    assert payload["checks"]["support_search_surface_pass"] is True
    assert payload["checks"]["node_to_surface_proxy_surface_pass"] is True
    assert payload["checks"]["support_depth_surface_pass"] is True
    assert payload["checks"]["support_search_family_surface_required"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_required"] is True
    assert payload["checks"]["support_search_family_surface_explicit"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_explicit"] is True
    assert payload["checks"]["support_search_family_requirements_met"] is True
    assert payload["checks"]["node_to_surface_proxy_family_requirements_met"] is True
    assert payload["checks"]["support_search_family_count_coverage_pass"] is True
    assert payload["checks"]["support_search_family_surface_pass"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_pass"] is True
    assert payload["checks"]["all_matrix_rows_ready"] is True
    assert payload["summary"]["ready_row_count"] == 10
    assert payload["summary"]["total_row_count"] == 10
    assert payload["summary"]["direct_structural_contact_ready_count"] == 6
    assert payload["summary"]["direct_structural_contact_total_count"] == 6
    assert payload["summary"]["support_link_group_counts"] == {"contact": 6, "foundation": 4, "device": 5}
    assert payload["summary"]["support_depth_score"] == 21
    assert payload["summary"]["coupling_depth_score"] == 31
    assert len(payload["summary"]["support_search_model_types"]) == 9
    assert len(payload["summary"]["node_to_surface_proxy_model_types"]) == 5
    assert payload["summary"]["support_search_family_types"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    assert payload["summary"]["support_search_missing_family_types"] == []
    assert payload["summary"]["support_search_missing_family_counts"] == []
    assert payload["summary"]["node_to_surface_proxy_family_types"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    assert payload["summary"]["node_to_surface_proxy_missing_family_types"] == []
    surface = payload["general_fe_contact_matrix_surface"]
    assert surface == payload["summary"]["general_fe_contact_matrix_surface"]
    assert surface["status"] == "PASS"
    assert surface["support_link_group_counts"] == {"contact": 6, "foundation": 4, "device": 5}
    assert surface["support_search_model_count"] == 9
    assert surface["node_to_surface_proxy_model_count"] == 5
    assert surface["support_depth_score"] == 21
    assert surface["coupling_depth_score"] == 31
    assert surface["support_search_family_count"] == 2
    assert surface["support_search_family_requirement_count"] == 2
    assert surface["node_to_surface_proxy_family_count"] == 2
    assert surface["node_to_surface_proxy_family_requirement_count"] == 2
    assert surface["support_search_family_surface_pass"] is True
    assert surface["node_to_surface_proxy_family_surface_pass"] is True
    assert payload["summary_line"].startswith("General FE contact matrix: PASS")
    assert "support=contact:6,foundation:4,device:5" in payload["summary_line"]
    assert "support_search=9" in payload["summary_line"]
    assert "node_surface_proxy=5" in payload["summary_line"]
    assert "support_depth=21" in payload["summary_line"]
    assert "coupling_depth=31" in payload["summary_line"]
    assert "support_families=2/2" in payload["summary_line"]
    assert "proxy_families=2/2" in payload["summary_line"]


def test_general_fe_contact_benchmark_gate_fails_when_support_family_surface_is_incomplete(tmp_path: Path) -> None:
    validation = tmp_path / "validation.json"
    structural_gate = tmp_path / "structural_contact_gate.json"
    foundation = tmp_path / "foundation.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    soil_tunnel = tmp_path / "soil_tunnel.json"
    out = tmp_path / "general_fe_contact.json"

    _write(
        validation,
        {
            "contract_pass": True,
            "summary": {
                "link_model_types": [
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                    "compression_only_penalty",
                    "bearing_bilinear",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                ],
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
                    "t-z",
                ],
                "search_family_counts": {
                    "foundation_support_search": 4,
                },
                "support_search_family_types": [
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 21,
            },
            "categories": {
                "gap": {"validated": True, "link_model_type": "normal_gap_unilateral", "implementation_class": "unilateral_gap"},
                "uplift": {"validated": True, "link_model_type": "uplift_seat_unilateral", "implementation_class": "unilateral_uplift"},
                "compression_only": {"validated": True, "link_model_type": "compression_only_penalty", "implementation_class": "compression_only"},
                "bearing": {"validated": True, "link_model_type": "bearing_bilinear", "implementation_class": "bearing"},
                "friction": {"validated": True, "link_model_type": "coulomb_friction", "implementation_class": "friction"},
                "pounding": {"validated": True, "link_model_type": "kelvin_voigt_pounding", "implementation_class": "impact"},
            },
        },
    )
    _write(
        structural_gate,
        {
            "contract_pass": True,
            "checks": {
                "gap_ready": True,
                "uplift_ready": True,
                "compression_only_ready": True,
                "bearing_ready": True,
                "friction_ready": True,
                "pounding_ready": True,
                "all_structural_contact_categories_ready": True,
                "support_search_surface_present": True,
                "node_to_surface_proxy_surface_present": True,
                "support_depth_surface_present": True,
                "support_search_family_surface_present": False,
                "node_to_surface_proxy_family_surface_present": False,
            },
            "support_surface_evidence": {
                "support_link_group_counts": {
                    "contact": 6,
                    "foundation": 4,
                    "device": 5,
                },
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
                    "t-z",
                ],
                "search_family_counts": {
                    "foundation_support_search": 4,
                },
                "support_search_family_types": [
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 21,
            },
            "category_readiness": [
                {"category": "gap", "ready": True},
                {"category": "uplift", "ready": True},
                {"category": "compression-only", "ready": True},
                {"category": "bearing", "ready": True},
                {"category": "friction", "ready": True},
                {"category": "pounding", "ready": True},
            ],
        },
    )
    _write(
        foundation,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_artifact_ready": True,
                "foundation_link_models_ready": True,
                "support_search_surface_ready": True,
                "node_to_surface_proxy_surface_ready": True,
                "support_search_family_surface_ready": False,
                "node_to_surface_proxy_family_surface_ready": False,
            },
            "summary": {
                "foundation_member_type_count": 76,
                "optimized_foundation_group_count": 2,
                "support_library_group_counts": {
                    "contact": 6,
                    "foundation": 4,
                    "device": 5,
                },
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
                    "t-z",
                ],
                "support_search_family_types": [
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "search_family_counts": {
                    "foundation_support_search": 4,
                },
                "support_depth_score": 21,
            },
        },
    )
    for path, payload in (
        (
            ssi,
            {
                "contract_pass": True,
                "checks": {
                    "ssi_nonlinear_boundary_active": True,
                    "ssi_transfer_finite": True,
                    "material_model_pass": True,
                },
            },
        ),
        (
            substructuring,
            {
                "contract_pass": True,
                "checks": {"finite_transfer": True, "coupling_stability": True},
                "metrics": {"mean_transfer_ratio_building_to_track": 0.45},
            },
        ),
        (
            soil_tunnel,
            {
                "contract_pass": True,
                "checks": {
                    "finite_response": True,
                    "monotonic_stiffness": True,
                    "positive_damping": True,
                    "high_freq_attenuation": True,
                },
                "metrics": {
                    "k_min": 1.2,
                    "k_max": 4.8,
                    "c_min": 0.11,
                    "c_max": 0.37,
                },
            },
        ),
    ):
        _write(path, payload)

    proc = _run_gate(validation, structural_gate, foundation, ssi, substructuring, soil_tunnel, out)
    assert proc.returncode == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["checks"]["support_search_family_surface_required"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_required"] is True
    assert payload["checks"]["support_search_family_surface_explicit"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_explicit"] is True
    assert payload["checks"]["support_search_family_requirements_met"] is False
    assert payload["checks"]["node_to_surface_proxy_family_requirements_met"] is False
    assert payload["checks"]["support_search_family_count_coverage_pass"] is False
    assert payload["checks"]["support_search_family_surface_pass"] is False
    assert payload["checks"]["node_to_surface_proxy_family_surface_pass"] is False
    assert payload["reason_code"] == "ERR_SUPPORT_FAMILY_SURFACE"
    surface = payload["general_fe_contact_matrix_surface"]
    assert surface["status"] == "CHECK"
    assert surface["support_search_family_count"] == 1
    assert surface["support_search_family_requirement_count"] == 2
    assert surface["node_to_surface_proxy_family_count"] == 1
    assert surface["node_to_surface_proxy_family_requirement_count"] == 2
    assert surface["support_search_family_surface_pass"] is False
    assert surface["node_to_surface_proxy_family_surface_pass"] is False
    assert surface["support_search_missing_family_types"] == ["device_support_search"]
    assert surface["support_search_missing_family_counts"] == ["device_support_search"]
    assert surface["node_to_surface_proxy_missing_family_types"] == ["device_support_search"]


def test_general_fe_contact_benchmark_gate_merges_partial_structural_surface_with_foundation_summary(
    tmp_path: Path,
) -> None:
    validation = tmp_path / "validation.json"
    structural_gate = tmp_path / "structural_contact_gate.json"
    foundation = tmp_path / "foundation.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    soil_tunnel = tmp_path / "soil_tunnel.json"
    out = tmp_path / "general_fe_contact.json"

    _write(
        validation,
        {
            "contract_pass": True,
            "summary": {
                "link_model_types": [
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                    "compression_only_penalty",
                    "bearing_bilinear",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                ],
                "support_search_model_types": ["p-y", "q-z"],
                "node_to_surface_proxy_model_types": ["p-y"],
                "search_family_counts": {"foundation_support_search": 2},
                "support_search_family_types": ["foundation_support_search"],
                "node_to_surface_proxy_family_types": ["foundation_support_search"],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 7,
            },
            "categories": {
                "gap": {"validated": True, "link_model_type": "normal_gap_unilateral", "implementation_class": "unilateral_gap"},
                "uplift": {"validated": True, "link_model_type": "uplift_seat_unilateral", "implementation_class": "unilateral_uplift"},
                "compression_only": {"validated": True, "link_model_type": "compression_only_penalty", "implementation_class": "compression_only"},
                "bearing": {"validated": True, "link_model_type": "bearing_bilinear", "implementation_class": "bearing"},
                "friction": {"validated": True, "link_model_type": "coulomb_friction", "implementation_class": "friction"},
                "pounding": {"validated": True, "link_model_type": "kelvin_voigt_pounding", "implementation_class": "impact"},
            },
        },
    )
    _write(
        structural_gate,
        {
            "contract_pass": True,
            "checks": {
                "gap_ready": True,
                "uplift_ready": True,
                "compression_only_ready": True,
                "bearing_ready": True,
                "friction_ready": True,
                "pounding_ready": True,
                "all_structural_contact_categories_ready": True,
                "support_search_surface_present": True,
                "node_to_surface_proxy_surface_present": True,
                "support_depth_surface_present": True,
                "support_search_family_surface_present": False,
                "node_to_surface_proxy_family_surface_present": False,
            },
            "support_surface_evidence": {
                "support_link_group_counts": {
                    "contact": 6,
                    "foundation": 2,
                    "device": 0,
                },
                "support_search_model_types": ["p-y", "q-z"],
                "node_to_surface_proxy_model_types": ["p-y"],
                "search_family_counts": {"foundation_support_search": 2},
                "support_search_family_types": ["foundation_support_search"],
                "node_to_surface_proxy_family_types": ["foundation_support_search"],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 7,
            },
            "category_readiness": [
                {"category": "gap", "ready": True},
                {"category": "uplift", "ready": True},
                {"category": "compression-only", "ready": True},
                {"category": "bearing", "ready": True},
                {"category": "friction", "ready": True},
                {"category": "pounding", "ready": True},
            ],
        },
    )
    _write(
        foundation,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_artifact_ready": True,
                "foundation_link_models_ready": True,
                "support_search_surface_ready": True,
                "node_to_surface_proxy_surface_ready": True,
                "support_search_family_surface_ready": True,
                "node_to_surface_proxy_family_surface_ready": True,
            },
            "summary": {
                "foundation_member_type_count": 76,
                "optimized_foundation_group_count": 2,
                "support_library_group_counts": {
                    "contact": 6,
                    "foundation": 4,
                    "device": 5,
                },
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
                    "t-z",
                ],
                "search_family_counts": {
                    "foundation_support_search": 4,
                    "device_support_search": 5,
                },
                "support_search_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 21,
            },
        },
    )
    for path, payload in (
        (
            ssi,
            {
                "contract_pass": True,
                "checks": {
                    "ssi_nonlinear_boundary_active": True,
                    "ssi_transfer_finite": True,
                    "material_model_pass": True,
                    "section_family_pass": True,
                },
            },
        ),
        (
            substructuring,
            {
                "contract_pass": True,
                "checks": {
                    "finite_transfer": True,
                    "coupling_stability": True,
                },
                "metrics": {"mean_transfer_ratio_building_to_track": 0.45},
            },
        ),
        (
            soil_tunnel,
            {
                "contract_pass": True,
                "checks": {
                    "finite_response": True,
                    "monotonic_stiffness": True,
                    "positive_damping": True,
                    "high_freq_attenuation": True,
                },
                "metrics": {
                    "k_min": 1.2,
                    "k_max": 4.8,
                    "c_min": 0.11,
                    "c_max": 0.37,
                },
            },
        ),
    ):
        _write(path, payload)

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--structural-contact-validation-report",
            str(validation),
            "--structural-contact-gate-report",
            str(structural_gate),
            "--foundation-soil-link-gate-report",
            str(foundation),
            "--ssi-boundary-report",
            str(ssi),
            "--substructuring-interface-report",
            str(substructuring),
            "--soil-tunnel-ssi-report",
            str(soil_tunnel),
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
    assert payload["summary"]["support_link_group_counts"] == {"contact": 6, "foundation": 4, "device": 5}
    assert payload["summary"]["support_search_family_types"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    assert payload["summary"]["node_to_surface_proxy_family_types"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    assert payload["summary"]["support_depth_score"] == 21
    surface = payload["general_fe_contact_matrix_surface"]
    assert surface["support_link_group_counts"] == {"contact": 6, "foundation": 4, "device": 5}
    assert surface["support_search_family_count"] == 2
    assert surface["node_to_surface_proxy_family_count"] == 2
    assert surface["coupling_depth_score"] == 31
    assert "support_families=2/2" in payload["summary_line"]
    assert "proxy_families=2/2" in payload["summary_line"]


def test_general_fe_contact_benchmark_gate_fails_when_family_flags_exist_without_explicit_coverage(tmp_path: Path) -> None:
    validation = tmp_path / "validation.json"
    structural_gate = tmp_path / "structural_contact_gate.json"
    foundation = tmp_path / "foundation.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    soil_tunnel = tmp_path / "soil_tunnel.json"
    out = tmp_path / "general_fe_contact.json"

    _write(
        validation,
        {
            "contract_pass": True,
            "summary": {
                "link_model_types": [
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                    "compression_only_penalty",
                    "bearing_bilinear",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                ],
                "support_search_model_types": ["friction_pendulum", "p-y"],
                "node_to_surface_proxy_model_types": ["friction_pendulum", "p-y"],
                "support_depth_score": 21,
            },
            "categories": {
                "gap": {"validated": True, "link_model_type": "normal_gap_unilateral", "implementation_class": "unilateral_gap"},
                "uplift": {"validated": True, "link_model_type": "uplift_seat_unilateral", "implementation_class": "unilateral_uplift"},
                "compression_only": {"validated": True, "link_model_type": "compression_only_penalty", "implementation_class": "compression_only"},
                "bearing": {"validated": True, "link_model_type": "bearing_bilinear", "implementation_class": "bearing"},
                "friction": {"validated": True, "link_model_type": "coulomb_friction", "implementation_class": "friction"},
                "pounding": {"validated": True, "link_model_type": "kelvin_voigt_pounding", "implementation_class": "impact"},
            },
        },
    )
    _write(
        structural_gate,
        {
            "contract_pass": True,
            "checks": {
                "gap_ready": True,
                "uplift_ready": True,
                "compression_only_ready": True,
                "bearing_ready": True,
                "friction_ready": True,
                "pounding_ready": True,
                "support_search_surface_present": True,
                "node_to_surface_proxy_surface_present": True,
                "support_depth_surface_present": True,
                "support_search_family_surface_present": True,
                "node_to_surface_proxy_family_surface_present": True,
            },
            "support_surface_evidence": {
                "support_link_group_counts": {"contact": 6, "foundation": 4, "device": 5},
                "support_search_model_types": ["friction_pendulum", "p-y"],
                "node_to_surface_proxy_model_types": ["friction_pendulum", "p-y"],
                "support_depth_score": 21,
            },
            "category_readiness": [
                {"category": "gap", "ready": True},
                {"category": "uplift", "ready": True},
                {"category": "compression-only", "ready": True},
                {"category": "bearing", "ready": True},
                {"category": "friction", "ready": True},
                {"category": "pounding", "ready": True},
            ],
        },
    )
    _write(
        foundation,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_artifact_ready": True,
                "foundation_link_models_ready": True,
                "support_search_surface_ready": True,
                "node_to_surface_proxy_surface_ready": True,
                "support_search_family_surface_ready": True,
                "node_to_surface_proxy_family_surface_ready": True,
            },
            "summary": {
                "foundation_member_type_count": 76,
                "optimized_foundation_group_count": 2,
                "support_library_group_counts": {"contact": 6, "foundation": 4, "device": 5},
                "support_search_model_types": ["friction_pendulum", "p-y"],
                "node_to_surface_proxy_model_types": ["friction_pendulum", "p-y"],
                "support_depth_score": 21,
            },
        },
    )
    for path, payload in (
        (
            ssi,
            {
                "contract_pass": True,
                "checks": {
                    "ssi_nonlinear_boundary_active": True,
                    "ssi_transfer_finite": True,
                    "material_model_pass": True,
                },
            },
        ),
        (
            substructuring,
            {
                "contract_pass": True,
                "checks": {"finite_transfer": True, "coupling_stability": True},
                "metrics": {"mean_transfer_ratio_building_to_track": 0.45},
            },
        ),
        (
            soil_tunnel,
            {
                "contract_pass": True,
                "checks": {
                    "finite_response": True,
                    "monotonic_stiffness": True,
                    "positive_damping": True,
                    "high_freq_attenuation": True,
                },
                "metrics": {
                    "k_min": 1.2,
                    "k_max": 4.8,
                    "c_min": 0.11,
                    "c_max": 0.37,
                },
            },
        ),
    ):
        _write(path, payload)

    proc = _run_gate(validation, structural_gate, foundation, ssi, substructuring, soil_tunnel, out)
    assert proc.returncode == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["checks"]["support_search_surface_pass"] is True
    assert payload["checks"]["node_to_surface_proxy_surface_pass"] is True
    assert payload["checks"]["support_search_family_surface_required"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_required"] is True
    assert payload["checks"]["support_search_family_surface_explicit"] is False
    assert payload["checks"]["node_to_surface_proxy_family_surface_explicit"] is False
    assert payload["checks"]["support_search_family_requirements_met"] is False
    assert payload["checks"]["node_to_surface_proxy_family_requirements_met"] is False
    assert payload["checks"]["support_search_family_count_coverage_pass"] is False
    assert payload["checks"]["support_search_family_surface_pass"] is False
    assert payload["checks"]["node_to_surface_proxy_family_surface_pass"] is False
    assert payload["reason_code"] == "ERR_SUPPORT_FAMILY_SURFACE"
    assert payload["summary"]["support_search_missing_family_types"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    assert payload["summary"]["support_search_missing_family_counts"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    assert payload["summary"]["node_to_surface_proxy_missing_family_types"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    surface = payload["general_fe_contact_matrix_surface"]
    assert surface["status"] == "CHECK"
    assert surface["support_search_family_count"] == 0
    assert surface["support_search_family_requirement_count"] == 2
    assert surface["node_to_surface_proxy_family_count"] == 0
    assert surface["node_to_surface_proxy_family_requirement_count"] == 2
    assert surface["support_search_family_surface_pass"] is False
    assert surface["node_to_surface_proxy_family_surface_pass"] is False


def test_general_fe_contact_benchmark_gate_fails_when_proxy_surface_lacks_required_family_span(tmp_path: Path) -> None:
    validation = tmp_path / "validation.json"
    structural_gate = tmp_path / "structural_contact_gate.json"
    foundation = tmp_path / "foundation.json"
    ssi = tmp_path / "ssi.json"
    substructuring = tmp_path / "substructuring.json"
    soil_tunnel = tmp_path / "soil_tunnel.json"
    out = tmp_path / "general_fe_contact.json"

    _write(
        validation,
        {
            "contract_pass": True,
            "summary": {
                "link_model_types": [
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                    "compression_only_penalty",
                    "bearing_bilinear",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                ],
                "support_search_model_types": ["friction_pendulum", "p-y"],
                "node_to_surface_proxy_model_types": ["friction_pendulum", "p-y"],
                "search_family_counts": {
                    "device_support_search": 1,
                    "foundation_support_search": 1,
                },
                "support_search_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 21,
            },
            "categories": {
                "gap": {"validated": True, "link_model_type": "normal_gap_unilateral", "implementation_class": "unilateral_gap"},
                "uplift": {"validated": True, "link_model_type": "uplift_seat_unilateral", "implementation_class": "unilateral_uplift"},
                "compression_only": {"validated": True, "link_model_type": "compression_only_penalty", "implementation_class": "compression_only"},
                "bearing": {"validated": True, "link_model_type": "bearing_bilinear", "implementation_class": "bearing"},
                "friction": {"validated": True, "link_model_type": "coulomb_friction", "implementation_class": "friction"},
                "pounding": {"validated": True, "link_model_type": "kelvin_voigt_pounding", "implementation_class": "impact"},
            },
        },
    )
    _write(
        structural_gate,
        {
            "contract_pass": True,
            "checks": {
                "gap_ready": True,
                "uplift_ready": True,
                "compression_only_ready": True,
                "bearing_ready": True,
                "friction_ready": True,
                "pounding_ready": True,
                "support_search_surface_present": True,
                "node_to_surface_proxy_surface_present": True,
                "support_depth_surface_present": True,
                "support_search_family_surface_present": True,
                "node_to_surface_proxy_family_surface_present": True,
            },
            "support_surface_evidence": {
                "support_link_group_counts": {"contact": 6, "foundation": 4, "device": 5},
                "support_search_model_types": ["friction_pendulum", "p-y"],
                "node_to_surface_proxy_model_types": ["friction_pendulum", "p-y"],
                "search_family_counts": {
                    "device_support_search": 1,
                    "foundation_support_search": 1,
                },
                "support_search_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 21,
            },
            "category_readiness": [
                {"category": "gap", "ready": True},
                {"category": "uplift", "ready": True},
                {"category": "compression-only", "ready": True},
                {"category": "bearing", "ready": True},
                {"category": "friction", "ready": True},
                {"category": "pounding", "ready": True},
            ],
        },
    )
    _write(
        foundation,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_artifact_ready": True,
                "foundation_link_models_ready": True,
                "support_search_surface_ready": True,
                "node_to_surface_proxy_surface_ready": True,
                "support_search_family_surface_ready": True,
                "node_to_surface_proxy_family_surface_ready": True,
            },
            "summary": {
                "foundation_member_type_count": 76,
                "optimized_foundation_group_count": 2,
                "support_library_group_counts": {"contact": 6, "foundation": 4, "device": 5},
                "support_search_model_types": ["friction_pendulum", "p-y"],
                "node_to_surface_proxy_model_types": ["friction_pendulum", "p-y"],
                "search_family_counts": {
                    "device_support_search": 1,
                    "foundation_support_search": 1,
                },
                "support_search_family_types": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "node_to_surface_proxy_family_types": [
                    "foundation_support_search",
                ],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "support_depth_score": 21,
            },
        },
    )
    for path, payload in (
        (
            ssi,
            {
                "contract_pass": True,
                "checks": {
                    "ssi_nonlinear_boundary_active": True,
                    "ssi_transfer_finite": True,
                    "material_model_pass": True,
                },
            },
        ),
        (
            substructuring,
            {
                "contract_pass": True,
                "checks": {"finite_transfer": True, "coupling_stability": True},
                "metrics": {"mean_transfer_ratio_building_to_track": 0.45},
            },
        ),
        (
            soil_tunnel,
            {
                "contract_pass": True,
                "checks": {
                    "finite_response": True,
                    "monotonic_stiffness": True,
                    "positive_damping": True,
                    "high_freq_attenuation": True,
                },
                "metrics": {
                    "k_min": 1.2,
                    "k_max": 4.8,
                    "c_min": 0.11,
                    "c_max": 0.37,
                },
            },
        ),
    ):
        _write(path, payload)

    proc = _run_gate(validation, structural_gate, foundation, ssi, substructuring, soil_tunnel, out)
    assert proc.returncode == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["checks"]["support_search_family_surface_pass"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_required"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_explicit"] is True
    assert payload["checks"]["node_to_surface_proxy_family_requirements_met"] is False
    assert payload["checks"]["node_to_surface_proxy_family_surface_pass"] is False
    assert payload["summary"]["node_to_surface_proxy_missing_family_types"] == ["device_support_search"]
    surface = payload["general_fe_contact_matrix_surface"]
    assert surface["status"] == "CHECK"
    assert surface["support_search_family_count"] == 2
    assert surface["node_to_surface_proxy_family_count"] == 1
    assert surface["node_to_surface_proxy_family_requirement_count"] == 2
    assert surface["node_to_surface_proxy_family_surface_pass"] is False
    assert surface["node_to_surface_proxy_missing_family_types"] == ["device_support_search"]
    assert payload["reason_code"] == "ERR_SUPPORT_FAMILY_SURFACE"
