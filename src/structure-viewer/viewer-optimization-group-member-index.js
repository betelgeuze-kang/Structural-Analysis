import { buildTimelineStepHighlights } from './viewer-optimization-timeline-model.js';

function normalizeText(value) {
  return String(value ?? '').trim();
}

export const DEFAULT_GROUP_MEMBER_INDEX_PATH =
  'implementation/phase1/release_evidence/productization/design_optimization_group_member_index.json';

export function resolveGroupMemberIndexPath(workspace = {}) {
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const provenance = drawing.provenance && typeof drawing.provenance === 'object' ? drawing.provenance : {};
  const candidates = [
    drawing.group_member_index_path,
    drawing.optimization_group_member_index_path,
    provenance.group_member_index_path,
    DEFAULT_GROUP_MEMBER_INDEX_PATH,
  ];
  for (const candidate of candidates) {
    const path = normalizeText(candidate);
    if (path) return path;
  }
  return DEFAULT_GROUP_MEMBER_INDEX_PATH;
}

export function buildGroupMemberIndexModel(payload = {}) {
  const byGroupId = payload?.by_group_id && typeof payload.by_group_id === 'object' ? payload.by_group_id : {};
  const byGroupIndex = payload?.by_group_index && typeof payload.by_group_index === 'object' ? payload.by_group_index : {};
  return {
    schemaVersion: normalizeText(payload?.schema_version) || 'design-optimization-group-member-index.v1',
    status: Object.keys(byGroupId).length ? 'ready' : 'missing',
    memberCount: Number(payload?.member_count) || 0,
    groupCount: Number(payload?.group_count) || Object.keys(byGroupId).length,
    byGroupId,
    byGroupIndex,
    provenancePath: normalizeText(payload?.source_npz || payload?.artifact_path || ''),
  };
}

export function resolveMemberIdsForOptimizationChange(change = {}, index = null) {
  if (!change || !index || index.status !== 'ready') return [];
  const groupId = normalizeText(change.group_id);
  const groupIndex = change.group_index;
  if (groupId && Array.isArray(index.byGroupId[groupId])) {
    return [...index.byGroupId[groupId]];
  }
  if (groupIndex !== undefined && groupIndex !== null) {
    const key = String(groupIndex);
    if (Array.isArray(index.byGroupIndex[key])) return [...index.byGroupIndex[key]];
  }
  return [];
}

export function buildTimelineHighlightsWithGroupIndex(options = {}) {
  const fallback = buildTimelineStepHighlights(options);
  const index = options.groupMemberIndex;
  if (!index || index.status !== 'ready') {
    return { ...fallback, morphByElementId: {} };
  }

  const changes = Array.isArray(options.changesPayload?.changes) ? options.changesPayload.changes : [];
  const idx = Math.round(Number(options.stepIndex ?? -1));
  if (idx < 0 || !changes.length) {
    return { ...fallback, morphByElementId: {} };
  }

  const cumulative = changes.slice(0, idx + 1);
  const memberIds = new Set(fallback.memberIds || []);
  const toneByMemberId = { ...(fallback.toneByMemberId || {}) };
  const morphByElementId = {};
  const highlightLimit = Math.max(1, Number(options.highlightLimit) || 600);

  for (const change of cumulative) {
    resolveMemberIdsForOptimizationChange(change, index).forEach((memberId) => {
      if (memberIds.size >= highlightLimit) return;
      memberIds.add(memberId);
      toneByMemberId[memberId] = 'changed';
      const rebarScale = Number(change.after_rebar_ratio);
      const thicknessScale = Number(change.after_thickness_scale);
      const current = morphByElementId[memberId] || { rebarScale: 1, thicknessScale: 1 };
      if (Number.isFinite(rebarScale) && rebarScale > 0) current.rebarScale = rebarScale;
      if (Number.isFinite(thicknessScale) && thicknessScale > 0) current.thicknessScale = thicknessScale;
      morphByElementId[memberId] = current;
    });
  }

  return {
    memberIds: [...memberIds],
    toneByMemberId,
    storyClipLabel: fallback.storyClipLabel,
    matchCount: memberIds.size,
    morphByElementId,
    changeRows: cumulative,
  };
}
