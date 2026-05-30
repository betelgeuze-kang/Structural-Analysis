function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeToken(value) {
  return normalizeText(value).toLowerCase();
}

function safeNumber(value, fallback = NaN) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export const DEFAULT_OPTIMIZATION_CHANGES_PATH =
  'implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json';

const SECTION_DIMENSION_PATTERN = /(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)/;

export function resolveBaselineArtifactPath(workspace = {}) {
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const variants = Array.isArray(drawing.variants) ? drawing.variants : [];
  const baselineVariant = variants.find((row) => row.variant === 'baseline');
  if (baselineVariant?.artifact_path) return baselineVariant.artifact_path;
  if (drawing.baseline_ref) {
    const byRef = variants.find((row) => normalizeToken(row.variant) === normalizeToken(drawing.baseline_ref));
    if (byRef?.artifact_path) return byRef.artifact_path;
  }
  const lineage = Array.isArray(drawing.lineage) ? drawing.lineage : [];
  const baselineLineage = lineage.find((row) => /baseline|source/i.test(normalizeText(row.stage || row.label)));
  if (baselineLineage?.path) return baselineLineage.path;
  return '';
}

export function resolveOptimizationChangesPath(workspace = {}) {
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const provenance = drawing.provenance && typeof drawing.provenance === 'object' ? drawing.provenance : {};
  const candidates = [
    drawing.changes_json_path,
    drawing.optimization_changes_path,
    provenance.changes_json_path,
    provenance.optimization_changes_path,
    DEFAULT_OPTIMIZATION_CHANGES_PATH,
  ];
  for (const candidate of candidates) {
    const path = normalizeText(candidate);
    if (path) return path;
  }
  return DEFAULT_OPTIMIZATION_CHANGES_PATH;
}

export function elementKey(element = {}) {
  return normalizeText(element.member_id || element.case_id || element.id);
}

export function buildElementSectionIndex(elements = []) {
  const index = new Map();
  for (const element of elements) {
    const key = elementKey(element);
    if (!key) continue;
    index.set(key, {
      sectionId: safeNumber(element.section_id, NaN),
      section: normalizeText(element.section || element.section_name),
      type: normalizeText(element.type),
    });
  }
  return index;
}

export function parseSectionAreaProxy(sectionLabel = '') {
  const text = normalizeText(sectionLabel);
  if (!text) return NaN;
  const match = text.match(SECTION_DIMENSION_PATTERN);
  if (!match) return NaN;
  const a = safeNumber(match[1]);
  const b = safeNumber(match[2]);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return NaN;
  return a * b;
}

export function inferSectionVisualScale(beforeSection = '', afterSection = '') {
  const beforeArea = parseSectionAreaProxy(beforeSection);
  const afterArea = parseSectionAreaProxy(afterSection);
  if (Number.isFinite(beforeArea) && Number.isFinite(afterArea) && beforeArea > 0 && afterArea > 0) {
    return Math.max(0.55, Math.min(1.45, Math.sqrt(afterArea / beforeArea)));
  }
  if (beforeSection && afterSection && beforeSection !== afterSection) {
    return afterSection.length < beforeSection.length ? 0.88 : 1.08;
  }
  return 1;
}

export function diffElementSections(baselineElements = [], optimizedElements = []) {
  const baselineIndex = buildElementSectionIndex(baselineElements);
  const optimizedIndex = buildElementSectionIndex(optimizedElements);
  const changed = [];
  const removed = [];
  const added = [];
  const visualByElementId = new Map();
  const toneByElementId = new Map();

  for (const [id, baselineRow] of baselineIndex.entries()) {
    const optimizedRow = optimizedIndex.get(id);
    if (!optimizedRow) {
      removed.push(id);
      toneByElementId.set(id, 'section_removed');
      continue;
    }
    const sameSectionId = Number.isFinite(baselineRow.sectionId)
      && Number.isFinite(optimizedRow.sectionId)
      && baselineRow.sectionId === optimizedRow.sectionId;
    const sameSectionLabel = baselineRow.section && optimizedRow.section && baselineRow.section === optimizedRow.section;
    if (sameSectionId || sameSectionLabel) continue;
    const scale = inferSectionVisualScale(baselineRow.section, optimizedRow.section);
    const tone = scale < 0.98 ? 'section_reduced' : scale > 1.02 ? 'section_increased' : 'changed';
    changed.push(id);
    visualByElementId.set(id, { scale, tone });
    toneByElementId.set(id, tone);
  }

  for (const id of optimizedIndex.keys()) {
    if (!baselineIndex.has(id)) added.push(id);
  }

  return {
    changed,
    removed,
    added,
    visualByElementId,
    toneByElementId,
    baselineCount: baselineIndex.size,
    optimizedCount: optimizedIndex.size,
  };
}

export function summarizeOptimizationChanges(changesPayload = {}) {
  const changes = Array.isArray(changesPayload?.changes) ? changesPayload.changes : [];
  const costDelta = changes.reduce((sum, row) => sum + safeNumber(row.cost_proxy_delta, 0), 0);
  const rebarActions = changes.filter((row) => normalizeText(row.action_family) === 'rebar').length;
  const sectionActions = changes.filter((row) => /section|merge|remove/i.test(normalizeText(row.action_name))).length;
  const maxDriftAfter = changes.reduce((max, row) => Math.max(max, safeNumber(row.drift_after_pct, max)), 0);
  return {
    changeCount: changes.length,
    costProxyDelta: costDelta,
    rebarActionCount: rebarActions,
    sectionActionCount: sectionActions,
    maxDriftAfterPct: maxDriftAfter,
    provenancePath: normalizeText(changesPayload?.source_path || changesPayload?.artifact_path || ''),
    generatedAt: normalizeText(changesPayload?.generated_at || ''),
  };
}

export function buildDrawingComparisonDeliveryRows({
  workspace = {},
  sectionDiff = {},
  changesSummary = {},
  comparison = null,
  memberComparison = null,
} = {}) {
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const rows = [
    {
      label: 'Baseline artifact',
      value: normalizeText(resolveBaselineArtifactPath(workspace)) || drawing.baseline_ref || '--',
      provenance: 'workspace variant baseline',
    },
    {
      label: 'Optimized artifact',
      value: normalizeText(drawing.artifact_path || workspace.artifactPath) || '--',
      provenance: 'workspace active variant',
    },
    {
      label: 'Optimization changes JSON',
      value: resolveOptimizationChangesPath(workspace),
      provenance: 'design_optimization_cost_reduction_changes.json',
    },
    {
      label: 'Section-id diff (3D)',
      value: `${sectionDiff.changed?.length || 0} changed | ${sectionDiff.removed?.length || 0} removed | ${sectionDiff.added?.length || 0} added`,
      provenance: 'element id alignment contract',
    },
    {
      label: 'Optimization actions',
      value: String(changesSummary.changeCount ?? '--'),
      provenance: changesSummary.generatedAt || 'changes payload',
    },
    {
      label: 'Cost proxy delta (sum)',
      value: Number.isFinite(changesSummary.costProxyDelta)
        ? changesSummary.costProxyDelta.toFixed(1)
        : '--',
      provenance: 'changes.cost_proxy_delta',
    },
    {
      label: 'Max drift after (changes)',
      value: Number.isFinite(changesSummary.maxDriftAfterPct)
        ? `${changesSummary.maxDriftAfterPct.toFixed(3)}%`
        : '--',
      provenance: 'changes.drift_after_pct',
    },
    {
      label: 'Member comparison filter',
      value: normalizeText(memberComparison?.filter) || '--',
      provenance: 'viewer overlay',
    },
    {
      label: 'Manifest comparison headline',
      value: normalizeText(comparison?.headline) || '--',
      provenance: normalizeText(comparison?.verification?.source) || 'optimization_summary',
    },
  ];
  return rows;
}

export function mergeMemberAlignmentIntoSectionDiff(sectionDiff = {}, changesPayload = null) {
  const alignment = changesPayload?.member_alignment;
  if (!alignment || typeof alignment !== 'object') {
    return sectionDiff;
  }
  const removedSet = new Set(
    [
      ...(Array.isArray(sectionDiff?.removed) ? sectionDiff.removed : []),
      ...(Array.isArray(alignment.removed_member_ids) ? alignment.removed_member_ids : []),
    ].map((id) => normalizeText(id)).filter(Boolean),
  );
  const addedSet = new Set(
    [
      ...(Array.isArray(sectionDiff?.added) ? sectionDiff.added : []),
      ...(Array.isArray(alignment.added_member_ids) ? alignment.added_member_ids : []),
    ].map((id) => normalizeText(id)).filter(Boolean),
  );
  return {
    ...sectionDiff,
    removed: [...removedSet],
    added: [...addedSet],
    memberAlignment: alignment,
    groupMergeCount: safeNumber(alignment.group_merge_count, 0),
  };
}

export function buildDrawingComparisonRemovedSummary(sectionDiff = {}, changesPayload = null) {
  const merged = mergeMemberAlignmentIntoSectionDiff(sectionDiff, changesPayload);
  const removed = Array.isArray(merged?.removed) ? merged.removed : [];
  const added = Array.isArray(merged?.added) ? merged.added : [];
  return {
    removedCount: removed.length,
    addedCount: added.length,
    removedMemberIds: removed.map((id) => normalizeText(id)).filter(Boolean),
    addedMemberIds: added.map((id) => normalizeText(id)).filter(Boolean),
    groupMergeCount: safeNumber(merged?.groupMergeCount, 0),
  };
}

export function buildDrawingComparisonState({
  workspace = {},
  optimizedData = {},
  baselineData = null,
  changesPayload = null,
} = {}) {
  const variant = normalizeToken(workspace?.variant)
    || normalizeToken(workspace?.urlVariant);
  const enabled = variant === 'compare';
  const sectionDiff = baselineData
    ? diffElementSections(baselineData.elements || [], optimizedData.elements || [])
    : {
      changed: [],
      removed: [],
      added: [],
      visualByElementId: new Map(),
      toneByElementId: new Map(),
      baselineCount: 0,
      optimizedCount: Array.isArray(optimizedData?.elements) ? optimizedData.elements.length : 0,
    };
  const mergedSectionDiff = mergeMemberAlignmentIntoSectionDiff(sectionDiff, changesPayload);
  const changesSummary = summarizeOptimizationChanges(changesPayload || {});
  return {
    enabled,
    variant,
    baselineArtifactPath: resolveBaselineArtifactPath(workspace),
    changesPath: resolveOptimizationChangesPath(workspace),
    sectionDiff: mergedSectionDiff,
    changesSummary,
    baselineLoaded: Boolean(baselineData),
    memberAlignment: mergedSectionDiff.memberAlignment || null,
  };
}
