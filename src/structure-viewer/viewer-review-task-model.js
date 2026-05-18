export const STRUCTURE_VIEWER_REVIEW_TASK_STATUSES = [
  'needs_check',
  'approved',
  'hold',
  'rerun_required',
];

const REVIEW_TASK_LABELS = {
  needs_check: '확인 필요',
  approved: '승인',
  hold: '보류',
  rerun_required: '재해석 필요',
};

const REVIEW_TASK_TONES = {
  needs_check: 'warn',
  approved: 'success',
  hold: 'danger',
  rerun_required: 'danger',
};

function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeToken(value) {
  return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

export function normalizeReviewTaskStatus(value = '') {
  const status = normalizeToken(value);
  return STRUCTURE_VIEWER_REVIEW_TASK_STATUSES.includes(status) ? status : 'needs_check';
}

export function buildReviewTaskKey({
  projectId = '',
  drawingId = '',
  memberId = '',
} = {}) {
  return [
    normalizeToken(projectId),
    normalizeToken(drawingId),
    normalizeText(memberId),
  ].join('::');
}

function readTaskMap(state = {}) {
  return state.reviewTasks && typeof state.reviewTasks === 'object' ? state.reviewTasks : {};
}

export function buildReviewTaskModel({
  state = {},
  workspace = {},
  memberId = '',
  note = '',
  now = '',
} = {}) {
  const taskKey = buildReviewTaskKey({
    projectId: workspace.projectId,
    drawingId: workspace.drawingId,
    memberId,
  });
  const task = readTaskMap(state)[taskKey] || {};
  const status = normalizeReviewTaskStatus(task.status || 'needs_check');
  const reviewerNote = normalizeText(task.note || note);
  return {
    schemaVersion: 'structure-viewer-review-task.v1',
    taskKey,
    projectId: normalizeToken(workspace.projectId),
    drawingId: normalizeToken(workspace.drawingId),
    memberId: normalizeText(memberId),
    status,
    label: REVIEW_TASK_LABELS[status],
    tone: REVIEW_TASK_TONES[status],
    note: reviewerNote,
    updatedAt: normalizeText(task.updatedAt || now),
    auditTrail: Array.isArray(task.auditTrail) ? task.auditTrail : [],
    hasTask: Boolean(task.status || reviewerNote),
  };
}

export function buildReviewTaskSummary(reviewTasks = {}, {
  projectId = '',
  drawingId = '',
} = {}) {
  const prefix = `${normalizeToken(projectId)}::${normalizeToken(drawingId)}::`;
  const counts = Object.fromEntries(STRUCTURE_VIEWER_REVIEW_TASK_STATUSES.map((status) => [status, 0]));
  Object.entries(reviewTasks && typeof reviewTasks === 'object' ? reviewTasks : {}).forEach(([key, task]) => {
    if (!key.startsWith(prefix)) return;
    const status = normalizeReviewTaskStatus(task?.status);
    counts[status] = (counts[status] || 0) + 1;
  });
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  return {
    total,
    counts,
    label: total
      ? `${total} review tasks · ${counts.needs_check} check · ${counts.approved} approved · ${counts.hold} hold · ${counts.rerun_required} rerun`
      : 'No saved review tasks',
  };
}

export function buildReviewTaskReportRows(reviewTask = {}) {
  return [
    { label: 'Task status', value: reviewTask.label || REVIEW_TASK_LABELS.needs_check, evidence: 'local audit state' },
    { label: 'Task code', value: normalizeReviewTaskStatus(reviewTask.status), evidence: 'local audit state' },
    { label: 'Reviewer note', value: normalizeText(reviewTask.note) || '--', evidence: reviewTask.note ? 'local annotation' : 'missing evidence' },
    { label: 'Updated', value: normalizeText(reviewTask.updatedAt) || '--', evidence: reviewTask.updatedAt ? 'local audit state' : 'missing evidence' },
  ];
}
