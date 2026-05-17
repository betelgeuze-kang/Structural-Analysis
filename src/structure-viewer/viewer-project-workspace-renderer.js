function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function buildProjectDrawingListHtml(drawings = []) {
  if (!drawings.length) return '<div class="panel-placeholder">No drawings match the active project filter.</div>';
  return drawings.map((drawing) => `
    <button type="button" class="project-drawing-button${drawing.active ? ' is-active' : ''}" data-project-drawing="${escapeHtml(drawing.drawingId)}">
      <span><strong>${escapeHtml(drawing.drawingTitle)}</strong><small>${escapeHtml(drawing.sourceFamily)} | ${escapeHtml(drawing.comparisonLabel)} | ${escapeHtml(drawing.qualityFlags.join(', ') || 'no quality flags')}</small></span>
      <span class="project-drawing-badges">
        <span class="project-status-badge project-status-badge--${escapeHtml(drawing.statusTone)}">${escapeHtml(drawing.status)}</span>
        <span class="project-status-badge project-status-badge--${escapeHtml(drawing.verificationTone)}" title="${escapeHtml(drawing.verificationSource || '')}">${escapeHtml(drawing.verificationShortLabel || drawing.verificationLabel || 'count pending')}</span>
        <span class="project-status-badge project-status-badge--${escapeHtml(drawing.reviewTone || 'accent')}">${escapeHtml(drawing.issueCountLabel || '0 issues')}</span>
      </span>
    </button>`).join('');
}

export function buildProjectEvidencePanelHtml(evidence = {}) {
  const variants = Array.isArray(evidence.variants) ? evidence.variants : [];
  const rows = Array.isArray(evidence.rows) ? evidence.rows : [];
  const review = evidence.review || {};
  const issues = Array.isArray(review.issues) ? review.issues : [];
  if (!rows.length) return '<div class="panel-placeholder">No drawing evidence selected.</div>';
  return `
    <div class="project-evidence-header">
      <strong>${escapeHtml(evidence.title || 'Drawing Evidence')}</strong>
      <span class="project-status-badge project-status-badge--${escapeHtml(review.tone || evidence.verification?.tone || 'accent')}">${escapeHtml(review.label || evidence.verification?.shortLabel || 'count pending')}</span>
    </div>
    <div class="project-review-card project-review-card--${escapeHtml(review.tone || 'accent')}">
      <strong>${escapeHtml(review.label || 'Review status pending')}</strong>
      <span>${escapeHtml(review.reason || '--')}</span>
      <small>${escapeHtml(review.recommendedAction || '--')}</small>
    </div>
    <div class="project-evidence-grid">
      ${rows.map(row => `<span>${escapeHtml(row.label)}</span><strong class="prop-value--${escapeHtml(row.tone || 'neutral')}" title="${escapeHtml(row.value || '')}">${escapeHtml(row.value || '--')}</strong>`).join('')}
    </div>
    <div class="project-issue-list">
      ${issues.length ? issues.map(issue => `<div class="project-issue-row project-issue-row--${escapeHtml(issue.tone)}"><strong>${escapeHtml(issue.severity)}</strong><span>${escapeHtml(issue.label)}</span><small>${escapeHtml(issue.recommendedAction)}</small></div>`).join('') : '<div class="project-issue-row project-issue-row--success"><strong>ready</strong><span>No registered quality issue</span><small>Proceed with assisted review.</small></div>'}
    </div>
    <div class="project-evidence-variants">
      ${variants.map(variant => `<span class="project-variant-chip${variant.active ? ' is-active' : ''}" title="${escapeHtml(variant.artifactPath || variant.viewerPreset || '')}">${escapeHtml(variant.label || variant.variant)}</span>`).join('')}
    </div>`;
}

export function buildMemberComparisonPanelHtml(model = {}) {
  const filters = Array.isArray(model.filterOptions) ? model.filterOptions : [];
  const rows = Array.isArray(model.summaryRows) ? model.summaryRows : [];
  const items = Array.isArray(model.items) ? model.items : [];
  return `
    <div class="member-comparison-toolbar">
      ${filters.map(option => `<button type="button" class="${option.key === model.filter ? 'is-active' : ''}" data-member-comparison-filter="${escapeHtml(option.key)}">${escapeHtml(option.label)} <span>${escapeHtml(option.count)}</span></button>`).join('')}
    </div>
    <div class="member-comparison-highlight-status" data-member-comparison-highlight-count="${escapeHtml(model.highlightCount || 0)}">
      3D highlight ${escapeHtml(model.highlightCount || 0)} exact members · active ${escapeHtml(model.filter || 'changed')}
    </div>
    <div class="member-comparison-summary">
      ${rows.map(row => `<div><span>${escapeHtml(row.label)}</span><strong class="prop-value--${escapeHtml(row.tone)}">${escapeHtml(row.value)}</strong><small>${escapeHtml(row.evidence)}</small></div>`).join('')}
    </div>
    <div class="member-comparison-table">
      ${items.length ? items.map(item => `<button type="button" class="member-comparison-row member-comparison-row--${escapeHtml(item.tone)}" data-member-comparison-member="${escapeHtml(item.id)}"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.delta)}</strong><small>D/C ${escapeHtml(item.dcr)} | ${escapeHtml(item.weightCost)} | ${escapeHtml(item.evidence)}</small></button>`).join('') : `<div class="panel-placeholder">${escapeHtml(model.emptyText || 'No comparison rows.')}</div>`}
    </div>`;
}

export function buildProjectRecentListHtml(recentRows = []) {
  return recentRows.length
    ? recentRows.slice(0, 6).map(row => `<button type="button" class="project-recent-chip" data-project-recent-project="${escapeHtml(row.projectId)}" data-project-recent-drawing="${escapeHtml(row.drawingId)}" data-project-recent-variant="${escapeHtml(row.variant)}">${escapeHtml(row.drawingId || row.label || 'recent')}</button>`).join('')
    : '<div class="panel-placeholder">Recent project selections appear here.</div>';
}
