export const STRUCTURE_VIEWER_DRAWING_SHEET_PACKAGE_SCHEMA_VERSION = 'structure-viewer-drawing-sheet-package.v1';

function normalizeText(value) {
  return String(value ?? '').trim();
}

function slug(value, fallback = 'sheet') {
  return normalizeText(value).replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toLowerCase() || fallback;
}

function resolveMemberId(selectedElement = {}) {
  return normalizeText(selectedElement.member_id || selectedElement.case_id || selectedElement.id);
}

function resolveRevision(workspace = {}) {
  const drawing = workspace.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const optimizationSummary = drawing.optimization_summary && typeof drawing.optimization_summary === 'object'
    ? drawing.optimization_summary
    : {};
  return normalizeText(
    drawing.revision_id
    || drawing.revision
    || drawing.review_revision
    || optimizationSummary.revision_id
    || optimizationSummary.revision
    || workspace.revision
  ) || 'unrevisioned';
}

function resolveSheetName(row = {}) {
  const explicit = normalizeText(row.sheet || row.sheet_name || row.name);
  if (explicit) return explicit;
  const href = normalizeText(row.href || row.url);
  if (!href) return '';
  try {
    const url = new URL(href, 'https://structure-viewer.local/');
    const filename = url.pathname.split('/').filter(Boolean).pop() || '';
    return filename.replace(/\.svg$/i, '');
  } catch (_err) {
    return '';
  }
}

function readUrlParam(href = '', name = '') {
  if (!href || !name) return '';
  try {
    return normalizeText(new URL(href, 'https://structure-viewer.local/').searchParams.get(name));
  } catch (_err) {
    return '';
  }
}

function normalizeSheetLink(row = {}, {
  fallbackMemberId = '',
  fallbackRevision = '',
  fallbackCalloutId = '',
} = {}) {
  const label = normalizeText(row.label || row.kind || row.sheet || row.sheet_name) || 'Sheet';
  const href = normalizeText(row.href || row.url);
  const sheetName = resolveSheetName(row) || slug(label);
  const memberId = normalizeText(row.member_id || row.memberId || readUrlParam(href, 'member') || fallbackMemberId);
  const revision = normalizeText(row.revision || row.revision_id || readUrlParam(href, 'revision') || fallbackRevision);
  const calloutId = normalizeText(row.callout_id || row.calloutId || readUrlParam(href, 'callout') || fallbackCalloutId);
  return {
    label,
    sheet_name: sheetName,
    href,
    member_id: memberId,
    revision,
    callout_id: calloutId,
    deep_linked: Boolean(href && (memberId || calloutId)),
  };
}

function collectWorkspaceSheetLinks(workspace = {}) {
  const drawing = workspace.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const candidates = [
    drawing.svg_sheets,
    drawing.sheet_links,
    drawing.drawing_sheet_links,
    workspace.svg_sheets,
  ];
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length) return candidate;
  }
  return [];
}

export function buildDrawingSheetPackage({
  workspace = {},
  selectedElement = null,
  sheetLinks = [],
  deepLinkUrl = '',
  generatedAt = new Date().toISOString(),
} = {}) {
  const drawing = workspace.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const element = selectedElement && typeof selectedElement === 'object' ? selectedElement : {};
  const memberId = resolveMemberId(element);
  const revision = resolveRevision(workspace);
  const drawingId = normalizeText(workspace.drawingId || drawing.drawing_id || drawing.id);
  const calloutId = normalizeText(
    element.callout_id
    || element.calloutId
    || drawing.callout_id
  ) || `${slug(drawingId, 'drawing')}:${slug(memberId, 'selection')}`;
  const calloutLabel = normalizeText(
    element.callout_label
    || element.calloutLabel
    || (memberId ? `Member ${memberId}` : '')
  ) || 'Active selection';
  const rawLinks = Array.isArray(sheetLinks) && sheetLinks.length ? sheetLinks : collectWorkspaceSheetLinks(workspace);
  const sheets = rawLinks
    .map((row) => normalizeSheetLink(row, {
      fallbackMemberId: memberId,
      fallbackRevision: revision,
      fallbackCalloutId: calloutId,
    }))
    .filter((row) => row.href || row.sheet_name);
  const status = sheets.length && normalizeText(deepLinkUrl)
    ? 'linked'
    : sheets.length || normalizeText(deepLinkUrl)
      ? 'partial'
      : 'missing';
  const primarySheet = sheets[0] || null;
  return {
    schema_version: STRUCTURE_VIEWER_DRAWING_SHEET_PACKAGE_SCHEMA_VERSION,
    generated_at: generatedAt,
    status,
    project_id: normalizeText(workspace.projectId),
    drawing_id: drawingId,
    drawing_title: normalizeText(workspace.drawingTitle || drawing.title || drawing.label),
    variant: normalizeText(workspace.variant),
    member_id: memberId,
    revision,
    callout_id: calloutId,
    callout_label: calloutLabel,
    deep_link_url: normalizeText(deepLinkUrl),
    sheet_count: sheets.length,
    primary_sheet_name: primarySheet?.sheet_name || '',
    primary_sheet_href: primarySheet?.href || '',
    sheets,
    summary: (
      `Drawing sheet package: ${status} | sheets=${sheets.length} | `
      + `member=${memberId || '--'} | revision=${revision}`
    ),
  };
}

export function buildDrawingSheetPackageReportRows(sheetPackage = {}) {
  const rows = [
    { label: 'Package status', value: sheetPackage.status || 'missing', evidence: 'viewer URL state' },
    { label: 'Revision', value: sheetPackage.revision || 'unrevisioned', evidence: 'drawing metadata' },
    { label: 'Callout', value: sheetPackage.callout_id || '--', evidence: 'selection metadata' },
    { label: 'Deep-link', value: sheetPackage.deep_link_url ? 'available' : 'missing', evidence: 'viewer URL state' },
    { label: 'Primary sheet', value: sheetPackage.primary_sheet_name || '--', evidence: 'SVG sheet index' },
  ];
  const sheets = Array.isArray(sheetPackage.sheets) ? sheetPackage.sheets : [];
  sheets.forEach((sheet) => {
    rows.push({
      label: `Sheet ${sheet.label || sheet.sheet_name || '--'}`,
      value: sheet.sheet_name || '--',
      evidence: sheet.deep_linked ? 'member callout deep-link' : 'sheet link',
      href: sheet.href || '',
    });
  });
  return rows;
}
