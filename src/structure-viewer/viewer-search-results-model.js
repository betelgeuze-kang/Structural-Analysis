import {
  normalizeSelectionValue,
} from './viewer-shared-selection-state.js';

export function getViewerSearchTokens(query = '') {
  return normalizeSelectionValue(query).toLowerCase().split(/\s+/).filter(Boolean);
}

export function viewerElementMatchesSearchQuery(element = {}, query = '', {
  resolveEffectiveSectionValue = (row) => normalizeSelectionValue(row?.section) || '--',
} = {}) {
  const tokens = getViewerSearchTokens(query);
  if (!tokens.length) return true;
  const haystack = [
    resolveEffectiveSectionValue(element),
    element?.member_id,
    element?.id,
    element?.section,
    element?.section_family,
    element?.section_shape,
    element?.group_label,
    ...(Array.isArray(element?.group_names) ? element.group_names : []),
    element?.review_case_id,
    element?.review_row_label,
    element?.review_summary_label,
    element?.story_band_label,
    element?.zone_label,
  ].map((value) => String(value || '').toLowerCase()).join(' | ');
  return tokens.every((token) => haystack.includes(token));
}

export function resolveViewerSearchMatches(elements = [], query = '', {
  limit = 12,
  resolveMemberId = (row) => normalizeSelectionValue(row?.member_id || row?.case_id || row?.id),
  resolveEffectiveSectionValue = (row) => normalizeSelectionValue(row?.section) || '--',
} = {}) {
  const seen = new Set();
  const maxItems = Math.max(0, Math.floor(Number.isFinite(Number(limit)) ? Number(limit) : 12));
  return (Array.isArray(elements) ? elements : [])
    .filter((element) => viewerElementMatchesSearchQuery(element, query, { resolveEffectiveSectionValue }))
    .filter((element) => {
      const memberId = resolveMemberId(element);
      if (!memberId || seen.has(memberId)) return false;
      seen.add(memberId);
      return true;
    })
    .slice(0, maxItems);
}

export function buildViewerSearchResultsModel(data = {}, {
  query = '',
  limit = 10,
  selectedMemberId = '',
  activeIsolation = {},
  resolveMemberId = (row) => normalizeSelectionValue(row?.member_id || row?.case_id || row?.id),
  resolveEffectiveSectionValue = (row) => normalizeSelectionValue(row?.section) || '--',
  hasAppliedSectionOverride = () => false,
} = {}) {
  const elements = Array.isArray(data?.elements) ? data.elements : [];
  const normalizedQuery = normalizeSelectionValue(query);
  if (!Array.isArray(data?.elements)) {
    return {
      statusText: 'Search unavailable',
      items: [],
      emptyHtml: '',
      unavailable: true,
    };
  }
  if (!normalizedQuery) {
    const memberCount = new Set(elements.map((element) => resolveMemberId(element)).filter(Boolean)).size;
    return {
      statusText: `Search ready | members ${memberCount}`,
      items: [],
      emptyHtml: '',
      ready: true,
    };
  }
  const matches = resolveViewerSearchMatches(elements, normalizedQuery, {
    limit,
    resolveMemberId,
    resolveEffectiveSectionValue,
  });
  const maxItems = Math.max(0, Math.floor(Number.isFinite(Number(limit)) ? Number(limit) : 10));
  return {
    statusText: `"${normalizedQuery}" | matches ${matches.length}${matches.length === maxItems ? '+' : ''}`,
    items: matches.map((match) => {
      const memberId = resolveMemberId(match);
      const memberLabel = hasAppliedSectionOverride(match)
        ? resolveEffectiveSectionValue(match)
        : normalizeSelectionValue(match?.section_family || match?.section || match?.type || 'member');
      return {
        memberId,
        memberLabel,
        selected: normalizeSelectionValue(selectedMemberId) === memberId,
        isolateActive: activeIsolation?.kind === 'member' && activeIsolation?.value === memberId,
      };
    }),
    emptyHtml: '<div class="search-status">No matches</div>',
  };
}
