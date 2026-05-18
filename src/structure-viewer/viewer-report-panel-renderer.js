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
  reviewTask = null,
  solverReceipt = null,
  commercialCrosswalk = null,
  commercialMapper = null,
  importPreview = null,
  ingestPreview = null,
  drawingSheetPackage = null,
  lastExport = null,
  reviewNote = '',
} = {}) {
  const verification = comparison.verification || {};
  const verificationTone = verification.status === 'verified' ? 'success' : verification.status === 'missing' ? 'danger' : 'accent';
  const rows = Array.isArray(comparison.rows) ? comparison.rows : [];
  const crosswalkRows = Array.isArray(commercialCrosswalk?.rows) ? commercialCrosswalk.rows : [];
  const mapperRows = Array.isArray(commercialMapper?.rows) ? commercialMapper.rows : [];
  const mapperPresets = Array.isArray(commercialMapper?.presets) ? commercialMapper.presets : [];
  const sheetRows = Array.isArray(drawingSheetPackage?.sheets) ? drawingSheetPackage.sheets : [];
  const ingestRenderableLabel = ingestPreview?.renderable_payload_available
    ? ` · renderable ${ingestPreview.renderable_payload_kind || 'model'} · elements ${ingestPreview.renderable_element_count || 0} · segments ${ingestPreview.renderable_segment_count || 0}`
    : '';
  return `
    <div class="prop-row"><span class="prop-label">Project</span><span class="prop-value">${escapeHtml(workspace.projectTitle || workspace.projectId || '--')}</span></div>
    <div class="prop-row"><span class="prop-label">Drawing</span><span class="prop-value">${escapeHtml(workspace.drawingTitle || workspace.drawingId || '--')}</span></div>
    <div class="prop-row"><span class="prop-label">Variant</span><span class="prop-value">${escapeHtml(workspace.variant || '--')}</span></div>
    <div class="prop-row"><span class="prop-label">Review Card</span><span class="prop-value prop-value--${escapeHtml(drawingReview.tone || 'accent')}">${escapeHtml(drawingReview.label || 'Review pending')}</span></div>
    <div class="prop-row"><span class="prop-label">Comparison</span><span class="prop-value prop-value--${escapeHtml(comparison.status === 'ready' ? 'success' : 'accent')}">${escapeHtml(comparison.headline)}</span></div>
    <div class="prop-row"><span class="prop-label">Count Check</span><span class="prop-value prop-value--${escapeHtml(verificationTone)}">${escapeHtml(verification.label || 'Comparison evidence pending')}</span></div>
    <div class="prop-row"><span class="prop-label">Count Source</span><span class="prop-value">${escapeHtml(verification.source || '--')}</span></div>
    <div class="prop-row"><span class="prop-label">Review Task</span><span class="prop-value prop-value--${escapeHtml(reviewTask?.tone || 'warn')}">${escapeHtml(reviewTask?.label || '확인 필요')}</span></div>
    <div class="prop-row"><span class="prop-label">Solver Receipt</span><span class="prop-value prop-value--${escapeHtml(solverReceipt?.tone || 'warn')}">${escapeHtml(solverReceipt?.label || 'solver receipt pending')}</span></div>
    <div class="prop-row"><span class="prop-label">Sheet Package</span><span class="prop-value prop-value--${escapeHtml(drawingSheetPackage?.status === 'linked' ? 'success' : drawingSheetPackage?.status === 'partial' ? 'warn' : 'neutral')}">${escapeHtml(drawingSheetPackage?.summary || 'drawing sheet package pending')}</span></div>
    <div class="drawing-sheet-link-preview">
      ${sheetRows.length ? sheetRows.slice(0, 4).map(row => `<a class="prop-link" href="${escapeHtml(row.href || '#')}" target="_blank" rel="noopener">${escapeHtml(row.label || row.sheet_name)}</a>`).join(' · ') : '<span class="panel-placeholder">No SVG sheet callout links attached.</span>'}
    </div>
    <div class="prop-row"><span class="prop-label">Tool Crosswalk</span><span class="prop-value prop-value--${escapeHtml(commercialCrosswalk?.tone || 'neutral')}">${escapeHtml(commercialCrosswalk?.summary || 'commercial tool crosswalk pending')}</span></div>
    <div class="prop-row"><span class="prop-label">CSV Mapper</span><span class="prop-value prop-value--accent">${escapeHtml(commercialMapper?.summary || 'commercial CSV mapper pending')}</span></div>
    <div class="prop-row"><span class="prop-label">Import Preview</span><span class="prop-value prop-value--${escapeHtml(importPreview?.blocked ? 'danger' : importPreview ? 'success' : 'neutral')}">${escapeHtml(importPreview ? `${importPreview.blocked ? 'blocked' : 'mergeable'} · ${importPreview.incoming_counts?.reviewTasks || 0} tasks · ${importPreview.incoming_counts?.receiptIndex || 0} receipts` : '--')}</span></div>
    <div class="prop-row"><span class="prop-label">Evidence Ingest</span><span class="prop-value prop-value--${escapeHtml((ingestPreview?.blocked_issues || []).length ? 'warn' : ingestPreview ? 'success' : 'neutral')}">${escapeHtml(ingestPreview ? `${ingestPreview.source_type || '--'} · ${ingestPreview.drawing_count || 0} drawings · ${(ingestPreview.blocked_issues || []).length} blocked${ingestRenderableLabel}` : '--')}</span></div>
    ${rows.map(row => `<div class="prop-row"><span class="prop-label">${escapeHtml(row.label)}</span><span class="prop-value prop-value--${escapeHtml(row.tone)}">${escapeHtml(row.delta || row.value)}</span></div>`).join('')}
    <div class="panel-field report-note-field">
      <label for="review-task-status-select">Review Task</label>
      <select id="review-task-status-select">
        ${['needs_check', 'approved', 'hold', 'rerun_required'].map(status => `<option value="${status}"${status === reviewTask?.status ? ' selected' : ''}>${escapeHtml(status.replaceAll('_', ' '))}</option>`).join('')}
      </select>
    </div>
    <div class="panel-field report-note-field">
      <label for="review-note-input">Review Note</label>
      <textarea id="review-note-input" rows="3" placeholder="Local engineer-in-loop note">${escapeHtml(reviewNote)}</textarea>
    </div>
    <input id="project-bundle-import-input" type="file" accept="application/json,.json" hidden onchange="previewProjectBundleImportFromInput(event)"/>
    <input id="evidence-ingest-input" type="file" accept=".csv,.json,.ifc,text/csv,application/json" hidden onchange="previewEvidenceIngestFromInput(event)"/>
    <div class="panel-field report-note-field">
      <label for="evidence-ingest-source-select">Evidence Ingest</label>
      <select id="evidence-ingest-source-select">
        ${['auto', 'csv', 'json', 'ifc'].map(source => `<option value="${source}">${escapeHtml(source)}</option>`).join('')}
      </select>
    </div>
    <div class="panel-field report-note-field">
      <label for="commercial-tool-mapper-select">Commercial Tool Mapper</label>
      <select id="commercial-tool-mapper-select" onchange="setCommercialToolMapperProfile(this.value)">
        <option value="auto"${commercialMapper?.requestedProfile === 'auto' ? ' selected' : ''}>Auto detect</option>
        ${mapperPresets.map(preset => `<option value="${escapeHtml(preset.profile)}"${commercialMapper?.requestedProfile !== 'auto' && preset.profile === commercialMapper?.profile ? ' selected' : ''}>${escapeHtml(preset.label)}</option>`).join('')}
      </select>
    </div>
    <div class="commercial-mapper-preview">
      ${mapperRows.slice(0, 6).map(row => `<div class="prop-row"><span class="prop-label">${escapeHtml(row.field)}</span><span class="prop-value">${escapeHtml(row.label)}</span></div>`).join('')}
    </div>
    <div class="commercial-crosswalk-table">
      ${crosswalkRows.length ? crosswalkRows.slice(0, 8).map(row => {
        const selectableMember = row.viewerMemberId && row.viewerMemberId !== '--' ? row.viewerMemberId : '';
        return `<button type="button" class="member-comparison-row member-comparison-row--${escapeHtml(row.tone)}" data-commercial-crosswalk-member="${escapeHtml(selectableMember)}" data-commercial-crosswalk-status="${escapeHtml(row.status)}"${selectableMember ? '' : ' disabled'}><span>${escapeHtml(row.status)} · ${escapeHtml(row.externalMemberId)}</span><strong>${escapeHtml(row.externalSection)} / ${escapeHtml(row.viewerSection)}</strong><small>${escapeHtml(row.sourceTool || row.sourceProfile)} · D/C ${escapeHtml(row.externalDcr)} / ${escapeHtml(row.viewerDcr)} · ${escapeHtml(row.evidence)}</small></button>`;
      }).join('') : '<div class="panel-placeholder">Commercial tool crosswalk rows appear after CSV/JSON ingest.</div>'}
    </div>
    <div class="prop-row"><span class="prop-label">Last Export</span><span class="prop-value">${escapeHtml(lastExport?.filename || '--')}</span></div>
    <div class="panel-actions">
      <button id="report-panel-export-html-button" type="button" onclick="exportWorkspaceHtmlReport()">Export HTML</button>
      <button type="button" onclick="exportWorkspaceAuditJsonl()">Export Audit</button>
      <button type="button" onclick="exportProjectBundleJson()">Export Bundle</button>
      <button type="button" onclick="document.getElementById('project-bundle-import-input')?.click()">Import Bundle</button>
      <button type="button" onclick="mergeProjectBundleImportPreview()">Merge Preview</button>
      <button type="button" onclick="document.getElementById('evidence-ingest-input')?.click()">Ingest Evidence</button>
      <button type="button" onclick="attachEvidenceIngestPreview()">Attach Ingest</button>
      <button type="button" onclick="isolateFirstCommercialCrosswalkMismatch()">Isolate Mismatch</button>
      <button type="button" onclick="saveReviewTask()">Save Task</button>
      <button type="button" onclick="saveReviewNote()">Save Note</button>
      <button type="button" onclick="copyCurrentDeepLink()">Copy Link</button>
    </div>`;
}
