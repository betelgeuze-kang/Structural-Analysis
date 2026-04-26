from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_generate_benchmark_optimization_review_ui_emits_anchor_review_html(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "benchmark_svg" / "canton" / "baseline"
    optimized_dir = tmp_path / "benchmark_svg" / "canton" / "ai_optimized"
    baseline_review_dir = tmp_path / "benchmark_svg" / "canton" / "baseline_review"
    optimized_review_dir = tmp_path / "benchmark_svg" / "canton" / "ai_optimized_review"
    peer_baseline_dir = tmp_path / "benchmark_svg" / "peer" / "baseline"
    peer_optimized_dir = tmp_path / "benchmark_svg" / "peer" / "ai_optimized"
    peer_baseline_review_dir = tmp_path / "benchmark_svg" / "peer" / "baseline_review"
    peer_optimized_review_dir = tmp_path / "benchmark_svg" / "peer" / "ai_optimized_review"
    peer_dir = tmp_path / "benchmark_svg" / "peer"
    manifest = tmp_path / "benchmark_svg" / "benchmark_optimization_drawings_manifest.json"
    out_html = tmp_path / "release" / "visualization" / "benchmark_optimization_review.html"
    summary_out = tmp_path / "release" / "visualization" / "benchmark_optimization_review_summary.json"

    svg = "<svg xmlns='http://www.w3.org/2000/svg'><text x='10' y='20'>ok</text></svg>"
    for name in (
        "isometric.svg",
        "elevation_xz.svg",
        "elevation_yz.svg",
        "detail_family.svg",
        "detail_member_zoom.svg",
        "detail_floor_stack.svg",
        "detail_zone_cluster.svg",
        "detail_story_change_register.svg",
        "detail_section.svg",
        "detail_anchorage_cut.svg",
        "detail_anchorage_exploded.svg",
        "detail_rebar_callout.svg",
        "detail_bar_bending_schedule.svg",
        "detail_schedule.svg",
        "plan_01.svg",
    ):
        _write_text(baseline_dir / name, svg)
        _write_text(optimized_dir / name, svg)
        _write_text(baseline_review_dir / name, svg)
        _write_text(optimized_review_dir / name, svg)
        _write_text(peer_baseline_dir / name, svg)
        _write_text(peer_optimized_dir / name, svg)
        _write_text(peer_baseline_review_dir / name, svg)
        _write_text(peer_optimized_review_dir / name, svg)
    _write_text(peer_dir / "peer_blind_prediction_readiness_sheet.svg", svg)

    _write_json(
        manifest,
        {
            "canton_tower_reduced_shm": {
                "selected_case_id": "canton-test-0001",
                "baseline_output_dir": str(baseline_dir),
                "ai_optimized_output_dir": str(optimized_dir),
                "baseline_review_output_dir": str(baseline_review_dir),
                "ai_optimized_review_output_dir": str(optimized_review_dir),
                "baseline_summary": {
                    "case_id": "canton-test-0001",
                    "topology_type": "diagrid",
                    "element_mix": "shell_beam_mix",
                    "node_count": 16,
                    "element_count": 24,
                    "drift_ratio_pct": 1.234,
                },
                "ai_optimized_summary": {
                    "case_id": "canton-test-0001",
                    "optimization_mode": "proxy_tune",
                    "proposed_change_count": 1,
                    "base_shear_kN": 3210.5,
                    "proposed_changes": [
                        {
                            "action": "tune",
                            "group": "diagrid-panel-a",
                            "from_section": "DG-1",
                            "to_section": "DG-1 tuned",
                            "baseline_dcr": 0.91,
                            "optimized_dcr": 0.77,
                        }
                    ],
                },
            },
            "peer_blind_prediction": {
                "selected_case_id": "peer-test-0001",
                "baseline_output_dir": str(peer_baseline_dir),
                "ai_optimized_output_dir": str(peer_optimized_dir),
                "baseline_review_output_dir": str(peer_baseline_review_dir),
                "ai_optimized_review_output_dir": str(peer_optimized_review_dir),
                "drawing_kind": "document_derived_proxy_svg_set",
                "baseline_summary": {
                    "case_id": "peer-test-0001",
                    "topology_type": "blind_prediction_frame",
                    "element_mix": "frame_wall_mix",
                    "acceleration_channel_count": 11,
                    "drift_channel_count": 11,
                    "node_count": 20,
                    "element_count": 14,
                },
                "ai_optimized_summary": {
                    "case_id": "peer-test-0001",
                    "optimization_mode": "blind_prediction_document_derived_proposal",
                    "geometry_provenance_label": "Columns.pdf + Bent-Cap.pdf",
                    "detail_layers": {
                        "post_tension": 4,
                        "anchorage": 2,
                        "column_cage_rebar": 8,
                        "cap_rebar": 2,
                    },
                    "detail_dimensions_in": {
                        "column_outer_diameter_in": 16.0,
                        "column_length_in": 184.0,
                        "cap_beam_length_in": 164.0,
                        "cap_beam_outer_diameter_in": 22.0,
                        "anchor_plate_length_in": 14.0,
                        "anchor_plate_width_in": 12.0,
                    },
                    "proposed_change_count": 2,
                    "proposed_changes": [
                        {
                            "action": "strengthen",
                            "group": "north-column",
                            "from_section": "SLV01",
                            "to_section": "SLV01+",
                            "baseline_dcr": 0.91,
                            "optimized_dcr": 0.71,
                        }
                    ],
                },
                "readiness_sheet": {
                    "sheet_path": str(peer_dir / "peer_blind_prediction_readiness_sheet.svg"),
                }
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_benchmark_optimization_review_ui.py",
            "--manifest",
            str(manifest),
            "--out-html",
            str(out_html),
            "--summary-out",
            str(summary_out),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    html = out_html.read_text(encoding="utf-8")
    summary = json.loads(summary_out.read_text(encoding="utf-8"))

    assert "Benchmark Optimization Review" in html
    assert "route-selection-target" in html
    assert "route_benchmark_family" in html
    assert "route_projection" in html
    assert "route_case_id" in html
    assert "id='canton-review'" in html
    assert "id='peer-benchmark'" in html
    assert "data-route-benchmark-family='canton'" in html
    assert "data-route-benchmark-family='peer'" in html
    assert "PEER Blind Prediction Baseline" in html
    assert "PEER Blind Prediction AI Optimized" in html
    assert "peer-projection" in html
    assert "Open MIDAS33 optimized drawing review" in html
    assert "Open results explorer" in html
    assert "Open committee dashboard" in html
    assert "Open validation boundary" in html
    assert "Open project registry" in html
    assert "Open project package zip" in html
    assert "Open registry signature" in html
    assert "Open batch job report" in html
    assert "peer_blind_prediction_readiness_sheet.svg" in html
    assert "../../benchmark_svg/canton/baseline_review/isometric.svg" in html
    assert "../../benchmark_svg/peer/baseline_review/isometric.svg" in html
    assert "frame-canton" in html
    assert "Detail layers" in html
    assert "detail_family.svg" in html
    assert "detail_member_zoom.svg" in html
    assert "detail_floor_stack.svg" in html
    assert "detail_zone_cluster.svg" in html
    assert "detail_story_change_register.svg" in html
    assert "detail_section.svg" in html
    assert "detail_anchorage_cut.svg" in html
    assert "detail_anchorage_exploded.svg" in html
    assert "detail_rebar_callout.svg" in html
    assert "detail_bar_bending_schedule.svg" in html
    assert "detail_schedule.svg" in html
    assert "<option value='detail_story_change_register.svg' selected>" in html
    assert "<option value='detail_section.svg' selected>" in html
    assert "canton-test-0001" in html
    assert "peer-test-0001" in html
    assert summary["canton_case_id"] == "canton-test-0001"
    assert summary["peer_case_id"] == "peer-test-0001"
    assert summary["peer_drawing_kind"] == "document_derived_proxy_svg_set"
    assert summary["output_html"].endswith("benchmark_optimization_review.html")
    assert summary["artifact_links"]["committee_dashboard_html"].endswith("committee_review_dashboard.html")
    assert summary["artifact_links"]["release_gap_report_json"].endswith("release_gap_report.json")
    assert summary["artifact_links"]["project_registry_report"].endswith("project_registry.json")
    assert summary["artifact_links"]["project_registry_json"].endswith("project_registry.json")
    assert summary["artifact_links"]["project_package_zip"].endswith("project_package.zip")
    assert summary["artifact_links"]["project_registry_signature"].endswith("project_registry.signature.b64")
    assert summary["artifact_links"]["external_benchmark_batch_job_report_json"].endswith(
        "external_benchmark_batch_job_report.json"
    )
