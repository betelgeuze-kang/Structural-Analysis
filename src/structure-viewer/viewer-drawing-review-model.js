const CRITICAL_FLAGS = new Set(['empty_geometry', 'missing_members', 'provenance_missing']);
const WARNING_FLAGS = new Set(['load_model_missing', 'axis_flipped_review', 'scale_outlier', 'aspect_ratio_outlier']);
const INFO_FLAGS = new Set(['proxy_assets_present', 'synthetic_compare', 'external_receipt_pending', 'large_release_artifact', 'optimization_pair_available']);

const FLAG_LABELS = {
  empty_geometry: 'Empty geometry',
  missing_members: 'Missing members',
  provenance_missing: 'Provenance missing',
  load_model_missing: 'Load model missing',
  axis_flipped_review: 'Axis flip review',
  scale_outlier: 'Scale outlier',
  aspect_ratio_outlier: 'Aspect ratio outlier',
  proxy_assets_present: 'Proxy assets present',
  synthetic_compare: 'Synthetic compare',
  external_receipt_pending: 'External receipt pending',
  large_release_artifact: 'Large release artifact',
  optimization_pair_available: 'Optimization pair available',
};

function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeToken(value) {
  return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

function uniqueFlags(flags = []) {
  return [...new Set((Array.isArray(flags) ? flags : []).map(normalizeToken).filter(Boolean))];
}

export function classifyDrawingQualityFlag(flag = '') {
  const key = normalizeToken(flag);
  if (CRITICAL_FLAGS.has(key)) return 'critical';
  if (WARNING_FLAGS.has(key)) return 'warning';
  if (INFO_FLAGS.has(key)) return 'info';
  return key ? 'info' : '';
}

function buildRecommendedAction(severity = '', flag = '') {
  if (severity === 'critical') return 'Block commercial review until geometry/provenance is restored.';
  if (severity === 'warning') {
    if (flag === 'load_model_missing') return 'Attach load evidence or keep engineer-in-loop review boundary.';
    if (flag.includes('axis')) return 'Confirm coordinate orientation before drawing signoff.';
    if (flag.includes('scale') || flag.includes('aspect')) return 'Confirm model units and framing before comparison.';
    return 'Resolve warning or record engineer acceptance before release review.';
  }
  return 'Track as contextual evidence; no hard block for assisted review.';
}

export function buildDrawingQualityIssues(drawing = {}) {
  return uniqueFlags(drawing.quality_flags).map((flag) => {
    const severity = classifyDrawingQualityFlag(flag);
    return {
      flag,
      label: FLAG_LABELS[flag] || flag.replaceAll('_', ' '),
      severity,
      tone: severity === 'critical' ? 'danger' : severity === 'warning' ? 'warn' : 'accent',
      recommendedAction: buildRecommendedAction(severity, flag),
    };
  });
}

export function buildDrawingReviewModel(drawing = {}) {
  const issues = buildDrawingQualityIssues(drawing);
  const counts = {
    critical: issues.filter((issue) => issue.severity === 'critical').length,
    warning: issues.filter((issue) => issue.severity === 'warning').length,
    info: issues.filter((issue) => issue.severity === 'info').length,
  };
  const manifestStatus = normalizeToken(drawing.commercial_review_status) || 'needs_review';
  const computedStatus = normalizeToken(drawing.computed_review_status) || manifestStatus;
  const blocked = counts.critical > 0 || manifestStatus === 'blocked' || computedStatus === 'blocked';
  const limited = !blocked && (counts.warning > 0 || counts.info > 0 || manifestStatus === 'needs_review' || computedStatus === 'needs_review');
  const verdict = blocked ? 'blocked' : limited ? 'limited_review' : 'ready';
  return {
    verdict,
    label: verdict === 'ready' ? '상용 검토 가능' : verdict === 'limited_review' ? '제한적 검토' : '검토 불가',
    tone: verdict === 'ready' ? 'success' : verdict === 'limited_review' ? 'warn' : 'danger',
    reason: blocked
      ? 'Critical drawing evidence is missing or the manifest marks this drawing as blocked.'
      : limited
        ? 'Warnings or contextual evidence require engineer-in-loop review before commercial use.'
        : 'No blocking or warning issue is registered for the current drawing.',
    recommendedAction: blocked
      ? 'Restore the critical evidence before commercial review.'
      : limited
        ? 'Proceed only as engineer-in-loop assisted review and keep warnings visible in the report.'
        : 'Proceed with assisted commercial review and retain provenance evidence.',
    manifestStatus,
    computedStatus,
    issueCount: issues.length,
    counts,
    issues,
  };
}
