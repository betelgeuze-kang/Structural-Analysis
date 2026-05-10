const DEFAULT_NORMALIZATION_CHUNK_SIZE = 1200;

export function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function normalizeElementType(value) {
  const type = String(value || 'beam').trim().toLowerCase();
  return type || 'beam';
}

export function isModelPayload(payload) {
  return Boolean(extractModelPayload(payload));
}

export function extractModelPayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (Array.isArray(payload.nodes) && Array.isArray(payload.elements)) {
    return { model: payload, root: payload };
  }
  if (
    payload.model &&
    typeof payload.model === 'object' &&
    Array.isArray(payload.model.nodes) &&
    Array.isArray(payload.model.elements)
  ) {
    return { model: payload.model, root: payload };
  }
  return null;
}

export function extractInteractivePayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.interactive_3d && typeof payload.interactive_3d === 'object') return payload.interactive_3d;
  if (payload.interactive_3d_payload && typeof payload.interactive_3d_payload === 'object') {
    return payload.interactive_3d_payload;
  }
  if (Array.isArray(payload.baseline_segments) || Array.isArray(payload.after_segments)) return payload;
  return null;
}

export function normalizePoint(point) {
  if (!Array.isArray(point) || point.length < 3) return null;
  return [
    safeNumber(point[0], 0),
    safeNumber(point[1], 0),
    safeNumber(point[2], 0),
  ];
}

export function registerSegmentNode(point, nodeIndexByKey, nodes) {
  const normalized = normalizePoint(point);
  if (!normalized) return null;
  const key = normalized.map(value => value.toFixed(4)).join('|');
  if (nodeIndexByKey.has(key)) return nodeIndexByKey.get(key);
  const id = nodes.length;
  const node = {
    id,
    x: normalized[0],
    y: normalized[2],
    z: normalized[1],
    dx: 0,
    dy: 0,
    dz: 0,
    disp_mag: 0,
    stress_vm: 0,
    dcr: 0,
    axial: 0,
    moment: 0,
    shear: 0,
  };
  nodes.push(node);
  nodeIndexByKey.set(key, id);
  return id;
}

export function rgbArrayToHex(value) {
  if (!Array.isArray(value) || value.length < 3) return '';
  const channels = value
    .slice(0, 3)
    .map(entry => Math.max(0, Math.min(255, Math.round(safeNumber(entry, 0)))));
  return `#${channels.map(entry => entry.toString(16).padStart(2, '0')).join('')}`;
}

export function estimateStoryCount(nodes, axisRefs = {}) {
  const axisStoryCount = Array.isArray(axisRefs?.z) ? axisRefs.z.length : 0;
  const levels = new Set();
  (Array.isArray(nodes) ? nodes : []).forEach(node => {
    const z = safeNumber(node?.z, NaN);
    if (Number.isFinite(z)) levels.add(z.toFixed(3));
  });
  const nodeStoryCount = levels.size > 1 ? Math.max(levels.size - 1, 0) : 0;
  return Math.max(axisStoryCount, nodeStoryCount, 0);
}

function addInteractiveSegment(row, scope, index, { nodeIndexByKey, nodes, elements }) {
  const p0 = normalizePoint(row?.p0);
  const p1 = normalizePoint(row?.p1);
  if (!p0 || !p1) return;
  const n0 = registerSegmentNode(p0, nodeIndexByKey, nodes);
  const n1 = registerSegmentNode(p1, nodeIndexByKey, nodes);
  const type = normalizeElementType(row?.member_type || row?.category || row?.type);
  elements.push({
    ...row,
    id: `${scope}:${row?.member_id || index}:${index}`,
    type,
    node_ids: [n0, n1],
    section: row?.after_section || row?.before_section || row?.section_name || '--',
    color: String(row?.color || '').trim(),
    dcr: safeNumber(row?.dcr, safeNumber(row?.max_dcr_after, safeNumber(row?.max_dcr_before, 0))),
    axial: safeNumber(row?.axial, 0),
    moment: safeNumber(row?.moment, 0),
    shear: safeNumber(row?.shear, 0),
    overlay_scope: scope,
    story_band_label: String(row?.story_band_label || '').trim(),
    zone_label: String(row?.zone_label || '').trim(),
    action_name: String(row?.action_name || '').trim(),
    optimization_meaning_label: String(row?.optimization_meaning_label || '').trim(),
    before_after_snapshot_note: String(row?.before_after_snapshot_note || '').trim(),
  });
}

function buildInteractiveModel(payload, sourceMeta, { nodes, elements, normalizationMode }) {
  const interactive = extractInteractivePayload(payload);
  const metaSource = payload?.case_context && typeof payload.case_context === 'object' ? payload.case_context : {};
  const storyOptions = Array.isArray(interactive?.story_slice_options) ? interactive.story_slice_options : [];
  const axisRefs = interactive?.axis_refs && typeof interactive.axis_refs === 'object' ? interactive.axis_refs : {};
  const baselineSegments = Array.isArray(interactive?.baseline_segments)
    ? interactive.baseline_segments.filter(Boolean)
    : [];
  const afterSegments = Array.isArray(interactive?.after_segments)
    ? interactive.after_segments.filter(Boolean)
    : [];
  return {
    nodes,
    elements,
    meta: {
      name: String(
        metaSource.case_id ||
        metaSource.case_label ||
        payload?.meta?.name ||
        payload?.viewer_mode ||
        'Repo interactive 3D artifact'
      ),
      stories: Math.max(
        Array.isArray(axisRefs.z) ? axisRefs.z.length : 0,
        storyOptions.length
      ) || '--',
      source_mode: String(sourceMeta.mode || 'artifact_interactive_3d'),
      source_label: String(sourceMeta.label || 'interactive_3d'),
      source_path: String(sourceMeta.resolvedPath || ''),
      loaded_at: String(sourceMeta.loadedAt || payload?.generated_at || payload?.meta?.generated_at || ''),
      generated_at: String(payload?.generated_at || payload?.meta?.generated_at || ''),
      normalization_mode: normalizationMode,
      comparison_availability: String(interactive?.comparison_availability || 'baseline_vs_changed'),
      story_slices: storyOptions.map(option => String(option?.label || option?.value || '').trim()).filter(Boolean),
      baseline_segment_count: baselineSegments.length,
      optimized_segment_count: afterSegments.length,
    },
  };
}

export function buildModelFromInteractivePayload(payload, sourceMeta = {}) {
  const interactive = extractInteractivePayload(payload);
  if (!interactive) return null;
  const baselineSegments = Array.isArray(interactive.baseline_segments) ? interactive.baseline_segments.filter(Boolean) : [];
  const afterSegments = Array.isArray(interactive.after_segments) ? interactive.after_segments.filter(Boolean) : [];
  if (!baselineSegments.length && !afterSegments.length) return null;

  const context = { nodeIndexByKey: new Map(), nodes: [], elements: [] };
  baselineSegments.forEach((row, index) => addInteractiveSegment(row, 'baseline', index, context));
  afterSegments.forEach((row, index) => addInteractiveSegment(row, 'optimized', index, context));
  return buildInteractiveModel(payload, sourceMeta, {
    nodes: context.nodes,
    elements: context.elements,
    normalizationMode: 'direct',
  });
}

export async function buildModelFromInteractivePayloadAsync(payload, sourceMeta = {}, {
  processInChunks,
  chunkSize = DEFAULT_NORMALIZATION_CHUNK_SIZE,
} = {}) {
  const interactive = extractInteractivePayload(payload);
  if (!interactive) return null;
  const baselineSegments = Array.isArray(interactive.baseline_segments) ? interactive.baseline_segments.filter(Boolean) : [];
  const afterSegments = Array.isArray(interactive.after_segments) ? interactive.after_segments.filter(Boolean) : [];
  if (!baselineSegments.length && !afterSegments.length) return null;

  const context = { nodeIndexByKey: new Map(), nodes: [], elements: [] };
  const totalSegments = baselineSegments.length + afterSegments.length;
  const chunker = typeof processInChunks === 'function'
    ? processInChunks
    : async (rows, handler) => {
      (Array.isArray(rows) ? rows : []).forEach((row, index) => handler(row, index, index));
    };
  await chunker(baselineSegments, (row, index) => addInteractiveSegment(row, 'baseline', index, context), {
    progressLabel: 'Normalizing interactive_3d segments',
    totalCount: totalSegments,
    forceChunking: totalSegments > chunkSize,
  });
  await chunker(afterSegments, (row, index) => addInteractiveSegment(row, 'optimized', index, context), {
    progressLabel: 'Normalizing interactive_3d segments',
    startOffset: baselineSegments.length,
    totalCount: totalSegments,
    forceChunking: totalSegments > chunkSize,
  });
  return buildInteractiveModel(payload, sourceMeta, {
    nodes: context.nodes,
    elements: context.elements,
    normalizationMode: 'chunked',
  });
}
