function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function normalizeText(value) {
  return String(value ?? '').trim();
}

function resolveStatusTone(status = '') {
  const normalized = normalizeText(status).toLowerCase();
  if (normalized === 'linked') return 'success';
  if (normalized === 'partial') return 'warn';
  if (normalized === 'missing') return 'danger';
  return 'neutral';
}

function resolveReviewTone(review = {}) {
  const tone = normalizeText(review.tone).toLowerCase();
  return ['success', 'warn', 'danger', 'accent', 'neutral'].includes(tone) ? tone : 'neutral';
}

function buildDrawingHandoffPreviewHtml({
  sheets = [],
  sheetPackage = {},
  revision = '',
  calloutId = '',
  calloutLabel = '',
  memberId = '',
} = {}) {
  const activeSheetName = normalizeText(sheetPackage.active_sheet_name);
  const activeSheet = sheets.find(sheet => normalizeText(sheet?.sheet_name) === activeSheetName)
    || (sheets[0] && typeof sheets[0] === 'object' ? sheets[0] : {});
  const sheetName = normalizeText(activeSheet.sheet_name || sheetPackage.primary_sheet_name) || 'no_sheet';
  const sheetLabel = normalizeText(activeSheet.label || sheetName) || 'Primary sheet';
  const sheetHref = normalizeText(activeSheet.href || sheetPackage.primary_sheet_href);
  const previewRevision = normalizeText(activeSheet.revision || revision) || 'unrevisioned';
  const previewCallout = normalizeText(activeSheet.callout_id || calloutId) || '--';
  const previewMember = normalizeText(activeSheet.member_id || memberId) || '--';
  const previewStatus = normalizeText(sheetPackage.status) || 'missing';
  const previewTitle = `${sheetLabel} ${sheetName}`;
  const linkClass = `drawing-handoff-preview${sheetHref ? '' : ' is-disabled'}`;

  return `<a class="${linkClass}" href="${escapeHtml(sheetHref || '#')}" target="_blank" rel="noopener" data-drawing-handoff-preview data-drawing-handoff-preview-sheet="${escapeHtml(sheetName)}" data-drawing-handoff-preview-callout="${escapeHtml(previewCallout)}" data-drawing-handoff-preview-link aria-disabled="${sheetHref ? 'false' : 'true'}" aria-label="${escapeHtml(`Open ${previewTitle}`)}">
    <svg class="drawing-handoff-preview__svg" viewBox="0 0 286 128" role="img" aria-label="${escapeHtml(`Sheet preview ${previewTitle}`)}">
      <rect class="drawing-handoff-preview__page" x="8" y="8" width="270" height="112" rx="4"></rect>
      <path class="drawing-handoff-preview__grid" d="M32 24h184M32 44h184M32 64h184M32 84h184M32 104h184M52 22v84M92 22v84M132 22v84M172 22v84M212 22v84"></path>
      <path class="drawing-handoff-preview__core" d="M102 42h60v44h-60zM112 50h40v28h-40z"></path>
      <path class="drawing-handoff-preview__member" d="M52 42h160M52 64h160M52 86h160M72 24v80M132 24v80M192 24v80"></path>
      <path class="drawing-handoff-preview__callout-leader" d="M204 44l34-18h26"></path>
      <circle class="drawing-handoff-preview__callout-dot" cx="204" cy="44" r="6"></circle>
      <rect class="drawing-handoff-preview__callout-tag" x="228" y="15" width="42" height="18" rx="3"></rect>
      <text class="drawing-handoff-preview__callout-text" x="249" y="28" text-anchor="middle" data-drawing-handoff-preview-callout-text>${escapeHtml(previewCallout)}</text>
      <text class="drawing-handoff-preview__sheet-text" x="20" y="116" data-drawing-handoff-preview-sheet-text>${escapeHtml(sheetName)}</text>
      <text class="drawing-handoff-preview__rev-text" x="222" y="116" data-drawing-handoff-preview-revision-text>${escapeHtml(previewRevision)}</text>
    </svg>
    <div class="drawing-handoff-preview__meta">
      <span>Sheet Preview</span>
      <strong data-drawing-handoff-preview-label>${escapeHtml(sheetLabel)}</strong>
      <small data-drawing-handoff-preview-meta>${escapeHtml(calloutLabel)} · ${escapeHtml(previewMember)} · ${escapeHtml(previewStatus)}</small>
    </div>
  </a>`;
}

export function buildDrawingHandoffPanelHtml({
  workspace = {},
  drawingReview = {},
  drawingSheetPackage = {},
} = {}) {
  const sheetPackage = drawingSheetPackage && typeof drawingSheetPackage === 'object' ? drawingSheetPackage : {};
  const sheets = Array.isArray(sheetPackage.sheets) ? sheetPackage.sheets : [];
  const status = normalizeText(sheetPackage.status) || 'missing';
  const statusTone = resolveStatusTone(status);
  const reviewTone = resolveReviewTone(drawingReview);
  const deepLinkUrl = normalizeText(sheetPackage.deep_link_url);
  const activeSheetName = normalizeText(sheetPackage.active_sheet_name || sheetPackage.primary_sheet_name || sheets[0]?.sheet_name);
  const activeSheet = sheets.find(sheet => normalizeText(sheet?.sheet_name) === activeSheetName)
    || (sheets[0] && typeof sheets[0] === 'object' ? sheets[0] : {});
  const primarySheetHref = normalizeText(activeSheet.href || sheetPackage.primary_sheet_href || sheets[0]?.href);
  const primarySheetLabel = normalizeText(activeSheet.sheet_name || activeSheet.label || sheetPackage.primary_sheet_name || sheets[0]?.sheet_name || 'Open sheet');
  const drawingTitle = normalizeText(sheetPackage.drawing_title || workspace.drawingTitle || workspace.drawingId) || 'Drawing handoff';
  const revision = normalizeText(sheetPackage.revision) || 'unrevisioned';
  const calloutId = normalizeText(sheetPackage.callout_id) || '--';
  const calloutLabel = normalizeText(sheetPackage.callout_label) || 'Active selection';
  const memberId = normalizeText(sheetPackage.member_id) || '--';
  const previewHtml = buildDrawingHandoffPreviewHtml({
    sheets,
    sheetPackage,
    revision,
    calloutId,
    calloutLabel,
    memberId,
  });
  const sheetButtons = sheets.slice(0, 4).map((sheet) => {
    const href = normalizeText(sheet.href);
    const label = normalizeText(sheet.label || sheet.sheet_name) || 'Sheet';
    const sheetName = normalizeText(sheet.sheet_name) || label;
    const sheetRevision = normalizeText(sheet.revision) || revision;
    const sheetCallout = normalizeText(sheet.callout_id) || calloutId;
    const sheetMember = normalizeText(sheet.member_id || memberId) || '--';
    const isActive = sheetName === (activeSheetName || primarySheetLabel);
    const className = `drawing-handoff-sheet${href ? '' : ' is-disabled'}${isActive ? ' is-active' : ''}`;
    return `<a class="${className}" href="${escapeHtml(href || '#')}" target="_blank" rel="noopener" data-drawing-handoff-sheet="${escapeHtml(sheetName)}" data-drawing-handoff-sheet-label="${escapeHtml(label)}" data-drawing-handoff-sheet-href="${escapeHtml(href)}" data-drawing-handoff-sheet-revision="${escapeHtml(sheetRevision)}" data-drawing-handoff-sheet-callout="${escapeHtml(sheetCallout)}" data-drawing-handoff-sheet-member="${escapeHtml(sheetMember)}" aria-current="${isActive ? 'true' : 'false'}" aria-disabled="${href ? 'false' : 'true'}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(sheetName)}</strong>
      <small>${escapeHtml(sheetRevision)} · ${escapeHtml(sheetCallout)}</small>
    </a>`;
  }).join('');

  return `<div class="drawing-handoff-panel" data-drawing-handoff-panel data-drawing-handoff-status="${escapeHtml(status)}">
    <div class="drawing-handoff-header">
      <div>
        <span>Drawing Handoff</span>
        <strong>${escapeHtml(drawingTitle)}</strong>
      </div>
      <span class="drawing-handoff-badge drawing-handoff-badge--${escapeHtml(statusTone)}">${escapeHtml(status)}</span>
    </div>
    <div class="drawing-handoff-grid">
      <div><span>Revision</span><strong>${escapeHtml(revision)}</strong></div>
      <div><span>Member</span><strong>${escapeHtml(memberId)}</strong></div>
      <div><span>Sheets</span><strong>${escapeHtml(String(sheetPackage.sheet_count ?? sheets.length ?? 0))}</strong></div>
      <div><span>Review</span><strong class="drawing-handoff-tone--${escapeHtml(reviewTone)}">${escapeHtml(drawingReview.label || 'Review pending')}</strong></div>
    </div>
    ${previewHtml}
    <div class="drawing-handoff-callout">
      <span>Active callout</span>
      <strong>${escapeHtml(calloutLabel)}</strong>
      <small>${escapeHtml(calloutId)}</small>
    </div>
    <div class="drawing-handoff-sheet-list">
      ${sheetButtons || '<div class="drawing-handoff-empty">No SVG sheet callout links attached.</div>'}
    </div>
    <div class="drawing-handoff-actions">
      <a class="${primarySheetHref ? '' : 'is-disabled'}" href="${escapeHtml(primarySheetHref || '#')}" target="_blank" rel="noopener" data-drawing-handoff-active-sheet-open data-drawing-handoff-active-sheet-name="${escapeHtml(primarySheetLabel)}" aria-disabled="${primarySheetHref ? 'false' : 'true'}">Open Active Sheet</a>
      <a class="${deepLinkUrl ? '' : 'is-disabled'}" href="${escapeHtml(deepLinkUrl || '#')}" target="_blank" rel="noopener">Open Deep Link</a>
      <button type="button" data-drawing-handoff-copy-link>Copy Link</button>
    </div>
  </div>`;
}
