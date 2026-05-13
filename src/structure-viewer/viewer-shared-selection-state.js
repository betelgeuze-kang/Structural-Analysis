export const SHARED_SELECTION_KEY = 'structural-viewer-selection-v1';

export function normalizeSelectionValue(value) {
  const text = String(value ?? '').trim();
  return text || '';
}

export function normalizeSelectionValues(values) {
  const source = Array.isArray(values) ? values : String(values ?? '').split('|');
  const unique = [];
  source.forEach((value) => {
    const normalized = normalizeSelectionValue(value);
    if (normalized && !unique.includes(normalized)) unique.push(normalized);
  });
  return unique;
}

function defaultStorageGet(key) {
  try {
    return globalThis.localStorage?.getItem(key) ?? null;
  } catch (_err) {
    return null;
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

export function readStoredSharedSelection({
  storageGet = defaultStorageGet,
  storageKey = SHARED_SELECTION_KEY,
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

export function readSharedSelectionState({
  search = '',
  storageGet = defaultStorageGet,
  storageKey = SHARED_SELECTION_KEY,
} = {}) {
  const params = new URLSearchParams(resolveSearchString(search));
  const queryMember = normalizeSelectionValue(
    params.get('drawing_asset')
      || params.get('asset_ref')
      || params.get('member')
      || params.get('member_id')
      || params.get('focus_member')
      || params.get('case_id')
      || params.get('focus'),
  );
  const queryMemberIds = normalizeSelectionValues(params.get('member_set') || '');
  const queryLoadCase = normalizeSelectionValue(
    params.get('load_case') || params.get('loadcase') || params.get('combination'),
  );
  const stored = readStoredSharedSelection({ storageGet, storageKey });
  const storedMemberIds = normalizeSelectionValues(
    stored.memberIds || stored.memberSet || stored.member_ids || [],
  );
  const memberIds = queryMemberIds.length
    ? queryMemberIds
    : (queryMember ? normalizeSelectionValues([queryMember, ...storedMemberIds]) : storedMemberIds);
  const memberId = queryMember
    || memberIds[0]
    || normalizeSelectionValue(stored.memberId)
    || normalizeSelectionValue(stored.focusMember);
  return {
    memberId,
    memberIds,
    selectionSetCount: memberIds.length,
    loadCase: queryLoadCase || normalizeSelectionValue(stored.loadCase),
    updatedAt: normalizeSelectionValue(stored.updated_at),
  };
}

export function buildSharedSelectionPayload(
  selection,
  {
    source = 'interactive3d',
    viewerFamily = 'interactive_3d_viewer',
    updatedAt = new Date().toISOString(),
  } = {},
) {
  const memberIds = normalizeSelectionValues(selection?.memberIds || selection?.memberId || []);
  const primaryMember = normalizeSelectionValue(selection?.memberId) || memberIds[0] || '';
  return {
    memberId: primaryMember,
    memberIds,
    memberSet: memberIds,
    selectionSetCount: memberIds.length,
    focusMember: primaryMember,
    loadCase: normalizeSelectionValue(selection?.loadCase),
    source,
    viewerFamily,
    updated_at: updatedAt,
  };
}

export function applySharedSelectionQueryParams(url, selection = {}) {
  if (!(url instanceof URL)) return url;
  const memberId = normalizeSelectionValue(selection.memberId);
  if (memberId) url.searchParams.set('member', memberId);
  else url.searchParams.delete('member');

  const memberIds = normalizeSelectionValues(selection.memberIds || []);
  if (memberIds.length) url.searchParams.set('member_set', memberIds.join('|'));
  else url.searchParams.delete('member_set');

  const loadCase = normalizeSelectionValue(selection.loadCase);
  if (loadCase) url.searchParams.set('load_case', loadCase);
  else url.searchParams.delete('load_case');
  return url;
}
