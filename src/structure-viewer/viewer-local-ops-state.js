export const VIEWER_LOCAL_OPS_STATE_KEY = 'structure-viewer-local-ops-state-v1';

function normalizeText(value) {
  return String(value ?? '').trim();
}

function slug(value, fallback = 'viewer') {
  return normalizeText(value).replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toLowerCase() || fallback;
}

function parseState(text) {
  if (!text) return {};
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (_err) {
    return {};
  }
}

export function readViewerLocalOpsState({
  storageGet = (key) => globalThis.localStorage?.getItem(key),
  storageKey = VIEWER_LOCAL_OPS_STATE_KEY,
} = {}) {
  const state = parseState(storageGet(storageKey));
  return {
    recentSelections: Array.isArray(state.recentSelections) ? state.recentSelections : [],
    auditEventsJsonl: normalizeText(state.auditEventsJsonl),
    exportHistory: Array.isArray(state.exportHistory) ? state.exportHistory : [],
    reviewNotes: state.reviewNotes && typeof state.reviewNotes === 'object' ? state.reviewNotes : {},
  };
}

export function writeViewerLocalOpsState(state = {}, {
  storageSet = (key, value) => globalThis.localStorage?.setItem(key, value),
  storageKey = VIEWER_LOCAL_OPS_STATE_KEY,
} = {}) {
  storageSet(storageKey, JSON.stringify({
    recentSelections: Array.isArray(state.recentSelections) ? state.recentSelections.slice(0, 12) : [],
    auditEventsJsonl: normalizeText(state.auditEventsJsonl),
    exportHistory: Array.isArray(state.exportHistory) ? state.exportHistory.slice(0, 20) : [],
    reviewNotes: state.reviewNotes && typeof state.reviewNotes === 'object' ? state.reviewNotes : {},
  }));
}

export function rememberViewerWorkspaceSelection(state = {}, selection = {}, {
  maxRecent = 8,
} = {}) {
  const key = [
    normalizeText(selection.projectId),
    normalizeText(selection.drawingId),
    normalizeText(selection.variant),
  ].join('::');
  if (key === '::::') return state;
  const row = {
    projectId: normalizeText(selection.projectId),
    drawingId: normalizeText(selection.drawingId),
    variant: normalizeText(selection.variant),
    memberId: normalizeText(selection.memberId),
    filter: normalizeText(selection.filter),
    label: normalizeText(selection.label),
    rememberedAt: normalizeText(selection.rememberedAt) || new Date().toISOString(),
  };
  const next = [
    row,
    ...(Array.isArray(state.recentSelections) ? state.recentSelections : []).filter((item) => (
      [
        normalizeText(item?.projectId),
        normalizeText(item?.drawingId),
        normalizeText(item?.variant),
      ].join('::') !== key
    )),
  ].slice(0, maxRecent);
  return { ...state, recentSelections: next };
}

export function appendViewerAuditEvent(state = {}, event = {}, {
  maxLines = 80,
} = {}) {
  const row = {
    at: normalizeText(event.at) || new Date().toISOString(),
    type: normalizeText(event.type) || 'viewer_event',
    projectId: normalizeText(event.projectId),
    drawingId: normalizeText(event.drawingId),
    variant: normalizeText(event.variant),
    memberId: normalizeText(event.memberId),
    filter: normalizeText(event.filter),
    note: normalizeText(event.note),
  };
  const existing = normalizeText(state.auditEventsJsonl).split('\n').filter(Boolean);
  const nextLines = [...existing, JSON.stringify(row)].slice(-maxLines);
  return { ...state, auditEventsJsonl: nextLines.join('\n') };
}

export function appendViewerExportHistory(state = {}, event = {}, {
  maxItems = 20,
} = {}) {
  const row = {
    at: normalizeText(event.at) || new Date().toISOString(),
    type: normalizeText(event.type) || 'html_report',
    filename: normalizeText(event.filename),
    projectId: normalizeText(event.projectId),
    drawingId: normalizeText(event.drawingId),
    variant: normalizeText(event.variant),
  };
  return {
    ...state,
    exportHistory: [row, ...(Array.isArray(state.exportHistory) ? state.exportHistory : [])].slice(0, maxItems),
  };
}

function noteKey({ projectId = '', drawingId = '', memberId = '' } = {}) {
  return [
    normalizeText(projectId),
    normalizeText(drawingId),
    normalizeText(memberId),
  ].join('::');
}

export function getViewerReviewNote(state = {}, selection = {}) {
  const notes = state.reviewNotes && typeof state.reviewNotes === 'object' ? state.reviewNotes : {};
  return normalizeText(notes[noteKey(selection)]);
}

export function setViewerReviewNote(state = {}, selection = {}, {
  maxNotes = 80,
} = {}) {
  const notes = state.reviewNotes && typeof state.reviewNotes === 'object' ? state.reviewNotes : {};
  const key = noteKey(selection);
  const row = {
    note: normalizeText(selection.note),
    projectId: normalizeText(selection.projectId),
    drawingId: normalizeText(selection.drawingId),
    memberId: normalizeText(selection.memberId),
    updatedAt: normalizeText(selection.updatedAt) || new Date().toISOString(),
  };
  const entries = Object.entries({ ...notes, [key]: row.note }).slice(-maxNotes);
  return {
    ...state,
    reviewNotes: Object.fromEntries(entries),
  };
}

export function buildViewerProjectBundleExport(state = {}, {
  projectId = '',
  drawingId = '',
  variant = '',
  manifest = null,
  generatedAt = new Date().toISOString(),
} = {}) {
  const payload = {
    schema_version: 'structure-viewer-project-bundle.v1',
    generated_at: generatedAt,
    project_id: normalizeText(projectId),
    drawing_id: normalizeText(drawingId),
    variant: normalizeText(variant),
    manifest,
    local_state: readViewerLocalOpsState({
      storageGet: () => JSON.stringify(state),
    }),
  };
  return {
    json: JSON.stringify(payload, null, 2),
    filename: `structure_viewer_bundle_${slug(projectId, 'project')}_${slug(drawingId, 'drawing')}.json`,
    generatedAt,
  };
}

export function buildViewerAuditJsonlExport(state = {}, {
  projectId = '',
  drawingId = '',
  generatedAt = new Date().toISOString(),
} = {}) {
  const jsonl = normalizeText(state.auditEventsJsonl);
  return {
    jsonl: jsonl ? `${jsonl}\n` : '',
    filename: `structure_viewer_audit_${slug(projectId, 'project')}_${slug(drawingId, 'drawing')}.jsonl`,
    generatedAt,
    eventCount: jsonl ? jsonl.split('\n').filter(Boolean).length : 0,
  };
}
