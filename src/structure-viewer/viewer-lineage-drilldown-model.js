export const STRUCTURE_VIEWER_LINEAGE_DRILLDOWN_SCHEMA_VERSION = 'structure-viewer-lineage-drilldown.v1';

function normalizeText(value) {
  return String(value ?? '').trim();
}

function slug(value, fallback = 'viewer') {
  return normalizeText(value).replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').toLowerCase() || fallback;
}

function firstText(...values) {
  return values.map(normalizeText).find(Boolean) || '';
}

function memberIdFrom(element = {}, selection = {}) {
  return firstText(element?.member_id, element?.case_id, element?.id, selection?.memberId);
}

function findLineageStage(lineage = [], ...tokens) {
  const lowered = tokens.map((token) => normalizeText(token).toLowerCase()).filter(Boolean);
  return (Array.isArray(lineage) ? lineage : []).find((row) => {
    const haystack = [
      row?.stage,
      row?.label,
      row?.path,
    ].map((value) => normalizeText(value).toLowerCase()).join(' ');
    return lowered.some((token) => haystack.includes(token));
  }) || null;
}

function hasSectionDelta(element = {}) {
  return Boolean(firstText(
    element?.before_section,
    element?.original_section,
    element?.section_before,
  ) || firstText(
    element?.after_section,
    element?.optimized_section,
    element?.section_after,
  ));
}

function formatSectionDelta(element = {}) {
  const before = firstText(element?.before_section, element?.original_section, element?.section_before);
  const after = firstText(element?.after_section, element?.optimized_section, element?.section_after, element?.section);
  return before || after ? `${before || '--'} -> ${after || '--'}` : '';
}

function formatMemberDelta(drawing = {}) {
  const summary = drawing.optimization_summary && typeof drawing.optimization_summary === 'object'
    ? drawing.optimization_summary
    : {};
  const baseline = Number(summary.baseline_member_count);
  const optimized = Number(summary.optimized_member_count);
  if (!Number.isFinite(baseline) || !Number.isFinite(optimized)) return '';
  return `${Math.round(baseline).toLocaleString('en-US')} -> ${Math.round(optimized).toLocaleString('en-US')}`;
}

function buildRow(stage, label, value, {
  evidence = '',
  tone = 'neutral',
  source = '',
} = {}) {
  const normalizedValue = normalizeText(value);
  return {
    stage,
    label,
    value: normalizedValue || '--',
    evidence: evidence || (normalizedValue ? 'exact source' : 'missing evidence'),
    tone,
    source: normalizeText(source),
  };
}

function receiptLabel(receipt = null) {
  if (!receipt) return '';
  return firstText(
    receipt.label,
    receipt.status ? `solver receipt ${receipt.status}` : '',
    receipt.receipt_path,
  );
}

export function buildViewerLineageDrilldownModel({
  workspace = {},
  element = null,
  selection = {},
  solverReceipt = null,
  reviewTask = null,
  ingestPreview = null,
} = {}) {
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const selected = element && typeof element === 'object' ? element : {};
  const lineage = Array.isArray(drawing.lineage) ? drawing.lineage : [];
  const sourceStage = findLineageStage(lineage, 'source', 'baseline');
  const optimizedStage = findLineageStage(lineage, 'optimized', 'after');
  const reportStage = findLineageStage(lineage, 'report', 'viewer');
  const memberId = memberIdFrom(selected, selection);
  const sourcePath = firstText(sourceStage?.path, drawing.provenance?.source_path, drawing.artifact_path);
  const optimizedPath = firstText(
    optimizedStage?.path,
    workspace?.variantRow?.artifact_path,
    drawing.optimized_ref,
    drawing.artifact_path,
  );
  const analysisValue = solverReceipt
    ? [solverReceipt.source_tool, solverReceipt.load_combo, solverReceipt.status].map(normalizeText).filter(Boolean).join(' · ')
    : '';
  const sectionDelta = formatSectionDelta(selected);
  const memberDelta = formatMemberDelta(drawing);
  const reportPackage = `structure_viewer_report_${slug(workspace.projectId, 'project')}_${slug(workspace.drawingId, 'drawing')}_${slug(workspace.variant || 'optimized', 'optimized')}.html`;
  const ingestRenderable = ingestPreview?.renderable_payload_available
    ? `${ingestPreview.renderable_payload_kind || 'renderable'} · elements=${ingestPreview.renderable_element_count || 0} · segments=${ingestPreview.renderable_segment_count || 0}`
    : '';

  const rows = [
    buildRow('source_model', 'Source model', sourcePath, {
      evidence: sourcePath ? 'exact source' : 'missing evidence',
      tone: sourcePath ? 'success' : 'warn',
      source: firstText(sourceStage?.label, drawing.source_family, 'project manifest'),
    }),
    buildRow('analysis_result', 'Analysis result', analysisValue, {
      evidence: solverReceipt?.status === 'verified' ? 'exact source' : solverReceipt ? 'derived proxy' : 'missing evidence',
      tone: solverReceipt?.status === 'verified' ? 'success' : solverReceipt?.status === 'mismatch' ? 'danger' : 'warn',
      source: firstText(solverReceipt?.receipt_path, solverReceipt?.source_tool, 'solver receipt index'),
    }),
    buildRow('optimization_delta', 'Optimization delta', sectionDelta || memberDelta, {
      evidence: hasSectionDelta(selected) ? 'exact source' : memberDelta ? 'derived proxy' : 'missing evidence',
      tone: sectionDelta || memberDelta ? 'accent' : 'warn',
      source: hasSectionDelta(selected) ? 'selected member' : firstText(drawing.optimization_summary?.source, optimizedStage?.path, 'manifest summary'),
    }),
    buildRow('optimized_model', 'Optimized model', optimizedPath, {
      evidence: optimizedPath ? 'exact source' : 'missing evidence',
      tone: optimizedPath ? 'success' : 'warn',
      source: firstText(optimizedStage?.label, workspace.variantRow?.label, 'project manifest'),
    }),
    buildRow('solver_receipt', 'Solver receipt', receiptLabel(solverReceipt), {
      evidence: solverReceipt?.evidence_level || 'missing evidence',
      tone: solverReceipt?.tone || (solverReceipt?.status === 'verified' ? 'success' : solverReceipt?.status === 'mismatch' ? 'danger' : 'warn'),
      source: firstText(solverReceipt?.receipt_path, 'receipt index'),
    }),
    buildRow('review_task', 'Review task', reviewTask?.label || reviewTask?.status || '확인 필요', {
      evidence: reviewTask?.hasTask ? 'local audit state' : 'derived proxy',
      tone: reviewTask?.tone || 'warn',
      source: firstText(reviewTask?.updatedAt, 'local ops state'),
    }),
    buildRow('report_package', 'Report package', firstText(reportStage?.path, reportPackage), {
      evidence: 'derived proxy',
      tone: 'accent',
      source: firstText(reportStage?.label, 'viewer report export'),
    }),
    buildRow('evidence_ingest', 'Evidence ingest', ingestRenderable, {
      evidence: ingestRenderable ? 'local ingest payload' : 'missing evidence',
      tone: ingestRenderable ? 'accent' : 'warn',
      source: ingestPreview?.source_type || 'local ops state',
    }),
  ];
  const hasDanger = rows.some((row) => row.tone === 'danger');
  const hasMissing = rows.some((row) => row.evidence === 'missing evidence');
  return {
    schema_version: STRUCTURE_VIEWER_LINEAGE_DRILLDOWN_SCHEMA_VERSION,
    memberId: memberId || '--',
    status: hasDanger ? 'blocked' : hasMissing ? 'needs_review' : 'ready',
    summary: `${memberId || 'selected member'} lineage · ${rows.filter((row) => row.evidence !== 'missing evidence').length}/${rows.length} evidence links`,
    rows,
  };
}
