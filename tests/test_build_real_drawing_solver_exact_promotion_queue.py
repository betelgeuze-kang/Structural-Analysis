from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "implementation/phase1/build_real_drawing_solver_exact_promotion_queue.py"
SPEC = importlib.util.spec_from_file_location("build_real_drawing_solver_exact_promotion_queue", SCRIPT_PATH)
assert SPEC is not None
promotion_queue = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(promotion_queue)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _quality_gate(path: Path) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "real-drawing-viewer-quality-gate.v1",
            "contract_pass": True,
            "reason_code": "PASS_WITH_REVIEW_QUEUE",
            "structure_viewer_href": "src/structure-viewer/index.html?preset=real_drawing_private_3d",
            "summary": {
                "asset_count": 5,
                "solver_exact_asset_count": 1,
                "review_queue_asset_count": 4,
            },
            "asset_quality_rows": [
                {
                    "asset_ref": "RD-001",
                    "file_type": ".mgt",
                    "route": "midas_mgt_direct_parser",
                    "status": "solver_graph_ready",
                    "quality_tier": "solver_exact_ready",
                    "quality_flags": [],
                    "segment_count": 12,
                    "renderable_segment_count": 12,
                    "node_count": 13,
                    "element_count": 12,
                    "solver_exact": True,
                    "geometry_available": True,
                },
                {
                    "asset_ref": "RD-002",
                    "file_type": ".ifc",
                    "route": "ifc_to_structural_graph_adapter",
                    "status": "ifc_proxy_graph_ready",
                    "quality_tier": "proxy_preview_review",
                    "quality_flags": ["proxy_layout_not_true_geometry", "not_solver_exact"],
                    "segment_count": 90,
                    "renderable_segment_count": 90,
                    "node_count": 100,
                    "element_count": 90,
                    "solver_exact": False,
                    "geometry_available": True,
                },
                {
                    "asset_ref": "RD-003",
                    "file_type": ".zip",
                    "route": "midas_binary_decoded_preview_bridge",
                    "status": "archive_decoded_preview_bridge_ready",
                    "quality_tier": "proxy_preview_review",
                    "quality_flags": ["not_solver_exact"],
                    "segment_count": 22,
                    "renderable_segment_count": 22,
                    "node_count": 23,
                    "element_count": 22,
                    "solver_exact": False,
                    "geometry_available": True,
                },
                {
                    "asset_ref": "RD-004",
                    "file_type": ".zip",
                    "route": "midas_binary_decoded_preview_bridge",
                    "status": "archive_decoded_preview_bridge_ready",
                    "quality_tier": "sparse_preview_review",
                    "quality_flags": ["sparse_preview", "not_solver_exact"],
                    "segment_count": 3,
                    "renderable_segment_count": 3,
                    "node_count": 4,
                    "element_count": 3,
                    "solver_exact": False,
                    "geometry_available": True,
                },
                {
                    "asset_ref": "RD-005",
                    "file_type": ".mgt",
                    "route": "midas_mgt_direct_parser",
                    "status": "solver_graph_ready",
                    "quality_tier": "solver_exact_sampled_review",
                    "quality_flags": ["sampled_dense_model"],
                    "segment_count": 1800,
                    "renderable_segment_count": 34000,
                    "node_count": 2000,
                    "element_count": 34000,
                    "solver_exact": True,
                    "geometry_available": True,
                },
            ],
        },
    )


def test_promotion_queue_prioritizes_archive_quick_wins_before_ifc(tmp_path: Path) -> None:
    gate_path = _quality_gate(tmp_path / "quality_gate.json")

    report = promotion_queue.build_promotion_queue(gate_path, target_solver_exact_asset_count=3)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS_PROMOTION_QUEUE_OPEN"
    assert report["summary"]["current_solver_exact_asset_count"] == 1
    assert report["summary"]["target_solver_exact_asset_count"] == 3
    assert report["summary"]["required_solver_exact_delta"] == 2
    assert report["summary"]["planned_unlock_batch_count"] == 2
    assert report["summary"]["planned_solver_exact_asset_count_after_unlock_batch"] == 3
    assert report["planned_unlock_batch"][0]["asset_ref"] == "RD-003"
    assert report["planned_unlock_batch"][0]["promotion_family"] == "archive_preview_exactness_verification"
    assert report["planned_unlock_batch"][1]["asset_ref"] == "RD-004"
    assert report["planned_unlock_batch"][1]["promotion_family"] == "archive_sparse_preview_expansion"
    assert report["promotion_items"][0]["asset_ref"] == "RD-003"
    assert report["promotion_items"][0]["effort_label"] == "low"
    assert report["promotion_items"][-1]["asset_ref"] == "RD-005"
    assert report["promotion_items"][-1]["expected_solver_exact_delta"] == 0


def test_promotion_queue_attaches_ifc_reconstruction_blocker_evidence(tmp_path: Path) -> None:
    gate_path = _quality_gate(tmp_path / "quality_gate.json")
    plan_path = _write_json(
        tmp_path / "ifc_reconstruction_plan.json",
        {
            "ifc_reconstruction_items": [
                {
                    "asset_ref": "RD-002",
                    "blocker_family": "ifc_geometry_material_load_solver_exact_adapter_required",
                    "blocker_reason_code": "ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY",
                    "commercial_claim_blocked": True,
                    "metrics": {"edge_coverage_ratio": 1.0},
                    "required_evidence": [
                        "ifc_local_placement_coordinate_extraction_receipt",
                        "solver_graph_json_npz_receipt",
                    ],
                    "attached_evidence": [
                        "ifc_local_placement_coordinate_extraction_receipt",
                        "ifc_representation_shape_axis_receipt",
                        "ifc_material_section_binding_receipt",
                        "solver_graph_json_npz_receipt",
                    ],
                    "open_evidence": [
                        "ifc_load_case_extraction_or_engineer_signed_zero_load_receipt",
                        "viewer_sidecar_rebuild_receipt",
                    ],
                    "commercialization_recommendation": "keep proxy claim until IFC solver-exact receipts are attached",
                }
            ]
        },
    )

    report = promotion_queue.build_promotion_queue(
        gate_path,
        target_solver_exact_asset_count=3,
        ifc_reconstruction_plan_path=plan_path,
    )

    ifc_item = next(item for item in report["promotion_items"] if item["asset_ref"] == "RD-002")
    assert ifc_item["blocker_reason_code"] == "ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY"
    assert ifc_item["commercial_claim_blocked"] is True
    assert ifc_item["reconstruction_plan_status"] == "open"
    assert ifc_item["attached_evidence"] == [
        "ifc_local_placement_coordinate_extraction_receipt",
        "ifc_representation_shape_axis_receipt",
        "ifc_material_section_binding_receipt",
        "solver_graph_json_npz_receipt",
    ]
    assert ifc_item["closure_evidence_required"] == [
        "ifc_load_case_extraction_or_engineer_signed_zero_load_receipt",
        "viewer_sidecar_rebuild_receipt",
    ]
    assert "IFC solver-exact receipts" in ifc_item["recommended_action"]


def test_promotion_queue_blocks_when_quality_gate_is_missing(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    report = promotion_queue.build_promotion_queue(missing_path, target_solver_exact_asset_count=3)

    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_REAL_DRAWING_QUALITY_GATE_MISSING"
    assert report["promotion_items"] == []


def test_promotion_queue_closes_unlock_batch_when_solver_exact_target_is_reached(tmp_path: Path) -> None:
    gate_path = _quality_gate(tmp_path / "quality_gate.json")

    report = promotion_queue.build_promotion_queue(gate_path, target_solver_exact_asset_count=1)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS_SOLVER_EXACT_TARGET_REACHED"
    assert report["summary"]["current_solver_exact_asset_count"] == 1
    assert report["summary"]["target_solver_exact_asset_count"] == 1
    assert report["summary"]["required_solver_exact_delta"] == 0
    assert report["planned_unlock_batch"] == []
    assert "already reached" in report["recommended_claim"]


def test_promotion_queue_cli_writes_outputs_and_strict_exit(tmp_path: Path) -> None:
    gate_path = _quality_gate(tmp_path / "quality_gate.json")
    out_path = tmp_path / "promotion.json"
    out_md_path = tmp_path / "promotion.md"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--quality-gate",
            str(gate_path),
            "--out",
            str(out_path),
            "--out-md",
            str(out_md_path),
            "--target-solver-exact-assets",
            "3",
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["summary"]["planned_unlock_batch_count"] == 2
    assert json.loads(out_path.read_text(encoding="utf-8"))["reason_code"] == "PASS_PROMOTION_QUEUE_OPEN"
    assert "Real Drawing Solver-Exact Promotion Queue" in out_md_path.read_text(encoding="utf-8")

    strict_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--quality-gate",
            str(gate_path),
            "--out",
            str(tmp_path / "strict.json"),
            "--out-md",
            str(tmp_path / "strict.md"),
            "--target-solver-exact-assets",
            "99",
            "--fail-on-uncovered-target",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert strict_result.returncode == 2
