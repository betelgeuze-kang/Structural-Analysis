from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.load_combination_engine import (
    canonicalize_kds_family,
    generate_kds_steel_service_combinations,
    generate_kds_steel_strength_combinations,
    generate_named_scale_library,
    infer_combination_family_from_midas_model,
    load_combinations_from_midas_model,
    summarize_runtime_combination_model,
)


def _canonical_midas_generator_payload() -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    payload_path = repo_root / "implementation" / "phase1" / "open_data" / "midas" / "midas_generator_33.json"
    return json.loads(payload_path.read_text(encoding="utf-8"))


def test_kds_steel_basic_generators_match_canonical_midas_steel_factor_maps() -> None:
    payload = _canonical_midas_generator_payload()

    runtime_steel_maps = {
        tuple(sorted(combo.factors.items()))
        for combo in load_combinations_from_midas_model(payload)
        if combo.name.startswith("sLCB")
    }
    library_steel_maps = {
        tuple(sorted(combo.factors.items()))
        for combo in [*generate_kds_steel_strength_combinations(), *generate_kds_steel_service_combinations()]
    }

    assert runtime_steel_maps == library_steel_maps


def test_generate_named_scale_library_supports_steel_basic_family() -> None:
    uls = generate_named_scale_library(family="KDS-2022-STEEL-BASIC", limit_state="ULS")
    sls = generate_named_scale_library(family="KDS-2022-STEEL-BASIC", limit_state="SLS")

    assert [name for name, _ in uls] == ["KDS_STEEL_ULS_1", "KDS_STEEL_ULS_2"]
    assert [name for name, _ in sls] == ["KDS_STEEL_SLS_1"]
    assert [scale for _, scale in sls] == [1.0]


def test_canonicalize_kds_family_maps_gate_aliases() -> None:
    assert canonicalize_kds_family("KDS-2022-RC-BASIC") == "KDS-2022"
    assert canonicalize_kds_family("KDS-2022-RC-WIND") == "KDS-2022"
    assert canonicalize_kds_family("KDS-2022-RC-SEISMIC") == "KDS-2022"
    assert canonicalize_kds_family("KDS-2022-RC-NESTED") == "KDS-2022"
    assert canonicalize_kds_family("KDS-2022-generic") == "KDS-2022"
    assert canonicalize_kds_family("KDS-2022-rc-wind") == "KDS-2022"
    assert canonicalize_kds_family("KDS-2022-rc-seismic") == "KDS-2022"
    assert canonicalize_kds_family("KDS-2022-rc-nested") == "KDS-2022"
    assert canonicalize_kds_family("KDS-2022-steel-gravity") == "KDS-2022-STEEL-BASIC"


def test_generate_named_scale_library_supports_rc_breadth_aliases() -> None:
    rc_wind = generate_named_scale_library(family="KDS-2022-RC-WIND", limit_state="ULS")
    rc_seismic = generate_named_scale_library(family="KDS-2022-rc-seismic", limit_state="SLS")

    assert [name for name, _ in rc_wind[:2]] == ["KDS_ULS_1", "KDS_ULS_2"]
    assert [name for name, _ in rc_seismic[:2]] == ["KDS_SLS_1", "KDS_SLS_2_WX+"]


def test_infer_combination_family_detects_canonical_steel_basic_signature() -> None:
    payload = _canonical_midas_generator_payload()

    assert infer_combination_family_from_midas_model(payload) == "KDS-2022-STEEL-BASIC"


def test_infer_combination_family_falls_back_when_steel_signature_is_incomplete() -> None:
    payload = {
        "model": {
            "loads": {
                "load_combinations": [
                    {
                        "name": "sLCB1",
                        "combination_type": "STEEL",
                        "limit_state": "ACTIVE",
                        "expanded_factor_map": {"DEAD": 1.3, "LIVE": 1.5},
                    },
                    {
                        "name": "ULS1",
                        "combination_type": "GEN",
                        "limit_state": "STRENGTH",
                        "expanded_factor_map": {"DEAD": 1.2, "LIVE": 1.6},
                    },
                ]
            }
        }
    }

    assert infer_combination_family_from_midas_model(payload) == "KDS-2022"


def test_load_combinations_from_midas_model_expands_nested_combo_rows() -> None:
    payload = {
        "model": {
            "loads": {
                "load_combinations": [
                    {
                        "name": "ULS_BASE",
                        "combination_type": "GEN",
                        "limit_state": "ULS",
                        "entry_rows": [
                            {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.2},
                            {"reference_kind": "ST", "reference_name": "LIVE", "factor": 1.6},
                        ],
                    },
                    {
                        "name": "ULS_ENV",
                        "combination_type": "GEN",
                        "limit_state": "ULS",
                        "entry_rows": [
                            {"reference_kind": "CB", "reference_name": "ULS_BASE", "factor": 1.0},
                            {"reference_kind": "ST", "reference_name": "WIND+X", "factor": 0.7},
                        ],
                    },
                ]
            }
        }
    }

    combos = {combo.name: combo for combo in load_combinations_from_midas_model(payload)}

    assert combos["ULS_BASE"].factors == {"D": 1.2, "L": 1.6}
    assert combos["ULS_ENV"].factors == {"D": 1.2, "L": 1.6, "Wx": 0.7}


def test_summarize_runtime_combination_model_surfaces_family_breadth_and_nested_depth() -> None:
    payload = {
        "model": {
            "loads": {
                "load_combinations": [
                    {
                        "name": "RC_BASE",
                        "combination_type": "GEN",
                        "limit_state": "ULS",
                        "entry_rows": [
                            {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.2},
                            {"reference_kind": "ST", "reference_name": "LIVE", "factor": 0.5},
                        ],
                    },
                    {
                        "name": "RC_WIND_ENV",
                        "combination_type": "GEN",
                        "limit_state": "ULS",
                        "entry_rows": [
                            {"reference_kind": "CB", "reference_name": "RC_BASE", "factor": 1.0},
                            {"reference_kind": "ST", "reference_name": "WIND+X", "factor": 1.0},
                        ],
                    },
                    {
                        "name": "RC_SEISMIC_ENV",
                        "combination_type": "GEN",
                        "limit_state": "SERVICE",
                        "entry_rows": [
                            {"reference_kind": "CB", "reference_name": "RC_WIND_ENV", "factor": 1.0},
                            {"reference_kind": "ST", "reference_name": "EX", "factor": 0.7},
                        ],
                    },
                ]
            }
        }
    }

    summary = summarize_runtime_combination_model(payload)

    assert summary["combo_count"] == 3
    assert summary["linear_combo_count"] == 1
    assert summary["nested_combo_count"] == 2
    assert summary["max_nested_depth"] == 3
    assert summary["runtime_case_names"] == ["D", "Ex", "L", "Wx"]
    assert summary["runtime_case_family_counts"] == {"rc": 2, "seismic": 1, "wind": 1}
    assert summary["runtime_case_breadth_count"] == 3
    assert summary["runtime_case_breadth_label"] == "rc, wind, seismic"
    assert summary["combo_family_counts"] == {"rc": 1, "rc+wind+nested": 1, "rc+wind+seismic+nested": 1}
    assert summary["family_tag_counts"]["rc"] == 3
    assert summary["family_tag_counts"]["wind"] == 2
    assert summary["family_tag_counts"]["seismic"] == 1
    assert summary["rc_combo_count"] == 3
    assert summary["wind_combo_count"] == 2
    assert summary["seismic_combo_count"] == 1
    assert summary["rc_max_nested_depth"] == 3
    assert summary["wind_max_nested_depth"] == 3
    assert summary["seismic_max_nested_depth"] == 3
    assert summary["limit_state_counts"] == {"SLS": 1, "ULS": 2}
    assert summary["combo_depth_rows"] == [
        {
            "name": "RC_BASE",
            "limit_state": "ULS",
            "nested_reference_count": 0,
            "nested_depth": 1,
            "case_count": 2,
            "case_names": ["D", "L"],
            "family_label": "rc",
            "family_tags": ["rc"],
            "rc_present": True,
            "wind_present": False,
            "seismic_present": False,
            "nested_present": False,
        },
        {
            "name": "RC_SEISMIC_ENV",
            "limit_state": "SLS",
            "nested_reference_count": 1,
            "nested_depth": 3,
            "case_count": 4,
            "case_names": ["D", "Ex", "L", "Wx"],
            "family_label": "rc+wind+seismic+nested",
            "family_tags": ["rc", "wind", "seismic", "nested"],
            "rc_present": True,
            "wind_present": True,
            "seismic_present": True,
            "nested_present": True,
        },
        {
            "name": "RC_WIND_ENV",
            "limit_state": "ULS",
            "nested_reference_count": 1,
            "nested_depth": 2,
            "case_count": 3,
            "case_names": ["D", "L", "Wx"],
            "family_label": "rc+wind+nested",
            "family_tags": ["rc", "wind", "nested"],
            "rc_present": True,
            "wind_present": True,
            "seismic_present": False,
            "nested_present": True,
        },
    ]
    assert "breadth=rc, wind, seismic" in summary["summary_line"]
