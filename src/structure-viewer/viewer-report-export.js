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
  reviewTask = null,
  solverReceipt = null,
  commercialCrosswalk = null,
  commercialMapper = null,
  importPreview = null,
  ingestPreview = null,
  drawingSheetPackage = null,
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
  const importIssues = Array.isArray(importPreview?.issues) ? importPreview.issues : [];
  const ingestIssues = Array.isArray(ingestPreview?.blocked_issues) ? ingestPreview.blocked_issues : [];
  const lineageRows = Array.isArray(explainability?.lineageDrilldown?.rows) ? explainability.lineageDrilldown.rows : [];
  const crosswalkRows = Array.isArray(commercialCrosswalk?.rows) ? commercialCrosswalk.rows : [];
  const mapperRows = Array.isArray(commercialMapper?.rows) ? commercialMapper.rows : [];
  const sheetPackageRows = Array.isArray(drawingSheetPackage?.rows) ? drawingSheetPackage.rows : [];
  const sheetRows = Array.isArray(drawingSheetPackage?.sheets) ? drawingSheetPackage.sheets : [];
  const ingestRenderableLabel = ingestPreview?.renderable_payload_available
    ? `${ingestPreview.renderable_payload_kind || 'renderable'} · nodes=${ingestPreview.renderable_node_count || 0} · elements=${ingestPreview.renderable_element_count || 0} · segments=${ingestPreview.renderable_segment_count || 0}`
    : '--';
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

<h2>Drawing Sheet Package</h2>
<div class="grid">
<div class="row muted">Status</div><div class="row">${escapeHtml(drawingSheetPackage?.status || 'missing')}</div>
<div class="row muted">Revision</div><div class="row">${escapeHtml(drawingSheetPackage?.revision || 'unrevisioned')}</div>
<div class="row muted">Callout</div><div class="row">${escapeHtml(drawingSheetPackage?.callout_label || '--')} | ${escapeHtml(drawingSheetPackage?.callout_id || '--')}</div>
<div class="row muted">Deep-link</div><div class="row">${drawingSheetPackage?.deep_link_url ? `<a href="${escapeHtml(drawingSheetPackage.deep_link_url)}">Open viewer deep-link</a>` : '--'}</div>
<div class="row muted">Primary SVG sheet</div><div class="row">${drawingSheetPackage?.primary_sheet_href ? `<a href="${escapeHtml(drawingSheetPackage.primary_sheet_href)}">${escapeHtml(drawingSheetPackage.primary_sheet_name || 'Open SVG sheet')}</a>` : escapeHtml(drawingSheetPackage?.primary_sheet_name || '--')}</div>
</div>
<table>
<thead><tr><th>Sheet</th><th>SVG / Deep-link</th><th>Revision</th><th>Callout</th></tr></thead>
<tbody>
${sheetRows.length ? sheetRows.map((row) => `<tr><td>${escapeHtml(row.label || row.sheet_name)}</td><td>${row.href ? `<a href="${escapeHtml(row.href)}">${escapeHtml(row.sheet_name || 'open sheet')}</a>` : escapeHtml(row.sheet_name || '--')}</td><td>${escapeHtml(row.revision || '--')}</td><td>${escapeHtml(row.callout_id || '--')}</td></tr>`).join('') : '<tr><td colspan="4">No SVG sheet links are attached for this selection.</td></tr>'}
</tbody>
</table>

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
<div class="muted">Overlay state=${escapeHtml(memberComparison?.filter || '--')} | active layer count=${escapeHtml(memberComparison?.highlightCount ?? '--')}</div>
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

<h2>Review Task</h2>
<div class="grid">
<div class="row muted">Task status</div><div class="row ${escapeHtml(reviewTask?.tone || 'warn')}">${escapeHtml(reviewTask?.label || '확인 필요')}</div>
<div class="row muted">Task code</div><div class="row">${escapeHtml(reviewTask?.status || 'needs_check')}</div>
<div class="row muted">Reviewer note</div><div class="row">${escapeHtml(reviewTask?.note || reviewNote || '--')}</div>
<div class="row muted">Updated</div><div class="row">${escapeHtml(reviewTask?.updatedAt || '--')}</div>
</div>

<h2>Solver Receipt</h2>
<div class="grid">
<div class="row muted">Status</div><div class="row ${escapeHtml(solverReceipt?.tone || 'warn')}">${escapeHtml(solverReceipt?.label || 'solver receipt pending')}</div>
<div class="row muted">Source tool</div><div class="row">${escapeHtml(solverReceipt?.source_tool || '--')}</div>
<div class="row muted">Load combo</div><div class="row">${escapeHtml(solverReceipt?.load_combo || '--')}</div>
<div class="row muted">DCR before / after</div><div class="row">${escapeHtml(solverReceipt?.dcr_after !== null && solverReceipt?.dcr_after !== undefined ? `${solverReceipt?.dcr_before ?? '--'} -> ${solverReceipt.dcr_after}` : '--')}</div>
<div class="row muted">Governing constraint</div><div class="row">${escapeHtml(solverReceipt?.governing_constraint || '--')}</div>
<div class="row muted">Receipt path</div><div class="row">${escapeHtml(solverReceipt?.receipt_path || '--')}</div>
</div>

<h2>Commercial Tool Crosswalk</h2>
<div class="muted">${escapeHtml(commercialCrosswalk?.summary || 'commercial tool crosswalk pending')}</div>
<div class="muted">CSV mapper: ${escapeHtml(commercialMapper?.summary || '--')}</div>
<table>
<thead><tr><th>Status</th><th>External</th><th>Viewer</th><th>Section</th><th>DCR</th><th>Tool</th></tr></thead>
<tbody>
${crosswalkRows.length ? crosswalkRows.map((row) => `<tr><td>${escapeHtml(row.status)}</td><td>${escapeHtml(row.externalMemberId)}</td><td>${escapeHtml(row.viewerMemberId)}</td><td>${escapeHtml(row.externalSection)} / ${escapeHtml(row.viewerSection)}</td><td>${escapeHtml(row.externalDcr)} / ${escapeHtml(row.viewerDcr)}</td><td>${escapeHtml(row.sourceTool)}</td></tr>`).join('') : '<tr><td colspan="6">No commercial tool crosswalk rows attached.</td></tr>'}
</tbody>
</table>
<table>
<thead><tr><th>Canonical Field</th><th>Accepted Columns</th></tr></thead>
<tbody>
${mapperRows.length ? mapperRows.map((row) => `<tr><td>${escapeHtml(row.field)}</td><td>${escapeHtml(row.label)}</td></tr>`).join('') : '<tr><td colspan="2">No commercial CSV mapper selected.</td></tr>'}
</tbody>
</table>

<h2>Import / Lineage Summary</h2>
<div class="grid">
<div class="row muted">Import preview</div><div class="row">${escapeHtml(importPreview?.schema_version || 'none')}</div>
<div class="row muted">Import status</div><div class="row">${escapeHtml(importPreview ? (importPreview.blocked ? 'blocked' : 'mergeable') : '--')}</div>
<div class="row muted">Incoming tasks</div><div class="row">${escapeHtml(importPreview?.incoming_counts?.reviewTasks ?? '--')}</div>
<div class="row muted">Incoming receipts</div><div class="row">${escapeHtml(importPreview?.incoming_counts?.receiptIndex ?? '--')}</div>
<div class="row muted">Evidence ingest</div><div class="row">${escapeHtml(ingestPreview ? `${ingestPreview.source_type || '--'} · rows=${ingestPreview.row_count || 0} · drawings=${ingestPreview.drawing_count || 0}` : '--')}</div>
<div class="row muted">Renderable ingest</div><div class="row">${escapeHtml(ingestRenderableLabel)}</div>
</div>
<table>
<thead><tr><th>Severity</th><th>Issue</th><th>Value</th></tr></thead>
<tbody>
${importIssues.length ? importIssues.map((issue) => `<tr><td>${escapeHtml(issue.severity)}</td><td>${escapeHtml(issue.issue)}</td><td>${escapeHtml(issue.value)}</td></tr>`).join('') : '<tr><td>info</td><td>No bundle import issue registered</td><td>--</td></tr>'}
${ingestIssues.length ? ingestIssues.map((issue) => `<tr><td>warning</td><td>${escapeHtml(issue.issue)}</td><td>${escapeHtml(issue.drawing_id)}</td></tr>`).join('') : '<tr><td>info</td><td>No evidence ingest blocked issue registered</td><td>--</td></tr>'}
</tbody>
</table>

<h2>Lineage Drilldown</h2>
<div class="muted">${escapeHtml(explainability?.lineageDrilldown?.summary || '--')}</div>
<table>
<thead><tr><th>Stage</th><th>Value</th><th>Evidence</th><th>Source</th></tr></thead>
<tbody>
${lineageRows.length ? lineageRows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${escapeHtml(row.value)}</td><td>${escapeHtml(row.evidence)}</td><td>${escapeHtml(row.source)}</td></tr>`).join('') : '<tr><td colspan="4">Lineage evidence pending.</td></tr>'}
</tbody>
</table>

<h2>Sheet / Callout Evidence Rows</h2>
<table>
<thead><tr><th>Signal</th><th>Value</th><th>Evidence</th></tr></thead>
<tbody>
${sheetPackageRows.length ? sheetPackageRows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${row.href ? `<a href="${escapeHtml(row.href)}">${escapeHtml(row.value)}</a>` : escapeHtml(row.value)}</td><td>${escapeHtml(row.evidence)}</td></tr>`).join('') : '<tr><td colspan="3">Sheet package evidence pending.</td></tr>'}
</tbody>
</table>

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
  reviewTask = null,
  solverReceipt = null,
  commercialCrosswalk = null,
  commercialMapper = null,
  importPreview = null,
  ingestPreview = null,
  drawingSheetPackage = null,
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
    reviewTask,
    solverReceipt,
    commercialCrosswalk,
    commercialMapper,
    importPreview,
    ingestPreview,
    drawingSheetPackage,
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
