// Evidence Console prototype controller.
//
// Prototype-safety contract (PR1):
// - All case/evidence data comes from a fixture JSON file. Nothing is hardcoded
//   in the page, and there is no default "PASS" verdict anywhere in this module.
// - The reviewer decision is rendered strictly from the fixture value. A missing
//   or unknown decision renders as "Evidence unavailable", never as PASS.
// - All DOM is built with createElement/textContent. innerHTML is never used,
//   so untrusted fixture strings cannot inject markup.
// - Any missing evidence field renders an explicit "evidence unavailable" state.

const FIXTURE_URL = './fixtures/evidence_console_demo_cases.json';

const DECISION_LABELS = {
  PASS: 'Pass',
  REVIEW: 'Review',
  FAIL: 'Fail',
};
const DECISION_CLASS = {
  PASS: 'ec-pill--pass',
  REVIEW: 'ec-pill--review',
  FAIL: 'ec-pill--fail',
};

/** Create an element with optional class, text, and attributes. */
function el(tag, { className, text, attrs } = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value != null) node.setAttribute(key, String(value));
    }
  }
  return node;
}

/** True only when a value carries real evidence (not null/undefined/empty). */
function hasValue(value) {
  if (value == null) return false;
  if (typeof value === 'string') return value.trim() !== '';
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

/** Render an explicit "evidence unavailable" block. */
function unavailable(message) {
  return el('div', {
    className: 'ec-unavailable',
    text: message || 'Evidence unavailable',
    attrs: { 'data-ec-unavailable': '' },
  });
}

function formatNumber(value) {
  if (!hasValue(value) || typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }
  if (value !== 0 && (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e6)) {
    return value.toExponential(3);
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

/**
 * Normalize the reviewer decision from fixture data.
 * Returns one of PASS/REVIEW/FAIL, or null when no valid verdict is present.
 * There is intentionally no fallback to PASS.
 */
function normalizeDecision(rawDecision) {
  if (!hasValue(rawDecision)) return null;
  const key = String(rawDecision).trim().toUpperCase();
  return DECISION_LABELS[key] ? key : null;
}

function decisionPill(rawDecision) {
  const key = normalizeDecision(rawDecision);
  if (!key) {
    return el('span', {
      className: 'ec-pill ec-pill--unavailable',
      text: 'Evidence unavailable',
      attrs: { 'data-ec-decision': 'unavailable' },
    });
  }
  return el('span', {
    className: `ec-pill ${DECISION_CLASS[key]}`,
    text: DECISION_LABELS[key],
    attrs: { 'data-ec-decision': key },
  });
}

/* ---------- Case list ---------- */

function decisionAnnouncement(rawDecision) {
  const key = normalizeDecision(rawDecision);
  return key ? DECISION_LABELS[key] : 'verdict unavailable';
}

/**
 * Render the case list as a roving-tabindex group.
 * - The active button is the only tab stop (tabindex 0); others are -1.
 * - Arrow/Home/End keys move focus and select with automatic activation.
 * - aria-current marks the active case for assistive technology.
 */
function renderCaseList(listEl, cases, activeId, onSelect) {
  listEl.replaceChildren();
  cases.forEach((caseItem) => {
    const isActive = caseItem.id === activeId;
    const li = el('li', { attrs: { role: 'none' } });
    const displayName = hasValue(caseItem.name) ? caseItem.name : caseItem.id;
    const btn = el('button', {
      className: `ec-case-btn${isActive ? ' is-active' : ''}`,
      attrs: {
        type: 'button',
        'data-ec-case-id': caseItem.id,
        tabindex: isActive ? '0' : '-1',
        'aria-current': isActive ? 'true' : 'false',
        'aria-label': `${displayName}. Reviewer decision: ${decisionAnnouncement(caseItem.reviewer_decision)}.`,
      },
    });

    btn.appendChild(el('span', { className: 'ec-case-name', text: displayName }));

    const meta = el('span', { className: 'ec-case-meta', attrs: { 'aria-hidden': 'true' } });
    meta.appendChild(decisionPill(caseItem.reviewer_decision));
    if (hasValue(caseItem.structure_family)) {
      meta.appendChild(el('span', { text: caseItem.structure_family }));
    }
    btn.appendChild(meta);

    btn.addEventListener('click', () => onSelect(caseItem.id, { focusButton: false }));
    btn.addEventListener('keydown', (event) => {
      const index = cases.findIndex((c) => c.id === caseItem.id);
      let targetIndex = null;
      switch (event.key) {
        case 'ArrowDown':
        case 'ArrowRight':
          targetIndex = (index + 1) % cases.length;
          break;
        case 'ArrowUp':
        case 'ArrowLeft':
          targetIndex = (index - 1 + cases.length) % cases.length;
          break;
        case 'Home':
          targetIndex = 0;
          break;
        case 'End':
          targetIndex = cases.length - 1;
          break;
        default:
          return;
      }
      event.preventDefault();
      onSelect(cases[targetIndex].id, { focusButton: true });
    });

    li.appendChild(btn);
    listEl.appendChild(li);
  });
}

/* ---------- Detail sections ---------- */

function section(title) {
  const wrap = el('div', { className: 'ec-section' });
  wrap.appendChild(el('h3', { text: title }));
  return wrap;
}

function kvRow(dl, label, value) {
  dl.appendChild(el('dt', { text: label }));
  if (hasValue(value)) {
    dl.appendChild(el('dd', { text: value }));
  } else {
    const dd = el('dd');
    dd.appendChild(el('span', { className: 'ec-pill ec-pill--unavailable', text: 'unavailable' }));
    dl.appendChild(dd);
  }
}

function renderProvenance(caseItem) {
  const sec = section('Source / provenance inspector');
  const p = caseItem.provenance;
  if (!hasValue(p)) {
    sec.appendChild(unavailable('Source provenance not attached for this case.'));
    return sec;
  }
  const dl = el('dl', { className: 'ec-kv' });
  kvRow(dl, 'Model file', p.model_file);
  kvRow(dl, 'Model SHA-256', p.model_sha256);
  kvRow(dl, 'Source tool', p.source_tool);
  kvRow(dl, 'Engine version', p.engine_version);
  kvRow(dl, 'Analysis kind', p.analysis_kind);
  kvRow(dl, 'Generated at', p.generated_at);
  sec.appendChild(dl);
  return sec;
}

function comparisonCell(value, unit) {
  const formatted = formatNumber(value);
  if (formatted == null) {
    const td = el('td', { className: 'ec-num' });
    td.appendChild(el('span', { className: 'ec-pill ec-pill--unavailable', text: 'n/a' }));
    return td;
  }
  return el('td', { className: 'ec-num', text: hasValue(unit) && unit !== '-' ? `${formatted} ${unit}` : formatted });
}

function renderComparison(caseItem) {
  const sec = section('Reference vs engine comparison');
  const rows = caseItem.reference_vs_engine;
  if (!hasValue(rows)) {
    sec.appendChild(unavailable('No reference-vs-engine comparison attached.'));
    return sec;
  }
  const table = el('table', { className: 'ec-table' });
  const thead = el('thead');
  const hr = el('tr');
  ['Quantity', 'Reference', 'Engine', 'Δ (rel)', 'Within tol'].forEach((h, i) => {
    hr.appendChild(el('th', { text: h, className: i >= 1 && i <= 3 ? 'ec-num' : undefined }));
  });
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = el('tbody');
  rows.forEach((row) => {
    const tr = el('tr');
    tr.appendChild(el('td', { text: hasValue(row.quantity) ? row.quantity : '—' }));
    tr.appendChild(comparisonCell(row.reference, row.unit));
    tr.appendChild(comparisonCell(row.engine, row.unit));

    const bothNumeric = typeof row.reference === 'number' && typeof row.engine === 'number' && row.reference !== 0;
    const relDelta = bothNumeric ? Math.abs(row.engine - row.reference) / Math.abs(row.reference) : null;

    const deltaTd = el('td', { className: 'ec-num' });
    if (relDelta == null) {
      deltaTd.appendChild(el('span', { className: 'ec-pill ec-pill--unavailable', text: 'n/a' }));
    } else {
      deltaTd.textContent = `${(relDelta * 100).toFixed(2)}%`;
    }
    tr.appendChild(deltaTd);

    const tolTd = el('td');
    if (relDelta == null || !hasValue(row.tolerance_rel)) {
      tolTd.appendChild(el('span', { className: 'ec-pill ec-pill--unavailable', text: 'n/a' }));
    } else {
      const within = relDelta <= row.tolerance_rel;
      tolTd.appendChild(el('span', {
        className: within ? 'ec-flag-ok' : 'ec-flag-out',
        text: within ? 'within' : 'exceeded',
      }));
    }
    tr.appendChild(tolTd);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const scroll = el('div', { className: 'ec-table-scroll', attrs: { role: 'region', 'aria-label': 'Reference vs engine comparison table', tabindex: '0' } });
  scroll.appendChild(table);
  sec.appendChild(scroll);
  return sec;
}

function renderResidual(caseItem) {
  const sec = section('Residual audit');
  const rows = caseItem.residual_audit;
  if (!hasValue(rows)) {
    sec.appendChild(unavailable('No residual audit attached for this case.'));
    return sec;
  }
  const table = el('table', { className: 'ec-table' });
  const thead = el('thead');
  const hr = el('tr');
  ['Metric', 'Value', 'Tolerance', 'Status'].forEach((h, i) => {
    hr.appendChild(el('th', { text: h, className: i === 1 || i === 2 ? 'ec-num' : undefined }));
  });
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = el('tbody');
  rows.forEach((row) => {
    const tr = el('tr');
    tr.appendChild(el('td', { text: hasValue(row.metric) ? row.metric : '—' }));
    tr.appendChild(comparisonCell(row.value, row.unit));
    tr.appendChild(comparisonCell(row.tolerance, row.unit));
    const statusTd = el('td');
    if (!hasValue(row.within_tolerance)) {
      statusTd.appendChild(el('span', { className: 'ec-pill ec-pill--unavailable', text: 'n/a' }));
    } else {
      statusTd.appendChild(el('span', {
        className: row.within_tolerance ? 'ec-flag-ok' : 'ec-flag-out',
        text: row.within_tolerance ? 'within' : 'exceeded',
      }));
    }
    tr.appendChild(statusTd);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const scroll = el('div', { className: 'ec-table-scroll', attrs: { role: 'region', 'aria-label': 'Residual audit table', tabindex: '0' } });
  scroll.appendChild(table);
  sec.appendChild(scroll);
  return sec;
}

function renderWorst(caseItem) {
  const sec = section('Worst member / story');
  const worst = caseItem.worst;
  if (!hasValue(worst)) {
    sec.appendChild(unavailable('Governing member/story not attached for this case.'));
    return sec;
  }
  const dl = el('dl', { className: 'ec-kv' });
  kvRow(dl, 'Member', worst.member_id);
  kvRow(dl, 'Story', worst.story);
  kvRow(dl, 'Governing check', worst.governing_check);
  kvRow(dl, 'D/C ratio', formatNumber(worst.dcr));
  sec.appendChild(dl);
  return sec;
}

function renderReviewerDecision(caseItem) {
  const sec = section('Reviewer decision (PASS / REVIEW / FAIL)');
  sec.appendChild(decisionPill(caseItem.reviewer_decision));
  if (hasValue(caseItem.reviewer_decision_note)) {
    sec.appendChild(el('p', { className: 'ec-reviewer-note', text: caseItem.reviewer_decision_note }));
  }
  if (!normalizeDecision(caseItem.reviewer_decision)) {
    sec.appendChild(el('p', {
      className: 'ec-reviewer-note',
      text: 'No verdict is recorded for this case. A verdict is shown only when present in the evidence; it is never defaulted to PASS.',
    }));
  }
  return sec;
}

/* ---------- Reproduce bundle export ---------- */

function buildReproduceBundle(caseItem, dataset) {
  return {
    schema_version: 'evidence-console-reproduce-bundle.v1',
    dataset_kind: dataset.dataset_kind || 'demo_fixture',
    is_demo: dataset.is_demo === true,
    claim_boundary: dataset.claim_boundary || null,
    engine_version: dataset.engine_version || null,
    exported_at: new Date().toISOString(),
    case: caseItem,
  };
}

function renderActions(caseItem, dataset) {
  const sec = section('Reproduce bundle export');
  const actions = el('div', { className: 'ec-actions' });
  const btn = el('button', {
    className: 'ec-btn',
    text: 'Export reproduce bundle (JSON)',
    attrs: { type: 'button', 'data-ec-export': caseItem.id },
  });
  btn.addEventListener('click', () => {
    const bundle = buildReproduceBundle(caseItem, dataset);
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = el('a', { attrs: { href: url, download: `reproduce_bundle_${caseItem.id}.json` } });
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  });
  actions.appendChild(btn);
  actions.appendChild(el('span', {
    className: 'ec-action-hint',
    text: 'DEMO bundle — fixture inputs only, not a validated reproduction artifact.',
  }));
  sec.appendChild(actions);
  return sec;
}

function renderDetail(detailEl, caseItem, dataset) {
  detailEl.replaceChildren();
  if (!caseItem) {
    detailEl.appendChild(el('p', { className: 'ec-empty', text: 'Select a case to inspect its evidence.' }));
    return;
  }

  const head = el('div', { className: 'ec-detail-head' });
  const titleWrap = el('div');
  titleWrap.appendChild(el('h2', { text: hasValue(caseItem.name) ? caseItem.name : caseItem.id }));
  const subParts = [];
  if (hasValue(caseItem.structure_family)) subParts.push(caseItem.structure_family);
  if (hasValue(caseItem.load_combination)) subParts.push(caseItem.load_combination);
  titleWrap.appendChild(el('p', { className: 'ec-detail-sub', text: subParts.length ? subParts.join(' · ') : 'No metadata' }));
  head.appendChild(titleWrap);
  head.appendChild(decisionPill(caseItem.reviewer_decision));
  detailEl.appendChild(head);

  detailEl.appendChild(renderProvenance(caseItem));
  detailEl.appendChild(renderComparison(caseItem));
  detailEl.appendChild(renderResidual(caseItem));
  detailEl.appendChild(renderWorst(caseItem));
  detailEl.appendChild(renderReviewerDecision(caseItem));
  detailEl.appendChild(renderActions(caseItem, dataset));
}

/* ---------- Bootstrap ---------- */

async function init() {
  const listEl = document.querySelector('[data-ec-case-list]');
  const detailEl = document.querySelector('[data-ec-detail]');
  const statusEl = document.querySelector('[data-ec-status]');
  if (!listEl || !detailEl) return;

  let dataset;
  try {
    const response = await fetch(FIXTURE_URL, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    dataset = await response.json();
  } catch (error) {
    listEl.replaceChildren(unavailable('Demo fixture could not be loaded.'));
    detailEl.replaceChildren(unavailable(`Evidence fixture unavailable: ${error.message}`));
    return;
  }

  const cases = Array.isArray(dataset.cases) ? dataset.cases.filter((c) => c && hasValue(c.id)) : [];
  if (!cases.length) {
    listEl.replaceChildren(unavailable('No cases present in the fixture.'));
    detailEl.replaceChildren(unavailable('No evidence cases to display.'));
    return;
  }

  let activeId = cases[0].id;
  const select = (id, { focusButton = false } = {}) => {
    activeId = id;
    const caseItem = cases.find((c) => c.id === id) || null;
    renderCaseList(listEl, cases, activeId, select);
    renderDetail(detailEl, caseItem, dataset);

    if (statusEl && caseItem) {
      const name = hasValue(caseItem.name) ? caseItem.name : caseItem.id;
      statusEl.textContent = `Showing evidence for ${name}. Reviewer decision: ${decisionAnnouncement(caseItem.reviewer_decision)}.`;
    }

    if (focusButton) {
      const nextBtn = listEl.querySelector(`[data-ec-case-id="${CSS.escape(id)}"]`);
      if (nextBtn) nextBtn.focus();
    }
  };
  select(activeId);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

export { normalizeDecision, hasValue, formatNumber, buildReproduceBundle };
