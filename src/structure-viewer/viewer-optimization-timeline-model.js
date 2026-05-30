function normalizeText(value) {
  return String(value ?? '').trim();
}

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function classifyOptimizationChangeStage(row = {}) {
  const family = normalizeText(row.action_family).toLowerCase();
  const action = normalizeText(row.action_name).toLowerCase();
  const combined = `${family} ${action}`;
  if (/merge|simplif|detailing|connection|perimeter_frame/.test(combined)) return 'stage_c';
  if (/up|reinfor|thick|strengthen|add/.test(combined)) return 'stage_a';
  if (/down|reduc|remove|shrink|section/.test(combined)) return 'stage_b';
  return 'stage_b';
}

export function buildOptimizationTimelineModel(changesPayload = {}) {
  const changes = Array.isArray(changesPayload?.changes) ? changesPayload.changes : [];
  const steps = [{
    index: -1,
    key: 'baseline',
    label: 'Baseline (before changes)',
    stage: 'baseline',
    cumulativeCostDelta: 0,
    cumulativeCostProxyAfter: 0,
    changeCount: 0,
    maxGoverningDcrAfter: safeNumber(changes[0]?.governing_member_governing_dcr_before, 0),
    driftAfterPct: safeNumber(changes[0]?.drift_before_pct, NaN),
  }];
  let cumulativeDelta = 0;
  changes.forEach((row, index) => {
    cumulativeDelta += safeNumber(row.cost_proxy_delta, 0);
    const stage = classifyOptimizationChangeStage(row);
    steps.push({
      index,
      key: `change-${index}`,
      label: normalizeText(row.action_name) || normalizeText(row.group_id) || `Change ${index + 1}`,
      stage,
      groupId: normalizeText(row.group_id),
      actionFamily: normalizeText(row.action_family),
      cumulativeCostDelta: cumulativeDelta,
      cumulativeCostProxyAfter: safeNumber(row.cost_proxy_after, 0),
      changeCount: index + 1,
      maxGoverningDcrAfter: safeNumber(row.governing_member_governing_dcr_after, 0),
      driftAfterPct: safeNumber(row.drift_after_pct, NaN),
      costProxyDelta: safeNumber(row.cost_proxy_delta, 0),
      change: row,
    });
  });
  const stageSummary = ['stage_a', 'stage_b', 'stage_c'].map((stageKey) => ({
    key: stageKey,
    label: stageKey === 'stage_a' ? 'Stage A · reinforce' : stageKey === 'stage_b' ? 'Stage B · reduce' : 'Stage C · simplify',
    count: changes.filter((row) => classifyOptimizationChangeStage(row) === stageKey).length,
  }));
  return {
    schemaVersion: 'structure-viewer-optimization-timeline.v1',
    status: changes.length ? 'ready' : 'missing',
    changeCount: changes.length,
    steps,
    stageSummary,
    provenancePath: normalizeText(changesPayload?.source_path || changesPayload?.artifact_path || ''),
  };
}

export function resolveOptimizationTimelineStep(model = {}, stepIndex = -1) {
  const steps = Array.isArray(model.steps) ? model.steps : [];
  const index = Math.max(-1, Math.min(steps.length - 1, Math.round(safeNumber(stepIndex, -1))));
  return steps.find((step) => step.index === index) || steps[0] || null;
}

export function parseOptimizationGroupId(groupId = '') {
  const parts = normalizeText(groupId).split(':');
  const storyToken = parts[0] || '';
  const storyMatch = storyToken.match(/^S(\d+)$/i);
  return {
    storyBand: storyMatch ? safeNumber(storyMatch[1], NaN) : NaN,
    zoneLabel: normalizeText(parts[1]).toLowerCase(),
    memberType: normalizeText(parts[3] || parts[2]).toLowerCase(),
    raw: normalizeText(groupId),
  };
}

function elementMemberId(element = {}) {
  return normalizeText(element.member_id || element.case_id || element.id);
}

function normalizeMemberTypeToken(type = '') {
  const token = normalizeText(type).toLowerCase();
  if (token.includes('wall')) return 'wall';
  if (token.includes('slab')) return 'slab';
  if (token.includes('beam')) return 'beam';
  if (token.includes('column')) return 'column';
  return token;
}

function memberTypeMatches(elementType = '', targetType = '') {
  const elementToken = normalizeMemberTypeToken(elementType);
  const targetToken = normalizeMemberTypeToken(targetType);
  if (!targetToken) return true;
  if (!elementToken) return false;
  return elementToken === targetToken || elementToken.includes(targetToken) || targetToken.includes(elementToken);
}

function resolveStoryBandForIndex(storyBands = [], storyBandIndex = NaN) {
  if (!Number.isFinite(storyBandIndex) || storyBandIndex < 1) return null;
  const bands = Array.isArray(storyBands) ? storyBands : [];
  if (!bands.length) return null;
  const index = Math.min(bands.length - 1, Math.max(0, Math.round(storyBandIndex) - 1));
  return bands[index] || null;
}

function averageElementZ(element = {}, nodeMap = new Map()) {
  const nodeIds = Array.isArray(element?.node_ids) ? element.node_ids : [];
  const zValues = nodeIds
    .map((id) => safeNumber(nodeMap.get(String(id))?.z, NaN))
    .filter(Number.isFinite);
  if (!zValues.length) return NaN;
  return zValues.reduce((sum, value) => sum + value, 0) / zValues.length;
}

function elementMatchesOptimizationChange(element = {}, changeRow = {}, storyBands = [], nodeMap = new Map()) {
  const parsed = parseOptimizationGroupId(changeRow?.group_id);
  if (parsed.memberType && !memberTypeMatches(element?.type || element?.member_type, parsed.memberType)) {
    return false;
  }
  if (parsed.zoneLabel && parsed.zoneLabel !== 'nogroup') {
    const zone = normalizeText(element?.zone_label || element?.zone).toLowerCase();
    if (zone && zone !== parsed.zoneLabel && !zone.includes(parsed.zoneLabel) && !parsed.zoneLabel.includes(zone)) {
      return false;
    }
  }
  const band = resolveStoryBandForIndex(storyBands, parsed.storyBand);
  if (band) {
    const z = averageElementZ(element, nodeMap);
    if (Number.isFinite(z)) {
      return z >= band.zMin - 0.05 && z <= band.zMax + 0.05;
    }
  }
  return Boolean(parsed.raw);
}

export function buildTimelineStepHighlights({
  stepIndex = -1,
  changesPayload = {},
  elements = [],
  nodes = [],
  storyBands = [],
  sectionChangedIds = [],
  highlightLimit = 400,
} = {}) {
  const idx = Math.round(safeNumber(stepIndex, -1));
  if (idx < 0) {
    return {
      memberIds: [],
      toneByMemberId: {},
      storyClipLabel: '',
      matchCount: 0,
      changeRows: [],
    };
  }
  const changes = Array.isArray(changesPayload?.changes) ? changesPayload.changes : [];
  const cumulative = changes.slice(0, idx + 1);
  const nodeMap = new Map((Array.isArray(nodes) ? nodes : []).map((node) => [String(node.id), node]));
  const memberIds = new Set();
  const toneByMemberId = {};
  const sectionChanged = new Set(
    (Array.isArray(sectionChangedIds) ? sectionChangedIds : []).map((id) => normalizeText(id)).filter(Boolean),
  );
  const latestChange = cumulative[cumulative.length - 1] || null;
  const latestParsed = parseOptimizationGroupId(latestChange?.group_id);
  const latestBand = resolveStoryBandForIndex(storyBands, latestParsed.storyBand);

  for (const element of Array.isArray(elements) ? elements : []) {
    if (memberIds.size >= highlightLimit) break;
    const memberId = elementMemberId(element);
    if (!memberId) continue;
    const matched = cumulative.some((row) => elementMatchesOptimizationChange(element, row, storyBands, nodeMap));
    const sectionMatch = sectionChanged.has(memberId)
      && latestBand
      && (() => {
        const z = averageElementZ(element, nodeMap);
        return Number.isFinite(z) && z >= latestBand.zMin - 0.05 && z <= latestBand.zMax + 0.05;
      })();
    if (!matched && !sectionMatch) continue;
    memberIds.add(memberId);
    toneByMemberId[memberId] = sectionMatch ? 'section_reduced' : 'changed';
  }

  return {
    memberIds: [...memberIds],
    toneByMemberId,
    storyClipLabel: normalizeText(latestBand?.label),
    matchCount: memberIds.size,
    changeRows: cumulative,
  };
}

export function resolveFirstTimelineStepIndexForStage(model = {}, stageKey = '') {
  const stage = normalizeText(stageKey);
  if (!stage) return -1;
  const steps = Array.isArray(model.steps) ? model.steps : [];
  const match = steps.find((step) => step.index >= 0 && step.stage === stage);
  return match?.index ?? -1;
}

export function resolveTimelineStepIndexForMember(
  memberId = '',
  {
    changesPayload = {},
    elements = [],
    nodes = [],
    storyBands = [],
    sectionChangedIds = [],
  } = {},
) {
  const normalizedMemberId = normalizeText(memberId);
  if (!normalizedMemberId) return -1;
  const changes = Array.isArray(changesPayload?.changes) ? changesPayload.changes : [];
  for (let index = 0; index < changes.length; index += 1) {
    const highlight = buildTimelineStepHighlights({
      stepIndex: index,
      changesPayload,
      elements,
      nodes,
      storyBands,
      sectionChangedIds,
    });
    if (highlight.memberIds.includes(normalizedMemberId)) return index;
  }
  return -1;
}

export function resolveTimelineStepIndexForDeltaKey(deltaKey = '', changesPayload = {}) {
  const key = normalizeText(deltaKey).toLowerCase();
  const changes = Array.isArray(changesPayload?.changes) ? changesPayload.changes : [];
  if (!changes.length || !key || key === 'manifest_member_delta') return -1;
  if (key === 'cost' || key === 'co2') return changes.length - 1;

  const scoreChange = (row, pattern) => {
    const family = normalizeText(row.action_family).toLowerCase();
    const action = normalizeText(row.action_name).toLowerCase();
    const memberType = normalizeText(row.member_type).toLowerCase();
    const combined = `${family} ${action} ${memberType}`;
    return pattern.test(combined) ? Math.abs(safeNumber(row.cost_proxy_delta, 0)) : 0;
  };

  let bestIndex = -1;
  let bestScore = 0;
  const pattern = key === 'steel'
    ? /rebar|beam|steel|section/
    : key === 'concrete'
      ? /slab|wall|thickness|concrete/
      : null;

  if (pattern) {
    changes.forEach((row, index) => {
      const score = scoreChange(row, pattern);
      if (score > bestScore) {
        bestScore = score;
        bestIndex = index;
      }
    });
    if (bestIndex >= 0) return bestIndex;
  }

  const tileMatch = key.match(/^delta-(\d+)$/);
  if (tileMatch) {
    const tileIndex = Math.max(0, Math.round(safeNumber(tileMatch[1], 1)) - 1);
    return Math.min(changes.length - 1, Math.floor((tileIndex / 4) * changes.length));
  }

  return changes.length - 1;
}

export function buildOptimizationTimelineDeliveryRows(model = {}, step = null, shareUrl = '') {
  if (model?.status !== 'ready') return [];
  const activeStep = step || resolveOptimizationTimelineStep(model, (model.changeCount || 1) - 1);
  const stageBreakdown = (model.stageSummary || [])
    .map((row) => `${row.key}=${row.count}`)
    .join(', ');
  return [
    {
      label: 'Timeline snapshot label',
      value: normalizeText(activeStep?.label) || 'Baseline',
      provenance: 'viewer optimization timeline scrubber',
    },
    {
      label: 'Timeline applied changes',
      value: `${activeStep?.changeCount || 0} / ${model.changeCount || 0}`,
      provenance: 'design_optimization_cost_reduction_changes.json cumulative index',
    },
    {
      label: 'Timeline cumulative cost proxy delta',
      value: safeNumber(activeStep?.cumulativeCostDelta, 0).toFixed(1),
      provenance: 'changes.cost_proxy_delta sum',
    },
    {
      label: 'Timeline governing DCR after',
      value: safeNumber(activeStep?.maxGoverningDcrAfter, 0) > 0
        ? safeNumber(activeStep.maxGoverningDcrAfter, 0).toFixed(3)
        : '--',
      provenance: 'changes.governing_member_governing_dcr_after',
    },
    {
      label: 'Timeline drift after',
      value: Number.isFinite(activeStep?.driftAfterPct)
        ? `${safeNumber(activeStep.driftAfterPct, 0).toFixed(3)}%`
        : '--',
      provenance: 'changes.drift_after_pct',
    },
    {
      label: 'Timeline stage breakdown',
      value: stageBreakdown || '--',
      provenance: 'classifyOptimizationChangeStage',
    },
    ...(normalizeText(shareUrl)
      ? [{
        label: 'Compare share URL',
        value: shareUrl,
        provenance: 'variant=compare + optimization_timeline_step',
      }]
      : []),
  ];
}
