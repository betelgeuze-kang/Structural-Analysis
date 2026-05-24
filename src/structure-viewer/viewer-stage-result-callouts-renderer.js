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

function buildKpiCallout(card = {}, { label = '', key = '' } = {}) {
  return {
    key,
    label,
    value: normalizeText(card.value) || '--',
    meta: normalizeText(card.meta) || '--',
    tone: normalizeTone(card.tone),
  };
}

function renderStageCallout(callout) {
  const tone = normalizeTone(callout.tone);
  const selectedClass = callout.selected ? ' is-selected' : '';
  const content = `<i class="stage-result-callout__pin" aria-hidden="true"></i>
      <span class="stage-result-callout__label">${escapeHtml(callout.label)}</span>
      <strong>${escapeHtml(callout.value)}</strong>
      <small>${escapeHtml(callout.meta)}</small>`;
  if (callout.focusMemberId) {
    return `<button type="button" class="stage-result-callout stage-result-callout--${escapeHtml(tone)}${selectedClass}" data-stage-result-callout-key="${escapeHtml(callout.key)}" data-stage-callout-focus-member="${escapeHtml(callout.focusMemberId)}" aria-pressed="${callout.selected ? 'true' : 'false'}" title="Focus critical member ${escapeHtml(callout.focusMemberId)}">
      ${content}
    </button>`;
  }
  return `<article class="stage-result-callout stage-result-callout--${escapeHtml(tone)}${selectedClass}" data-stage-result-callout-key="${escapeHtml(callout.key)}">
      ${content}
    </article>`;
}

export function buildStageResultCalloutsHtml({ cockpitModel = {}, activeMemberId = '' } = {}) {
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
    maxDisplacement ? buildKpiCallout(maxDisplacement, { key: 'max-displacement', label: 'Max Disp' }) : null,
    drift ? buildKpiCallout(drift, { key: 'max-drift', label: 'Drift' }) : null,
    baseShear ? buildKpiCallout(baseShear, { key: 'base-shear', label: 'Base Shear' }) : null,
    criticalMember ? {
      key: 'critical-member',
      label: 'Critical',
      value: normalizeText(criticalMember.id) || '--',
      meta: formatCriticalMemberMeta(criticalMember),
      tone: criticalMemberTone(criticalMember),
      focusMemberId: normalizeText(criticalMember.id) || '',
      selected: Boolean(normalizedActiveMemberId && normalizeText(criticalMember.id) === normalizedActiveMemberId),
    } : null,
  ].filter(Boolean);

  if (!callouts.length) {
    return '<div class="stage-result-callout stage-result-callout--neutral" data-stage-result-callout-key="empty"><span class="stage-result-callout__label">Result Callouts</span><strong>--</strong><small>Awaiting model</small></div>';
  }

  return callouts.map(renderStageCallout).join('');
}
