from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_foundation_soil_link_gate.py")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_foundation_soil_link_gate_passes_with_foundation_ssi_and_link_evidence(tmp_path: Path) -> None:
    foundation_report = tmp_path / "foundation_report.json"
    foundation_artifact = tmp_path / "foundation_artifact.json"
    ssi = tmp_path / "ssi.json"
    soil_tunnel = tmp_path / "soil_tunnel.json"
    soil_impedance = tmp_path / "soil_impedance_table.json"
    structural_contact_validation = tmp_path / "structural_contact_validation.json"
    out = tmp_path / "foundation_soil_link_gate.json"

    _write(
        foundation_report,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_optimization_evidence_present": True,
            },
            "summary": {
                "foundation_member_type_count": 4,
                "foundation_scope_source": "dataset_summary",
                "optimization_mode": "active_foundation_member_optimization",
            },
        },
    )
    _write(
        foundation_artifact,
        {
            "contract_pass": True,
            "summary": {
                "optimized_foundation_group_count": 2,
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
            },
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
        },
    )
    soil_impedance.write_text(
        '{"properties":{"soil_profiles":{"additionalProperties":{"properties":{"impedance_functions":{"description":"Pre-computed impedance springs/dashpots for tunnel/track interface","properties":{"k_radial_N_m2":{},"k_tangential_N_m2":{},"c_radial_Ns_m2":{},"c_tangential_Ns_m2":{}}}}}}}}',
        encoding="utf-8",
    )
    _write(
        structural_contact_validation,
        {
            "contract_pass": True,
            "summary": {
                "link_model_types": [
                    "bearing_bilinear",
                    "compression_only_penalty",
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                ],
                "foundation_support_model_types": ["p-y", "q-z"],
                "device_model_types": ["friction_pendulum"],
                "support_search_model_types": ["p-y", "q-z"],
                "node_to_surface_proxy_model_types": ["p-y"],
                "support_search_family_types": ["foundation_support_search"],
                "node_to_surface_proxy_family_types": ["foundation_support_search"],
                "search_surface_mode_counts": {"node_to_soil_surface_proxy": 1},
                "search_family_counts": {"foundation_support_search": 2},
                "support_depth_score": 3,
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--foundation-optimization-report",
            str(foundation_report),
            "--foundation-optimization-artifact",
            str(foundation_artifact),
            "--ssi-boundary-report",
            str(ssi),
            "--soil-tunnel-ssi-report",
            str(soil_tunnel),
            "--soil-impedance-table",
            str(soil_impedance),
            "--structural-contact-validation-report",
            str(structural_contact_validation),
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
    assert payload["checks"]["foundation_scope_ready"] is True
    assert payload["checks"]["foundation_artifact_ready"] is True
    assert payload["checks"]["ssi_boundary_ready"] is True
    assert payload["checks"]["soil_tunnel_ready"] is True
    assert payload["checks"]["impedance_schema_ready"] is True
    assert payload["checks"]["foundation_link_models_ready"] is True
    assert payload["checks"]["foundation_support_model_surface_ready"] is True
    assert payload["checks"]["device_model_surface_ready"] is True
    assert payload["checks"]["contact_family_surface_ready"] is True
    assert payload["checks"]["support_search_surface_ready"] is True
    assert payload["checks"]["support_search_family_surface_ready"] is True
    assert payload["checks"]["node_to_surface_proxy_ready"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_ready"] is True
    assert payload["summary"]["foundation_member_type_count"] == 4
    assert payload["summary"]["optimized_foundation_group_count"] == 2
    assert payload["summary"]["missing_foundation_link_models"] == []
    assert payload["summary"]["contact_family_count"] == 4
    assert payload["summary"]["foundation_support_model_types"] == ["p-y", "pile_head", "q-z", "t-z"]
    assert payload["summary"]["device_model_types"] == [
        "friction_pendulum",
        "lead_rubber_bearing",
        "tmd",
        "viscoelastic_damper",
        "viscous_damper",
    ]
    assert payload["summary"]["support_search_model_types"] == [
        "friction_pendulum",
        "lead_rubber_bearing",
        "p-y",
        "pile_head",
        "q-z",
        "t-z",
        "tmd",
        "viscoelastic_damper",
        "viscous_damper",
    ]
    assert payload["summary"]["node_to_surface_proxy_model_types"] == [
        "friction_pendulum",
        "lead_rubber_bearing",
        "p-y",
        "q-z",
        "t-z",
    ]
    assert payload["summary"]["support_search_family_types"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    assert payload["summary"]["node_to_surface_proxy_family_types"] == [
        "device_support_search",
        "foundation_support_search",
    ]
    assert payload["summary"]["support_link_group_counts"] == {
        "contact": 4,
        "foundation": 4,
        "device": 5,
    }
    assert payload["summary"]["search_surface_mode_counts"]["brace_end_support_search"] == 2
    assert payload["summary"]["support_depth_score"] == 21
    assert payload["summary_line"].startswith("Foundation/soil link: PASS")
    assert "foundation_support=4" in payload["summary_line"]
    assert "devices=5" in payload["summary_line"]
    assert "support_search=9" in payload["summary_line"]
    assert "node_surface_proxy=5" in payload["summary_line"]
    assert "support_families=2" in payload["summary_line"]
    assert "proxy_families=2" in payload["summary_line"]


def test_foundation_soil_link_gate_ignores_stale_low_contact_family_count(tmp_path: Path) -> None:
    foundation_report = tmp_path / "foundation_report.json"
    foundation_artifact = tmp_path / "foundation_artifact.json"
    ssi = tmp_path / "ssi.json"
    soil_tunnel = tmp_path / "soil_tunnel.json"
    soil_impedance = tmp_path / "soil_impedance_table.json"
    structural_contact_validation = tmp_path / "structural_contact_validation.json"
    out = tmp_path / "foundation_soil_link_gate.json"

    _write(
        foundation_report,
        {
            "contract_pass": True,
            "checks": {
                "foundation_scope_ready": True,
                "foundation_optimization_evidence_present": True,
            },
            "summary": {
                "foundation_member_type_count": 4,
                "foundation_scope_source": "dataset_summary",
                "optimization_mode": "active_foundation_member_optimization",
            },
        },
    )
    _write(
        foundation_artifact,
        {
            "contract_pass": True,
            "summary": {
                "optimized_foundation_group_count": 2,
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
            },
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
        },
    )
    soil_impedance.write_text(
        '{"properties":{"soil_profiles":{"additionalProperties":{"properties":{"impedance_functions":{"properties":{"k_radial_N_m2":{},"k_tangential_N_m2":{},"c_radial_Ns_m2":{},"c_tangential_Ns_m2":{}}}}}}}}',
        encoding="utf-8",
    )
    _write(
        structural_contact_validation,
        {
            "contract_pass": True,
            "summary": {
                "contact_family_count": 1,
                "link_model_types": [
                    "bearing_bilinear",
                    "compression_only_penalty",
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                ],
                "support_link_group_counts": {
                    "contact": 4,
                },
            },
            "checks": {
                "support_search_surface_pass": True,
                "contact_family_surface_pass": True,
                "support_search_family_surface_pass": True,
                "node_to_surface_proxy_pass": True,
                "node_to_surface_proxy_family_surface_pass": True,
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--foundation-optimization-report",
            str(foundation_report),
            "--foundation-optimization-artifact",
            str(foundation_artifact),
            "--ssi-boundary-report",
            str(ssi),
            "--soil-tunnel-ssi-report",
            str(soil_tunnel),
            "--soil-impedance-table",
            str(soil_impedance),
            "--structural-contact-validation-report",
            str(structural_contact_validation),
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
    assert payload["checks"]["contact_family_surface_ready"] is True
    assert payload["summary"]["contact_family_count"] == 4
