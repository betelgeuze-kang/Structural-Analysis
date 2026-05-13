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


def test_viewer_stats_summary_module_builds_kpi_entries_and_real_drawing_counts() -> None:
    payload = _run_node_contract_script(
        """
import {
  VIEWER_KPI_CARD_CONFIGS,
  VIEWER_STATS_PANEL_KEYS,
  buildViewerStatEntries,
  buildViewerStatsSummary,
} from './src/structure-viewer/viewer-stats-summary.js';

const data = {
  nodes: [{id: 1}, {id: 2}, {id: 3}],
  elements: [
    {id: 'E1', dcr: 0.85},
    {id: 'E2', dcr: 1.2},
    {id: 'E3', dcr: 0},
  ],
  meta: {
    name: 'Tower A',
    source_label: '',
    stories: 12,
    member_count: 25,
    group_count: 4,
    section_count: 9,
    used_section_count: 7,
    geometry_bridge_review_count: 3,
    load_pattern_count: 6,
    real_drawing_asset_count: 2,
    real_drawing_renderable_asset_count: 2,
    real_drawing_solver_exact_asset_count: 1,
    real_drawing_proxy_or_preview_asset_count: 1,
    real_drawing_asset_registry: [
      {
        asset_ref: 'RD-001',
        geometry_available: true,
        segment_count: 4,
        solver_exact: true,
        load_model_ready: true,
        analysis_claim_ready: true,
      },
      {
        asset_ref: 'RD-002',
        geometry_available: true,
        segment_count: 2,
        solver_exact: false,
        quality_flags: ['proxy_layout_not_true_geometry', 'not_solver_exact'],
        zero_load_signature_required: true,
      },
    ],
    real_drawing_solver_exact_promotion_queue: {
      summary: {
        target_solver_exact_asset_count: 2,
        planned_solver_exact_asset_count_after_unlock_batch: 2,
        required_solver_exact_delta: 1,
        planned_unlock_batch_count: 1,
      },
      planned_unlock_batch: [{asset_ref: 'RD-002'}],
    },
  },
};

const largeModelBuildProfile = {
  enabled: true,
  pickingMode: 'spatial-index',
  normalizationMode: 'worker',
  geometryMode: 'streamed',
  pickSpatialMeshTriangleBvhEnabled: true,
  pickSpatialMeshTriangleCount: 42,
  pickSpatialMeshLocalCatalogCount: 2,
  pickSpatialSurfaceFacetBvhEnabled: true,
  pickSpatialSurfaceFacetCount: 9,
  pickSpatialFullBvhEnabled: false,
  pickSpatialDenseBucketBvhEnabled: true,
  pickSpatialDenseBucketRecordCount: 6,
};
const summary = buildViewerStatsSummary(data, {
  largeModelBuildProfile,
  surfaceRenderLodProfile: {label: 'medium'},
  preferInstancedSurfacePicking: true,
  modelSourceLabel: 'artifact fallback',
});
const entries = buildViewerStatEntries(summary, {largeModelBuildProfile});

console.log(JSON.stringify({
  summary: {
    maxDcr: summary.maxDcr,
    avgDcr: summary.avgDcr,
    ngCount: summary.ngCount,
    sectionCoverage: summary.sectionCoverage,
    reviewCoverage: summary.reviewCoverage,
    sourceLabel: summary.sourceLabel,
    surfaceLodLabel: summary.surfaceLodLabel,
    surfacePickLabel: summary.surfacePickLabel,
    buildPathLabel: summary.buildPathLabel,
    realDrawingReviewQueueLabel: summary.realDrawingReviewQueueLabel,
    realDrawingZeroLoadRequiredLabel: summary.realDrawingZeroLoadRequiredLabel,
    realDrawingPromotionTargetLabel: summary.realDrawingPromotionTargetLabel,
    realDrawingPromotionUnlockBatchLabel: summary.realDrawingPromotionUnlockBatchLabel,
  },
  statsKeys: VIEWER_STATS_PANEL_KEYS.slice(0, 5),
  kpiKeys: VIEWER_KPI_CARD_CONFIGS.map((config) => config.key),
  entries: {
    maxDcrTone: entries.maxDcr.statsTone,
    realDrawingAssetsTone: entries.realDrawingAssets.statsTone,
    promotionTargetTone: entries.realDrawingPromotionTarget.statsTone,
    pickMeshTriangles: entries.pickMeshTriangles.value,
    pickDenseBuckets: entries.pickDenseBuckets.value,
  },
}));
"""
    )

    assert payload["summary"] == {
        "maxDcr": "1.200",
        "avgDcr": "1.025",
        "ngCount": 1,
        "sectionCoverage": "7/9",
        "reviewCoverage": "3",
        "sourceLabel": "artifact fallback",
        "surfaceLodLabel": "medium",
        "surfacePickLabel": "spatial index + raycaster fallback + mesh triangle BVH + mesh-local BVH + surface facet BVH + dense-bucket BVH",
        "buildPathLabel": "worker | streamed",
        "realDrawingReviewQueueLabel": "1",
        "realDrawingZeroLoadRequiredLabel": "1",
        "realDrawingPromotionTargetLabel": "1/2",
        "realDrawingPromotionUnlockBatchLabel": "1 assets -> 2 exact",
    }
    assert payload["statsKeys"] == ["maxDcr", "avgDcr", "ngCount", "stories", "model"]
    assert payload["kpiKeys"] == [
        "maxDcr",
        "avgDcr",
        "ngCount",
        "stories",
        "members",
        "groups",
        "reviewIds",
        "loadPatterns",
    ]
    assert payload["entries"] == {
        "maxDcrTone": "danger",
        "realDrawingAssetsTone": "success",
        "promotionTargetTone": "success",
        "pickMeshTriangles": "42 triangles",
        "pickDenseBuckets": "6",
    }
