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


def test_real_drawing_quality_module_classifies_searches_and_sorts_assets() -> None:
    payload = _run_node_contract_script(
        """
import {
  buildRealDrawingQualitySummary,
  getRealDrawingAssetOptionLabel,
  getRealDrawingBrowserSearchText,
  getRealDrawingInspectorRows,
  getRealDrawingLoadEvidenceLabel,
  getRealDrawingOpenPromotionItems,
  getRealDrawingPlannedUnlockBatch,
  getRealDrawingQualityBadge,
  getRealDrawingReviewAction,
  getRealDrawingSegmentLabel,
  realDrawingAssetMatchesBrowserQuery,
  realDrawingAssetMatchesQualityFilter,
  sortRealDrawingBrowserAssets,
} from './src/structure-viewer/viewer-real-drawing-quality.js';

const data = {
  meta: {
    real_drawing_asset_registry: [
      {
        asset_ref: 'RD-010',
        geometry_available: true,
        segment_count: 12,
        renderable_segment_count: 12,
        solver_exact: true,
        status: 'solver_graph_ready',
        geometry_mode: 'solver_topology_xyz',
        load_model_ready: true,
        analysis_claim_ready: true,
      },
      {
        asset_ref: 'RD-002',
        geometry_available: true,
        segment_count: 4,
        solver_exact: false,
        status: 'ifc_proxy_graph_ready',
        geometry_mode: 'ifc_proxy_topology_3d_layout',
        graph_source_kind: 'ifc_solver_graph_draft',
        quality_flags: ['proxy_layout_not_true_geometry', 'not_solver_exact'],
        source_quality_flags: ['ifc_source_partial'],
        claim_quality_flags: ['commercial_claim_blocked'],
        structural_load_count: 0,
        load_case_group_count: 0,
        zero_load_signature_required: true,
        warning_label: 'proxy layout',
      },
      {
        asset_ref: 'RD-003',
        geometry_available: true,
        segment_count: 7,
        solver_exact: false,
        status: 'ifc_geometry_ready',
        geometry_claim_status: 'ifc_geometry_exact_ready',
        load_model_status: 'source_ifc_load_model_missing',
        graph_source_kind: 'ifc_solver_graph_draft',
      },
      {
        asset_ref: 'RD-004',
        geometry_available: true,
        segment_count: 2,
        solver_exact: false,
        quality_flags: ['sparse_preview'],
      },
      {
        asset_ref: 'RD-005',
        geometry_available: true,
        segment_count: 20,
        full_detail_segment_count: 100,
        viewer_sample_segment_count: 20,
        renderable_segment_count: 20,
        solver_exact: true,
        quality_flags: ['sampled_dense_model'],
        lod_evidence_status: 'PASS_LOD_EVIDENCE_ATTACHED',
      },
      {
        asset_ref: 'RD-000',
        geometry_available: false,
        segment_count: 0,
        solver_exact: false,
        status: 'missing_geometry',
      },
    ],
    real_drawing_solver_exact_promotion_queue: {
      planned_unlock_batch: [
        {asset_ref: 'RD-002', promotion_family: 'ifc_coordinate_geometry_reconstruction'},
      ],
      open_promotion_items: [
        {asset_ref: 'RD-003', promotion_family: 'ifc_load_model_evidence_closure', priority_rank: 1},
      ],
    },
  },
};

const assets = data.meta.real_drawing_asset_registry;
const summary = buildRealDrawingQualitySummary(data);
const sortedByPriority = sortRealDrawingBrowserAssets(assets, 'priority').map((row) => row.asset_ref);
const sortedByAsset = sortRealDrawingBrowserAssets(assets, 'asset').map((row) => row.asset_ref);
const sortedBySegments = sortRealDrawingBrowserAssets(assets, 'segments').map((row) => row.asset_ref);
const proxy = assets.find((row) => row.asset_ref === 'RD-002');
const geometry = assets.find((row) => row.asset_ref === 'RD-003');
const sampled = assets.find((row) => row.asset_ref === 'RD-005');

console.log(JSON.stringify({
  summary: {
    assetCount: summary.assetCount,
    exactCount: summary.exactCount,
    reviewQueueCount: summary.reviewQueueCount,
    blockedCount: summary.blockedCount,
    geometryReadyCount: summary.geometryReadyCount,
    proxyCount: summary.proxyCount,
    sampledCount: summary.sampledCount,
    sparseCount: summary.sparseCount,
    gateLabel: summary.gateLabel,
  },
  proxyBadge: getRealDrawingQualityBadge(proxy),
  geometryAction: getRealDrawingReviewAction(geometry),
  sampledSegmentLabel: getRealDrawingSegmentLabel(sampled),
  sampledInspectorRows: getRealDrawingInspectorRows(sampled).map((row) => [row.label, row.tone]),
  proxyLoadEvidence: getRealDrawingLoadEvidenceLabel(proxy),
  proxyOption: getRealDrawingAssetOptionLabel(proxy),
  proxySearchText: getRealDrawingBrowserSearchText(proxy),
  matchesIfcLoad: realDrawingAssetMatchesBrowserQuery(geometry, 'ifc load'),
  matchesProxyZero: realDrawingAssetMatchesBrowserQuery(proxy, 'proxy zero-load'),
  isSolverExactFilter: assets.filter((row) => realDrawingAssetMatchesQualityFilter(row, 'solver_exact')).map((row) => row.asset_ref),
  isGeometryReadyFilter: assets.filter((row) => realDrawingAssetMatchesQualityFilter(row, 'geometry_ready')).map((row) => row.asset_ref),
  plannedUnlock: getRealDrawingPlannedUnlockBatch(data).map((row) => row.asset_ref),
  openPromotions: getRealDrawingOpenPromotionItems(data).map((row) => row.asset_ref),
  sortedByPriority,
  sortedByAsset,
  sortedBySegments,
}));
"""
    )

    assert payload["summary"] == {
        "assetCount": 6,
        "exactCount": 2,
        "reviewQueueCount": 5,
        "blockedCount": 1,
        "geometryReadyCount": 1,
        "proxyCount": 1,
        "sampledCount": 1,
        "sparseCount": 1,
        "gateLabel": "Blocked",
    }
    assert payload["proxyBadge"] == {"label": "proxy", "tone": "proxy"}
    assert payload["geometryAction"] == "Attach IFC load-model evidence"
    assert payload["sampledSegmentLabel"] == "20/100"
    assert ["LOD", "success"] in payload["sampledInspectorRows"]
    assert payload["proxyLoadEvidence"] == "zero-load signature required"
    assert payload["proxyOption"] == "RD-002 · proxy · 4 · proxy layout"
    assert "ifc_source_partial" in payload["proxySearchText"]
    assert payload["matchesIfcLoad"] is True
    assert payload["matchesProxyZero"] is True
    assert payload["isSolverExactFilter"] == ["RD-010", "RD-005"]
    assert payload["isGeometryReadyFilter"] == ["RD-003"]
    assert payload["plannedUnlock"] == ["RD-002"]
    assert payload["openPromotions"] == ["RD-003"]
    assert payload["sortedByPriority"][0] == "RD-000"
    assert payload["sortedByAsset"] == ["RD-000", "RD-002", "RD-003", "RD-004", "RD-005", "RD-010"]
    assert payload["sortedBySegments"][0] == "RD-005"
