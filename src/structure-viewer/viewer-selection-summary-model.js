import {
  normalizeSelectionValue,
} from './viewer-shared-selection-state.js';

export function buildElementSelectionKey(data = {}, {
  resolveMemberId = (row) => normalizeSelectionValue(row?.member_id || row?.case_id || row?.id),
} = {}) {
  return `${resolveMemberId(data) || ''}::${normalizeSelectionValue(data?.id)}`;
}

export function buildSelectionSetSummary(records = [], selectedKeys = new Set(), {
  limit = 4,
  resolveMemberId = (row) => normalizeSelectionValue(row?.member_id || row?.case_id || row?.id),
  resolveSummaryLabel = (row) => normalizeSelectionValue(row?.member_id) || `#${normalizeSelectionValue(row?.id)}`,
  buildSelectionKey = buildElementSelectionKey,
} = {}) {
  const keySet = selectedKeys instanceof Set ? selectedKeys : new Set(Array.isArray(selectedKeys) ? selectedKeys : []);
  const labels = (Array.isArray(records) ? records : [])
    .filter((item) => item && keySet.has(buildSelectionKey(item, { resolveMemberId })))
    .map((item) => resolveSummaryLabel(item))
    .filter(Boolean);
  const unique = [...new Set(labels)];
  if (!unique.length) return '--';
  const maxItems = Math.max(0, Math.floor(Number.isFinite(Number(limit)) ? Number(limit) : 4));
  const head = unique.slice(0, maxItems).join(', ');
  return unique.length > maxItems ? `${head} +${unique.length - maxItems}` : head;
}

export function buildClearSelectionButtonModel(selectedCount = 0) {
  const count = Math.max(0, Math.floor(Number(selectedCount) || 0));
  return {
    visible: count > 0,
    display: count > 0 ? 'inline-flex' : 'none',
    text: count > 1 ? `Clear Selection (${count})` : 'Clear Selection',
  };
}
