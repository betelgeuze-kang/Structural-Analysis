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


def test_real_drawing_panel_renderer_builds_switcher_browser_and_promotion_markup() -> None:
    payload = _run_node_contract_script(
        """
import {REAL_DRAWING_BROWSER_SORT_OPTIONS, REAL_DRAWING_QUALITY_FILTERS} from './src/structure-viewer/viewer-real-drawing-browser-state.js';
import {
  buildRealDrawingQualitySummary,
  realDrawingAssetMatchesBrowserQuery,
  realDrawingAssetMatchesQualityFilter,
  sortRealDrawingBrowserAssets,
} from './src/structure-viewer/viewer-real-drawing-quality.js';
import {buildRealDrawingQualityPanelHtml} from './src/structure-viewer/viewer-real-drawing-panel-renderer.js';

const data = {
  meta: {
    real_drawing_renderable_asset_count: 2,
    real_drawing_asset_registry: [
      {
        asset_ref: 'RD-001',
        geometry_available: true,
        segment_count: 4,
        solver_exact: true,
        load_model_ready: true,
        analysis_claim_ready: true,
        status: 'solver_graph_ready',
      },
      {
        asset_ref: 'RD-002',
        geometry_available: true,
        segment_count: 2,
        solver_exact: false,
        quality_flags: ['proxy_layout_not_true_geometry', 'not_solver_exact'],
        source_quality_flags: ['ifc_source_partial'],
        claim_quality_flags: ['commercial_claim_blocked'],
        zero_load_signature_required: true,
        promotion_id: 'RP-001',
        promotion_family: 'ifc_coordinate_geometry_reconstruction',
      },
    ],
  },
};

const quality = buildRealDrawingQualitySummary(data);
const filteredAssets = quality.assets.filter((row) => realDrawingAssetMatchesQualityFilter(row, 'all'));
const browserAssets = sortRealDrawingBrowserAssets(
  filteredAssets.filter((row) => realDrawingAssetMatchesBrowserQuery(row, 'proxy zero-load')),
  'priority',
);
const html = buildRealDrawingQualityPanelHtml({
  data,
  quality,
  filteredAssets,
  browserAssets,
  reviewRows: browserAssets,
  activeAssetRef: 'RD-002',
  activeAsset: quality.assets[1],
  activeIsolation: {kind: 'member', value: 'RD-002'},
  activeFilter: 'all',
  activeSort: 'priority',
  activeQuery: 'proxy zero-load',
  recentAssetRefs: ['RD-002', 'RD-001'],
  qualityFilters: REAL_DRAWING_QUALITY_FILTERS,
  sortOptions: REAL_DRAWING_BROWSER_SORT_OPTIONS,
  plannedUnlockBatch: [
    {
      asset_ref: 'RD-002',
      promotion_id: 'RP-001',
      promotion_family: 'ifc_coordinate_geometry_reconstruction',
      recommended_action: 'recover true geometry',
      expected_solver_exact_delta: 1,
      quality_flags: ['proxy_layout_not_true_geometry'],
    },
  ],
  openPromotionItems: [],
  nextQueueTitle: 'IFC Reconstruction Queue',
  promotionTarget: 2,
  promotionAfterBatch: 2,
  promotionCurrent: 1,
  promotionRequiredDelta: 1,
});

console.log(JSON.stringify({
  hasSwitcher: html.includes('data-real-drawing-asset-select="true"'),
  hasBrowserQuery: html.includes('proxy zero-load'),
  hasRecent: html.includes('data-real-drawing-recent-asset="RD-002"'),
  hasActiveInspector: html.includes('data-real-drawing-active-inspector="true"'),
  hasBrowserItem: html.includes('data-real-drawing-browser-asset="RD-002"'),
  hasReviewItem: html.includes('data-real-drawing-review-asset="RD-002"'),
  hasPromotionItem: html.includes('data-real-drawing-promotion-asset="RD-002"'),
  hasIsolationButton: html.includes('data-real-drawing-isolate="true"') && html.includes(' is-active'),
  hasEscapedArrow: html.includes('1 -&gt; 2/2'),
  hasNoRawScript: !html.includes('<script>'),
}));
"""
    )

    assert payload == {
        "hasSwitcher": True,
        "hasBrowserQuery": True,
        "hasRecent": True,
        "hasActiveInspector": True,
        "hasBrowserItem": True,
        "hasReviewItem": True,
        "hasPromotionItem": True,
        "hasIsolationButton": True,
        "hasEscapedArrow": True,
        "hasNoRawScript": True,
    }
