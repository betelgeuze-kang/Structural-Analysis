#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_wind_extract_produces_base_shear_and_low_conf_drift() -> None:
    out = (
        REPO_ROOT
        / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.wind_test.json"
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/extract_midas_wind_same_mesh_result.py"),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source"]["kind"] == "model_derived_wind_estimate"
    assert "WIND" in payload["source"]["load_case"]
    assert payload["metrics"]["base_shear_kN"] > 0.0
    # Drift band: stiff low-rise, full-height columns only (not mesh-stub inflated K).
    assert 0.0 < payload["metrics"]["drift_ratio_pct"] < 0.05
    assert payload["confidence"]["base_shear_kN"] == "medium"
    assert payload["assumptions"]["lateral_stiffness_basis"] == "mechanics_real_section"
    assert payload["assumptions"]["lateral_full_height_column_count"] >= 100
    assert payload["assumptions"]["real_section_column_line_fraction"] >= 0.8
    assert payload["confidence"]["drift_ratio_pct"] == "high"
    assert payload["derivation"]["total_nodal_mass_ton"] > 1000.0

    wd = payload["wind_directional"]
    assert wd["governing_direction"] in {"X", "Y"}
    assert wd["base_shear_x_kN"] > 0.0
    assert wd["base_shear_y_kN"] > 0.0
    torsion = wd["accidental_torsion"]
    gov_amp = float(torsion["governing_amplification"])
    assert 1.0 < gov_amp < 1.5
    drift = float(payload["metrics"]["drift_ratio_pct"])
    corner = float(payload["metrics"]["corner_drift_ratio_pct"])
    assert corner >= drift
    assert corner < 1.0
    assert payload["confidence"]["corner_drift_ratio_pct"] == payload["confidence"]["drift_ratio_pct"]
    assert (
        payload["metric_provenance"]["corner_drift_ratio_pct"]
        == "translational_drift_x_accidental_torsion_amplification"
    )


def test_wind_extract_site_override_scales_base_shear() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from extract_midas_wind_same_mesh_result import extract_midas_wind_same_mesh_result  # noqa: E402

    mgt = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    low = extract_midas_wind_same_mesh_result(mgt_path=mgt, roundtrip_json=roundtrip, basic_wind_speed_mps=30.0)
    high = extract_midas_wind_same_mesh_result(mgt_path=mgt, roundtrip_json=roundtrip, basic_wind_speed_mps=40.0)
    assert high["metrics"]["base_shear_kN"] > low["metrics"]["base_shear_kN"]
    assert high["assumptions"]["resolved_basic_wind_speed_mps"] == 40.0


def test_wind_result_comparison_status_is_wind_ingest() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from run_midas_gen_same_mesh_native_comparison import (  # noqa: E402
        run_midas_gen_same_mesh_native_comparison,
    )

    base = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized"
    result_json = base.parent / "midas_generator_33.optimized.midas_gen_same_mesh_result.wind_test.json"
    report = run_midas_gen_same_mesh_native_comparison(
        result_json=result_json,
        roundtrip_json=Path(str(base) + ".roundtrip.json"),
        native_3d_solve_json=Path("/nonexistent"),
        native_condensed_solve_json=Path("/nonexistent"),
    )
    assert report["status"] == "ready"
    assert report["comparison_status"] in {
        "pass_model_derived_wind_aligned",
        "pass_model_derived_wind_bracketed",
        "pass_model_derived_wind_ingest",
    }
    assert report["load_case_track"] == "wind"


def test_wind_extract_angle_sweep_envelope_eight_directions() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from extract_midas_wind_same_mesh_result import (  # noqa: E402
        extract_midas_wind_same_mesh_result,
    )

    mgt = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    payload = extract_midas_wind_same_mesh_result(mgt_path=mgt, roundtrip_json=roundtrip)
    wd = payload["wind_directional"]
    sweep = wd.get("angle_sweep") or []
    assert len(sweep) == 8
    angles = [float(row["angle_deg"]) for row in sweep]
    assert angles == [0.0, 22.5, 45.0, 67.5, 90.0, 112.5, 135.0, 157.5]
    zero_row = sweep[0]
    ninety_row = sweep[4]
    assert abs(float(zero_row["base_shear_theta_kN"]) - float(wd["base_shear_x_kN"])) < 1.0e-6
    assert abs(float(ninety_row["base_shear_theta_kN"]) - float(wd["base_shear_y_kN"])) < 1.0e-6
    peak = max(sweep, key=lambda r: abs(float(r["base_shear_theta_kN"])))
    assert float(wd.get("envelope_max_base_shear_kN") or 0.0) == float(peak["base_shear_theta_kN"])
    assert float(wd.get("governing_angle_deg") or -1.0) == float(peak["angle_deg"])
    assert abs(float(wd.get("envelope_max_base_shear_kN") or 0.0)) >= max(
        abs(float(wd["base_shear_x_kN"])),
        abs(float(wd["base_shear_y_kN"])),
    )


def test_wind_extract_custom_angle_sweep() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from extract_midas_wind_same_mesh_result import (  # noqa: E402
        extract_midas_wind_same_mesh_result,
    )

    mgt = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
    roundtrip = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
    payload = extract_midas_wind_same_mesh_result(
        mgt_path=mgt,
        roundtrip_json=roundtrip,
        angle_sweep_deg=(0.0, 30.0, 60.0, 90.0),
    )
    sweep = payload["wind_directional"]["angle_sweep"]
    assert [float(r["angle_deg"]) for r in sweep] == [0.0, 30.0, 60.0, 90.0]
    sweep_keys = list(sweep[0].keys())
    for required in {"angle_deg", "base_shear_theta_kN", "drift_theta_pct", "cos_theta", "sin_theta"}:
        assert required in sweep_keys
