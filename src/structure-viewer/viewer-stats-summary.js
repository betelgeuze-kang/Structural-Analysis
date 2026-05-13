import {
  buildRealDrawingQualitySummary,
  getRealDrawingPlannedUnlockBatch,
  getRealDrawingPromotionQueue,
} from './viewer-real-drawing-quality.js';

export const VIEWER_STATS_PANEL_KEYS = [
  'maxDcr',
  'avgDcr',
  'ngCount',
  'stories',
  'model',
  'source',
  'members',
  'groups',
  'sections',
  'realDrawingAssets',
  'realDrawingSolverExact',
  'realDrawingGeometryReady',
  'realDrawingProxyPreview',
  'realDrawingReviewQueue',
  'realDrawingZeroLoadRequired',
  'realDrawingFullSolverExact',
  'realDrawingPromotionTarget',
  'realDrawingPromotionUnlockBatch',
  'buildPath',
  'surfaceLod',
  'picking',
  'pickMeshTriangles',
  'pickMeshLocal',
  'pickDeformedTriangles',
  'pickDeformedLocal',
  'pickSurfaceFacets',
  'pickFullBvh',
  'pickNonSurfaceBvh',
  'pickDenseBuckets',
  'reviewIds',
  'loadPatterns',
];

export const VIEWER_KPI_CARD_CONFIGS = [
  { key: 'maxDcr' },
  { key: 'avgDcr' },
  { key: 'ngCount', label: 'NG Members' },
  { key: 'stories', tone: 'accent' },
  { key: 'members' },
  { key: 'groups' },
  { key: 'reviewIds', label: 'Review IDs' },
  { key: 'loadPatterns', label: 'Load Patterns' },
];

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizeViewerText(value) {
  const text = String(value ?? '').trim();
  return text || '';
}

function buildSurfacePickLabel({ largeModelBuildProfile = null, preferInstancedSurfacePicking = false } = {}) {
  if (!largeModelBuildProfile?.enabled) return preferInstancedSurfacePicking ? 'instanced surfaces' : 'direct meshes';
  if (largeModelBuildProfile.pickingMode !== 'spatial-index') return 'analytic + raycaster fallback';
  return `spatial index + raycaster fallback${largeModelBuildProfile.pickSpatialMeshTriangleBvhEnabled ? ' + mesh triangle BVH' : ''}${largeModelBuildProfile.pickSpatialMeshLocalCatalogCount ? ' + mesh-local BVH' : ''}${largeModelBuildProfile.pickSpatialDeformedMeshLocalCatalogCount ? ' + deformed-local BVH' : ''}${largeModelBuildProfile.pickSpatialSurfaceFacetBvhEnabled ? ' + surface facet BVH' : ''}${largeModelBuildProfile.pickSpatialFullBvhEnabled ? ' + full BVH' : ''}${largeModelBuildProfile.pickSpatialDenseBucketBvhEnabled ? ' + dense-bucket BVH' : ''}`;
}

function buildPathLabel(largeModelBuildProfile = null) {
  return largeModelBuildProfile?.enabled
    ? `${largeModelBuildProfile.normalizationMode || 'worker'} | ${largeModelBuildProfile.geometryMode || 'streamed'}`
    : 'default';
}

export function buildViewerStatsSummary(
  data,
  {
    largeModelBuildProfile = null,
    surfaceRenderLodProfile = null,
    preferInstancedSurfacePicking = false,
    modelSourceLabel = '',
  } = {},
) {
  const elements = Array.isArray(data?.elements) ? data.elements : [];
  let maxDcrValue = 0;
  let dcrSum = 0;
  let dcrCount = 0;
  let ngCount = 0;
  elements.forEach((element) => {
    const dcr = safeNumber(element?.dcr, 0);
    if (dcr <= 0) return;
    dcrCount += 1;
    dcrSum += dcr;
    if (dcr > maxDcrValue) maxDcrValue = dcr;
    if (dcr > 1) ngCount += 1;
  });
  const avgDcrValue = dcrCount ? dcrSum / dcrCount : 0;
  const sectionCoverage = Number.isFinite(Number(data?.meta?.section_count))
    && Number.isFinite(Number(data?.meta?.used_section_count))
    ? `${safeNumber(data.meta?.used_section_count, 0)}/${safeNumber(data.meta?.section_count, 0)}`
    : '--';
  const reviewCoverage = Number.isFinite(Number(data?.meta?.geometry_bridge_review_count))
    ? `${safeNumber(data.meta?.geometry_bridge_review_count, 0)}`
    : '--';
  const memberCount = Number.isFinite(Number(data?.meta?.member_count))
    ? safeNumber(data?.meta?.member_count, 0)
    : elements.length;
  const groupCount = Number.isFinite(Number(data?.meta?.group_count))
    ? safeNumber(data?.meta?.group_count, 0)
    : 0;
  const nodeCount = Array.isArray(data?.nodes) ? data.nodes.length : safeNumber(data?.meta?.node_count, 0);
  const elementCount = elements.length;
  const realDrawingAssetCount = safeNumber(data?.meta?.real_drawing_asset_count, 0);
  const realDrawingRenderableCount = safeNumber(data?.meta?.real_drawing_renderable_asset_count, 0);
  const realDrawingSolverExactCount = safeNumber(data?.meta?.real_drawing_solver_exact_asset_count, 0);
  const realDrawingProxyPreviewCount = safeNumber(data?.meta?.real_drawing_proxy_or_preview_asset_count, 0);
  const realDrawingQualitySummary = buildRealDrawingQualitySummary(data);
  const realDrawingPromotionQueue = getRealDrawingPromotionQueue(data);
  const realDrawingPromotionSummary = realDrawingPromotionQueue.summary && typeof realDrawingPromotionQueue.summary === 'object'
    ? realDrawingPromotionQueue.summary
    : {};
  const realDrawingPromotionUnlockBatch = getRealDrawingPlannedUnlockBatch(data);
  const realDrawingPromotionTarget = safeNumber(realDrawingPromotionSummary.target_solver_exact_asset_count, 0);
  const realDrawingPromotionAfterBatch = safeNumber(
    realDrawingPromotionSummary.planned_solver_exact_asset_count_after_unlock_batch,
    0,
  );
  const realDrawingPromotionRequiredDelta = safeNumber(realDrawingPromotionSummary.required_solver_exact_delta, 0);
  const realDrawingPromotionUnlockBatchCount = safeNumber(
    realDrawingPromotionSummary.planned_unlock_batch_count,
    realDrawingPromotionUnlockBatch.length,
  );
  return {
    maxDcrValue,
    avgDcrValue,
    maxDcr: maxDcrValue.toFixed(3),
    avgDcr: avgDcrValue.toFixed(3),
    ngCount,
    sectionCoverage,
    reviewCoverage,
    surfaceLodLabel: surfaceRenderLodProfile?.label || 'full',
    surfacePickLabel: buildSurfacePickLabel({ largeModelBuildProfile, preferInstancedSurfacePicking }),
    buildPathLabel: buildPathLabel(largeModelBuildProfile),
    storiesLabel: String(data?.meta?.stories ?? '--'),
    modelLabel: normalizeViewerText(data?.meta?.name) || '--',
    sourceLabel: normalizeViewerText(data?.meta?.source_label || modelSourceLabel) || '--',
    memberCountLabel: String(memberCount),
    groupCountLabel: String(groupCount),
    nodeCountLabel: String(nodeCount),
    elementCountLabel: String(elementCount),
    loadPatternCountLabel: String(data?.meta?.load_pattern_count ?? '--'),
    realDrawingAssetCount,
    realDrawingRenderableCount,
    realDrawingSolverExactCount,
    realDrawingGeometryReadyCount: realDrawingQualitySummary.geometryReadyCount,
    realDrawingProxyPreviewCount,
    realDrawingReviewQueueCount: realDrawingQualitySummary.reviewQueueCount,
    realDrawingZeroLoadRequiredCount: realDrawingQualitySummary.zeroLoadSignatureRequiredCount,
    realDrawingFullSolverExactReady: realDrawingQualitySummary.fullSolverExactReady,
    realDrawingGateLabel: realDrawingQualitySummary.gateLabel,
    realDrawingAssetCountLabel: realDrawingAssetCount ? String(realDrawingAssetCount) : '--',
    realDrawingSolverExactLabel: realDrawingAssetCount ? String(realDrawingSolverExactCount) : '--',
    realDrawingGeometryReadyLabel: realDrawingAssetCount ? String(realDrawingQualitySummary.geometryReadyCount) : '--',
    realDrawingProxyPreviewLabel: realDrawingAssetCount ? String(realDrawingProxyPreviewCount) : '--',
    realDrawingReviewQueueLabel: realDrawingAssetCount ? String(realDrawingQualitySummary.reviewQueueCount) : '--',
    realDrawingZeroLoadRequiredLabel: realDrawingAssetCount
      ? String(realDrawingQualitySummary.zeroLoadSignatureRequiredCount)
      : '--',
    realDrawingFullSolverExactLabel: realDrawingAssetCount
      ? (realDrawingQualitySummary.fullSolverExactReady ? 'true' : 'false')
      : '--',
    realDrawingPromotionTargetCount: realDrawingPromotionTarget,
    realDrawingPromotionAfterBatchCount: realDrawingPromotionAfterBatch,
    realDrawingPromotionRequiredDelta,
    realDrawingPromotionUnlockBatchCount,
    realDrawingPromotionTargetLabel: realDrawingAssetCount && realDrawingPromotionTarget
      ? `${realDrawingSolverExactCount}/${realDrawingPromotionTarget}`
      : '--',
    realDrawingPromotionUnlockBatchLabel: realDrawingPromotionTarget && realDrawingPromotionRequiredDelta === 0
      ? 'target reached'
      : realDrawingPromotionUnlockBatchCount
        ? `${realDrawingPromotionUnlockBatchCount} assets -> ${realDrawingPromotionAfterBatch || '--'} exact`
        : '--',
  };
}

export function buildViewerStatEntries(summary, { largeModelBuildProfile = null } = {}) {
  const buildProfile = largeModelBuildProfile;
  return {
    maxDcr: {
      label: 'Max D/C',
      value: summary.maxDcr,
      meta: summary.maxDcrValue > 1 ? 'Above unity threshold' : 'Within unity threshold',
      statsTone: summary.maxDcrValue > 1 ? 'danger' : 'success',
    },
    avgDcr: {
      label: 'Avg D/C',
      value: summary.avgDcr,
      meta: `Build ${summary.buildPathLabel}`,
    },
    ngCount: {
      label: 'NG Count',
      value: String(summary.ngCount),
      meta: `Review IDs ${summary.reviewCoverage}`,
      statsTone: summary.ngCount > 0 ? 'danger' : 'success',
    },
    stories: {
      label: 'Stories',
      value: summary.storiesLabel,
      meta: `Load patterns ${summary.loadPatternCountLabel}`,
    },
    model: { label: 'Model', value: summary.modelLabel },
    source: { label: 'Source', value: summary.sourceLabel },
    members: { label: 'Members', value: summary.memberCountLabel },
    groups: { label: 'Groups', value: summary.groupCountLabel },
    sections: { label: 'Sections', value: summary.sectionCoverage },
    realDrawingAssets: {
      label: 'Real Drawing Assets',
      value: summary.realDrawingAssetCountLabel,
      statsTone: summary.realDrawingRenderableCount === summary.realDrawingAssetCount && summary.realDrawingAssetCount > 0
        ? 'success'
        : 'neutral',
    },
    realDrawingSolverExact: { label: 'Solver-Exact Assets', value: summary.realDrawingSolverExactLabel },
    realDrawingGeometryReady: { label: 'IFC Geometry-Ready Assets', value: summary.realDrawingGeometryReadyLabel },
    realDrawingProxyPreview: { label: 'Proxy / Preview Assets', value: summary.realDrawingProxyPreviewLabel },
    realDrawingReviewQueue: {
      label: 'Drawing Review Queue',
      value: summary.realDrawingReviewQueueLabel,
      statsTone: summary.realDrawingReviewQueueCount > 0 ? 'accent' : 'success',
    },
    realDrawingZeroLoadRequired: {
      label: 'Zero-Load Signatures',
      value: summary.realDrawingZeroLoadRequiredLabel,
      statsTone: summary.realDrawingZeroLoadRequiredCount > 0 ? 'accent' : 'success',
    },
    realDrawingFullSolverExact: {
      label: 'Full Solver-Exact Ready',
      value: summary.realDrawingFullSolverExactLabel,
      statsTone: summary.realDrawingFullSolverExactReady ? 'success' : summary.realDrawingAssetCount ? 'danger' : 'neutral',
    },
    realDrawingPromotionTarget: {
      label: 'Solver-Exact Target',
      value: summary.realDrawingPromotionTargetLabel,
      statsTone: summary.realDrawingPromotionAfterBatchCount >= summary.realDrawingPromotionTargetCount
        && summary.realDrawingPromotionTargetCount > 0
        ? 'success'
        : 'accent',
    },
    realDrawingPromotionUnlockBatch: {
      label: 'Next Unlock Batch',
      value: summary.realDrawingPromotionUnlockBatchLabel,
      statsTone: summary.realDrawingPromotionUnlockBatchCount > 0 ? 'accent' : 'neutral',
    },
    buildPath: { label: 'Build Path', value: summary.buildPathLabel },
    surfaceLod: { label: 'Surface LOD', value: summary.surfaceLodLabel },
    picking: { label: 'Picking', value: summary.surfacePickLabel },
    pickMeshTriangles: {
      label: 'Pick Mesh Triangles',
      value: buildProfile?.pickSpatialMeshTriangleBvhEnabled ? `${buildProfile.pickSpatialMeshTriangleCount} triangles` : 'disabled',
    },
    pickMeshLocal: {
      label: 'Pick Mesh Local',
      value: buildProfile?.pickSpatialMeshLocalCatalogCount ? `${buildProfile.pickSpatialMeshLocalCatalogCount} catalogs` : 'disabled',
    },
    pickDeformedTriangles: {
      label: 'Pick Deformed Triangles',
      value: buildProfile?.pickSpatialDeformedMeshTriangleBvhEnabled
        ? `${buildProfile.pickSpatialDeformedMeshTriangleCount} triangles`
        : 'disabled',
    },
    pickDeformedLocal: {
      label: 'Pick Deformed Local',
      value: buildProfile?.pickSpatialDeformedMeshLocalCatalogCount
        ? `${buildProfile.pickSpatialDeformedMeshLocalCatalogCount} catalogs`
        : 'disabled',
    },
    pickSurfaceFacets: {
      label: 'Pick Surface Facets',
      value: buildProfile?.pickSpatialSurfaceFacetBvhEnabled ? `${buildProfile.pickSpatialSurfaceFacetCount} facets` : 'disabled',
    },
    pickFullBvh: {
      label: 'Pick Full BVH',
      value: buildProfile?.pickSpatialFullBvhEnabled ? `${buildProfile.pickSpatialFullBvhRecordCount} records` : 'disabled',
    },
    pickNonSurfaceBvh: {
      label: 'Pick Non-Surface BVH',
      value: buildProfile?.pickSpatialNonSurfaceBvhEnabled
        ? `${buildProfile.pickSpatialNonSurfaceBvhRecordCount} records`
        : 'disabled',
    },
    pickDenseBuckets: {
      label: 'Pick Dense Buckets',
      value: String(buildProfile?.pickSpatialDenseBucketRecordCount ?? '--'),
    },
    reviewIds: { label: 'Review IDs', value: summary.reviewCoverage },
    loadPatterns: { label: 'Load Patterns', value: summary.loadPatternCountLabel },
  };
}

