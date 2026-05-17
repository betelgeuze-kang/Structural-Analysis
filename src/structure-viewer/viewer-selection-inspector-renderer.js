function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function checklistTone(status = '') {
  if (status === 'ready') return 'success';
  if (status === 'blocked') return 'danger';
  return 'warn';
}

export function buildSelectionInspectorHtml(explanation = {}, {
  hasElement = false,
} = {}) {
  if (!hasElement) {
    return '<div class="panel-placeholder">Select a member to see section, material, load, D/C, optimization delta, and evidence status.</div>';
  }
  const groups = Array.isArray(explanation.groups) && explanation.groups.length
    ? explanation.groups
    : [{ title: 'Member Evidence', rows: Array.isArray(explanation.rows) ? explanation.rows : [] }];
  const checklist = Array.isArray(explanation.checklist) ? explanation.checklist : [];
  return `
    <div class="explainability-header">
      <strong>${escapeHtml(explanation.title)}</strong>
      <span class="project-status-badge project-status-badge--${escapeHtml(explanation.reviewTone)}">${escapeHtml(explanation.reviewStatus)}</span>
    </div>
    <div class="selection-inspector-groups">
      ${groups.map(group => `
        <div class="selection-inspector-group">
          <strong>${escapeHtml(group.title)}</strong>
          ${(group.rows || []).map(row => `
            <div class="explainability-row">
              <span>${escapeHtml(row.label)}</span>
              <div>
                <strong class="prop-value--${escapeHtml(row.tone)}">${escapeHtml(row.value)}</strong>
                <small>${escapeHtml(row.evidence)}${row.source ? ` | ${escapeHtml(row.source)}` : ''}</small>
              </div>
            </div>`).join('')}
        </div>`).join('')}
    </div>
    <div class="explainability-checklist">
      ${checklist.map(item => `<div><span>${escapeHtml(item.label)}</span><span class="explainability-chip--${escapeHtml(checklistTone(item.status))}">${escapeHtml(item.status)}</span></div>`).join('')}
    </div>`;
}
