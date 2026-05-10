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
                "warning_label": "proxy layout",
                "segments": [
                    {"p0": [0, 0, 0], "p1": [0, 3, 2], "family": "contained_in_spatial_structure"},
                ],
            },
        ],
    }

    presets = build_structure_viewer_preset_payload(registry)
    entry = presets[STRUCTURE_VIEWER_PRESET_KEY]
    payload = entry["payload"]
    model = payload["model"]

    assert STRUCTURE_VIEWER_HREF == "src/structure-viewer/index.html?preset=real_drawing_private_3d"
    assert payload["schema_version"] == "real-drawing-private-3d-viewer-preset.v1"
    assert payload["meta"]["real_drawing_asset_count"] == 2
    assert payload["meta"]["real_drawing_registry_summary"]["solver_exact_asset_count"] == 1
    assert payload["meta"]["real_drawing_registry_summary"]["quality_flag_counts"]["not_solver_exact"] == 1
    assert payload["meta"]["real_drawing_asset_registry"][0]["asset_ref"] == "RD-001"
    assert payload["meta"]["real_drawing_asset_registry"][1]["warning_label"] == "proxy layout"
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

    sidecar = serialize_structure_viewer_sidecar(registry)
    assert sidecar.startswith("window.__STRUCTURE_VIEWER_PRESET_PAYLOADS__=")
    assert "SHOULD_NOT_LEAK" not in sidecar

    raw_json = sidecar.removeprefix("window.__STRUCTURE_VIEWER_PRESET_PAYLOADS__=").rstrip(";\n")
    parsed = json.loads(raw_json)
    assert parsed[STRUCTURE_VIEWER_PRESET_KEY]["payload"]["model"]["elements"][0]["member_id"] == "RD-001"


def test_export_real_drawing_structure_viewer_preset_is_canonical_non_html_cli_path(tmp_path: Path) -> None:
    graph_path = tmp_path / "graphs" / "solver.json"
    queue_path = tmp_path / "model_optimization_intake_queue.json"
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

    summary = export_structure_viewer_preset(
        intake_queue_path=queue_path,
        out_summary=out_summary,
        out_viewer_sidecar=out_sidecar,
    )

    assert summary["output_html"] == ""
    assert summary["output_viewer_sidecar"] == str(out_sidecar)
    assert summary["structure_viewer_href"] == STRUCTURE_VIEWER_HREF
    assert out_summary.exists()
    assert out_sidecar.exists()
