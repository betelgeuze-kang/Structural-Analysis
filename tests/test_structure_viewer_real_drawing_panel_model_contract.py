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


def test_real_drawing_panel_model_builds_browser_review_and_promotion_state() -> None:
    payload = _run_node_contract_script(
        """
import {
  buildRealDrawingQualityPanelModel,
  selectRealDrawingOpenPromotionItems,
  sortRealDrawingOpenPromotionItems,
} from './src/structure-viewer/viewer-real-drawing-panel-model.js';

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
      },
      {
        asset_ref: 'RD-003',
        geometry_available: true,
        segment_count: 5,
        solver_exact: false,
        status: 'ifc_geometry_ready',
        geometry_claim_status: 'ifc_geometry_exact_ready',
        load_model_status: 'source_ifc_load_model_missing',
      },
    ],
    real_drawing_solver_exact_promotion_queue: {
      summary: {
        target_solver_exact_asset_count: 3,
        planned_solver_exact_asset_count_after_unlock_batch: 2,
        current_solver_exact_asset_count: 1,
        required_solver_exact_delta: 2,
      },
      planned_unlock_batch: [
        {asset_ref: 'RD-002', promotion_family: 'ifc_coordinate_geometry_reconstruction'},
        {asset_ref: 'RD-003', promotion_family: 'ifc_load_model_evidence_closure'},
      ],
      open_promotion_items: [
        {asset_ref: 'RD-001', promotion_family: 'manual_engineer_review', priority_rank: 1},
        {asset_ref: 'RD-002', promotion_family: 'ifc_coordinate_geometry_reconstruction', priority_rank: 5},
        {asset_ref: 'RD-003', promotion_family: 'ifc_load_model_evidence_closure', priority_rank: 4},
      ],
    },
  },
};

const model = buildRealDrawingQualityPanelModel(data, {
  activeAssetRef: 'MISSING',
  activeIsolation: {kind: 'member', value: 'RD-003'},
  activeFilter: 'review',
  activeSort: 'asset',
  activeQuery: 'ifc',
  recentAssetRefs: ['RD-002', 'RD-001'],
  maxReviewRows: 2,
  maxPlannedUnlock: 1,
  maxOpenPromotionItems: 1,
});
const sortedPromotions = sortRealDrawingOpenPromotionItems(
  data.meta.real_drawing_solver_exact_promotion_queue.open_promotion_items,
).map((row) => row.asset_ref);
const selectedPromotions = selectRealDrawingOpenPromotionItems(
  data.meta.real_drawing_solver_exact_promotion_queue.open_promotion_items,
  {maxItems: 2},
);

console.log(JSON.stringify({
  quality: {
    assetCount: model.quality.assetCount,
    exactCount: model.quality.exactCount,
    reviewQueueCount: model.quality.reviewQueueCount,
  },
  filteredAssets: model.filteredAssets.map((row) => row.asset_ref),
  browserAssets: model.browserAssets.map((row) => row.asset_ref),
  reviewRows: model.reviewRows.map((row) => row.asset_ref),
  active: {
    ref: model.activeAssetRef,
    asset: model.activeAsset.asset_ref,
    isolation: model.activeIsolation,
  },
  recents: model.recentAssetRefs,
  promotion: {
    plannedUnlock: model.plannedUnlockBatch.map((row) => row.asset_ref),
    openItems: model.openPromotionItems.map((row) => row.asset_ref),
    title: model.nextQueueTitle,
    target: model.promotionTarget,
    afterBatch: model.promotionAfterBatch,
    current: model.promotionCurrent,
    requiredDelta: model.promotionRequiredDelta,
    sortedPromotions,
    selectedPromotions: selectedPromotions.openPromotionItems.map((row) => row.asset_ref),
    selectedTitle: selectedPromotions.nextQueueTitle,
  },
}));
"""
    )

    assert payload["quality"] == {
        "assetCount": 3,
        "exactCount": 1,
        "reviewQueueCount": 2,
    }
    assert payload["filteredAssets"] == ["RD-002", "RD-003"]
    assert payload["browserAssets"] == ["RD-002", "RD-003"]
    assert payload["reviewRows"] == ["RD-002", "RD-003"]
    assert payload["active"] == {
        "ref": "RD-001",
        "asset": "RD-001",
        "isolation": {"kind": "member", "value": "RD-003"},
    }
    assert payload["recents"] == ["RD-002", "RD-001"]
    assert payload["promotion"] == {
        "plannedUnlock": ["RD-002"],
        "openItems": ["RD-003"],
        "title": "IFC Load Evidence Queue",
        "target": 3,
        "afterBatch": 2,
        "current": 1,
        "requiredDelta": 2,
        "sortedPromotions": ["RD-003", "RD-002", "RD-001"],
        "selectedPromotions": ["RD-003"],
        "selectedTitle": "IFC Load Evidence Queue",
    }
