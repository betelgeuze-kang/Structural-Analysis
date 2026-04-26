from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from implementation.phase1.advanced_ssi import build_report


def _sample_payload() -> dict:
    return {
        "soil_profile": {
            "profile_id": "seoul_layered_dense_transition",
            "groundwater_depth_m": 2.0,
            "layers": [
                {
                    "layer_id": "fill",
                    "thickness_m": 4.0,
                    "density_kg_m3": 1850.0,
                    "shear_wave_velocity_m_s": 170.0,
                    "damping_ratio": 0.08,
                    "poisson_ratio": 0.34,
                },
                {
                    "layer_id": "dense_sand",
                    "thickness_m": 10.0,
                    "density_kg_m3": 1950.0,
                    "shear_wave_velocity_m_s": 310.0,
                    "damping_ratio": 0.05,
                    "poisson_ratio": 0.30,
                },
                {
                    "layer_id": "weathered_rock",
                    "thickness_m": 20.0,
                    "density_kg_m3": 2200.0,
                    "shear_wave_velocity_m_s": 760.0,
                    "damping_ratio": 0.03,
                    "poisson_ratio": 0.25,
                },
            ],
        },
        "foundation_groups": [
            {
                "group_id": "MAT_CORE",
                "foundation_type": "raft",
                "count": 1,
                "length_m": 18.0,
                "width_m": 12.0,
                "embedment_m": 2.5,
                "mass_tonnes": 2400.0,
                "structure_period_s": 1.6,
                "structural_damping_ratio": 0.05,
                "base_shear_share": 0.58,
            },
            {
                "group_id": "PILE_PERIM",
                "foundation_type": "pilecap",
                "count": 6,
                "length_m": 5.5,
                "width_m": 5.5,
                "embedment_m": 6.0,
                "mass_tonnes": 420.0,
                "structure_period_s": 1.05,
                "structural_damping_ratio": 0.06,
                "base_shear_share": 0.42,
            },
        ],
        "hazard": {
            "dominant_frequency_hz": 2.4,
            "pga_g": 0.32,
        },
        "frequency_grid": {
            "f_min_hz": 0.4,
            "f_max_hz": 10.0,
            "f_count": 56,
            "reference_frequency_hz": 3.0,
        },
    }


def test_build_advanced_ssi_report_summarizes_layered_profile_and_grouped_foundations() -> None:
    payload = build_report(_sample_payload())

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["soil_layer_count"] == 3
    assert payload["summary"]["foundation_group_count"] == 2
    assert payload["summary"]["foundation_instance_count"] == 7
    assert payload["summary"]["vs30_m_s"] > 300.0
    assert payload["summary"]["soil_impedance_contrast_ratio_max"] > 1.0
    assert payload["checks"]["positive_impedance"] is True
    assert payload["checks"]["finite_transfer"] is True
    assert payload["summary_line"].startswith("Advanced SSI: PASS")
    assert payload["impedance_summary"]["tokens"][0] == "k_horizontal_n_m"
    assert payload["transfer_summary"]["peak_transfer_ratio_max"] >= 1.0
    assert payload["amplification_summary"]["peak_amplification_ratio_max"] >= payload["transfer_summary"]["peak_transfer_ratio_max"]
    assert payload["checks"]["frequency_response_metrics_finite"] is True
    assert payload["checks"]["pile_group_interaction_metrics_finite"] is True
    assert payload["frequency_response_summary"]["max_hazard_detuning_ratio"] >= 0.0
    assert payload["pile_group_interaction_summary"]["min_interaction_efficiency_ratio"] <= 1.0
    assert payload["results_explorer"]["entry_kind"] == "advanced_ssi_reduced_order"
    assert payload["group_reports"][0]["curve_head"][0]["frequency_hz"] == 0.4
    assert payload["group_reports"][0]["frequency_response_metrics"]["transfer_half_power_bandwidth_hz"] >= 0.0
    assert payload["group_reports"][0]["frequency_response_metrics"]["transfer_high_frequency_decay_ratio"] <= 1.0
    assert payload["group_reports"][1]["pile_group_interaction"]["grouping_regime"] != "single_foundation"
    assert payload["group_reports"][1]["pile_group_interaction"]["interaction_efficiency_ratio"] < 1.0


def test_build_advanced_ssi_report_orders_groups_and_exposes_governing_group() -> None:
    payload = build_report(_sample_payload())

    group_ids = [row["group_id"] for row in payload["group_reports"]]
    assert group_ids == ["MAT_CORE", "PILE_PERIM"]
    governing = payload["summary"]["governing_response_group_id"]
    assert governing in group_ids
    transfer_governing = payload["transfer_summary"]["governing_group_id"]
    assert transfer_governing in group_ids
    mat_k = payload["group_reports"][0]["impedance_reference"]["k_horizontal_n_m"]
    pile_k = payload["group_reports"][1]["impedance_reference"]["k_horizontal_n_m"]
    assert mat_k > pile_k
    assert payload["group_reports"][0]["effective_soil"]["influence_depth_m"] > payload["group_reports"][1]["effective_soil"]["influence_depth_m"]
    assert payload["summary"]["max_hazard_detuning_group_id"] in group_ids
    assert payload["summary"]["min_group_interaction_group_id"] in group_ids
    assert payload["group_reports"][0]["pile_group_interaction"]["interaction_efficiency_ratio"] == pytest.approx(1.0)
    assert payload["group_reports"][1]["frequency_response_metrics"]["amplification_half_power_bandwidth_hz"] >= 0.0


def test_advanced_ssi_cli_writes_report_and_rejects_invalid_input(tmp_path: Path) -> None:
    profile_json = tmp_path / "advanced_ssi_profile.json"
    profile_json.write_text(json.dumps(_sample_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "advanced_ssi_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/advanced_ssi.py",
            "--profile-json",
            str(profile_json),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["summary"]["peak_transfer_group_id"] in {"MAT_CORE", "PILE_PERIM"}
    assert report["frequency_response_summary"]["governing_group_id"] in {"MAT_CORE", "PILE_PERIM"}
    assert report["pile_group_interaction_summary"]["governing_group_id"] in {"MAT_CORE", "PILE_PERIM"}

    bad_json = tmp_path / "advanced_ssi_bad.json"
    bad_json.write_text(
        json.dumps({"soil_profile": {"profile_id": "bad", "layers": []}, "foundation_groups": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    bad_out = tmp_path / "advanced_ssi_bad_report.json"
    bad_proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/advanced_ssi.py",
            "--profile-json",
            str(bad_json),
            "--out",
            str(bad_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad_proc.returncode != 0
    bad_report = json.loads(bad_out.read_text(encoding="utf-8"))
    assert bad_report["contract_pass"] is False
    assert bad_report["reason_code"] == "ERR_INVALID_INPUT"
