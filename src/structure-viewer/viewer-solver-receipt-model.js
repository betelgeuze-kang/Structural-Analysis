export const STRUCTURE_VIEWER_SOLVER_RECEIPT_SCHEMA_VERSION = 'structure-viewer-solver-receipt.v1';

const SOLVER_RECEIPT_STATUSES = ['verified', 'pending', 'mismatch'];

function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeToken(value) {
  return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

function safeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalizeStatus(value = '') {
  const status = normalizeToken(value);
  return SOLVER_RECEIPT_STATUSES.includes(status) ? status : 'pending';
}

function receiptKey({
  project_id = '',
  projectId = '',
  drawing_id = '',
  drawingId = '',
  member_id = '',
  memberId = '',
} = {}) {
  return [
    normalizeToken(project_id || projectId),
    normalizeToken(drawing_id || drawingId),
    normalizeText(member_id || memberId),
  ].join('::');
}

export function buildSolverReceiptKey(row = {}) {
  return receiptKey(row);
}

export function normalizeSolverReceiptRow(row = {}) {
  const normalized = {
    schema_version: normalizeText(row.schema_version) || STRUCTURE_VIEWER_SOLVER_RECEIPT_SCHEMA_VERSION,
    project_id: normalizeToken(row.project_id || row.projectId),
    drawing_id: normalizeToken(row.drawing_id || row.drawingId),
    member_id: normalizeText(row.member_id || row.memberId || row.id),
    source_tool: normalizeText(row.source_tool || row.sourceTool || row.tool || 'unknown'),
    load_combo: normalizeText(row.load_combo || row.loadCombo || row.combination),
    dcr_before: safeNumber(row.dcr_before ?? row.dcrBefore ?? row.max_dcr_before),
    dcr_after: safeNumber(row.dcr_after ?? row.dcrAfter ?? row.max_dcr_after ?? row.dcr),
    governing_constraint: normalizeText(row.governing_constraint || row.governingConstraint || row.constraint),
    status: normalizeStatus(row.status),
    receipt_path: normalizeText(row.receipt_path || row.receiptPath || row.path),
    evidence_level: normalizeText(row.evidence_level || row.evidenceLevel || row.evidence) || 'missing evidence',
  };
  return {
    ...normalized,
    key: receiptKey(normalized),
    hasReceiptPath: Boolean(normalized.receipt_path),
    evidenceStatus: normalized.status === 'verified'
      ? 'solver receipt verified'
      : normalized.status === 'mismatch'
        ? 'solver receipt mismatch'
        : 'solver receipt pending',
  };
}

function receiptRowsFromWorkspace(workspace = {}) {
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  return Array.isArray(drawing.solver_receipts) ? drawing.solver_receipts : [];
}

function receiptRowsFromState(state = {}) {
  const index = state.receiptIndex && typeof state.receiptIndex === 'object' ? state.receiptIndex : {};
  return Object.values(index);
}

export function buildSolverReceiptIndex({
  workspace = {},
  state = {},
} = {}) {
  const rows = [
    ...receiptRowsFromWorkspace(workspace),
    ...receiptRowsFromState(state),
  ].map((row) => normalizeSolverReceiptRow({
    project_id: workspace.projectId,
    drawing_id: workspace.drawingId,
    ...row,
  }));
  return Object.fromEntries(rows.filter((row) => row.member_id).map((row) => [row.key, row]));
}

export function buildSolverReceiptModel({
  workspace = {},
  state = {},
  memberId = '',
  element = null,
} = {}) {
  const normalizedMemberId = normalizeText(memberId || element?.member_id || element?.case_id || element?.id);
  const key = receiptKey({
    projectId: workspace.projectId,
    drawingId: workspace.drawingId,
    memberId: normalizedMemberId,
  });
  const index = buildSolverReceiptIndex({ workspace, state });
  const receipt = index[key] || null;
  if (receipt) {
    return {
      ...receipt,
      label: receipt.evidenceStatus,
      tone: receipt.status === 'verified' ? 'success' : receipt.status === 'mismatch' ? 'danger' : 'warn',
      missing: false,
    };
  }
  return {
    schema_version: STRUCTURE_VIEWER_SOLVER_RECEIPT_SCHEMA_VERSION,
    key,
    project_id: normalizeToken(workspace.projectId),
    drawing_id: normalizeToken(workspace.drawingId),
    member_id: normalizedMemberId,
    source_tool: 'unknown',
    load_combo: '',
    dcr_before: null,
    dcr_after: null,
    governing_constraint: '',
    status: 'pending',
    receipt_path: '',
    evidence_level: 'missing evidence',
    evidenceStatus: 'solver receipt pending',
    label: 'solver receipt pending',
    tone: 'warn',
    missing: true,
  };
}

export function buildSolverReceiptSummary(receiptIndex = {}) {
  const rows = Object.values(receiptIndex && typeof receiptIndex === 'object' ? receiptIndex : {}).map(normalizeSolverReceiptRow);
  const counts = { verified: 0, pending: 0, mismatch: 0 };
  rows.forEach((row) => {
    counts[row.status] = (counts[row.status] || 0) + 1;
  });
  return {
    total: rows.length,
    counts,
    label: rows.length
      ? `${rows.length} solver receipts · ${counts.verified} verified · ${counts.pending} pending · ${counts.mismatch} mismatch`
      : 'No solver receipts attached',
  };
}

export function buildSolverReceiptReportRows(receipt = {}) {
  return [
    { label: 'Solver receipt', value: receipt.label || 'solver receipt pending', evidence: receipt.evidence_level || 'missing evidence' },
    { label: 'Source tool', value: normalizeText(receipt.source_tool) || '--', evidence: receipt.source_tool ? 'exact source' : 'missing evidence' },
    { label: 'Load combo', value: normalizeText(receipt.load_combo) || '--', evidence: receipt.load_combo ? 'exact source' : 'missing evidence' },
    { label: 'DCR before / after', value: receipt.dcr_before !== null && receipt.dcr_after !== null ? `${Number(receipt.dcr_before).toFixed(3)} -> ${Number(receipt.dcr_after).toFixed(3)}` : '--', evidence: receipt.dcr_after !== null ? 'exact source' : 'missing evidence' },
    { label: 'Governing constraint', value: normalizeText(receipt.governing_constraint) || '--', evidence: receipt.governing_constraint ? 'exact source' : 'missing evidence' },
    { label: 'Receipt path', value: normalizeText(receipt.receipt_path) || '--', evidence: receipt.receipt_path ? 'exact source' : 'missing evidence' },
  ];
}
