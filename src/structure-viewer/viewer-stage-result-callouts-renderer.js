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

function normalizeTone(value) {
  const tone = normalizeText(value).toLowerCase();
  return ['accent', 'danger', 'neutral', 'success', 'warn'].includes(tone) ? tone : 'neutral';
}

export const STRUCTURE_VIEWER_STAGE_RESULT_CALLOUTS_SCHEMA_VERSION = 'structure-viewer-stage-result-callouts.v3';

function findKpiCard(cards = [], key = '') {
  return cards.find((card) => normalizeText(card?.key) === key) || null;
}

function formatCriticalMemberMeta(row = {}) {
  const ratio = Number(row.ratio);
  const ratioText = Number.isFinite(ratio) ? `D/C ${ratio.toFixed(2)}` : 'D/C --';
  return [
    normalizeText(row.type) || 'Member',
    ratioText,
    normalizeText(row.status) || 'Review',
  ].join(' · ');
}

function criticalMemberTone(row = {}) {
  const ratio = Number(row.ratio);
  if (Number.isFinite(ratio) && ratio >= 1) return 'danger';
  if (Number.isFinite(ratio) && ratio >= 0.9) return 'warn';
  const status = normalizeText(row.status).toLowerCase();
  if (status.includes('high')) return 'warn';
  if (status.includes('watch')) return 'warn';
  if (status.includes('ok')) return 'success';
  return 'neutral';
}

function classifyCalloutSource(label = '') {
  const text = normalizeText(label).toLowerCase();
  if (text.includes('source')) return 'source';
  if (text.includes('solver')) return 'source';
  if (text.includes('model')) return 'estimate';
  if (text.includes('estimate')) return 'estimate';
  return 'review';
}

function buildCalloutAnchorProfile(key = '') {
  switch (normalizeText(key)) {
    case 'max-displacement':
      return {
        anchorKind: 'roof-displacement',
        anchorLabel: 'Roof displacement contour peak',
      };
    case 'max-drift':
      return {
        anchorKind: 'governing-drift-story',
        anchorLabel: 'Governing interstory drift band',
      };
    case 'base-shear':
      return {
        anchorKind: 'base-reaction',
        anchorLabel: 'Base shear reaction line',
      };
    case 'critical-member':
      return {
        anchorKind: 'critical-member',
        anchorLabel: 'Critical member focus',
      };
    default:
      return {
        anchorKind: 'review-result',
        anchorLabel: 'Review result anchor',
      };
  }
}

function buildKpiCallout(card = {}, { label = '', key = '', timeline = {} } = {}) {
  const sourceLabel = normalizeText(card.evidenceLabel) || normalizeText(card.meta) || 'Model estimate';
  return {
    key,
    label,
    fullLabel: normalizeText(card.label) || label,
    value: normalizeText(card.value) || '--',
    fullValue: normalizeText(card.value) || '--',
    meta: normalizeText(card.meta) || '--',
    sourceLabel,
    sourceType: classifyCalloutSource(sourceLabel),
    loadCase: normalizeText(timeline.loadCase) || '--',
    stepLabel: timeline.totalSteps ? `${timeline.activeStep || '--'}/${timeline.totalSteps}` : '--',
    tone: normalizeTone(card.tone),
  };
}

function renderStageCallout(callout) {
  const tone = normalizeTone(callout.tone);
  const selectedClass = callout.selected ? ' is-selected' : '';
  const sourceLabel = normalizeText(callout.sourceLabel) || 'Review evidence';
  const sourceType = normalizeText(callout.sourceType) || classifyCalloutSource(sourceLabel);
  const stepLabel = normalizeText(callout.stepLabel) || '--';
  const fullLabel = normalizeText(callout.fullLabel) || normalizeText(callout.label) || '--';
  const fullValue = normalizeText(callout.fullValue) || normalizeText(callout.value) || '--';
  const anchorKind = normalizeText(callout.anchorKind) || 'review-result';
  const anchorLabel = normalizeText(callout.anchorLabel) || 'Review result anchor';
  const memberAttr = callout.focusMemberId
    ? ` data-stage-result-callout-member="${escapeHtml(callout.focusMemberId)}"`
    : '';
  const evidenceLabel = sourceType === 'source' ? 'Source' : sourceType === 'estimate' ? 'Estimate' : 'Review';
  const content = `<i class="stage-result-callout__pin" aria-hidden="true"></i>
      <span class="stage-result-callout__label">${escapeHtml(callout.label)}</span>
      <strong data-stage-result-callout-full-value="${escapeHtml(fullValue)}" title="${escapeHtml(fullValue)}">${escapeHtml(callout.value)}</strong>
      <small>${escapeHtml(callout.meta)}</small>`;
  const evidence = `<span class="stage-result-callout__evidence" data-stage-result-callout-evidence>
      <b>${escapeHtml(evidenceLabel)}</b>
      <em>${escapeHtml(stepLabel)}</em>
    </span>`;
  const anchor = `<span class="stage-result-callout__leader" data-stage-result-callout-leader aria-hidden="true"></span>`;
  const commonAttrs = `data-stage-result-callout data-stage-result-callout-key="${escapeHtml(callout.key)}" data-stage-result-callout-full-label="${escapeHtml(fullLabel)}" data-stage-result-callout-source="${escapeHtml(sourceLabel)}" data-stage-result-callout-source-type="${escapeHtml(sourceType)}" data-stage-result-callout-load-case="${escapeHtml(callout.loadCase || '--')}" data-stage-result-callout-step="${escapeHtml(stepLabel)}" data-stage-result-callout-anchor-kind="${escapeHtml(anchorKind)}" data-stage-result-callout-anchor-label="${escapeHtml(anchorLabel)}" data-stage-result-callout-projection="pending"${memberAttr}`;
  if (callout.focusMemberId) {
    return `<button type="button" class="stage-result-callout stage-result-callout--${escapeHtml(tone)}${selectedClass}" ${commonAttrs} data-stage-callout-focus-member="${escapeHtml(callout.focusMemberId)}" aria-pressed="${callout.selected ? 'true' : 'false'}" title="Focus critical member ${escapeHtml(callout.focusMemberId)} · ${escapeHtml(fullValue)}">
      ${anchor}
      ${content}
      ${evidence}
    </button>`;
  }
  return `<article class="stage-result-callout stage-result-callout--${escapeHtml(tone)}${selectedClass}" ${commonAttrs} title="${escapeHtml(fullLabel)} · ${escapeHtml(fullValue)}">
      ${anchor}
      ${content}
      ${evidence}
    </article>`;
}

export function buildStageResultCalloutsHtml({ cockpitModel = {}, activeMemberId = '', timeline = {} } = {}) {
  const kpiCards = Array.isArray(cockpitModel?.kpiCards) ? cockpitModel.kpiCards : [];
  const criticalMembers = Array.isArray(cockpitModel?.criticalMembers) ? cockpitModel.criticalMembers : [];
  const normalizedActiveMemberId = normalizeText(activeMemberId);
  const maxDisplacement = findKpiCard(kpiCards, 'maxDisplacement');
  const drift = findKpiCard(kpiCards, 'maxInterstoryDrift');
  const baseShear = findKpiCard(kpiCards, 'baseShear');
  const activeCriticalMember = normalizedActiveMemberId
    ? criticalMembers.find((row) => normalizeText(row?.id) === normalizedActiveMemberId)
    : null;
  const criticalMember = activeCriticalMember || criticalMembers[0] || null;
  const callouts = [
    maxDisplacement ? buildKpiCallout(maxDisplacement, { key: 'max-displacement', label: 'Max Disp', timeline }) : null,
    drift ? buildKpiCallout(drift, { key: 'max-drift', label: 'Drift', timeline }) : null,
    baseShear ? buildKpiCallout(baseShear, { key: 'base-shear', label: 'Base Shear', timeline }) : null,
    criticalMember ? {
      key: 'critical-member',
      label: 'Critical',
      fullLabel: 'Critical Member',
      value: normalizeText(criticalMember.id) || '--',
      fullValue: normalizeText(criticalMember.id) || '--',
      meta: formatCriticalMemberMeta(criticalMember),
      sourceLabel: normalizeText(criticalMember.sourceLabel) || 'Critical member table',
      sourceType: 'source',
      loadCase: normalizeText(timeline.loadCase) || '--',
      stepLabel: timeline.totalSteps ? `${timeline.activeStep || '--'}/${timeline.totalSteps}` : '--',
      tone: criticalMemberTone(criticalMember),
      focusMemberId: normalizeText(criticalMember.id) || '',
      selected: Boolean(normalizedActiveMemberId && normalizeText(criticalMember.id) === normalizedActiveMemberId),
    } : null,
  ].filter(Boolean);

  callouts.forEach((callout) => {
    const anchor = buildCalloutAnchorProfile(callout.key);
    callout.anchorKind = anchor.anchorKind;
    callout.anchorLabel = anchor.anchorLabel;
  });

  if (!callouts.length) {
    return `<div class="stage-result-callout stage-result-callout--neutral" data-stage-result-callout data-stage-result-callout-key="empty" data-stage-result-callout-full-label="Result Callouts" data-stage-result-callout-full-value="--" data-stage-result-callout-source="missing" data-stage-result-callout-source-type="review" data-stage-result-callout-load-case="--" data-stage-result-callout-step="--" data-stage-result-callout-anchor-kind="review-result" data-stage-result-callout-anchor-label="Review result anchor" data-stage-result-callout-projection="pending"><span class="stage-result-callout__leader" data-stage-result-callout-leader aria-hidden="true"></span><span class="stage-result-callout__label">Result Callouts</span><strong>--</strong><small>Awaiting model</small></div>`;
  }

  return callouts.map(renderStageCallout).join('');
}
