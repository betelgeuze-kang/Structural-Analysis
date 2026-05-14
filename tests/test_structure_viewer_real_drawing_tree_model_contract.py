from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node_contract_script(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_real_drawing_tree_model_builds_badged_filtered_asset_items() -> None:
    payload = _run_node_contract_script(
        """
import {buildRealDrawingTreeModel} from './src/structure-viewer/viewer-real-drawing-tree-model.js';

const data = {
  meta: {
    real_drawing_asset_registry: [
      {
        asset_ref: 'RD-001',
        geometry_available: true,
        segment_count: 10,
        solver_exact: true,
        status: 'solver_graph_ready',
      },
      {
        asset_ref: 'RD-002',
        geometry_available: true,
        segment_count: 3,
        solver_exact: false,
        status: 'ifc_proxy_graph_ready',
        geometry_mode: 'ifc_proxy_topology_3d_layout',
        quality_flags: ['proxy_layout_not_true_geometry', 'not_solver_exact'],
        source_quality_flags: ['ifc_source_partial'],
        claim_quality_flags: ['commercial_claim_blocked'],
        zero_load_signature_required: true,
        warning_label: 'proxy layout',
      },
      {
        asset_ref: 'RD-003',
        geometry_available: true,
        segment_count: 20,
        full_detail_segment_count: 100,
        solver_exact: true,
        quality_flags: ['sampled_dense_model'],
      },
    ],
  },
};

const proxyTree = buildRealDrawingTreeModel(data, {
  activeFilter: 'proxy',
  maxItems: 8,
});
const exactTree = buildRealDrawingTreeModel(data, {
  activeFilter: 'solver_exact',
  maxItems: 1,
});
const emptyTree = buildRealDrawingTreeModel(data, {
  activeFilter: 'geometry_ready',
});

console.log(JSON.stringify({
  proxy: {
    heading: proxyTree.heading,
    totalCount: proxyTree.totalCount,
    filteredCount: proxyTree.filteredCount,
    items: proxyTree.items,
  },
  exact: {
    heading: exactTree.heading,
    totalCount: exactTree.totalCount,
    filteredCount: exactTree.filteredCount,
    items: exactTree.items,
  },
  empty: {
    heading: emptyTree.heading,
    totalCount: emptyTree.totalCount,
    filteredCount: emptyTree.filteredCount,
    emptyText: emptyTree.emptyText,
    items: emptyTree.items,
  },
}));
"""
    )

    assert payload["proxy"]["heading"] == "Real Drawing Assets · 1/3"
    assert payload["proxy"]["totalCount"] == 3
    assert payload["proxy"]["filteredCount"] == 1
    assert payload["proxy"]["items"] == [
        {
            "assetRef": "RD-002",
            "label": "RD-002 · proxy layout",
            "badgeText": "proxy · 3",
            "badgeTone": "proxy",
            "badgeTitle": (
                "ifc_proxy_graph_ready | proxy_layout_not_true_geometry, not_solver_exact, "
                "claim:commercial_claim_blocked, source:ifc_source_partial, zero-load signature required"
            ),
            "isolateKind": "member",
            "isolateValue": "RD-002",
            "isolateLabel": "RD-002 · proxy layout",
        }
    ]
    assert payload["exact"]["heading"] == "Real Drawing Assets · 2/3"
    assert payload["exact"]["filteredCount"] == 2
    assert [item["assetRef"] for item in payload["exact"]["items"]] == ["RD-001"]
    assert payload["empty"] == {
        "heading": "Real Drawing Assets · 0/3",
        "totalCount": 3,
        "filteredCount": 0,
        "emptyText": "No assets match the active drawing quality filter.",
        "items": [],
    }
