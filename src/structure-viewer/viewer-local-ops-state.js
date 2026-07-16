import {
  VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS,
  inspectViewerProjectBundleLocalState,
  mergeViewerProjectBundleLocalState,
} from './viewer-project-bundle-state-policy.js';
import {
  prepareViewerLocalOpsStateForStorage,
} from './viewer-local-ops-persistence-policy.js';

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

function emptyViewerLocalOpsState() {
  return {
    recentSelections: [],
    auditEventsJsonl: '',
    exportHistory: [],
    reviewNotes: {},
    reviewTasks: {},
    annotations: {},
    receiptIndex: {},
    lastImportPreview: null,
    lastIngestPreview: null,
    lastIngestRenderablePayload: null,
  };
}

export function readViewerLocalOpsState({
  storageGet = (key) => globalThis.localStorage?.getItem(key),
  storageKey = VIEWER_LOCAL_OPS_STATE_KEY,
} = {}) {
  const parsed = parseState(storageGet(storageKey));
  const candidate = {
    recentSelections: Array.isArray(parsed.recentSelections) ? parsed.recentSelections : [],
    auditEventsJsonl: normalizeText(parsed.auditEventsJsonl),
    exportHistory: Array.isArray(parsed.exportHistory) ? parsed.exportHistory : [],
    reviewNotes: parsed.reviewNotes && typeof parsed.reviewNotes === 'object' ? parsed.reviewNotes : {},
    reviewTasks: parsed.reviewTasks && typeof parsed.reviewTasks === 'object' ? parsed.reviewTasks : {},
    annotations: parsed.annotations && typeof parsed.annotations === 'object' ? parsed.annotations : {},
    receiptIndex: parsed.receiptIndex && typeof parsed.receiptIndex === 'object' ? parsed.receiptIndex : {},
    lastImportPreview: parsed.lastImportPreview && typeof parsed.lastImportPreview === 'object' ? parsed.lastImportPreview : null,
    lastIngestPreview: parsed.lastIngestPreview && typeof parsed.lastIngestPreview === 'object' ? parsed.lastIngestPreview : null,
    lastIngestRenderablePayload: parsed.lastIngestRenderablePayload && typeof parsed.lastIngestRenderablePayload === 'object'
      ? parsed.lastIngestRenderablePayload
      : null,
  };
  const prepared = prepareViewerLocalOpsStateForStorage(candidate);
  return prepared.valid ? prepared.state : emptyViewerLocalOpsState();
}

export function writeViewerLocalOpsState(state = {}, {
  storageGet = (key) => globalThis.localStorage?.getItem(key),
  storageSet = (key, value) => globalThis.localStorage?.setItem(key, value),
  storageKey = VIEWER_LOCAL_OPS_STATE_KEY,
} = {}) {
  const prepared = prepareViewerLocalOpsStateForStorage(state);
  if (!prepared.valid) {
    return readViewerLocalOpsState({storageGet, storageKey});
  }
  storageSet(storageKey, JSON.stringify(prepared.state));
  return prepared.state;
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
  const hasLocalState = payload !== null
    && typeof payload === 'object'
    && !Array.isArray(payload)
    && Object.prototype.hasOwnProperty.call(payload, 'local_state');
  const rawLocalState = hasLocalState ? payload.local_state : {};
  const stateInspection = inspectViewerProjectBundleLocalState(rawLocalState);
  const localState = stateInspection.valid ? rawLocalState : {};
  const manifest = payload?.manifest && typeof payload.manifest === 'object' ? payload.manifest : null;
  const issues = [...stateInspection.issues];
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
  const receiptRows = stateInspection.valid
    ? Object.values(localState.receiptIndex && typeof localState.receiptIndex === 'object' ? localState.receiptIndex : {})
    : [];
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
    state_policy: stateInspection.policy,
    state_limits: stateInspection.limits,
    local_state_serialized_bytes: stateInspection.serialized_bytes,
    incoming_counts: {
      recentSelections: stateInspection.counts.recentSelections,
      auditEvents: stateInspection.counts.auditEvents,
      exportHistory: stateInspection.counts.exportHistory,
      reviewNotes: stateInspection.counts.reviewNotes,
      reviewTasks: stateInspection.counts.reviewTasks,
      annotations: stateInspection.counts.annotations,
      receiptIndex: stateInspection.counts.receiptIndex,
    },
    manifest,
    local_state: stateInspection.valid
      ? readViewerLocalOpsState({storageGet: () => JSON.stringify(localState)})
      : {},
  };
}

function storedProjectBundleImportPreview(preview = {}) {
  return {
    schema_version: normalizeText(preview.schema_version),
    source_schema_version: normalizeText(preview.source_schema_version),
    project_id: normalizeText(preview.project_id),
    drawing_id: normalizeText(preview.drawing_id),
    variant: normalizeText(preview.variant),
    blocked: Boolean(preview.blocked),
    issues: Array.isArray(preview.issues) ? preview.issues.slice(0, 100) : [],
    incoming_counts: preview.incoming_counts && typeof preview.incoming_counts === 'object'
      ? {...preview.incoming_counts}
      : {},
    state_policy: normalizeText(preview.state_policy),
    state_limits: preview.state_limits && typeof preview.state_limits === 'object'
      ? {...preview.state_limits}
      : {},
    local_state_serialized_bytes: Number.isSafeInteger(preview.local_state_serialized_bytes)
      ? preview.local_state_serialized_bytes
      : 0,
    file_read: preview.file_read && typeof preview.file_read === 'object'
      ? {...preview.file_read}
      : null,
  };
}

export function mergeViewerProjectBundleImport(state = {}, preview = {}) {
  if (!preview || preview.blocked) return state;
  const incoming = preview.local_state && typeof preview.local_state === 'object'
    ? preview.local_state
    : {};
  const merged = mergeViewerProjectBundleLocalState(state, incoming);
  if (!merged.valid) return state;
  const candidate = {
    ...merged.state,
    lastImportPreview: storedProjectBundleImportPreview(preview),
  };
  const finalInspection = inspectViewerProjectBundleLocalState(candidate);
  return finalInspection.valid ? candidate : state;
}

export function mergeViewerEvidenceIngestPreview(state = {}, preview = {}) {
  if (!preview || (Array.isArray(preview.blocked_issues) && preview.blocked_issues.length)) {
    return state;
  }
  const currentPrepared = prepareViewerLocalOpsStateForStorage(state);
  if (!currentPrepared.valid) return state;
  const current = currentPrepared.state;
  const index = current.receiptIndex && typeof current.receiptIndex === 'object'
    ? current.receiptIndex
    : {};
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
  const nextIndex = {...index};
  const receiptKeys = new Set(Object.keys(nextIndex));
  for (const receipt of receiptRows) {
    const key = [
      normalizeText(receipt.project_id),
      normalizeText(receipt.drawing_id),
      normalizeText(receipt.member_id || receipt.memberId),
    ].join('::');
    if (key === '::::' || key.endsWith('::')) continue;
    if (!receiptKeys.has(key) && receiptKeys.size >= VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS) {
      return state;
    }
    receiptKeys.add(key);
    nextIndex[key] = receipt;
  }
  const renderablePayload = preview.renderable_payload && typeof preview.renderable_payload === 'object'
    ? preview.renderable_payload
    : current.lastIngestRenderablePayload || null;
  const candidate = {
    ...current,
    receiptIndex: nextIndex,
    lastIngestPreview: preview && typeof preview === 'object' ? preview : null,
    lastIngestRenderablePayload: renderablePayload,
  };
  const prepared = prepareViewerLocalOpsStateForStorage(candidate);
  return prepared.valid ? prepared.state : state;
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
