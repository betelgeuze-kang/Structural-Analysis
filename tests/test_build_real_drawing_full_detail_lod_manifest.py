from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "implementation/phase1/build_real_drawing_full_detail_lod_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_real_drawing_full_detail_lod_manifest", SCRIPT_PATH)
assert SPEC is not None
lod_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(lod_manifest)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fixture_inputs(tmp_path: Path) -> Path:
    graph_path = tmp_path / "graphs" / "dense_solver.json"
    nodes = [{"id": index, "x": index, "y": 0, "z": 0} for index in range(1, 9)]
    elements = [
        {"id": index, "family": "beam", "node_ids": [index, index + 1]}
        for index in range(1, 8)
    ]
    _write_json(graph_path, {"model": {"nodes": nodes, "elements": elements}, "source_url": "SHOULD_NOT_LEAK"})
    return _write_json(
        tmp_path / "model_optimization_intake_queue.json",
        {
            "queue": [
                {
                    "file_id": "SHOULD_NOT_LEAK_FILE_ID",
                    "file_name": "SHOULD_NOT_LEAK.mgt",
                    "source_url": "https://SHOULD_NOT_LEAK.example/model.mgt",
                    "private_path": "/tmp/SHOULD_NOT_LEAK.mgt",
                    "solver_graph_model_json": str(graph_path),
                    "file_type": ".mgt",
                    "optimization_route": "midas_mgt_direct_parser",
                    "optimization_status": "solver_graph_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": True,
                }
            ]
        },
    )


def test_full_detail_lod_manifest_builds_sample_receipt_without_source_leak(tmp_path: Path) -> None:
    intake_queue = _fixture_inputs(tmp_path)

    report = lod_manifest.build_full_detail_lod_manifest(intake_queue, max_segments_per_asset=3)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS_FULL_DETAIL_LOD_MANIFEST_READY"
    assert report["summary"]["sampled_solver_exact_asset_count"] == 1
    item = report["lod_items"][0]
    assert item["asset_ref"] == "RD-001"
    assert item["full_detail_segment_count"] == 7
    assert item["viewer_sample_segment_count"] == 3
    assert item["reason_code"] == "PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED"
    assert "full_detail_segment_count_receipt" in item["closure_evidence"]
    assert "SHOULD_NOT_LEAK" not in json.dumps(report)


def test_full_detail_lod_manifest_includes_sampled_preview_assets(tmp_path: Path) -> None:
    exact_graph_path = tmp_path / "graphs" / "dense_solver.json"
    preview_graph_path = tmp_path / "graphs" / "dense_ifc_preview.json"
    nodes = [{"id": index, "x": index, "y": 0, "z": 0} for index in range(1, 9)]
    elements = [
        {"id": index, "family": "beam", "node_ids": [index, index + 1]}
        for index in range(1, 8)
    ]
    _write_json(exact_graph_path, {"model": {"nodes": nodes, "elements": elements}})
    _write_json(preview_graph_path, {"model": {"nodes": nodes, "elements": elements}})
    intake_queue = _write_json(
        tmp_path / "model_optimization_intake_queue.json",
        {
            "queue": [
                {
                    "solver_graph_model_json": str(exact_graph_path),
                    "file_type": ".mgt",
                    "optimization_route": "midas_mgt_direct_parser",
                    "optimization_status": "solver_graph_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": True,
                },
                {
                    "solver_graph_model_json": str(preview_graph_path),
                    "file_type": ".ifc",
                    "optimization_route": "ifc_to_structural_graph_adapter",
                    "optimization_status": "ifc_solver_graph_draft_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": False,
                },
            ]
        },
    )

    report = lod_manifest.build_full_detail_lod_manifest(intake_queue, max_segments_per_asset=3)

    assert report["summary"]["sampled_asset_count"] == 2
    assert report["summary"]["sampled_solver_exact_asset_count"] == 1
    assert report["summary"]["sampled_preview_asset_count"] == 1
    assert [item["asset_ref"] for item in report["lod_items"]] == ["RD-001", "RD-002"]
    assert report["lod_items"][1]["solver_exact"] is False


def test_full_detail_lod_manifest_cli_writes_outputs(tmp_path: Path) -> None:
    intake_queue = _fixture_inputs(tmp_path)
    out_path = tmp_path / "lod.json"
    out_md_path = tmp_path / "lod.md"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--intake-queue",
            str(intake_queue),
            "--out",
            str(out_path),
            "--out-md",
            str(out_md_path),
            "--max-segments-per-asset",
            "3",
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["summary"]["sampled_solver_exact_asset_count"] == 1
    assert json.loads(out_path.read_text(encoding="utf-8"))["lod_items"][0]["full_detail_segment_count"] == 7
    assert "Real Drawing Full-Detail LOD Manifest" in out_md_path.read_text(encoding="utf-8")
