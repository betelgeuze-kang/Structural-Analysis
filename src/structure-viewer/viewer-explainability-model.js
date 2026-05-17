function normalizeText(value) {
  return String(value ?? '').trim();
}

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatNumber(value, digits = 3) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '--';
}

function evidence(value, exactLabel = 'exact source') {
  return normalizeText(value) ? exactLabel : 'missing evidence';
}

function row(label, value, {
  evidenceLevel = '',
  tone = 'neutral',
  source = '',
} = {}) {
  const normalizedValue = normalizeText(value);
  return {
    label,
    value: normalizedValue || '--',
    evidence: evidenceLevel || evidence(normalizedValue),
    tone,
    source: normalizeText(source),
  };
}

function deriveDcrTone(dcr) {
  if (!Number.isFinite(dcr) || dcr <= 0) return 'neutral';
  if (dcr > 1) return 'danger';
  if (dcr >= 0.9) return 'warn';
  return 'success';
}

function resolveSectionDelta(element = {}) {
  const before = normalizeText(element.before_section || element.original_section || element.section_before);
  const after = normalizeText(element.after_section || element.optimized_section || element.section_after);
  if (before || after) {
    return {
      value: `${before || '--'} -> ${after || normalizeText(element.section) || '--'}`,
      evidence: before && after ? 'exact source' : 'derived proxy',
    };
  }
  const action = normalizeText(element.action_name || element.optimization_meaning_label);
  if (action) return { value: action, evidence: 'derived proxy' };
  return { value: '', evidence: 'missing evidence' };
}

function resolveCostDelta(element = {}) {
  const candidates = [
    ['weight_delta_pct', 'weight delta'],
    ['cost_delta_pct', 'cost delta'],
    ['cost_reduction_pct', 'cost reduction'],
    ['weight_reduction_pct', 'weight reduction'],
  ];
  for (const [key, label] of candidates) {
    const value = Number(element[key]);
    if (Number.isFinite(value)) return { value: `${label} ${value.toFixed(2)}%`, evidence: 'exact source' };
  }
  const before = normalizeText(element.before_section || element.original_section || element.section_before);
  const after = normalizeText(element.after_section || element.optimized_section || element.section_after);
  if (before && after && before !== after) return { value: 'section change proxy', evidence: 'derived proxy' };
  return { value: '', evidence: 'missing evidence' };
}

function resolveOptimizationRationale(element = {}) {
  const explicit = normalizeText(
    element.optimization_reason
    || element.optimization_rationale
    || element.retention_reason
    || element.change_reason,
  );
  if (explicit) return { value: explicit, evidence: 'exact source' };
  const constraint = normalizeText(
    element.governing_constraint
    || element.controlling_constraint
    || element.constraint_reason
    || (Array.isArray(element.constraints) ? element.constraints.join(', ') : element.constraints),
  );
  if (constraint) return { value: `governed by ${constraint}`, evidence: 'exact source' };
  const before = normalizeText(element.before_section || element.original_section || element.section_before);
  const after = normalizeText(element.after_section || element.optimized_section || element.section_after);
  const dcr = Number(element.dcr);
  if (before && after && before !== after) {
    return {
      value: Number.isFinite(dcr)
        ? `section changed while usage stays at ${(dcr * 100).toFixed(1)}%`
        : 'section changed with optimization overlay evidence',
      evidence: 'derived proxy',
    };
  }
  if (Number.isFinite(dcr) && dcr >= 0.9) {
    return { value: 'retained near utilization limit', evidence: 'derived proxy' };
  }
  return { value: '', evidence: 'missing evidence' };
}

export function buildViewerExplainabilityModel({
  data = {},
  element = null,
  selection = {},
  workspace = {},
} = {}) {
  const meta = data?.meta && typeof data.meta === 'object' ? data.meta : {};
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const selected = element && typeof element === 'object' ? element : {};
  const memberId = normalizeText(selected.member_id || selected.case_id || selected.id || selection.memberId);
  const dcr = Number(selected.dcr);
  const usagePct = Number.isFinite(dcr) && dcr > 0 ? `${(dcr * 100).toFixed(1)}%` : '';
  const sectionDelta = resolveSectionDelta(selected);
  const costDelta = resolveCostDelta(selected);
  const rationale = resolveOptimizationRationale(selected);
  const reviewStatus = normalizeText(drawing.commercial_review_status || meta.commercial_review_status || 'needs_review');
  const sourceFamily = normalizeText(drawing.source_family || meta.source_artifact_family || meta.source_mode || 'unknown');
  const qualityFlags = Array.isArray(drawing.quality_flags)
    ? drawing.quality_flags
    : Array.isArray(meta.quality_flags)
      ? meta.quality_flags
      : [];
  const riskTone = deriveDcrTone(dcr);
  const rows = [
    row('Section', selected.section || selected.section_name, { source: sourceFamily }),
    row('Material', selected.material || selected.material_name || selected.material_id, { source: sourceFamily }),
    row('Load case', selection.loadCase || selected.load_case || selected.combination || selected.review_combination_label, {
      source: sourceFamily,
    }),
    row('D/C ratio', Number.isFinite(dcr) ? formatNumber(dcr, 3) : '', {
      tone: riskTone,
      source: 'analysis result',
    }),
    row('Usage', usagePct, {
      evidenceLevel: usagePct ? 'derived proxy' : 'missing evidence',
      tone: riskTone,
      source: 'D/C ratio',
    }),
    row('Review status', reviewStatus, {
      evidenceLevel: drawing.commercial_review_status ? 'exact source' : 'derived proxy',
      tone: reviewStatus === 'ready' ? 'success' : reviewStatus === 'blocked' ? 'danger' : 'warn',
      source: 'project manifest',
    }),
    row('Optimization delta', sectionDelta.value, {
      evidenceLevel: sectionDelta.evidence,
      tone: sectionDelta.evidence === 'missing evidence' ? 'warn' : 'accent',
      source: 'optimization overlay',
    }),
    row('Weight / cost', costDelta.value, {
      evidenceLevel: costDelta.evidence,
      tone: costDelta.evidence === 'missing evidence' ? 'warn' : 'accent',
      source: 'optimization overlay',
    }),
    row('Optimization rationale', rationale.value, {
      evidenceLevel: rationale.evidence,
      tone: rationale.evidence === 'missing evidence' ? 'warn' : 'accent',
      source: rationale.evidence === 'exact source' ? 'optimization receipt' : 'optimization overlay',
    }),
    row('Risk focus', riskTone === 'danger' ? 'above unity threshold' : riskTone === 'warn' ? 'near limit' : 'within current threshold', {
      evidenceLevel: Number.isFinite(dcr) ? 'derived proxy' : 'missing evidence',
      tone: riskTone,
      source: 'D/C ratio',
    }),
  ];
  const checklist = [
    {
      label: '하중 확인 필요',
      status: qualityFlags.includes('load_model_missing') ? 'needs_review' : 'ready',
    },
    {
      label: 'DCR 재검토',
      status: riskTone === 'danger' ? 'blocked' : riskTone === 'warn' ? 'needs_review' : 'ready',
    },
    {
      label: '단면 변경 확인',
      status: sectionDelta.evidence === 'missing evidence' ? 'needs_review' : 'ready',
    },
    {
      label: '근거 누락 확인',
      status: rows.some((item) => item.evidence === 'missing evidence') ? 'needs_review' : 'ready',
    },
  ];

  return {
    memberId: memberId || '--',
    title: memberId ? `Member ${memberId}` : 'Selection required',
    reviewStatus,
    reviewTone: reviewStatus === 'ready' ? 'success' : reviewStatus === 'blocked' ? 'danger' : 'warn',
    sourceFamily,
    qualityFlags,
    rows,
    groups: [
      { title: 'Identity', rows: rows.slice(0, 3) },
      { title: 'Demand / Usage', rows: rows.slice(3, 6) },
      { title: 'Optimization Evidence', rows: rows.slice(6) },
    ],
    checklist,
  };
}
