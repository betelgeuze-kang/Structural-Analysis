function normalizePanelText(value) {
  const text = String(value ?? '').trim();
  return text || '';
}

function safePanelNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function classifyLoadCaseKind(label) {
  const text = normalizePanelText(label).toLowerCase();
  if (!text) return 'Load';
  if (text.includes('push')) return 'Pushover';
  if (text.includes('wind')) return 'Wind';
  if (text.includes('seis') || text.includes('quake') || text.includes('eq')) return 'Seismic';
  if (text.includes('dead') || text.includes('live') || text.includes('grav')) return 'Gravity';
  if (text.includes('comb') || text.startsWith('lcb') || text.startsWith('lc-')) return 'Combo';
  if (/^s\d+/i.test(text)) return 'Story';
  return 'Load';
}

function buildLoadCaseEvidence(label, index, {
  active = '',
  governing = '',
  activeStep = 1,
  totalSteps = 1,
  explicitInventory = false,
  pinnedSelection = false,
} = {}) {
  const selected = label === active;
  const isGoverning = label === governing;
  const resolvedTotalSteps = Math.max(1, Math.round(safePanelNumber(totalSteps, 1)));
  const resolvedActiveStep = Math.min(
    resolvedTotalSteps,
    Math.max(1, Math.round(safePanelNumber(activeStep, resolvedTotalSteps))),
  );
  const progressPct = selected || isGoverning
    ? Math.round((resolvedActiveStep / resolvedTotalSteps) * 100)
    : 100;
  const statusLabel = pinnedSelection
    ? 'Pinned selection'
    : isGoverning
      ? 'Governing'
      : selected
        ? 'Selected'
        : 'Available';
  return {
    label,
    selected,
    kind: classifyLoadCaseKind(label),
    statusLabel,
    stepLabel: selected || isGoverning ? `Step ${resolvedActiveStep}/${resolvedTotalSteps}` : 'Ready',
    sourceLabel: pinnedSelection
      ? 'Shared selection'
      : explicitInventory
        ? 'Load inventory'
        : 'Story slice fallback',
    progressPct,
    ordinal: index + 1,
  };
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
  const governing = normalizePanelText(data?.meta?.governing_load_case || data?.meta?.active_load_case);
  const activeStep = safePanelNumber(data?.meta?.active_step, 1);
  const totalSteps = safePanelNumber(data?.meta?.total_steps, 1);
  const labels = (explicitLoadCases.length ? explicitLoadCases : storySlices)
    .map(normalizePanelText)
    .filter(Boolean)
    .slice(0, limit);
  const active = normalizePanelText(activeLoadCase) || governing || labels[0] || '';
  const hasPinnedSelection = Boolean(active && !labels.includes(active));
  const inventory = hasPinnedSelection ? [active, ...labels] : labels;
  const sourceLabel = normalizePanelText(data?.meta?.source_label) || 'Artifact-driven view';
  const comparison = normalizePanelText(data?.meta?.comparison_availability);
  return {
    activeLoadCase: active,
    items: inventory.map((label, index) => buildLoadCaseEvidence(label, index, {
      active,
      governing,
      activeStep,
      totalSteps,
      explicitInventory: Boolean(explicitLoadCases.length),
      pinnedSelection: hasPinnedSelection && index === 0,
    })),
    emptyText: comparison ? `${sourceLabel} | ${comparison}` : sourceLabel,
  };
}
