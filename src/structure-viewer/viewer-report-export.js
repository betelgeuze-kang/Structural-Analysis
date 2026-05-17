function normalizeText(value) {
  return String(value ?? '').trim();
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function slug(value, fallback = 'structure_viewer') {
  return normalizeText(value).replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toLowerCase() || fallback;
}

export function buildStructureViewerReportFilename({
  projectId = '',
  drawingId = '',
  variant = '',
  extension = 'html',
} = {}) {
  const variantPart = slug(variant, '');
  return `structure_viewer_report_${slug(projectId, 'project')}_${slug(drawingId, 'drawing')}${variantPart ? `_${variantPart}` : ''}.${extension}`;
}

export function buildStructureViewerReportHtml({
  workspace = {},
  data = {},
  selectedElement = null,
  explainability = null,
  comparison = null,
  drawingReview = null,
  memberComparison = null,
  screenshotDataUrl = '',
  reviewNote = '',
  generatedAt = new Date().toISOString(),
} = {}) {
  const meta = data?.meta && typeof data.meta === 'object' ? data.meta : {};
  const drawing = workspace?.drawing || {};
  const rows = Array.isArray(explainability?.rows) ? explainability.rows : [];
  const checklist = Array.isArray(explainability?.checklist) ? explainability.checklist : [];
  const comparisonRows = Array.isArray(comparison?.rows) ? comparison.rows : [];
  const reviewIssues = Array.isArray(drawingReview?.issues) ? drawingReview.issues : [];
  const memberRows = Array.isArray(memberComparison?.items) ? memberComparison.items : [];
  const memberSummaryRows = Array.isArray(memberComparison?.summaryRows) ? memberComparison.summaryRows : [];
  const verification = comparison?.verification && typeof comparison.verification === 'object'
    ? comparison.verification
    : {};
  const selected = selectedElement && typeof selectedElement === 'object' ? selectedElement : {};
  const qualityFlags = Array.isArray(drawing.quality_flags) ? drawing.quality_flags : [];
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Structure Viewer Report - ${escapeHtml(workspace.drawingTitle || meta.name || 'Project')}</title>
<style>
body{font-family:Arial,sans-serif;margin:32px;color:#17202a;line-height:1.45}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:16px;margin:24px 0 8px}
.muted{color:#667085}
.grid{display:grid;grid-template-columns:180px 1fr;gap:6px 14px}
.row{border-bottom:1px solid #e5e7eb;padding:7px 0}
.badge{display:inline-block;border:1px solid #cbd5e1;border-radius:999px;padding:3px 8px;margin:2px;font-size:12px}
.ready{color:#047857}.needs_review{color:#b45309}.blocked{color:#b91c1c}
.review-card{border:1px solid #d0d5dd;border-radius:8px;padding:10px;margin-top:8px}
.screenshot{max-width:100%;border:1px solid #d0d5dd;border-radius:8px;margin-top:8px}
table{width:100%;border-collapse:collapse;margin-top:8px}
td,th{border-bottom:1px solid #e5e7eb;text-align:left;padding:7px;vertical-align:top}
th{font-size:12px;text-transform:uppercase;color:#667085}
</style>
</head>
<body>
<h1>${escapeHtml(workspace.projectTitle || 'Structure Project')}</h1>
<div class="muted">${escapeHtml(workspace.drawingTitle || meta.name || '--')} | variant=${escapeHtml(workspace.variant || '--')} | generated=${escapeHtml(generatedAt)}</div>

<h2>Project Summary</h2>
<div class="grid">
<div class="row muted">Project</div><div class="row">${escapeHtml(workspace.projectId || '--')}</div>
<div class="row muted">Drawing</div><div class="row">${escapeHtml(workspace.drawingId || '--')}</div>
<div class="row muted">Review status</div><div class="row ${escapeHtml(drawing.commercial_review_status || '')}">${escapeHtml(drawing.commercial_review_status || '--')}</div>
<div class="row muted">Review card</div><div class="row ${escapeHtml(drawingReview?.tone || '')}">${escapeHtml(drawingReview?.label || '--')}</div>
<div class="row muted">Source family</div><div class="row">${escapeHtml(drawing.source_family || meta.source_mode || '--')}</div>
<div class="row muted">Source</div><div class="row">${escapeHtml(drawing.artifact_path || meta.source_path || '--')}</div>
<div class="row muted">Model size</div><div class="row">nodes=${escapeHtml(Array.isArray(data.nodes) ? data.nodes.length : '--')} | elements=${escapeHtml(Array.isArray(data.elements) ? data.elements.length : '--')}</div>
</div>

<h2>Drawing Review</h2>
<div class="review-card">
<strong>${escapeHtml(drawingReview?.label || 'Review pending')}</strong>
<div>${escapeHtml(drawingReview?.reason || '--')}</div>
<div class="muted">${escapeHtml(drawingReview?.recommendedAction || '--')}</div>
</div>
<table>
<thead><tr><th>Severity</th><th>Issue</th><th>Recommended Action</th></tr></thead>
<tbody>
${reviewIssues.length ? reviewIssues.map((issue) => `<tr><td>${escapeHtml(issue.severity)}</td><td>${escapeHtml(issue.label)}</td><td>${escapeHtml(issue.recommendedAction)}</td></tr>`).join('') : '<tr><td>ready</td><td>No registered quality issue</td><td>Proceed with assisted review.</td></tr>'}
</tbody>
</table>

<h2>Before / Optimized Context</h2>
<div class="grid">
<div class="row muted">Baseline</div><div class="row">${escapeHtml(drawing.baseline_ref || '--')}</div>
<div class="row muted">Optimized</div><div class="row">${escapeHtml(drawing.optimized_ref || '--')}</div>
<div class="row muted">Comparison</div><div class="row">${escapeHtml(comparison?.headline || 'Before/optimized comparison evidence pending')}</div>
<div class="row muted">Count verification</div><div class="row">${escapeHtml(verification.label || 'Comparison evidence pending')}</div>
<div class="row muted">Count source</div><div class="row">${escapeHtml(verification.source || '--')}</div>
<div class="row muted">Quality flags</div><div class="row">${qualityFlags.length ? qualityFlags.map((flag) => `<span class="badge">${escapeHtml(flag)}</span>`).join(' ') : '<span class="badge ready">none</span>'}</div>
</div>

<h2>Optimization Summary</h2>
<table>
<thead><tr><th>Signal</th><th>Value</th><th>Delta</th><th>Evidence</th><th>Source</th></tr></thead>
<tbody>
${comparisonRows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${escapeHtml(row.value)}</td><td>${escapeHtml(row.delta)}</td><td>${escapeHtml(row.evidence)}</td><td>${escapeHtml(row.source)}</td></tr>`).join('')}
</tbody>
</table>

<h2>Before / After Member Comparison</h2>
<div class="muted">Active filter=${escapeHtml(memberComparison?.filter || '--')} | 3D highlight exact members=${escapeHtml(memberComparison?.highlightCount ?? '--')}</div>
<table>
<thead><tr><th>Signal</th><th>Value</th><th>Evidence</th></tr></thead>
<tbody>
${memberSummaryRows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${escapeHtml(row.value)}</td><td>${escapeHtml(row.evidence)}</td></tr>`).join('')}
</tbody>
</table>
<table>
<thead><tr><th>Member</th><th>Change</th><th>D/C</th><th>Weight / Cost</th><th>Evidence</th></tr></thead>
<tbody>
${memberRows.length ? memberRows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${escapeHtml(row.delta)}</td><td>${escapeHtml(row.dcr)}</td><td>${escapeHtml(row.weightCost)}</td><td>${escapeHtml(row.evidence)}</td></tr>`).join('') : '<tr><td colspan="5">No comparison rows for the active filter.</td></tr>'}
</tbody>
</table>

<h2>Selected Member</h2>
<div class="grid">
<div class="row muted">Member</div><div class="row">${escapeHtml(selected.member_id || selected.case_id || selected.id || '--')}</div>
<div class="row muted">Section</div><div class="row">${escapeHtml(selected.section || selected.section_name || '--')}</div>
<div class="row muted">Type</div><div class="row">${escapeHtml(selected.type || '--')}</div>
</div>

<h2>Explainability</h2>
<table>
<thead><tr><th>Signal</th><th>Value</th><th>Evidence</th><th>Source</th></tr></thead>
<tbody>
${rows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${escapeHtml(row.value)}</td><td>${escapeHtml(row.evidence)}</td><td>${escapeHtml(row.source)}</td></tr>`).join('')}
</tbody>
</table>

<h2>Review Note</h2>
<div class="review-card">${escapeHtml(reviewNote || '--')}</div>

<h2>Viewer Screenshot</h2>
${screenshotDataUrl ? `<img class="screenshot" alt="viewer screenshot marker" src="${escapeHtml(screenshotDataUrl)}"/>` : '<div class="muted">viewer screenshot marker: unavailable</div>'}

<h2>Engineer-in-loop Checklist</h2>
<table>
<thead><tr><th>Item</th><th>Status</th></tr></thead>
<tbody>
${checklist.map((item) => `<tr><td>${escapeHtml(item.label)}</td><td class="${escapeHtml(item.status)}">${escapeHtml(item.status)}</td></tr>`).join('')}
</tbody>
</table>
</body>
</html>`;
}

export function buildStructureViewerReportExport({
  workspace = {},
  data = {},
  selectedElement = null,
  explainability = null,
  comparison = null,
  drawingReview = null,
  memberComparison = null,
  screenshotDataUrl = '',
  reviewNote = '',
  generatedAt = new Date().toISOString(),
} = {}) {
  const html = buildStructureViewerReportHtml({
    workspace,
    data,
    selectedElement,
    explainability,
    comparison,
    drawingReview,
    memberComparison,
    screenshotDataUrl,
    reviewNote,
    generatedAt,
  });
  return {
    html,
    filename: buildStructureViewerReportFilename({
      projectId: workspace.projectId,
      drawingId: workspace.drawingId,
      variant: workspace.variant,
      extension: 'html',
    }),
    generatedAt,
  };
}
