from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_generate_benchmark_optimization_drawings_materializes_svg_outputs(tmp_path: Path) -> None:
    canton_cases = tmp_path / "canton_cases.json"
    peer_cases = tmp_path / "peer_cases.json"
    peer_contract = tmp_path / "peer_input_contract.json"
    peer_compare = tmp_path / "peer_compare_report.json"
    out_root = tmp_path / "benchmark_svg"
    manifest = out_root / "benchmark_optimization_drawings_manifest.json"

    _write_json(
        canton_cases,
        {
            "cases": [
                {
                    "case_id": "canton-mini-00001",
                    "topology_type": "outrigger",
                    "element_mix": "shell_beam_mix",
                    "node_features": [
                        [920.0, 80000.0, 255.0, 0.0, 1.1],
                        [930.0, 79000.0, 255.0, 0.0, 1.2],
                        [940.0, 78000.0, 255.0, 0.0, 1.3],
                        [950.0, 77000.0, 255.0, 0.0, 1.4],
                        [960.0, 76000.0, 255.0, 0.5, 1.2],
                        [970.0, 75000.0, 255.0, 0.5, 1.3],
                        [980.0, 74000.0, 255.0, 0.5, 1.4],
                        [990.0, 73000.0, 255.0, 0.5, 1.5],
                    ],
                    "response_u": [
                        [0.01, 0.02, 0.03, 0.04, 0.02, 0.05, 0.04, 0.03],
                        [0.02, 0.03, 0.06, 0.05, 0.03, 0.07, 0.05, 0.04],
                        [0.01, 0.04, 0.05, 0.07, 0.02, 0.08, 0.06, 0.05],
                    ],
                    "metrics": {
                        "drift_ratio_pct": {"hf": 3.2, "lf": 3.5},
                        "base_shear_kN": {"hf": 2400.0, "lf": 2310.0},
                        "equilibrium_residual": 0.04,
                    },
                }
            ]
        },
    )
    _write_json(
        peer_cases,
        {
            "cases": [
                {
                    "case_id": "peer-seed-01::gm01",
                    "benchmark_case_status": "ready",
                    "compare_ready": True,
                    "viewer_entry_ready": True,
                }
            ]
        },
    )
    _write_json(
        peer_contract,
        {
            "readiness": {
                "public_input_ready": True,
                "measured_response_ready": True,
                "viewer_entry_ready": True,
            },
            "geometry_package": {
                "docs": [
                    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01/Construction_Drawings.pdf",
                    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01/Columns.pdf",
                ]
            },
        },
    )
    _write_json(
        peer_compare,
        {
            "summary_line": "PEER blind compare lane: READY | cases=10 | measured_response=ready | channels=11",
            "summary": {
                "acceleration_channel_count": 11,
                "drift_channel_count": 11,
                "measured_response_ready": True,
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_benchmark_optimization_drawings.py",
            "--canton-cases",
            str(canton_cases),
            "--peer-cases",
            str(peer_cases),
            "--peer-input-contract",
            str(peer_contract),
            "--peer-compare-report",
            str(peer_compare),
            "--out-root",
            str(out_root),
            "--manifest-out",
            str(manifest),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["canton_tower_reduced_shm"]["selected_case_id"] == "canton-mini-00001"
    assert payload["canton_tower_reduced_shm"]["baseline_review_output_dir"].endswith("baseline_review")
    assert payload["canton_tower_reduced_shm"]["baseline_summary"]["element_count"] > 0
    assert payload["canton_tower_reduced_shm"]["ai_optimized_summary"]["proposed_change_count"] > 0
    assert payload["peer_blind_prediction"]["selected_case_id"] == "peer-seed-01::gm01"
    assert payload["peer_blind_prediction"]["drawing_kind"] == "document_derived_proxy_svg_set"
    assert payload["peer_blind_prediction"]["baseline_review_output_dir"].endswith("baseline_review")
    assert payload["peer_blind_prediction"]["baseline_summary"]["element_count"] > 0
    assert payload["peer_blind_prediction"]["ai_optimized_summary"]["proposed_change_count"] > 0
    assert payload["peer_blind_prediction"]["ai_optimized_summary"]["detail_layers"]["post_tension"] >= 4

    baseline_iso = out_root / "canton_tower_reduced_shm" / "baseline" / "isometric.svg"
    optimized_iso = out_root / "canton_tower_reduced_shm" / "ai_optimized" / "isometric.svg"
    baseline_review_iso = out_root / "canton_tower_reduced_shm" / "baseline_review" / "isometric.svg"
    canton_detail_family = out_root / "canton_tower_reduced_shm" / "ai_optimized_review" / "detail_family.svg"
    canton_detail_member = out_root / "canton_tower_reduced_shm" / "ai_optimized_review" / "detail_member_zoom.svg"
    canton_detail_floor = out_root / "canton_tower_reduced_shm" / "ai_optimized_review" / "detail_floor_stack.svg"
    canton_detail_zone = out_root / "canton_tower_reduced_shm" / "ai_optimized_review" / "detail_zone_cluster.svg"
    canton_detail_register = out_root / "canton_tower_reduced_shm" / "ai_optimized_review" / "detail_story_change_register.svg"
    peer_baseline_iso = out_root / "peer_blind_prediction" / "baseline" / "isometric.svg"
    peer_optimized_iso = out_root / "peer_blind_prediction" / "ai_optimized" / "isometric.svg"
    peer_review_iso = out_root / "peer_blind_prediction" / "ai_optimized_review" / "isometric.svg"
    peer_detail_section = out_root / "peer_blind_prediction" / "ai_optimized_review" / "detail_section.svg"
    peer_detail_anchor = out_root / "peer_blind_prediction" / "ai_optimized_review" / "detail_anchorage_cut.svg"
    peer_detail_anchor_exploded = out_root / "peer_blind_prediction" / "ai_optimized_review" / "detail_anchorage_exploded.svg"
    peer_detail_rebar = out_root / "peer_blind_prediction" / "ai_optimized_review" / "detail_rebar_callout.svg"
    peer_detail_bending = out_root / "peer_blind_prediction" / "ai_optimized_review" / "detail_bar_bending_schedule.svg"
    peer_detail_schedule = out_root / "peer_blind_prediction" / "ai_optimized_review" / "detail_schedule.svg"
    peer_sheet = out_root / "peer_blind_prediction" / "peer_blind_prediction_readiness_sheet.svg"

    assert baseline_iso.exists()
    assert optimized_iso.exists()
    assert baseline_review_iso.exists()
    assert canton_detail_family.exists()
    assert canton_detail_member.exists()
    assert canton_detail_floor.exists()
    assert canton_detail_zone.exists()
    assert canton_detail_register.exists()
    assert peer_baseline_iso.exists()
    assert peer_optimized_iso.exists()
    assert peer_review_iso.exists()
    assert peer_detail_section.exists()
    assert peer_detail_anchor.exists()
    assert peer_detail_anchor_exploded.exists()
    assert peer_detail_rebar.exists()
    assert peer_detail_bending.exists()
    assert peer_detail_schedule.exists()
    assert peer_sheet.exists()
    assert "AI OPT PROPOSAL" in optimized_iso.read_text(encoding="utf-8")
    assert "Canton Tower Family Zoom" in canton_detail_family.read_text(encoding="utf-8")
    assert "Canton Tower Member Zoom" in canton_detail_member.read_text(encoding="utf-8")
    assert "Canton Tower Floor Stack Zoom" in canton_detail_floor.read_text(encoding="utf-8")
    assert "Canton Tower Zone Cluster Zoom" in canton_detail_zone.read_text(encoding="utf-8")
    assert "Before → After" in canton_detail_zone.read_text(encoding="utf-8")
    assert "Callout legend" in canton_detail_zone.read_text(encoding="utf-8")
    assert "Baseline matrix" in canton_detail_zone.read_text(encoding="utf-8")
    assert "Optimized matrix" in canton_detail_zone.read_text(encoding="utf-8")
    assert "data-story-band='L01-L05'" in canton_detail_zone.read_text(encoding="utf-8")
    assert "data-zone-id='01'" in canton_detail_zone.read_text(encoding="utf-8")
    assert "benchmark_matrix=optimized" in canton_detail_zone.read_text(encoding="utf-8")
    assert "Canton Story-by-Story Optimized Change Register" in canton_detail_register.read_text(encoding="utf-8")
    assert "Baseline register" in canton_detail_register.read_text(encoding="utf-8")
    assert "Optimized register" in canton_detail_register.read_text(encoding="utf-8")
    assert "PEER Blind Prediction Bridge Bent" in peer_baseline_iso.read_text(encoding="utf-8")
    assert "AI OPT PROPOSAL" in peer_optimized_iso.read_text(encoding="utf-8")
    assert "Post-tension tendon path" in peer_optimized_iso.read_text(encoding="utf-8")
    assert "Detail B · Cap-End Anchorage Pocket" in peer_detail_section.read_text(encoding="utf-8")
    assert "PEER Anchorage Pocket Section Cut" in peer_detail_anchor.read_text(encoding="utf-8")
    assert "PEER Anchorage Pocket Exploded Detail" in peer_detail_anchor_exploded.read_text(encoding="utf-8")
    assert "PEER Rebar Callout / Bar-Mark Sheet" in peer_detail_rebar.read_text(encoding="utf-8")
    assert "PEER Bar Bending Schedule" in peer_detail_bending.read_text(encoding="utf-8")
    assert "Bend code" in peer_detail_bending.read_text(encoding="utf-8")
    assert "Total length" in peer_detail_bending.read_text(encoding="utf-8")
    assert "Total steel quantity" in peer_detail_bending.read_text(encoding="utf-8")
    assert "Bend code legend" in peer_detail_bending.read_text(encoding="utf-8")
    assert "Schedule totals" in peer_detail_bending.read_text(encoding="utf-8")
    assert "Shape sketch" in peer_detail_bending.read_text(encoding="utf-8")
    assert "Optimization / Detailing Schedule" in peer_detail_schedule.read_text(encoding="utf-8")
    assert "PEER Blind Prediction Benchmark" in peer_sheet.read_text(encoding="utf-8")
