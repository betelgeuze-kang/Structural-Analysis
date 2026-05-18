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
    reviewTasks: state.reviewTasks && typeof state.reviewTasks === 'object' ? state.reviewTasks : {},
    annotations: state.annotations && typeof state.annotations === 'object' ? state.annotations : {},
    receiptIndex: state.receiptIndex && typeof state.receiptIndex === 'object' ? state.receiptIndex : {},
    lastImportPreview: state.lastImportPreview && typeof state.lastImportPreview === 'object' ? state.lastImportPreview : null,
    lastIngestPreview: state.lastIngestPreview && typeof state.lastIngestPreview === 'object' ? state.lastIngestPreview : null,
    lastIngestRenderablePayload: state.lastIngestRenderablePayload && typeof state.lastIngestRenderablePayload === 'object'
      ? state.lastIngestRenderablePayload
      : null,
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
    reviewTasks: state.reviewTasks && typeof state.reviewTasks === 'object' ? state.reviewTasks : {},
    annotations: state.annotations && typeof state.annotations === 'object' ? state.annotations : {},
    receiptIndex: state.receiptIndex && typeof state.receiptIndex === 'object' ? state.receiptIndex : {},
    lastImportPreview: state.lastImportPreview && typeof state.lastImportPreview === 'object' ? state.lastImportPreview : null,
    lastIngestPreview: state.lastIngestPreview && typeof state.lastIngestPreview === 'object' ? state.lastIngestPreview : null,
    lastIngestRenderablePayload: state.lastIngestRenderablePayload && typeof state.lastIngestRenderablePayload === 'object'
      ? state.lastIngestRenderablePayload
      : null,
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
    status: normalizeText(event.status),
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

function taskKey(selection = {}) {
  return noteKey(selection);
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

export function getViewerReviewTask(state = {}, selection = {}) {
  const tasks = state.reviewTasks && typeof state.reviewTasks === 'object' ? state.reviewTasks : {};
  return tasks[taskKey(selection)] || null;
}

export function setViewerReviewTask(state = {}, selection = {}, {
  maxTasks = 200,
} = {}) {
  const tasks = state.reviewTasks && typeof state.reviewTasks === 'object' ? state.reviewTasks : {};
  const key = taskKey(selection);
  const previous = tasks[key] && typeof tasks[key] === 'object' ? tasks[key] : {};
  const updatedAt = normalizeText(selection.updatedAt) || new Date().toISOString();
  const row = {
    projectId: normalizeText(selection.projectId),
    drawingId: normalizeText(selection.drawingId),
    memberId: normalizeText(selection.memberId),
    status: normalizeText(selection.status) || normalizeText(previous.status) || 'needs_check',
    note: normalizeText(selection.note) || normalizeText(previous.note),
    updatedAt,
    auditTrail: [
      ...(Array.isArray(previous.auditTrail) ? previous.auditTrail : []),
      {
        at: updatedAt,
        status: normalizeText(selection.status) || normalizeText(previous.status) || 'needs_check',
        note: normalizeText(selection.note) || normalizeText(previous.note),
      },
    ].slice(-20),
  };
  const entries = Object.entries({ ...tasks, [key]: row }).slice(-maxTasks);
  return {
    ...state,
    reviewTasks: Object.fromEntries(entries),
  };
}

export function upsertViewerReceiptIndexRow(state = {}, receipt = {}, {
  maxReceipts = 500,
} = {}) {
  const index = state.receiptIndex && typeof state.receiptIndex === 'object' ? state.receiptIndex : {};
  const key = [
    normalizeText(receipt.project_id || receipt.projectId),
    normalizeText(receipt.drawing_id || receipt.drawingId),
    normalizeText(receipt.member_id || receipt.memberId),
  ].join('::');
  if (key === '::::' || key.endsWith('::')) return state;
  const entries = Object.entries({ ...index, [key]: receipt }).slice(-maxReceipts);
  return {
    ...state,
    receiptIndex: Object.fromEntries(entries),
  };
}

export function buildViewerProjectBundleImportPreview(payload = {}, {
  currentManifest = null,
} = {}) {
  const schemaVersion = normalizeText(payload?.schema_version);
  const localState = payload?.local_state && typeof payload.local_state === 'object' ? payload.local_state : {};
  const manifest = payload?.manifest && typeof payload.manifest === 'object' ? payload.manifest : null;
  const issues = [];
  if (schemaVersion !== 'structure-viewer-project-bundle.v1') {
    issues.push({ severity: 'critical', issue: 'invalid schema version', value: schemaVersion || '--' });
  }
  const incomingProject = normalizeText(payload?.project_id);
  const incomingDrawing = normalizeText(payload?.drawing_id);
  const projects = Array.isArray(currentManifest?.projects) ? currentManifest.projects : [];
  const project = projects.find((row) => normalizeText(row?.project_id) === incomingProject);
  const drawing = project?.drawings?.find((row) => normalizeText(row?.drawing_id) === incomingDrawing);
  if (currentManifest && incomingProject && !project) {
    issues.push({ severity: 'critical', issue: 'unknown project', value: incomingProject });
  }
  if (currentManifest && incomingDrawing && !drawing) {
    issues.push({ severity: 'critical', issue: 'unknown drawing', value: incomingDrawing });
  }
  const receiptRows = Object.values(localState.receiptIndex && typeof localState.receiptIndex === 'object' ? localState.receiptIndex : {});
  receiptRows.forEach((receipt) => {
    if (!normalizeText(receipt?.receipt_path || receipt?.receiptPath)) {
      issues.push({ severity: 'warning', issue: 'stale receipt path', value: normalizeText(receipt?.member_id || receipt?.memberId) || '--' });
    }
  });
  return {
    schema_version: 'structure-viewer-project-bundle-import-preview.v1',
    source_schema_version: schemaVersion,
    project_id: incomingProject,
    drawing_id: incomingDrawing,
    variant: normalizeText(payload?.variant),
    blocked: issues.some((issue) => issue.severity === 'critical'),
    issues,
    incoming_counts: {
      recentSelections: Array.isArray(localState.recentSelections) ? localState.recentSelections.length : 0,
      exportHistory: Array.isArray(localState.exportHistory) ? localState.exportHistory.length : 0,
      reviewTasks: localState.reviewTasks && typeof localState.reviewTasks === 'object' ? Object.keys(localState.reviewTasks).length : 0,
      annotations: localState.annotations && typeof localState.annotations === 'object' ? Object.keys(localState.annotations).length : 0,
      receiptIndex: localState.receiptIndex && typeof localState.receiptIndex === 'object' ? Object.keys(localState.receiptIndex).length : 0,
    },
    manifest,
    local_state: readViewerLocalOpsState({
      storageGet: () => JSON.stringify(localState),
    }),
  };
}

export function mergeViewerProjectBundleImport(state = {}, preview = {}) {
  if (!preview || preview.blocked) return state;
  const incoming = preview.local_state && typeof preview.local_state === 'object' ? preview.local_state : {};
  return {
    ...state,
    recentSelections: [
      ...(Array.isArray(incoming.recentSelections) ? incoming.recentSelections : []),
      ...(Array.isArray(state.recentSelections) ? state.recentSelections : []),
    ].slice(0, 12),
    auditEventsJsonl: [
      normalizeText(state.auditEventsJsonl),
      normalizeText(incoming.auditEventsJsonl),
    ].filter(Boolean).join('\n'),
    exportHistory: [
      ...(Array.isArray(incoming.exportHistory) ? incoming.exportHistory : []),
      ...(Array.isArray(state.exportHistory) ? state.exportHistory : []),
    ].slice(0, 20),
    reviewNotes: {
      ...(state.reviewNotes && typeof state.reviewNotes === 'object' ? state.reviewNotes : {}),
      ...(incoming.reviewNotes && typeof incoming.reviewNotes === 'object' ? incoming.reviewNotes : {}),
    },
    reviewTasks: {
      ...(state.reviewTasks && typeof state.reviewTasks === 'object' ? state.reviewTasks : {}),
      ...(incoming.reviewTasks && typeof incoming.reviewTasks === 'object' ? incoming.reviewTasks : {}),
    },
    annotations: {
      ...(state.annotations && typeof state.annotations === 'object' ? state.annotations : {}),
      ...(incoming.annotations && typeof incoming.annotations === 'object' ? incoming.annotations : {}),
    },
    receiptIndex: {
      ...(state.receiptIndex && typeof state.receiptIndex === 'object' ? state.receiptIndex : {}),
      ...(incoming.receiptIndex && typeof incoming.receiptIndex === 'object' ? incoming.receiptIndex : {}),
    },
    lastImportPreview: preview,
    lastIngestRenderablePayload: incoming.lastIngestRenderablePayload && typeof incoming.lastIngestRenderablePayload === 'object'
      ? incoming.lastIngestRenderablePayload
      : state.lastIngestRenderablePayload || null,
  };
}

export function mergeViewerEvidenceIngestPreview(state = {}, preview = {}) {
  const index = state.receiptIndex && typeof state.receiptIndex === 'object' ? state.receiptIndex : {};
  const projects = Array.isArray(preview?.manifest?.projects) ? preview.manifest.projects : [];
  const receiptRows = projects.flatMap((project) => (
    (Array.isArray(project?.drawings) ? project.drawings : []).flatMap((drawing) => (
      (Array.isArray(drawing?.solver_receipts) ? drawing.solver_receipts : []).map((receipt) => ({
        project_id: normalizeText(receipt.project_id || project.project_id),
        drawing_id: normalizeText(receipt.drawing_id || drawing.drawing_id),
        ...receipt,
      }))
    ))
  ));
  const nextIndex = { ...index };
  receiptRows.forEach((receipt) => {
    const key = [
      normalizeText(receipt.project_id),
      normalizeText(receipt.drawing_id),
      normalizeText(receipt.member_id || receipt.memberId),
    ].join('::');
    if (!key.endsWith('::')) nextIndex[key] = receipt;
  });
  return {
    ...state,
    receiptIndex: nextIndex,
    lastIngestPreview: preview && typeof preview === 'object' ? preview : null,
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
