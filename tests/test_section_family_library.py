from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


SCRIPT = Path("implementation/phase1/section_family_library.py")
SPEC = importlib.util.spec_from_file_location("section_family_library", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(SCRIPT.parent.resolve()))
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_evaluate_story_section_profile_exposes_beam_demand_summary() -> None:
    profile = MODULE.evaluate_story_section_profile(
        topology="wall-frame",
        material_type="rc_composite",
        story_h_m=np.array([3.8, 3.6, 3.5, 3.4, 3.3], dtype=np.float64),
        drift_ratio_profile=np.array([0.012, 0.0105, 0.009, 0.0075, 0.006], dtype=np.float64),
        load_scale=1.15,
    )

    summary = profile["summary"]
    assert summary["story_count"] == 5
    assert summary["beam_story_count"] == 5
    assert summary["section_max_abs_strain"] > 0.0
    assert summary["section_steel_yield_ratio_max"] > 0.0
    assert summary["section_concrete_crack_ratio_max"] > 0.0
    assert summary["section_strain_energy_total_n"] > 0.0
    assert summary["beam_tangent_scale_min"] > 0.0
    assert summary["beam_max_trial_end_moment_ratio"] > 1.0
    assert summary["beam_stability_index_max"] > 0.0
    assert summary["beam_strain_energy_total_n_m"] > 0.0
    assert sum(profile["family_counts"].values()) == summary["story_count"]
    assert len(profile["detail_rows"]) == summary["story_count"]
    assert all("section_steel_yield_ratio_max" in row for row in profile["detail_rows"])
    assert all("section_concrete_crack_ratio_max" in row for row in profile["detail_rows"])
    assert all("beam_max_trial_end_moment_ratio" in row for row in profile["detail_rows"])
    assert all("beam_stability_index" in row for row in profile["detail_rows"])


def test_evaluate_story_section_profile_increases_beam_demand_with_higher_drift() -> None:
    common = {
        "topology": "wall-frame",
        "material_type": "rc_composite",
        "story_h_m": np.array([3.8, 3.6, 3.5, 3.4, 3.3], dtype=np.float64),
        "load_scale": 1.0,
    }
    low = MODULE.evaluate_story_section_profile(
        drift_ratio_profile=np.array([0.0035, 0.003, 0.0025, 0.0022, 0.002], dtype=np.float64),
        **common,
    )
    high = MODULE.evaluate_story_section_profile(
        drift_ratio_profile=np.array([0.011, 0.0095, 0.0085, 0.0075, 0.0065], dtype=np.float64),
        **common,
    )

    low_summary = low["summary"]
    high_summary = high["summary"]
    assert high_summary["section_max_abs_strain"] > low_summary["section_max_abs_strain"]
    assert high_summary["section_steel_yield_ratio_max"] > low_summary["section_steel_yield_ratio_max"]
    assert high_summary["section_strain_energy_total_n"] > low_summary["section_strain_energy_total_n"]
    assert high_summary["beam_max_trial_end_moment_ratio"] > low_summary["beam_max_trial_end_moment_ratio"]
    assert high_summary["beam_strain_energy_total_n_m"] > low_summary["beam_strain_energy_total_n_m"]
    assert high_summary["beam_yielded_story_count"] >= low_summary["beam_yielded_story_count"]
    assert high_summary["beam_tangent_scale_min"] <= low_summary["beam_tangent_scale_min"]
