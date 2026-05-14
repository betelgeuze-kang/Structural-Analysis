import {
  buildRealDrawingQualitySummary,
  getRealDrawingAssetRegistry,
  realDrawingAssetMatchesBrowserQuery,
  realDrawingAssetMatchesQualityFilter,
  sortRealDrawingBrowserAssets,
} from './viewer-real-drawing-quality.js';
import {
  normalizeSelectionValue,
  normalizeSelectionValues,
} from './viewer-shared-selection-state.js';

function normalizeRealDrawingAssets(assets = []) {
  return (Array.isArray(assets) ? assets : [])
    .filter((row) => row && typeof row === 'object' && normalizeSelectionValue(row.asset_ref));
}

function buildRealDrawingAssetRefSet(assets = []) {
  return new Set(
    normalizeRealDrawingAssets(assets)
      .map((row) => normalizeSelectionValue(row.asset_ref))
      .filter(Boolean),
  );
}

function clampRecentLimit(maxRecent, fallback) {
  const value = Number(maxRecent);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

export function resolveRealDrawingAssetRefForSelection({
  assets = [],
  selection = {},
  selectedMemberId = '',
  activeIsolation = {},
  queryAssetRef = '',
} = {}) {
  const refs = buildRealDrawingAssetRefSet(assets);
  if (!refs.size) return '';
  const candidates = [
    selection?.memberId,
    ...(Array.isArray(selection?.memberIds) ? selection.memberIds : []),
    selectedMemberId,
    activeIsolation?.kind === 'member' ? activeIsolation.value : '',
    queryAssetRef,
  ].map(normalizeSelectionValue);
  return candidates.find((ref) => ref && refs.has(ref)) || '';
}

export function getActiveRealDrawingAssetRef({
  assets = [],
  selectedMemberId = '',
  sharedMemberId = '',
  activeIsolation = {},
} = {}) {
  const registry = normalizeRealDrawingAssets(assets);
  const refs = buildRealDrawingAssetRefSet(registry);
  if (!refs.size) return '';
  const selectedRef = normalizeSelectionValue(selectedMemberId);
  if (selectedRef && refs.has(selectedRef)) return selectedRef;
  const sharedRef = normalizeSelectionValue(sharedMemberId);
  if (sharedRef && refs.has(sharedRef)) return sharedRef;
  const isolatedRef = activeIsolation?.kind === 'member'
    ? normalizeSelectionValue(activeIsolation.value)
    : '';
  if (isolatedRef && refs.has(isolatedRef)) return isolatedRef;
  return normalizeSelectionValue(registry[0].asset_ref);
}

export function rememberRealDrawingAssetRef(assetRef, {
  assets = [],
  recentAssetRefs = [],
  maxRecent = 8,
} = {}) {
  const normalized = normalizeSelectionValue(assetRef);
  const limit = clampRecentLimit(maxRecent, 8);
  const recent = filterRecentRealDrawingAssetRefs({ assets, recentAssetRefs, maxRecent: limit });
  if (!normalized) return recent;
  const refs = buildRealDrawingAssetRefSet(assets);
  if (refs.size && !refs.has(normalized)) return recent;
  return normalizeSelectionValues([normalized, ...recent]).slice(0, limit);
}

export function filterRecentRealDrawingAssetRefs({
  assets = [],
  recentAssetRefs = [],
  maxRecent = 6,
} = {}) {
  const refs = buildRealDrawingAssetRefSet(assets);
  return normalizeSelectionValues(recentAssetRefs)
    .filter((ref) => !refs.size || refs.has(ref))
    .slice(0, clampRecentLimit(maxRecent, 6));
}

export function getRealDrawingBrowserVisibleAssets(data = {}, {
  activeFilter = 'all',
  activeQuery = '',
  activeSort = 'priority',
  fallbackToRegistry = true,
} = {}) {
  const quality = buildRealDrawingQualitySummary(data);
  const filteredAssets = quality.assets.filter((row) => realDrawingAssetMatchesQualityFilter(row, activeFilter));
  const browserAssets = sortRealDrawingBrowserAssets(
    filteredAssets.filter((row) => realDrawingAssetMatchesBrowserQuery(row, activeQuery)),
    activeSort,
  );
  return browserAssets.length || !fallbackToRegistry ? browserAssets : getRealDrawingAssetRegistry(data);
}

export function stepRealDrawingAssetRef({
  assets = [],
  activeAssetRef = '',
  direction = 1,
} = {}) {
  const registry = normalizeRealDrawingAssets(assets);
  if (!registry.length) return '';
  const activeRef = normalizeSelectionValue(activeAssetRef);
  const activeIndex = registry.findIndex((row) => normalizeSelectionValue(row.asset_ref) === activeRef);
  if (activeIndex < 0) {
    return normalizeSelectionValue(direction < 0 ? registry[registry.length - 1].asset_ref : registry[0].asset_ref);
  }
  const offset = direction < 0 ? -1 : 1;
  const nextIndex = (activeIndex + offset + registry.length) % registry.length;
  return normalizeSelectionValue(registry[nextIndex].asset_ref);
}
