function normalizeText(value) {
  return String(value ?? '').trim();
}

function safeNumber(value, fallback = NaN) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return NaN;
}

function formatInteger(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number).toLocaleString('en-US') : '--';
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const sign = number > 0 ? '+' : '';
  return `${sign}${number.toFixed(1)}%`;
}

function deriveDeltaTone(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'warn';
  if (number < 0) return 'success';
  if (number > 0) return 'danger';
  return 'neutral';
}

function buildRow(label, value, {
  delta = '',
  evidence = 'missing evidence',
  tone = 'neutral',
  source = '',
} = {}) {
  return {
    label,
    value: normalizeText(value) || '--',
    delta: normalizeText(delta),
    evidence: normalizeText(evidence) || 'missing evidence',
    tone,
    source: normalizeText(source),
  };
}

function buildArtifactCountVerification(summary = {}, {
  hasMemberPair = false,
  evidenceLevel = '',
  source = '',
} = {}) {
  const artifactCountSource = normalizeText(summary.artifact_count_source || summary.artifact_count_path);
  if (artifactCountSource) {
    return {
      status: 'verified',
      label: 'Artifact count verified',
      evidence: 'artifact_count_source',
      source: artifactCountSource,
    };
  }
  if (hasMemberPair) {
    return {
      status: 'manifest_only',
      label: 'Manifest comparison only',
      evidence: normalizeText(evidenceLevel) || 'manifest optimization_summary',
      source: normalizeText(source),
    };
  }
  return {
    status: 'missing',
    label: 'Comparison evidence pending',
    evidence: 'missing evidence',
    source: normalizeText(source),
  };
}

function normalizeSummarySource(workspace = {}, data = {}) {
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const meta = data?.meta && typeof data.meta === 'object' ? data.meta : {};
  const drawingSummary = drawing.optimization_summary && typeof drawing.optimization_summary === 'object'
    ? drawing.optimization_summary
    : {};
  const metaSummary = meta.optimization_summary && typeof meta.optimization_summary === 'object'
    ? meta.optimization_summary
    : {};
  return { ...metaSummary, ...drawingSummary };
}

export function buildOptimizationComparisonModel({
  workspace = {},
  data = {},
} = {}) {
  const summary = normalizeSummarySource(workspace, data);
  const elementCount = Array.isArray(data?.elements) ? data.elements.length : NaN;
  const baselineMembers = firstFiniteNumber(summary.baseline_member_count, summary.before_member_count);
  const optimizedMembers = firstFiniteNumber(summary.optimized_member_count, summary.after_member_count, elementCount);
  const hasMemberPair = Number.isFinite(baselineMembers) && baselineMembers > 0 && Number.isFinite(optimizedMembers);
  const memberDelta = hasMemberPair ? optimizedMembers - baselineMembers : NaN;
  const memberDeltaPct = Number.isFinite(summary.member_delta_pct)
    ? Number(summary.member_delta_pct)
    : hasMemberPair
      ? (memberDelta / baselineMembers) * 100
      : NaN;
  const weightDeltaPct = firstFiniteNumber(summary.weight_delta_pct, summary.weight_reduction_pct);
  const costDeltaPct = firstFiniteNumber(summary.cost_delta_pct, summary.cost_reduction_pct);
  const proxyDelta = Number.isFinite(weightDeltaPct)
    ? weightDeltaPct
    : Number.isFinite(costDeltaPct)
      ? costDeltaPct
      : memberDeltaPct;
  const evidenceLevel = normalizeText(summary.evidence_level) || (hasMemberPair ? 'exact source' : 'missing evidence');
  const proxyEvidence = Number.isFinite(weightDeltaPct) || Number.isFinite(costDeltaPct)
    ? evidenceLevel
    : hasMemberPair
      ? 'derived proxy'
      : 'missing evidence';
  const riskDelta = normalizeText(summary.risk_delta_label || summary.risk_focus || summary.risk_delta);
  const source = normalizeText(summary.source || summary.source_path || workspace?.drawing?.provenance?.report_path || workspace?.drawing?.source_family);
  const verification = buildArtifactCountVerification(summary, {
    hasMemberPair,
    evidenceLevel,
    source,
  });
  const rows = [
    buildRow('Members', hasMemberPair ? `${formatInteger(baselineMembers)} -> ${formatInteger(optimizedMembers)}` : '', {
      delta: Number.isFinite(memberDelta) ? `${formatInteger(memberDelta)} (${formatPercent(memberDeltaPct)})` : '',
      evidence: hasMemberPair ? evidenceLevel : 'missing evidence',
      tone: deriveDeltaTone(memberDelta),
      source,
    }),
    buildRow('Weight / cost proxy', Number.isFinite(proxyDelta) ? formatPercent(proxyDelta) : '', {
      evidence: proxyEvidence,
      tone: deriveDeltaTone(proxyDelta),
      source: Number.isFinite(weightDeltaPct) || Number.isFinite(costDeltaPct) ? source : 'member count delta',
    }),
    buildRow('Risk movement', riskDelta, {
      evidence: riskDelta ? evidenceLevel : 'missing evidence',
      tone: riskDelta.toLowerCase().includes('pending') ? 'warn' : 'accent',
      source,
    }),
    buildRow('Count verification', verification.label, {
      evidence: verification.evidence,
      tone: verification.status === 'verified' ? 'success' : verification.status === 'missing' ? 'danger' : 'warn',
      source: verification.source,
    }),
  ];
  const status = hasMemberPair ? 'ready' : 'needs_review';
  const headline = hasMemberPair
    ? `Members ${formatInteger(baselineMembers)} -> ${formatInteger(optimizedMembers)} (${formatPercent(memberDeltaPct)})`
    : 'Before/optimized comparison evidence pending';
  return {
    status,
    headline,
    memberDeltaPct: Number.isFinite(memberDeltaPct) ? memberDeltaPct : null,
    rows,
    evidenceLevel,
    source,
    verification,
  };
}
