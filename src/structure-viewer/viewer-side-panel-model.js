function normalizePanelText(value) {
  const text = String(value ?? '').trim();
  return text || '';
}

export function buildLayerToggleItems(types = {}) {
  return Object.keys(types || {}).map((type) => ({
    type,
    label: type,
    checked: true,
  }));
}

export function buildLoadCaseListModel(data = {}, {
  activeLoadCase = '',
  maxItems = 24,
} = {}) {
  const storySlices = Array.isArray(data?.meta?.story_slices) ? data.meta.story_slices : [];
  const explicitLoadCases = Array.isArray(data?.meta?.load_case_inventory) ? data.meta.load_case_inventory : [];
  const limit = Math.max(0, Math.floor(Number.isFinite(Number(maxItems)) ? Number(maxItems) : 24));
  const active = normalizePanelText(activeLoadCase);
  const labels = (explicitLoadCases.length ? explicitLoadCases : storySlices)
    .map(normalizePanelText)
    .filter(Boolean)
    .slice(0, limit);
  const inventory = active && !labels.includes(active) ? [active, ...labels] : labels;
  const sourceLabel = normalizePanelText(data?.meta?.source_label) || 'Artifact-driven view';
  const comparison = normalizePanelText(data?.meta?.comparison_availability);
  return {
    activeLoadCase: active,
    items: inventory.map((label) => ({
      label,
      selected: label === active,
    })),
    emptyText: comparison ? `${sourceLabel} | ${comparison}` : sourceLabel,
  };
}
