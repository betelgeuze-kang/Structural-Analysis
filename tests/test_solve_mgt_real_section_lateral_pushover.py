#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_native_dual_lateral_pushover_plausible() -> None:
    out = Path("/tmp/native_lat_test.json")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/solve_mgt_real_section_lateral_pushover.py"),
            "--boundary",
            "both",
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "wind_native_lateral_dual.v1"
    assert payload["n_stories"] >= 2
    assert payload["ei_aggregate_kNm2"] > 0.0
    assert payload["fixed_guided_drift_pct"] > 0.0
    assert payload["cantilever_drift_pct"] > 0.0
    assert payload["fixed_guided_drift_pct"] < payload["cantilever_drift_pct"]
    assert payload["base_shear_kn"] > 0.0
    assert payload["real_section_coverage_pct"] >= 80.0


def test_fixed_guided_stiffer_than_cantilever() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from solve_mgt_real_section_lateral_pushover import solve_real_section_lateral_pushover  # noqa: E402

    mgt = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
    npz = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.npz"

    fg = solve_real_section_lateral_pushover(
        roundtrip_npz=npz, mgt_path=mgt, n_stories=12, boundary="fixed_guided"
    )
    cv = solve_real_section_lateral_pushover(
        roundtrip_npz=npz, mgt_path=mgt, n_stories=12, boundary="cantilever"
    )
    assert fg["solve_mode"] == "fixed_guided_beam_fe_real_section"
    assert cv["solve_mode"] == "cantilever_beam_fe_real_section"
    assert float(fg["max_story_drift_ratio_pct"]) < float(cv["max_story_drift_ratio_pct"])


def test_fixed_guided_drift_converges_with_mesh_refinement() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from solve_mgt_real_section_lateral_pushover import solve_real_section_lateral_pushover  # noqa: E402

    mgt = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
    npz = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.npz"

    d12 = float(
        solve_real_section_lateral_pushover(
            roundtrip_npz=npz, mgt_path=mgt, n_stories=12, boundary="fixed_guided"
        )["max_story_drift_ratio_pct"]
    )
    d24 = float(
        solve_real_section_lateral_pushover(
            roundtrip_npz=npz, mgt_path=mgt, n_stories=24, boundary="fixed_guided"
        )["max_story_drift_ratio_pct"]
    )
    d48 = float(
        solve_real_section_lateral_pushover(
            roundtrip_npz=npz, mgt_path=mgt, n_stories=48, boundary="fixed_guided"
        )["max_story_drift_ratio_pct"]
    )

    ref = max(d12, 1.0e-12)
    assert abs(d24 - d12) / ref < 0.15
    assert abs(d48 - d12) / ref < 0.15

    d12c = float(
        solve_real_section_lateral_pushover(
            roundtrip_npz=npz, mgt_path=mgt, n_stories=12, boundary="cantilever"
        )["max_story_drift_ratio_pct"]
    )
    d24c = float(
        solve_real_section_lateral_pushover(
            roundtrip_npz=npz, mgt_path=mgt, n_stories=24, boundary="cantilever"
        )["max_story_drift_ratio_pct"]
    )
    assert abs(d24c - d12c) / max(d12c, 1.0e-12) < 0.15


def test_wind_comparison_dual_native_tier() -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))
    from extract_midas_wind_same_mesh_result import extract_midas_wind_same_mesh_result  # noqa: E402
    from run_midas_gen_same_mesh_native_comparison import run_midas_gen_same_mesh_native_comparison  # noqa: E402
    from solve_mgt_real_section_lateral_pushover import solve_wind_native_lateral_dual  # noqa: E402

    base = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized"
    result_json = base.parent / "midas_generator_33.optimized.midas_gen_same_mesh_result.wind_test.json"
    lateral = solve_wind_native_lateral_dual(
        roundtrip_npz=Path(str(base) + ".roundtrip.npz"),
        mgt_path=Path(str(base) + ".mgt"),
    )
    lateral_out = base.parent / "midas_generator_33.optimized.mgt_real_section_lateral_pushover_test.json"
    lateral_out.write_text(json.dumps(lateral, indent=2) + "\n", encoding="utf-8")

    wind = extract_midas_wind_same_mesh_result(
        mgt_path=Path(str(base) + ".mgt"),
        roundtrip_json=Path(str(base) + ".roundtrip.json"),
    )
    lumped = float(wind["metrics"]["drift_ratio_pct"])

    report = run_midas_gen_same_mesh_native_comparison(
        result_json=result_json,
        roundtrip_json=Path(str(base) + ".roundtrip.json"),
        native_3d_solve_json=Path("/nonexistent"),
        native_condensed_solve_json=Path("/nonexistent"),
        native_wind_lateral_json=lateral_out,
    )
    assert report["status"] == "ready"
    assert report["comparison_status"] in {
        "pass_model_derived_wind_aligned",
        "pass_model_derived_wind_bracketed",
        "pass_model_derived_wind_ingest",
    }
    tiers = report.get("comparison_tiers") or {}
    assert "wind_native_lateral" in tiers
    assert tiers["wind_native_lateral"] in {"pass", "bracketed", "diverge"}
    assert report.get("lumped_drift_pct") == lumped
    assert report.get("native_fixed_guided_drift_pct", 0) > 0
    assert report.get("native_cantilever_drift_pct", 0) > 0
    bracket = report.get("wind_drift_bracket") or {}
    assert "lumped_bracketed_between_bounds" in bracket
