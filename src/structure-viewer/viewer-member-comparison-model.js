function normalizeText(value) {
  return String(value ?? '').trim();
}

function safeNumber(value, fallback = NaN) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const sign = number > 0 ? '+' : '';
  return `${sign}${number.toFixed(1)}%`;
}

function memberId(element = {}) {
  return normalizeText(element.member_id || element.case_id || element.id);
}

function sectionBefore(element = {}) {
  return normalizeText(element.before_section || element.original_section || element.section_before);
}

function sectionAfter(element = {}) {
  return normalizeText(element.after_section || element.optimized_section || element.section_after || element.section || element.section_name);
}

function classifyMemberComparison(element = {}) {
  const before = sectionBefore(element);
  const after = sectionAfter(element);
  const dcrBefore = safeNumber(element.max_dcr_before, safeNumber(element.dcr_before));
  const dcrAfter = safeNumber(element.max_dcr_after, safeNumber(element.dcr_after, safeNumber(element.dcr)));
  const weightDelta = safeNumber(element.weight_delta_pct, safeNumber(element.weight_reduction_pct));
  const action = normalizeText(element.action_name || element.optimization_meaning_label || element.status).toLowerCase();
  const categories = [];
  if (before && after && before !== after) categories.push('changed');
  if (before && after && before === after) categories.push('retained');
  if (Number.isFinite(weightDelta) && weightDelta < 0) categories.push('reduced');
  if (action.includes('reduc') || action.includes('remove') || action.includes('delete')) categories.push('reduced');
  if (Number.isFinite(dcrAfter) && (dcrAfter > 1 || (Number.isFinite(dcrBefore) && dcrAfter > dcrBefore))) categories.push('risk_up');
  if (!before && !Number.isFinite(weightDelta) && !Number.isFinite(dcrAfter)) categories.push('missing_evidence');
  if (!categories.length) categories.push('retained');
  return [...new Set(categories)];
}

function buildItem(element = {}) {
  const categories = classifyMemberComparison(element);
  const before = sectionBefore(element) || '--';
  const after = sectionAfter(element) || '--';
  const dcrBefore = safeNumber(element.max_dcr_before, safeNumber(element.dcr_before));
  const dcrAfter = safeNumber(element.max_dcr_after, safeNumber(element.dcr_after, safeNumber(element.dcr)));
  const weightDelta = safeNumber(element.weight_delta_pct, safeNumber(element.cost_delta_pct, safeNumber(element.weight_reduction_pct)));
  return {
    id: memberId(element) || '--',
    label: normalizeText(element.label || element.name || memberId(element)) || '--',
    before,
    after,
    delta: before !== '--' && after !== '--' ? `${before} -> ${after}` : normalizeText(element.action_name || element.optimization_meaning_label) || '--',
    dcr: Number.isFinite(dcrAfter) ? dcrAfter.toFixed(3) : '--',
    dcrDelta: Number.isFinite(dcrAfter) && Number.isFinite(dcrBefore) ? (dcrAfter - dcrBefore).toFixed(3) : '--',
    weightCost: Number.isFinite(weightDelta) ? formatPercent(weightDelta) : '--',
    categories,
    evidence: before !== '--' || after !== '--' || Number.isFinite(weightDelta) ? 'exact source' : 'missing evidence',
    tone: categories.includes('risk_up') ? 'danger' : categories.includes('changed') || categories.includes('reduced') ? 'accent' : categories.includes('missing_evidence') ? 'warn' : 'success',
  };
}

function buildManifestProxyItem(summary = {}) {
  const baseline = safeNumber(summary.baseline_member_count);
  const optimized = safeNumber(summary.optimized_member_count);
  if (!Number.isFinite(baseline) || !Number.isFinite(optimized)) return null;
  const delta = optimized - baseline;
  const pct = baseline > 0 ? (delta / baseline) * 100 : NaN;
  return {
    id: 'manifest_member_delta',
    label: 'Manifest member count delta',
    before: Math.round(baseline).toLocaleString('en-US'),
    after: Math.round(optimized).toLocaleString('en-US'),
    delta: `${Math.round(baseline).toLocaleString('en-US')} -> ${Math.round(optimized).toLocaleString('en-US')}`,
    dcr: '--',
    dcrDelta: '--',
    weightCost: formatPercent(pct),
    categories: delta < 0 ? ['reduced'] : ['retained'],
    evidence: normalizeText(summary.evidence_level) || 'derived proxy',
    tone: delta < 0 ? 'success' : 'accent',
  };
}

export function buildMemberComparisonModel({
  data = {},
  workspace = {},
  filter = 'changed',
  limit = 25,
  highlightLimit = 200,
} = {}) {
  const elements = Array.isArray(data?.elements) ? data.elements : [];
  const summary = workspace?.drawing?.optimization_summary && typeof workspace.drawing.optimization_summary === 'object'
    ? workspace.drawing.optimization_summary
    : data?.meta?.optimization_summary && typeof data.meta.optimization_summary === 'object'
      ? data.meta.optimization_summary
      : {};
  const items = elements.map(buildItem);
  const proxy = buildManifestProxyItem(summary);
  const allItems = proxy ? [proxy, ...items] : items;
  const normalizedFilter = normalizeText(filter) || 'changed';
  const filterOptions = ['changed', 'reduced', 'retained', 'risk_up', 'missing_evidence'].map((key) => ({
    key,
    label: key.replaceAll('_', ' '),
    count: allItems.filter((item) => item.categories.includes(key)).length,
  }));
  const activeAllItems = allItems.filter((item) => item.categories.includes(normalizedFilter));
  const activeItems = activeAllItems.slice(0, limit);
  const highlightItems = activeAllItems
    .filter((item) => item.id && item.id !== 'manifest_member_delta')
    .slice(0, highlightLimit);
  const changedCount = filterOptions.find((option) => option.key === 'changed')?.count || 0;
  const reducedCount = filterOptions.find((option) => option.key === 'reduced')?.count || 0;
  const riskCount = filterOptions.find((option) => option.key === 'risk_up')?.count || 0;
  return {
    filter: normalizedFilter,
    filterOptions,
    items: activeItems,
    highlightMemberIds: highlightItems.map((item) => item.id),
    highlightToneByMemberId: Object.fromEntries(highlightItems.map((item) => [item.id, item.tone])),
    highlightCount: highlightItems.length,
    highlightLimit,
    summaryRows: [
      { label: 'Section changes', value: String(changedCount), evidence: changedCount ? 'exact source' : 'derived proxy', tone: changedCount ? 'accent' : 'neutral' },
      { label: 'Member reduction', value: String(reducedCount), evidence: proxy ? proxy.evidence : 'exact source', tone: reducedCount ? 'success' : 'neutral' },
      { label: 'Risk-up candidates', value: String(riskCount), evidence: riskCount ? 'derived proxy' : 'exact source', tone: riskCount ? 'danger' : 'success' },
      { label: 'Active filter rows', value: String(activeItems.length), evidence: 'viewer model', tone: activeItems.length ? 'accent' : 'warn' },
    ],
    emptyText: `No members match ${normalizedFilter.replaceAll('_', ' ')}.`,
  };
}
