from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.export_real_drawing_structure_viewer_preset import export_structure_viewer_preset
from implementation.phase1.real_drawing_structure_viewer_preset import (
    STRUCTURE_VIEWER_HREF,
    STRUCTURE_VIEWER_PRESET_KEY,
    build_structure_viewer_preset_payload,
    serialize_structure_viewer_sidecar,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_real_drawing_structure_viewer_preset_contract_tiles_assets_as_groups() -> None:
    registry = {
        "asset_count": 2,
        "renderable_asset_count": 2,
        "solver_exact_asset_count": 1,
        "proxy_or_preview_asset_count": 1,
        "assets": [
            {
                "asset_ref": "RD-001",
                "file_type": ".mgt",
                "route": "midas_mgt_direct_parser",
                "status": "solver_graph_ready",
                "solver_exact": True,
                "geometry_mode": "solver_topology_xyz",
                "quality_flags": [],
                "warning_label": "",
                "lod_evidence": {
                    "contract_pass": True,
                    "reason_code": "PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED",
                    "full_detail_segment_count": 12,
                    "viewer_sample_segment_count": 2,
                    "sample_ratio": 0.166667,
                },
                "segments": [
                    {"p0": [0, 0, 0], "p1": [10, 0, 0], "family": "beam", "color": "#2563eb"},
                    {"p0": [10, 0, 0], "p1": [10, 5, 0], "family": "column", "color": "#be123c"},
                ],
            },
            {
                "asset_ref": "RD-002",
                "file_type": ".ifc",
                "route": "ifc_to_structural_graph_adapter",
                "status": "ifc_proxy_graph_ready",
                "solver_exact": False,
                "geometry_mode": "ifc_proxy_topology_3d_layout",
                "quality_flags": ["proxy_layout_not_true_geometry", "not_solver_exact"],
                "load_evidence_status": "ERR_IFC_LOAD_CASES_MISSING_ENGINEER_ZERO_LOAD_SIGNATURE_REQUIRED",
                "load_case_group_count": 0,
                "structural_load_count": 0,
                "zero_load_signature_required": True,
                "warning_label": "proxy layout",
                "segments": [
                    {"p0": [0, 0, 0], "p1": [0, 3, 2], "family": "contained_in_spatial_structure"},
                ],
            },
        ],
    }
    promotion_queue = {
        "schema_version": "real-drawing-solver-exact-promotion-queue.v1",
        "contract_pass": True,
        "reason_code": "PASS_PROMOTION_QUEUE_OPEN",
        "summary": {
            "current_solver_exact_asset_count": 1,
            "target_solver_exact_asset_count": 2,
            "required_solver_exact_delta": 1,
            "planned_unlock_batch_count": 1,
            "planned_unlock_batch_expected_delta": 1,
            "planned_solver_exact_asset_count_after_unlock_batch": 2,
            "promotion_candidate_count": 1,
            "promotion_delta_available": 1,
            "sufficient_unlock_batch_for_target": True,
            "family_counts": {"ifc_coordinate_geometry_reconstruction": 1},
            "effort_counts": {"high": 1},
        },
        "planned_unlock_batch": [
            {
                "promotion_id": "RP-001",
                "asset_ref": "RD-002",
                "promotion_family": "ifc_coordinate_geometry_reconstruction",
                "expected_solver_exact_delta": 1,
                "recommended_action": "replace proxy layout with recovered structural geometry",
            }
        ],
        "promotion_items": [
            {
                "promotion_id": "RP-001",
                "asset_ref": "RD-002",
                "promotion_family": "ifc_coordinate_geometry_reconstruction",
                "effort_label": "high",
                "quality_tier": "proxy_preview_review",
                "file_type": ".ifc",
                "priority_rank": 40,
                "closure_evidence_required": ["proxy_layout_flag_removed"],
                "blocker_reason_code": "ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY",
                "load_evidence_status": "ERR_IFC_LOAD_CASES_MISSING_ENGINEER_ZERO_LOAD_SIGNATURE_REQUIRED",
                "zero_load_signature_required": True,
                "commercial_claim_blocked": True,
            }
        ],
    }

    presets = build_structure_viewer_preset_payload(registry, promotion_queue=promotion_queue)
    entry = presets[STRUCTURE_VIEWER_PRESET_KEY]
    payload = entry["payload"]
    model = payload["model"]

    assert STRUCTURE_VIEWER_HREF == "src/structure-viewer/index.html?preset=real_drawing_private_3d"
    assert payload["schema_version"] == "real-drawing-private-3d-viewer-preset.v1"
    assert payload["meta"]["real_drawing_asset_count"] == 2
    assert payload["meta"]["real_drawing_registry_summary"]["solver_exact_asset_count"] == 1
    assert payload["meta"]["real_drawing_registry_summary"]["quality_flag_counts"]["not_solver_exact"] == 1
    assert payload["meta"]["real_drawing_registry_summary"]["zero_load_signature_required_asset_count"] == 1
    assert payload["meta"]["real_drawing_asset_registry"][0]["asset_ref"] == "RD-001"
    assert payload["meta"]["real_drawing_asset_registry"][0]["lod_evidence_status"] == (
        "PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED"
    )
    assert payload["meta"]["real_drawing_asset_registry"][0]["full_detail_segment_count"] == 12
    assert payload["meta"]["real_drawing_asset_registry"][1]["warning_label"] == "proxy layout"
    assert payload["meta"]["real_drawing_asset_registry"][1]["zero_load_signature_required"] is True
    assert (
        payload["meta"]["real_drawing_solver_exact_promotion_queue"]["summary"][
            "target_solver_exact_asset_count"
        ]
        == 2
    )
    assert payload["meta"]["real_drawing_solver_exact_promotion_queue"]["planned_unlock_batch"][0]["asset_ref"] == "RD-002"
    assert payload["meta"]["real_drawing_solver_exact_promotion_queue"]["planned_unlock_batch"][0]["effort_label"] == "high"
    assert payload["meta"]["real_drawing_solver_exact_promotion_queue"]["planned_unlock_batch"][0][
        "closure_evidence_required"
    ] == ["proxy_layout_flag_removed"]
    assert payload["meta"]["real_drawing_solver_exact_promotion_queue"]["open_promotion_items"][0][
        "blocker_reason_code"
    ] == "ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY"
    assert payload["meta"]["real_drawing_solver_exact_promotion_queue"]["open_promotion_items"][0][
        "zero_load_signature_required"
    ] is True
    assert (
        payload["meta"]["real_drawing_solver_exact_promotion_queue"]["open_promotion_items"][0][
            "commercial_claim_blocked"
        ]
        is True
    )
    assert len(model["elements"]) == 3
    assert len(model["metadata"]["groups"]) == 2
    assert model["metadata"]["groups"][0]["name"] == "RD-001 · solver_topology_xyz"
    assert model["metadata"]["groups"][1]["name"] == "RD-002 · proxy layout"
    assert model["elements"][0]["member_id"] == "RD-001"
    assert model["elements"][2]["member_id"] == "RD-002"
    assert "IFC proxy topology layout" in model["elements"][2]["before_after_snapshot_note"]


def test_real_drawing_structure_viewer_sidecar_is_parseable_and_sanitized() -> None:
    registry = {
        "asset_count": 1,
        "renderable_asset_count": 1,
        "solver_exact_asset_count": 1,
        "proxy_or_preview_asset_count": 0,
        "assets": [
            {
                "asset_ref": "RD-001",
                "file_type": ".mgt",
                "route": "midas_mgt_direct_parser",
                "status": "solver_graph_ready",
                "solver_exact": True,
                "geometry_mode": "solver_topology_xyz",
                "quality_flags": [],
                "warning_label": "",
                "source_url": "SHOULD_NOT_LEAK",
                "private_path": "SHOULD_NOT_LEAK",
                "segments": [{"p0": [0, 0, 0], "p1": [1, 0, 0], "family": "beam"}],
            }
        ],
    }

    sidecar = serialize_structure_viewer_sidecar(
        registry,
        promotion_queue={
            "contract_pass": True,
            "summary": {"target_solver_exact_asset_count": 2},
            "planned_unlock_batch": [
                {
                    "promotion_id": "RP-001",
                    "asset_ref": "RD-001",
                    "source_url": "SHOULD_NOT_LEAK",
                    "private_path": "SHOULD_NOT_LEAK",
                }
            ],
        },
    )
    assert sidecar.startswith("window.__STRUCTURE_VIEWER_PRESET_PAYLOADS__=")
    assert "SHOULD_NOT_LEAK" not in sidecar

    raw_json = sidecar.removeprefix("window.__STRUCTURE_VIEWER_PRESET_PAYLOADS__=").rstrip(";\n")
    parsed = json.loads(raw_json)
    assert parsed[STRUCTURE_VIEWER_PRESET_KEY]["payload"]["model"]["elements"][0]["member_id"] == "RD-001"


def test_export_real_drawing_structure_viewer_preset_is_canonical_non_html_cli_path(tmp_path: Path) -> None:
    graph_path = tmp_path / "graphs" / "solver.json"
    queue_path = tmp_path / "model_optimization_intake_queue.json"
    promotion_queue_path = tmp_path / "solver_exact_promotion_queue.json"
    out_summary = tmp_path / "summary.json"
    out_sidecar = tmp_path / "index.real_drawing_private.data.js"
    _write_json(
        graph_path,
        {
            "model": {
                "nodes": [{"id": 1, "x": 0, "y": 0, "z": 0}, {"id": 2, "x": 5, "y": 0, "z": 0}],
                "elements": [{"id": 1, "family": "beam", "node_ids": [1, 2]}],
            }
        },
    )
    _write_json(
        queue_path,
        {
            "queue": [
                {
                    "solver_graph_model_json": str(graph_path),
                    "file_type": ".mgt",
                    "optimization_route": "midas_mgt_direct_parser",
                    "optimization_status": "solver_graph_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": True,
                    "model_asset_count": 1,
                }
            ]
        },
    )
    _write_json(
        promotion_queue_path,
        {
            "contract_pass": True,
            "summary": {
                "current_solver_exact_asset_count": 1,
                "target_solver_exact_asset_count": 1,
                "planned_unlock_batch_count": 0,
            },
            "planned_unlock_batch": [],
        },
    )

    summary = export_structure_viewer_preset(
        intake_queue_path=queue_path,
        out_summary=out_summary,
        out_viewer_sidecar=out_sidecar,
        promotion_queue_path=promotion_queue_path,
    )

    assert summary["output_html"] == ""
    assert summary["output_viewer_sidecar"] == str(out_sidecar)
    assert summary["structure_viewer_href"] == STRUCTURE_VIEWER_HREF
    assert summary["solver_exact_promotion_queue"] == str(promotion_queue_path)
    assert out_summary.exists()
    assert out_sidecar.exists()
    assert "real_drawing_solver_exact_promotion_queue" in out_sidecar.read_text(encoding="utf-8")
