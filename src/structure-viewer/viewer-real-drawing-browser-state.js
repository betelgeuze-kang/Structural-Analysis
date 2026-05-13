export const REAL_DRAWING_BROWSER_STATE_KEY = 'structural-viewer-real-drawing-browser-v1';

export const REAL_DRAWING_QUALITY_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'solver_exact', label: 'Solver Exact' },
  { key: 'geometry_ready', label: 'Geometry Ready' },
  { key: 'review', label: 'Review Queue' },
  { key: 'proxy', label: 'Proxy' },
  { key: 'sparse', label: 'Sparse' },
  { key: 'sampled', label: 'Sampled' },
];

export const REAL_DRAWING_BROWSER_SORT_OPTIONS = [
  { key: 'priority', label: 'Priority' },
  { key: 'asset', label: 'Asset ID' },
  { key: 'segments', label: 'Segments' },
  { key: 'status', label: 'Status' },
];

export function normalizeViewerText(value) {
  const text = String(value ?? '').trim();
  return text || '';
}

export function normalizeViewerTextList(values) {
  const source = Array.isArray(values) ? values : String(values ?? '').split('|');
  const unique = [];
  source.forEach((value) => {
    const normalized = normalizeViewerText(value);
    if (normalized && !unique.includes(normalized)) unique.push(normalized);
  });
  return unique;
}

export function normalizeRealDrawingQualityFilter(filterKey = 'all') {
  const normalized = normalizeViewerText(filterKey) || 'all';
  return REAL_DRAWING_QUALITY_FILTERS.some((filter) => filter.key === normalized) ? normalized : 'all';
}

export function normalizeRealDrawingBrowserSort(sortKey = 'priority') {
  const normalized = normalizeViewerText(sortKey) || 'priority';
  return REAL_DRAWING_BROWSER_SORT_OPTIONS.some((option) => option.key === normalized) ? normalized : 'priority';
}

function defaultStorageGet(key) {
  try {
    return globalThis.localStorage?.getItem(key) ?? null;
  } catch (_err) {
    return null;
  }
}

function defaultStorageSet(key, value) {
  try {
    globalThis.localStorage?.setItem(key, value);
  } catch (_err) {
    // Ignore unavailable storage in local files, privacy mode, and tests.
  }
}

function resolveSearchString(search) {
  if (typeof search === 'string' && search) return search.startsWith('?') ? search : `?${search}`;
  try {
    return globalThis.location?.search || '';
  } catch (_err) {
    return '';
  }
}

export function readRealDrawingBrowserStateFromStorage({
  storageGet = defaultStorageGet,
  storageKey = REAL_DRAWING_BROWSER_STATE_KEY,
} = {}) {
  const raw = storageGet(storageKey);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (_err) {
    return {};
  }
}

export function readInitialRealDrawingBrowserState({
  search = '',
  storageGet = defaultStorageGet,
  storageKey = REAL_DRAWING_BROWSER_STATE_KEY,
} = {}) {
  const stored = readRealDrawingBrowserStateFromStorage({ storageGet, storageKey });
  const params = new URLSearchParams(resolveSearchString(search));
  return {
    filter: normalizeRealDrawingQualityFilter(params.get('drawing_filter') || stored.filter),
    query: normalizeViewerText(params.get('drawing_query') ?? stored.query),
    sort: normalizeRealDrawingBrowserSort(params.get('drawing_sort') || stored.sort),
    recentAssetRefs: normalizeViewerTextList(stored.recentAssetRefs || stored.recentAssets || []),
  };
}

export function buildRealDrawingBrowserStateSnapshot({
  filter = 'all',
  query = '',
  sort = 'priority',
  recentAssetRefs = [],
  updatedAt = new Date().toISOString(),
} = {}) {
  return {
    filter: normalizeRealDrawingQualityFilter(filter),
    query: normalizeViewerText(query),
    sort: normalizeRealDrawingBrowserSort(sort),
    recentAssetRefs: normalizeViewerTextList(recentAssetRefs).slice(0, 8),
    updated_at: updatedAt,
  };
}

export function persistRealDrawingBrowserState(
  state,
  {
    storageSet = defaultStorageSet,
    storageKey = REAL_DRAWING_BROWSER_STATE_KEY,
  } = {},
) {
  storageSet(storageKey, JSON.stringify(buildRealDrawingBrowserStateSnapshot(state)));
}

export function applyRealDrawingBrowserQueryParams(
  url,
  {
    filter = 'all',
    query = '',
    sort = 'priority',
  } = {},
  { assetRef = '' } = {},
) {
  if (!(url instanceof URL)) return url;
  const normalizedAssetRef = normalizeViewerText(assetRef);
  if (normalizedAssetRef) url.searchParams.set('drawing_asset', normalizedAssetRef);
  else url.searchParams.delete('drawing_asset');

  const normalizedFilter = normalizeRealDrawingQualityFilter(filter);
  if (normalizedFilter && normalizedFilter !== 'all') url.searchParams.set('drawing_filter', normalizedFilter);
  else url.searchParams.delete('drawing_filter');

  const normalizedQuery = normalizeViewerText(query);
  if (normalizedQuery) url.searchParams.set('drawing_query', normalizedQuery);
  else url.searchParams.delete('drawing_query');

  const normalizedSort = normalizeRealDrawingBrowserSort(sort);
  if (normalizedSort && normalizedSort !== 'priority') url.searchParams.set('drawing_sort', normalizedSort);
  else url.searchParams.delete('drawing_sort');
  return url;
}
