import {
  buildRealDrawingQualitySummary,
  getRealDrawingOpenPromotionItems,
  getRealDrawingPlannedUnlockBatch,
  getRealDrawingPromotionQueue,
  isRealDrawingReviewAsset,
  normalizeRealDrawingText,
  realDrawingAssetMatchesBrowserQuery,
  realDrawingAssetMatchesQualityFilter,
  sortRealDrawingBrowserAssets,
} from './viewer-real-drawing-quality.js';

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function getPromotionFamilyRank(row) {
  return normalizeRealDrawingText(row?.promotion_family).startsWith('ifc_') ? 0 : 1;
}

export function sortRealDrawingOpenPromotionItems(items = []) {
  return [...(Array.isArray(items) ? items : [])].sort((a, b) => {
    return getPromotionFamilyRank(a) - getPromotionFamilyRank(b)
      || safeNumber(a?.priority_rank, 99) - safeNumber(b?.priority_rank, 99);
  });
}

export function selectRealDrawingOpenPromotionItems(items = [], { maxItems = 8 } = {}) {
  const sortedItems = sortRealDrawingOpenPromotionItems(items);
  const ifcOpenPromotionItems = sortedItems
    .filter((row) => normalizeRealDrawingText(row?.promotion_family).startsWith('ifc_'));
  const ifcLoadPromotionItems = ifcOpenPromotionItems
    .filter((row) => normalizeRealDrawingText(row?.promotion_family) === 'ifc_load_model_evidence_closure');
  const selectedItems = ifcLoadPromotionItems.length
    ? ifcLoadPromotionItems
    : ifcOpenPromotionItems.length
      ? ifcOpenPromotionItems
      : sortedItems;
  const nextQueueTitle = ifcLoadPromotionItems.length
    ? 'IFC Load Evidence Queue'
    : ifcOpenPromotionItems.length
      ? 'IFC Reconstruction Queue'
      : 'Next Quality Closure';
  const limit = Math.max(0, Math.floor(safeNumber(maxItems, 8)));
  return {
    allOpenPromotionItems: sortedItems,
    ifcOpenPromotionItems,
    ifcLoadPromotionItems,
    openPromotionItems: selectedItems.slice(0, limit),
    nextQueueTitle,
  };
}

export function buildRealDrawingQualityPanelModel(data = {}, {
  activeAssetRef = '',
  activeIsolation = {},
  activeFilter = 'all',
  activeSort = 'priority',
  activeQuery = '',
  recentAssetRefs = [],
  maxReviewRows = 16,
  maxPlannedUnlock = 8,
  maxOpenPromotionItems = 8,
} = {}) {
  const quality = buildRealDrawingQualitySummary(data);
  const filteredAssets = quality.assets.filter((row) => realDrawingAssetMatchesQualityFilter(row, activeFilter));
  const browserAssets = sortRealDrawingBrowserAssets(
    filteredAssets.filter((row) => realDrawingAssetMatchesBrowserQuery(row, activeQuery)),
    activeSort,
  );
  const reviewRows = browserAssets
    .filter(isRealDrawingReviewAsset)
    .slice(0, Math.max(0, Math.floor(safeNumber(maxReviewRows, 16))));
  const promotionQueue = getRealDrawingPromotionQueue(data);
  const promotionSummary = promotionQueue.summary && typeof promotionQueue.summary === 'object'
    ? promotionQueue.summary
    : {};
  const plannedUnlockBatch = getRealDrawingPlannedUnlockBatch(data)
    .slice(0, Math.max(0, Math.floor(safeNumber(maxPlannedUnlock, 8))));
  const {
    openPromotionItems,
    nextQueueTitle,
  } = selectRealDrawingOpenPromotionItems(
    getRealDrawingOpenPromotionItems(data),
    { maxItems: maxOpenPromotionItems },
  );
  const requestedActiveAssetRef = normalizeRealDrawingText(activeAssetRef);
  const activeAsset = quality.assets.find((row) => normalizeRealDrawingText(row?.asset_ref) === requestedActiveAssetRef)
    || quality.assets[0]
    || {};
  const resolvedActiveAssetRef = normalizeRealDrawingText(activeAsset?.asset_ref) || requestedActiveAssetRef;
  return {
    data,
    quality,
    filteredAssets,
    browserAssets,
    reviewRows,
    activeAssetRef: resolvedActiveAssetRef,
    activeAsset,
    activeIsolation,
    activeFilter,
    activeSort,
    activeQuery,
    recentAssetRefs,
    plannedUnlockBatch,
    openPromotionItems,
    nextQueueTitle,
    promotionTarget: safeNumber(promotionSummary.target_solver_exact_asset_count, 0),
    promotionAfterBatch: safeNumber(promotionSummary.planned_solver_exact_asset_count_after_unlock_batch, 0),
    promotionCurrent: safeNumber(promotionSummary.current_solver_exact_asset_count, quality.exactCount),
    promotionRequiredDelta: safeNumber(promotionSummary.required_solver_exact_delta, 0),
  };
}
