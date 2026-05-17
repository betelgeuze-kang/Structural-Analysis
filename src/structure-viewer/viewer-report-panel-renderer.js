function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function buildReportExportPanelHtml({
  workspace = {},
  comparison = {},
  drawingReview = {},
  lastExport = null,
  reviewNote = '',
} = {}) {
  const verification = comparison.verification || {};
  const verificationTone = verification.status === 'verified' ? 'success' : verification.status === 'missing' ? 'danger' : 'accent';
  const rows = Array.isArray(comparison.rows) ? comparison.rows : [];
  return `
    <div class="prop-row"><span class="prop-label">Project</span><span class="prop-value">${escapeHtml(workspace.projectTitle || workspace.projectId || '--')}</span></div>
    <div class="prop-row"><span class="prop-label">Drawing</span><span class="prop-value">${escapeHtml(workspace.drawingTitle || workspace.drawingId || '--')}</span></div>
    <div class="prop-row"><span class="prop-label">Variant</span><span class="prop-value">${escapeHtml(workspace.variant || '--')}</span></div>
    <div class="prop-row"><span class="prop-label">Review Card</span><span class="prop-value prop-value--${escapeHtml(drawingReview.tone || 'accent')}">${escapeHtml(drawingReview.label || 'Review pending')}</span></div>
    <div class="prop-row"><span class="prop-label">Comparison</span><span class="prop-value prop-value--${escapeHtml(comparison.status === 'ready' ? 'success' : 'accent')}">${escapeHtml(comparison.headline)}</span></div>
    <div class="prop-row"><span class="prop-label">Count Check</span><span class="prop-value prop-value--${escapeHtml(verificationTone)}">${escapeHtml(verification.label || 'Comparison evidence pending')}</span></div>
    <div class="prop-row"><span class="prop-label">Count Source</span><span class="prop-value">${escapeHtml(verification.source || '--')}</span></div>
    ${rows.map(row => `<div class="prop-row"><span class="prop-label">${escapeHtml(row.label)}</span><span class="prop-value prop-value--${escapeHtml(row.tone)}">${escapeHtml(row.delta || row.value)}</span></div>`).join('')}
    <div class="panel-field report-note-field">
      <label for="review-note-input">Review Note</label>
      <textarea id="review-note-input" rows="3" placeholder="Local engineer-in-loop note">${escapeHtml(reviewNote)}</textarea>
    </div>
    <div class="prop-row"><span class="prop-label">Last Export</span><span class="prop-value">${escapeHtml(lastExport?.filename || '--')}</span></div>
    <div class="panel-actions">
      <button id="report-panel-export-html-button" type="button" onclick="exportWorkspaceHtmlReport()">Export HTML</button>
      <button type="button" onclick="exportWorkspaceAuditJsonl()">Export Audit</button>
      <button type="button" onclick="exportProjectBundleJson()">Export Bundle</button>
      <button type="button" onclick="saveReviewNote()">Save Note</button>
      <button type="button" onclick="copyCurrentDeepLink()">Copy Link</button>
    </div>`;
}
