export const REAL_DRAWING_REVIEW_FLAG_KEYS = new Set([
  'not_solver_exact',
  'ifc_solver_graph_draft_not_member_extents',
  'proxy_layout_not_true_geometry',
  'proxy_node_glyph_fallback',
  'sampled_dense_model',
  'sparse_preview',
]);

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function normalizeRealDrawingText(value) {
  const text = String(value ?? '').trim();
  return text || '';
}

function normalizeRealDrawingTextList(values) {
  return (Array.isArray(values) ? values : [])
    .map((value) => normalizeRealDrawingText(value))
    .filter(Boolean);
}

export function getRealDrawingQualityFlags(row) {
  return normalizeRealDrawingTextList(row?.quality_flags);
}

export function getRealDrawingSourceQualityFlags(row) {
  return normalizeRealDrawingTextList(row?.source_quality_flags);
}

export function getRealDrawingClaimQualityFlags(row) {
  return normalizeRealDrawingTextList(row?.claim_quality_flags);
}

export function getRealDrawingLoadEvidenceLabel(row) {
  const status = normalizeRealDrawingText(row?.load_evidence_status);
  const loads = safeNumber(row?.structural_load_count, 0);
  const loadCases = safeNumber(row?.load_case_group_count, 0);
  const zeroLoadRequired = Boolean(row?.zero_load_signature_required);
  if (!status && !loads && !loadCases && !zeroLoadRequired) return '';
  if (zeroLoadRequired && !loads && !loadCases) return 'zero-load signature required';
  const parts = [`loads ${loads}`, `cases ${loadCases}`];
  if (zeroLoadRequired) parts.push('zero-load signature required');
  return `${status || 'load evidence'} · ${parts.join(' · ')}`;
}

export function getRealDrawingQualityTier(row) {
  const flags = new Set(getRealDrawingQualityFlags(row));
  const solverExact = Boolean(row?.solver_exact);
  const geometryClaimStatus = normalizeRealDrawingText(row?.geometry_claim_status);
  if (!row?.geometry_available || safeNumber(row?.segment_count, 0) <= 0) return 'blocked';
  if (flags.has('sparse_preview') && !solverExact) return 'sparse_preview';
  if (solverExact && flags.has('sampled_dense_model')) return 'solver_exact_sampled';
  if (geometryClaimStatus === 'ifc_geometry_exact_ready' && !solverExact) return 'ifc_geometry_ready';
  if (!solverExact || flags.has('not_solver_exact') || flags.has('proxy_layout_not_true_geometry')) {
    return 'proxy_preview';
  }
  return 'solver_exact_ready';
}

export function getRealDrawingQualityBadge(row) {
  const tier = getRealDrawingQualityTier(row);
  if (tier === 'blocked') return { label: 'blocked', tone: 'blocked' };
  if (tier === 'sparse_preview') return { label: 'sparse', tone: 'sparse' };
  if (tier === 'solver_exact_sampled') return { label: 'sampled', tone: 'sampled' };
  if (tier === 'ifc_geometry_ready') return { label: 'geometry', tone: 'geometry' };
  if (tier === 'proxy_preview') return { label: 'proxy', tone: 'proxy' };
  return { label: 'solver exact', tone: 'exact' };
}

export function getRealDrawingSegmentLabel(row) {
  const sampleCount = safeNumber(row?.segment_count, 0);
  const fullCount = safeNumber(row?.full_detail_segment_count, 0);
  if (fullCount > sampleCount && sampleCount > 0) return `${sampleCount}/${fullCount}`;
  return String(sampleCount);
}

export function getRealDrawingReviewAction(row) {
  const flags = new Set(getRealDrawingQualityFlags(row));
  const geometryClaimStatus = normalizeRealDrawingText(row?.geometry_claim_status);
  const loadModelStatus = normalizeRealDrawingText(row?.load_model_status);
  if (flags.has('sparse_preview') && !Boolean(row?.solver_exact)) return 'Expand sparse archive preview';
  if (flags.has('ifc_solver_graph_draft_not_member_extents')) return 'Recover member extents and loads';
  if (geometryClaimStatus === 'ifc_geometry_exact_ready' && loadModelStatus === 'source_ifc_load_model_missing') {
    return 'Attach IFC load-model evidence';
  }
  if (normalizeRealDrawingText(row?.graph_source_kind) === 'ifc_solver_graph_draft' && !Boolean(row?.solver_exact)) {
    return 'Close IFC loads and promote';
  }
  if (flags.has('sampled_dense_model')) return 'Inspect sampled dense model';
  if (flags.has('proxy_node_glyph_fallback')) return 'Replace node glyph fallback';
  if (flags.has('proxy_layout_not_true_geometry') || flags.has('not_solver_exact') || !Boolean(row?.solver_exact)) {
    return 'Promote to solver-exact topology';
  }
  return 'Engineer review';
}

export function getRealDrawingInspectorRows(row) {
  const sourceFlags = getRealDrawingSourceQualityFlags(row);
  const claimFlags = getRealDrawingClaimQualityFlags(row);
  const qualityFlags = getRealDrawingQualityFlags(row);
  const segmentCount = safeNumber(row?.segment_count, 0);
  const renderableCount = safeNumber(row?.renderable_segment_count, segmentCount);
  const sampleCount = safeNumber(row?.viewer_sample_segment_count, 0);
  const fullCount = safeNumber(row?.full_detail_segment_count, 0);
  const loadEvidence = getRealDrawingLoadEvidenceLabel(row);
  const geometryReady = Boolean(row?.geometry_available) && segmentCount > 0;
  const loadReady = Boolean(row?.load_model_ready) || Boolean(row?.solver_exact);
  const claimReady = Boolean(row?.analysis_claim_ready) || Boolean(row?.solver_exact);
  const lodStatus = normalizeRealDrawingText(row?.lod_evidence_status);
  return [
    {
      label: 'Geometry',
      value: normalizeRealDrawingText(row?.geometry_claim_status)
        || normalizeRealDrawingText(row?.geometry_mode)
        || (geometryReady ? 'available' : 'missing'),
      detail: `${renderableCount || segmentCount} renderable segments`,
      tone: geometryReady ? 'success' : 'danger',
    },
    {
      label: 'Load Model',
      value: normalizeRealDrawingText(row?.load_model_status) || (loadReady ? 'solver exact source' : 'not attached'),
      detail: loadEvidence || `loads ${safeNumber(row?.structural_load_count, 0)} / cases ${safeNumber(row?.load_case_group_count, 0)}`,
      tone: loadReady ? 'success' : Boolean(row?.zero_load_signature_required) ? 'warn' : 'neutral',
    },
    {
      label: 'Analysis Claim',
      value: claimReady ? 'ready' : 'blocked',
      detail: claimFlags.length ? claimFlags.join(', ') : 'claim flags clear',
      tone: claimReady && !claimFlags.length ? 'success' : 'warn',
    },
    {
      label: 'Source',
      value: normalizeRealDrawingText(row?.graph_source_kind)
        || normalizeRealDrawingText(row?.route)
        || normalizeRealDrawingText(row?.file_type)
        || '--',
      detail: sourceFlags.length ? sourceFlags.join(', ') : (normalizeRealDrawingText(row?.status) || 'source clear'),
      tone: sourceFlags.length ? 'warn' : 'neutral',
    },
    {
      label: 'LOD',
      value: lodStatus || (fullCount > sampleCount && sampleCount ? 'sampled viewport' : 'viewport'),
      detail: fullCount > 0 && sampleCount > 0 ? `${sampleCount}/${fullCount} segments` : `${segmentCount} segments`,
      tone: lodStatus ? 'success' : fullCount > sampleCount && sampleCount ? 'warn' : 'neutral',
    },
    {
      label: 'Review',
      value: getRealDrawingReviewAction(row),
      detail: qualityFlags.length ? qualityFlags.join(', ') : 'no review flags',
      tone: isRealDrawingReviewAsset(row) ? 'warn' : 'success',
    },
  ];
}

export function isRealDrawingReviewAsset(row) {
  const flags = getRealDrawingQualityFlags(row);
  const solverExact = Boolean(row?.solver_exact);
  return !solverExact || flags.some((flag) => REAL_DRAWING_REVIEW_FLAG_KEYS.has(flag) && !(solverExact && flag === 'sparse_preview'));
}

export function realDrawingAssetMatchesQualityFilter(row, filterKey = 'all') {
  const tier = getRealDrawingQualityTier(row);
  if (filterKey === 'solver_exact') return tier === 'solver_exact_ready' || tier === 'solver_exact_sampled';
  if (filterKey === 'geometry_ready') return tier === 'ifc_geometry_ready';
  if (filterKey === 'review') return isRealDrawingReviewAsset(row);
  if (filterKey === 'proxy') return tier === 'proxy_preview';
  if (filterKey === 'sparse') return tier === 'sparse_preview';
  if (filterKey === 'sampled') return tier === 'solver_exact_sampled';
  return true;
}

export function getRealDrawingAssetRegistry(data = {}) {
  return (Array.isArray(data?.meta?.real_drawing_asset_registry) ? data.meta.real_drawing_asset_registry : [])
    .filter((row) => row && typeof row === 'object' && normalizeRealDrawingText(row.asset_ref));
}

export function buildRealDrawingQualitySummary(data = {}) {
  const assets = getRealDrawingAssetRegistry(data);
  const reviewAssets = assets.filter(isRealDrawingReviewAsset);
  const exactAssets = assets.filter((row) => Boolean(row?.solver_exact));
  const blockedAssets = assets.filter((row) => getRealDrawingQualityTier(row) === 'blocked');
  const sampledAssets = assets.filter((row) => getRealDrawingQualityTier(row) === 'solver_exact_sampled');
  const sparseAssets = assets.filter((row) => getRealDrawingQualityTier(row) === 'sparse_preview');
  const geometryReadyAssets = assets.filter((row) => getRealDrawingQualityTier(row) === 'ifc_geometry_ready');
  const proxyAssets = assets.filter((row) => getRealDrawingQualityTier(row) === 'proxy_preview');
  const zeroLoadSignatureRequiredAssets = assets.filter((row) => Boolean(row?.zero_load_signature_required));
  const fullSolverExactReady = assets.length > 0
    && exactAssets.length === assets.length
    && reviewAssets.length === 0
    && blockedAssets.length === 0;
  return {
    assets,
    reviewAssets,
    exactAssets,
    blockedAssets,
    sampledAssets,
    sparseAssets,
    geometryReadyAssets,
    proxyAssets,
    zeroLoadSignatureRequiredAssets,
    assetCount: assets.length,
    reviewQueueCount: reviewAssets.length,
    exactCount: exactAssets.length,
    geometryReadyCount: geometryReadyAssets.length,
    proxyCount: proxyAssets.length,
    zeroLoadSignatureRequiredCount: zeroLoadSignatureRequiredAssets.length,
    sparseCount: sparseAssets.length,
    sampledCount: sampledAssets.length,
    blockedCount: blockedAssets.length,
    fullSolverExactReady,
    gateLabel: assets.length
      ? (blockedAssets.length ? 'Blocked' : fullSolverExactReady ? 'Full solver-exact' : 'Pass with review queue')
      : '--',
  };
}

export function getRealDrawingAssetOptionLabel(row) {
  const assetRef = normalizeRealDrawingText(row?.asset_ref);
  const badge = getRealDrawingQualityBadge(row);
  const warning = normalizeRealDrawingText(row?.warning_label);
  return `${assetRef} · ${badge.label} · ${getRealDrawingSegmentLabel(row)}${warning ? ` · ${warning}` : ''}`;
}

export function getRealDrawingPromotionQueue(data = {}) {
  const queue = data?.meta?.real_drawing_solver_exact_promotion_queue;
  return queue && typeof queue === 'object' ? queue : {};
}

export function getRealDrawingPlannedUnlockBatch(data = {}) {
  const queue = getRealDrawingPromotionQueue(data);
  return (Array.isArray(queue.planned_unlock_batch) ? queue.planned_unlock_batch : [])
    .filter((row) => row && typeof row === 'object' && normalizeRealDrawingText(row.asset_ref));
}

export function getRealDrawingOpenPromotionItems(data = {}) {
  const queue = getRealDrawingPromotionQueue(data);
  const rows = Array.isArray(queue.open_promotion_items)
    ? queue.open_promotion_items
    : (Array.isArray(queue.promotion_items) ? queue.promotion_items : []);
  return rows.filter((row) => row && typeof row === 'object' && normalizeRealDrawingText(row.asset_ref));
}

export function getRealDrawingBrowserSearchText(row) {
  return [
    row?.asset_ref,
    row?.file_type,
    row?.route,
    row?.status,
    row?.geometry_mode,
    row?.graph_source_kind,
    row?.geometry_claim_status,
    row?.load_model_status,
    row?.warning_label,
    row?.quality_notice,
    getRealDrawingQualityBadge(row).label,
    getRealDrawingReviewAction(row),
    getRealDrawingLoadEvidenceLabel(row),
    getRealDrawingSegmentLabel(row),
    ...getRealDrawingQualityFlags(row),
    ...getRealDrawingSourceQualityFlags(row),
    ...getRealDrawingClaimQualityFlags(row),
  ].map((value) => normalizeRealDrawingText(value).toLowerCase()).filter(Boolean).join(' ');
}

export function realDrawingAssetMatchesBrowserQuery(row, query = '') {
  const tokens = normalizeRealDrawingText(query).toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const haystack = getRealDrawingBrowserSearchText(row);
  return tokens.every((token) => haystack.includes(token));
}

export function getRealDrawingAssetSortId(row) {
  return normalizeRealDrawingText(row?.asset_ref).replace(/\d+/g, (value) => value.padStart(8, '0'));
}

export function getRealDrawingBrowserPriorityScore(row) {
  const flags = getRealDrawingQualityFlags(row);
  const sourceFlags = getRealDrawingSourceQualityFlags(row);
  const claimFlags = getRealDrawingClaimQualityFlags(row);
  let score = 0;
  if (getRealDrawingQualityTier(row) === 'blocked') score -= 120;
  if (isRealDrawingReviewAsset(row)) score -= 80;
  if (claimFlags.length) score -= 50;
  if (sourceFlags.length) score -= 35;
  if (Boolean(row?.zero_load_signature_required) && !Boolean(row?.engineer_zero_load_signature_attached)) score -= 30;
  if (flags.includes('sampled_dense_model')) score -= 16;
  if (flags.includes('sparse_preview')) score -= 14;
  if (!Boolean(row?.solver_exact)) score -= 10;
  score -= Math.min(safeNumber(row?.segment_count, 0), 2000) / 10000;
  return score;
}

export function sortRealDrawingBrowserAssets(assets, sortKey = 'priority') {
  const normalized = ['priority', 'asset', 'segments', 'status'].includes(sortKey) ? sortKey : 'priority';
  return [...(Array.isArray(assets) ? assets : [])].sort((a, b) => {
    if (normalized === 'segments') {
      return safeNumber(b?.segment_count, 0) - safeNumber(a?.segment_count, 0)
        || safeNumber(b?.renderable_segment_count, 0) - safeNumber(a?.renderable_segment_count, 0)
        || getRealDrawingAssetSortId(a).localeCompare(getRealDrawingAssetSortId(b));
    }
    if (normalized === 'status') {
      return getRealDrawingQualityTier(a).localeCompare(getRealDrawingQualityTier(b))
        || normalizeRealDrawingText(a?.status).localeCompare(normalizeRealDrawingText(b?.status))
        || getRealDrawingAssetSortId(a).localeCompare(getRealDrawingAssetSortId(b));
    }
    if (normalized === 'asset') {
      return getRealDrawingAssetSortId(a).localeCompare(getRealDrawingAssetSortId(b));
    }
    return getRealDrawingBrowserPriorityScore(a) - getRealDrawingBrowserPriorityScore(b)
      || getRealDrawingAssetSortId(a).localeCompare(getRealDrawingAssetSortId(b));
  });
}
