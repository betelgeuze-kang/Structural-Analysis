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

function compactReceiptValue(value = '') {
  const text = normalizeText(value) || '--';
  if (text.length <= 15) return text;
  if (text.includes(':')) {
    const tail = text.split(':').filter(Boolean).pop() || text;
    return tail.length <= 10 ? `...:${tail}` : `${tail.slice(0, 7)}...`;
  }
  return `${text.slice(0, 6)}...${text.slice(-5)}`;
}

function compactDrawingMaterialFamily(value = '') {
  const text = normalizeText(value);
  const lower = text.toLowerCase();
  // Match against the full 47-family ontology so every source material is readable in the drawing rail
  if (lower.includes('structural steel')) return 'Steel';
  if (lower.includes('stainless steel')) return 'SS';
  if (lower.includes('cold formed')) return 'CFS';
  if (lower.includes('rail steel')) return 'Rail';
  if (lower.includes('concrete')) return 'Conc';
  if (lower.includes('composite') || lower.includes('src') || lower.includes('cft') || lower.includes('comptr')) return 'Comp';
  if (lower.includes('rigid')) return 'Rigid';
  if (lower.includes('rebar')) return 'Rebar';
  if (lower.includes('prestress')) return 'PC';
  if (lower.includes('cable')) return 'Cable';
  if (lower.includes('bolt') || lower.includes('anchor')) return 'Bolt';
  if (lower.includes('weld')) return 'Weld';
  if (lower.includes('frp')) return 'FRP';
  if (lower.includes('timber') || lower.includes('wood') || lower.includes('glulam')) return 'Timber';
  if (lower.includes('masonry')) return 'Masonry';
  if (lower.includes('aluminum') || lower.includes('alum')) return 'Alum';
  if (lower.includes('metal deck')) return 'Deck';
  if (lower.includes('facade') || lower.includes('cladding')) return 'Facade';
  if (lower.includes('sleeve') || lower.includes('embed')) return 'Embed';
  if (lower.includes('rail fastener')) return 'Fastener';
  if (lower.includes('rail sleeper') || lower.includes('rail tie')) return 'Sleeper';
  if (lower.includes('seismic isolator') || lower.includes('lead rubber')) return 'Isolator';
  if (lower.includes('elastomer') || lower.includes('rubber bearing')) return 'Bearing';
  if (lower.includes('pot bearing') || lower.includes('spherical bearing')) return 'PotBrg';
  if (lower.includes('resilient pad')) return 'Pad';
  if (lower.includes('expansion joint')) return 'ExpJnt';
  if (lower.includes('damper')) return 'Damper';
  if (lower.includes('spring') || lower.includes('nonlinear link')) return 'Spring';
  if (lower.includes('mass') || lower.includes('inertia')) return 'Mass';
  if (lower.includes('glass') || lower.includes('glazing')) return 'Glass';
  if (lower.includes('ballast')) return 'Ballast';
  if (lower.includes('soil') || lower.includes('clay') || lower.includes('sand') || lower.includes('gravel') || lower.includes('rock')) return 'Soil';
  if (lower.includes('geosynthetic') || lower.includes('geomembrane') || lower.includes('geotextile')) return 'GeoSyn';
  if (lower.includes('adhesive') || lower.includes('epoxy') || lower.includes('resin')) return 'Adhesive';
  if (lower.includes('formwork') || lower.includes('shoring')) return 'Formwk';
  if (lower.includes('screed') || lower.includes('topping')) return 'Screed';
  if (lower.includes('ground improvement') || lower.includes('soil-cement') || lower.includes('jet grout')) return 'GrndImp';
  if (lower.includes('grout') || lower.includes('backfill')) return 'Grout';
  if (lower.includes('waterproof')) return 'Waterpf';
  if (lower.includes('roof')) return 'Roof';
  if (lower.includes('asphalt') || lower.includes('bitumen')) return 'Asphalt';
  if (lower.includes('insulat')) return 'Insul';
  if (lower.includes('fire proof') || lower.includes('fireproof') || lower.includes('intumescent')) return 'FirePrf';
  if (lower.includes('coating') || lower.includes('paint') || lower.includes('primer') || lower.includes('galvan')) return 'Coating';
  if (lower.includes('sealant') || lower.includes('caulk') || lower.includes('joint filler')) return 'Sealant';
  if (lower.includes('gypsum') || lower.includes('drywall') || lower.includes('plaster board')) return 'Gypsum';
  if (lower.includes('stone') || lower.includes('marble') || lower.includes('tile') || lower.includes('terrazzo')) return 'Stone';
  return text.length > 9 ? `${text.slice(0, 8)}...` : text;
}

function compactDrawingMaterialModel(value = '') {
  const text = normalizeText(value);
  const lower = text.toLowerCase();
  // Constitutive / behaviour models
  if (lower.includes('concrete damage')) return 'CDP';
  if (lower.includes('steel bilinear')) return 'Bilinear';
  if (lower.includes('composite steel')) return 'SRC int.';
  if (lower.includes('rigid link')) return 'Rigid link';
  if (lower.includes('elastic')) return 'Elastic';
  if (lower.includes('plastic')) return 'Plastic';
  if (lower.includes('hardening')) return lower.includes('kinematic') ? 'KineHard' : 'IsoHard';
  if (lower.includes('damage')) return 'Damage';
  if (lower.includes('drucker-prager')) return 'D-P';
  if (lower.includes('mohr-coulomb')) return 'M-C';
  if (lower.includes('von mises')) return 'vMises';
  if (lower.includes('ramberg-osgood')) return 'R-O';
  if (lower.includes('trilinear')) return 'Trilinear';
  if (lower.includes('multilinear')) return 'Multilinear';
  if (lower.includes('hyperelastic')) return 'HyperEl';
  if (lower.includes('creep')) return 'Creep';
  if (lower.includes('visco')) return 'Visco';
  if (lower.includes('fracture')) return 'Fracture';
  if (lower.includes('bond') || lower.includes('slip')) return 'BondSlip';
  if (lower.includes('contact')) return 'Contact';
  if (lower.includes('cohesive')) return 'Cohesive';
  return text.length > 10 ? `${text.slice(0, 9)}...` : text;
}

function compactDrawingRevision(value = '') {
  const text = normalizeText(value) || '--';
  if (text.toLowerCase() === 'unrevisioned') return 'unrev';
  return text.length > 7 ? `${text.slice(0, 6)}...` : text;
}

export const STRUCTURE_VIEWER_DRAWING_HANDOFF_PANEL_SCHEMA_VERSION = 'structure-viewer-drawing-handoff-panel.v2';
export const STRUCTURE_VIEWER_DRAWING_MATERIAL_PARITY_LEDGER_SCHEMA_VERSION = 'structure-viewer-drawing-material-parity-ledger.v1';
export const STRUCTURE_VIEWER_DRAWING_SOURCE_DETAIL_LEDGER_SCHEMA_VERSION = 'structure-viewer-drawing-source-detail-ledger.v1';
export const STRUCTURE_VIEWER_DRAWING_SHEET_DETAIL_MATRIX_SCHEMA_VERSION = 'structure-viewer-drawing-sheet-detail-matrix.v1';
export const STRUCTURE_VIEWER_DRAWING_FORCE_HANDOFF_LEDGER_SCHEMA_VERSION = 'structure-viewer-drawing-force-handoff-ledger.v1';
export const STRUCTURE_VIEWER_DRAWING_FORCE_VECTOR_EVIDENCE_SCHEMA_VERSION = 'structure-viewer-drawing-force-vector-evidence.v1';
export const STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_OVERLAY_SCHEMA_VERSION = 'structure-viewer-drawing-sheet-force-overlay.v1';
export const STRUCTURE_VIEWER_DRAWING_CAPACITY_HANDOFF_LEDGER_SCHEMA_VERSION = 'structure-viewer-drawing-capacity-handoff-ledger.v1';
export const STRUCTURE_VIEWER_DRAWING_MATERIAL_CONSTITUTIVE_REGISTER_SCHEMA_VERSION = 'structure-viewer-drawing-material-constitutive-register.v1';
export const STRUCTURE_VIEWER_DRAWING_MATERIAL_CURVE_EVIDENCE_SCHEMA_VERSION = 'structure-viewer-drawing-material-curve-evidence.v1';
export const STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_MATRIX_SCHEMA_VERSION = 'structure-viewer-drawing-sheet-force-matrix.v1';
export const STRUCTURE_VIEWER_DRAWING_MATERIAL_MODEL_MATRIX_SCHEMA_VERSION = 'structure-viewer-drawing-material-model-matrix.v1';

function formatLedgerNumber(value = 0, { digits = 0, unit = '' } = {}) {
  const number = Number(value);
  if (!Number.isFinite(number)) return unit ? `--${unit}` : '--';
  return `${number.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}${unit}`;
}

function resolveLedgerTone(row = {}) {
  const tone = normalizeText(row.tone).toLowerCase();
  return ['success', 'warn', 'danger', 'accent', 'neutral'].includes(tone) ? tone : 'neutral';
}

function formatDrawingCurveCoord(value = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '0';
  return number.toFixed(2).replace(/\.?0+$/, '');
}

function buildDrawingMaterialParityLedgerHtml(materialParity = {}) {
  const ledger = materialParity && typeof materialParity === 'object' ? materialParity : {};
  const rows = Array.isArray(ledger.rows) ? ledger.rows : [];
  if (!rows.length && !normalizeText(ledger.status)) return '';
  const status = normalizeText(ledger.status) || 'pending';
  const materialMatchPercent = Number(ledger.materialMatchPercent ?? 0);
  const memberAssignmentMatchPercent = Number(ledger.memberAssignmentMatchPercent ?? 0);
  const sectionAssignmentChangeCount = Number(ledger.sectionAssignmentChangeCount ?? 0);
  const materialMismatchCount = Number(ledger.materialMismatchCount ?? 0);
  const memberMaterialMismatchCount = Number(ledger.memberMaterialMismatchCount ?? 0);
  const locked = status === 'ready' && materialMismatchCount === 0 && memberMaterialMismatchCount === 0;
  const defaultRows = [
    {
      key: 'material-library',
      label: 'Material Library',
      value: formatLedgerNumber(materialMatchPercent, { digits: 1, unit: '%' }),
      detail: `${formatLedgerNumber(materialMismatchCount)} material mismatches`,
      tone: materialMismatchCount ? 'danger' : 'success',
    },
    {
      key: 'member-materials',
      label: 'Member Materials',
      value: formatLedgerNumber(memberAssignmentMatchPercent, { digits: 1, unit: '%' }),
      detail: `${formatLedgerNumber(memberMaterialMismatchCount)} assignment mismatches`,
      tone: memberMaterialMismatchCount ? 'danger' : 'success',
    },
    {
      key: 'drawing-scope',
      label: 'Drawing Scope',
      value: formatLedgerNumber(sectionAssignmentChangeCount),
      detail: 'section/drawing edits only',
      tone: sectionAssignmentChangeCount ? 'accent' : 'neutral',
    },
  ];
  const renderedRows = rows.length ? rows : defaultRows;

  return `<div class="drawing-material-parity-ledger drawing-material-parity-ledger--${escapeHtml(status)}" data-drawing-material-parity-ledger data-drawing-material-parity-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_MATERIAL_PARITY_LEDGER_SCHEMA_VERSION)}" data-drawing-material-parity-status="${escapeHtml(status)}" data-drawing-material-parity-material-match-percent="${escapeHtml(String(materialMatchPercent || 0))}" data-drawing-material-parity-member-assignment-match-percent="${escapeHtml(String(memberAssignmentMatchPercent || 0))}" data-drawing-material-parity-material-mismatch-count="${escapeHtml(String(Math.max(0, Math.round(materialMismatchCount || 0))))}" data-drawing-material-parity-member-material-mismatch-count="${escapeHtml(String(Math.max(0, Math.round(memberMaterialMismatchCount || 0))))}" data-drawing-material-parity-section-assignment-change-count="${escapeHtml(String(Math.max(0, Math.round(sectionAssignmentChangeCount || 0))))}" data-drawing-material-parity-sheet-count="${escapeHtml(String(Math.max(0, Math.round(Number(ledger.sheetCount ?? 0)))))}" data-drawing-material-parity-active-sheet="${escapeHtml(ledger.activeSheet || '')}" data-drawing-material-parity-locked="${locked ? 'true' : 'false'}">
    <div class="drawing-material-parity-ledger__head">
      <span>
        <b>Drawing Material Parity</b>
        <em>${escapeHtml(ledger.activeSheet || 'active drawing')} · ${escapeHtml(ledger.referenceMode || 'original-vs-optimized lock')}</em>
      </span>
      <strong>${escapeHtml(formatLedgerNumber(materialMatchPercent, { digits: 1, unit: '%' }))}</strong>
    </div>
    <div class="drawing-material-parity-ledger__rows">
      ${renderedRows.map(row => `<span class="drawing-material-parity-row drawing-material-parity-row--${escapeHtml(resolveLedgerTone(row))}" data-drawing-material-parity-row data-drawing-material-parity-row-key="${escapeHtml(row.key || '')}">
        <b>${escapeHtml(row.label || '--')}</b>
        <strong title="${escapeHtml(row.value || '--')}">${escapeHtml(row.value || '--')}</strong>
        <em title="${escapeHtml(row.detail || '')}">${escapeHtml(row.detail || '')}</em>
      </span>`).join('')}
    </div>
  </div>`;
}

function buildDrawingSourceDetailLedgerHtml(sourceDetailLedger = {}) {
  const ledger = sourceDetailLedger && typeof sourceDetailLedger === 'object' ? sourceDetailLedger : {};
  const rows = Array.isArray(ledger.rows) ? ledger.rows : [];
  if (!rows.length && !normalizeText(ledger.status)) return '';
  const status = normalizeText(ledger.status) || 'pending';
  const activeSheet = normalizeText(ledger.activeSheet) || '--';
  const sheetCount = Math.max(0, Math.round(Number(ledger.sheetCount ?? 0)));
  const sourceLinkedCount = Math.max(0, Math.round(Number(ledger.sourceLinkedCount ?? 0)));
  const detailCount = Math.max(0, Math.round(Number(ledger.detailCount ?? rows.length)));
  const sectionAssignmentChangeCount = Math.max(0, Math.round(Number(ledger.sectionAssignmentChangeCount ?? 0)));
  const materialMatchPercent = Number(ledger.materialMatchPercent ?? 0);
  const memberAssignmentMatchPercent = Number(ledger.memberAssignmentMatchPercent ?? 0);
  const materialLocked = ledger.materialLocked === true || normalizeText(ledger.materialLocked).toLowerCase() === 'true';
  const drawingOnlyOptimized = ledger.drawingOnlyOptimized === true || normalizeText(ledger.drawingOnlyOptimized).toLowerCase() === 'true';
  const renderedRows = rows.length ? rows : [
    {
      key: 'original-detail',
      label: 'Original Drawing Detail',
      value: `${formatLedgerNumber(sourceLinkedCount)}/${formatLedgerNumber(sheetCount)}`,
      detail: `${activeSheet} · source SVG linked`,
      tone: sourceLinkedCount ? 'success' : 'warn',
    },
    {
      key: 'material-lock',
      label: 'Source Material Lock',
      value: formatLedgerNumber(materialMatchPercent, { digits: 1, unit: '%' }),
      detail: 'library/member ids unchanged',
      tone: materialLocked ? 'success' : 'danger',
    },
    {
      key: 'optimized-scope',
      label: 'Optimized Scope',
      value: `${formatLedgerNumber(sectionAssignmentChangeCount)} edits`,
      detail: 'section/drawing only; material models locked',
      tone: drawingOnlyOptimized ? 'accent' : 'warn',
    },
  ];
  return `<div class="drawing-source-detail-ledger drawing-source-detail-ledger--${escapeHtml(status)}" data-drawing-source-detail-ledger data-drawing-source-detail-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_SOURCE_DETAIL_LEDGER_SCHEMA_VERSION)}" data-drawing-source-detail-status="${escapeHtml(status)}" data-drawing-source-detail-active-sheet="${escapeHtml(activeSheet)}" data-drawing-source-detail-sheet-count="${escapeHtml(String(sheetCount))}" data-drawing-source-detail-source-linked-count="${escapeHtml(String(sourceLinkedCount))}" data-drawing-source-detail-detail-count="${escapeHtml(String(Math.max(detailCount, renderedRows.length)))}" data-drawing-source-detail-material-locked="${materialLocked ? 'true' : 'false'}" data-drawing-source-detail-drawing-only-optimized="${drawingOnlyOptimized ? 'true' : 'false'}" data-drawing-source-detail-section-edit-count="${escapeHtml(String(sectionAssignmentChangeCount))}" data-drawing-source-detail-material-match-percent="${escapeHtml(String(Number.isFinite(materialMatchPercent) ? materialMatchPercent : 0))}" data-drawing-source-detail-member-assignment-match-percent="${escapeHtml(String(Number.isFinite(memberAssignmentMatchPercent) ? memberAssignmentMatchPercent : 0))}">
    <div class="drawing-source-detail-ledger__head">
      <span>
        <b>Original Drawing Detail</b>
        <em>${escapeHtml(activeSheet)} · original source preserved</em>
      </span>
      <strong>${escapeHtml(formatLedgerNumber(materialMatchPercent, { digits: 1, unit: '%' }))}</strong>
    </div>
    <div class="drawing-source-detail-ledger__summary" data-drawing-source-detail-summary>
      <span><b>${escapeHtml(formatLedgerNumber(sourceLinkedCount))}/${escapeHtml(formatLedgerNumber(sheetCount))}</b><em>source sheets</em></span>
      <span><b>${materialLocked ? 'locked' : 'review'}</b><em>materials</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(sectionAssignmentChangeCount))}</b><em>section edits</em></span>
      <span><b>${drawingOnlyOptimized ? 'drawing only' : 'review'}</b><em>opt scope</em></span>
    </div>
    <div class="drawing-source-detail-ledger__rows">
      ${renderedRows.map(row => {
        const sheetName = normalizeText(row.sheetName || activeSheet) || activeSheet;
        return `<button type="button" class="drawing-source-detail-row drawing-source-detail-row--${escapeHtml(resolveLedgerTone(row))}" data-drawing-source-detail-row data-drawing-source-detail-row-key="${escapeHtml(row.key || '')}" data-drawing-source-detail-row-sheet="${escapeHtml(sheetName)}">
          <b>${escapeHtml(row.label || '--')}</b>
          <strong title="${escapeHtml(row.value || '--')}">${escapeHtml(row.value || '--')}</strong>
          <em title="${escapeHtml(row.detail || '')}">${escapeHtml(row.detail || '')}</em>
        </button>`;
      }).join('')}
    </div>
  </div>`;
}

function buildDrawingSheetDetailMatrixHtml(sheetDetailMatrix = {}) {
  const matrix = sheetDetailMatrix && typeof sheetDetailMatrix === 'object' ? sheetDetailMatrix : {};
  const rows = Array.isArray(matrix.rows) ? matrix.rows : [];
  if (!rows.length && !normalizeText(matrix.status)) return '';
  const status = normalizeText(matrix.status) || 'pending';
  const activeSheet = normalizeText(matrix.activeSheet) || '--';
  const sheetCount = Math.max(0, Math.round(Number(matrix.sheetCount ?? rows.length)));
  const sourceLinkedCount = Math.max(0, Math.round(Number(matrix.sourceLinkedCount ?? 0)));
  const sectionEditCount = Math.max(0, Math.round(Number(matrix.sectionAssignmentChangeCount ?? 0)));
  const materialMatchPercent = Number(matrix.materialMatchPercent ?? 0);
  const memberAssignmentMatchPercent = Number(matrix.memberAssignmentMatchPercent ?? 0);
  const maxDcr = Number(matrix.maxDcr ?? 0);
  const materialLocked = matrix.materialLocked === true || normalizeText(matrix.materialLocked).toLowerCase() === 'true';
  const drawingOnlyOptimized = matrix.drawingOnlyOptimized === true || normalizeText(matrix.drawingOnlyOptimized).toLowerCase() === 'true';
  const renderedRows = rows.length ? rows : [{
    key: activeSheet,
    label: activeSheet,
    sheetName: activeSheet,
    revision: '--',
    callout: '--',
    sourceLinked: false,
    active: true,
    dcr: maxDcr,
    detail: 'sheet detail pending',
    tone: 'neutral',
  }];
  return `<div class="drawing-sheet-detail-matrix drawing-sheet-detail-matrix--${escapeHtml(status)}" data-drawing-sheet-detail-matrix data-drawing-sheet-detail-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_SHEET_DETAIL_MATRIX_SCHEMA_VERSION)}" data-drawing-sheet-detail-status="${escapeHtml(status)}" data-drawing-sheet-detail-active-sheet="${escapeHtml(activeSheet)}" data-drawing-sheet-detail-sheet-count="${escapeHtml(String(sheetCount))}" data-drawing-sheet-detail-source-linked-count="${escapeHtml(String(sourceLinkedCount))}" data-drawing-sheet-detail-material-locked="${materialLocked ? 'true' : 'false'}" data-drawing-sheet-detail-drawing-only-optimized="${drawingOnlyOptimized ? 'true' : 'false'}" data-drawing-sheet-detail-section-edit-count="${escapeHtml(String(sectionEditCount))}" data-drawing-sheet-detail-material-match-percent="${escapeHtml(String(Number.isFinite(materialMatchPercent) ? materialMatchPercent : 0))}" data-drawing-sheet-detail-member-assignment-match-percent="${escapeHtml(String(Number.isFinite(memberAssignmentMatchPercent) ? memberAssignmentMatchPercent : 0))}" data-drawing-sheet-detail-max-dcr="${escapeHtml(String(Number.isFinite(maxDcr) ? maxDcr : 0))}">
    <div class="drawing-sheet-detail-matrix__head">
      <span>
        <b>Drawing Sheet Details</b>
        <em>${escapeHtml(activeSheet)} · source sheets and locked material scope</em>
      </span>
      <strong>${escapeHtml(formatLedgerNumber(sourceLinkedCount))}/${escapeHtml(formatLedgerNumber(sheetCount))}</strong>
    </div>
    <div class="drawing-sheet-detail-matrix__summary" data-drawing-sheet-detail-summary>
      <span><b>${escapeHtml(formatLedgerNumber(materialMatchPercent, { digits: 1, unit: '%' }))}</b><em>library match</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(memberAssignmentMatchPercent, { digits: 1, unit: '%' }))}</b><em>member ids</em></span>
      <span><b>D/C ${escapeHtml(formatLedgerNumber(maxDcr, { digits: 2 }))}</b><em>force overlay</em></span>
      <span><b>${drawingOnlyOptimized ? 'drawing only' : 'review'}</b><em>${escapeHtml(formatLedgerNumber(sectionEditCount))} edits</em></span>
    </div>
    <div class="drawing-sheet-detail-matrix__rows">
      ${renderedRows.map(row => {
        const sheetName = normalizeText(row.sheetName || row.label || row.key) || '--';
        const dcr = Number(row.dcr ?? maxDcr);
        const dcrPct = Math.max(3, Math.min(100, Number.isFinite(dcr) ? dcr * 100 : 0));
        const active = Boolean(row.active) || sheetName === activeSheet;
        const sourceLinked = row.sourceLinked === true || normalizeText(row.sourceLinked).toLowerCase() === 'true';
        const tone = resolveLedgerTone(row);
        return `<button type="button" class="drawing-sheet-detail-row drawing-sheet-detail-row--${escapeHtml(tone)}${active ? ' is-active' : ''}" data-drawing-sheet-detail-row data-drawing-sheet-detail-row-sheet="${escapeHtml(sheetName)}" data-drawing-sheet-detail-row-active="${active ? 'true' : 'false'}" data-drawing-sheet-detail-row-source-linked="${sourceLinked ? 'true' : 'false'}" data-drawing-sheet-detail-row-material-locked="${materialLocked ? 'true' : 'false'}" aria-pressed="${active ? 'true' : 'false'}">
          <span class="drawing-sheet-detail-row__main">
            <b>${escapeHtml(row.label || sheetName)}</b>
            <em title="${escapeHtml(`${row.callout || '--'} · ${row.revision || '--'}`)}">${escapeHtml(compactReceiptValue(row.callout || '--'))} · ${escapeHtml(compactDrawingRevision(row.revision || '--'))}</em>
          </span>
          <span class="drawing-sheet-detail-row__source">
            <strong>${sourceLinked ? 'source' : 'missing'}</strong>
            <em>${materialLocked ? 'mat locked' : 'mat review'}</em>
          </span>
          <span class="drawing-sheet-detail-row__meter" aria-hidden="true"><i style="--drawing-sheet-detail-force:${dcrPct.toFixed(1)}%"></i></span>
          <small title="${escapeHtml(row.detail || '')}">${escapeHtml(row.detail || '')}</small>
        </button>`;
      }).join('')}
    </div>
  </div>`;
}

function buildDrawingForceHandoffLedgerHtml(forceHandoff = {}) {
  const ledger = forceHandoff && typeof forceHandoff === 'object' ? forceHandoff : {};
  const rows = Array.isArray(ledger.rows) ? ledger.rows : [];
  if (!rows.length && !normalizeText(ledger.status)) return '';
  const status = normalizeText(ledger.status) || 'pending';
  const selectedCombination = normalizeText(ledger.selectedCombination) || '--';
  const selectedMember = normalizeText(ledger.selectedMemberId) || '--';
  const activeSheet = normalizeText(ledger.activeSheet) || '--';
  const maxDcr = Number(ledger.maxDcr ?? 0);
  const forceRowCount = Math.max(0, Math.round(Number(ledger.forceRowCount ?? 0)));
  const sourceBackedCount = Math.max(0, Math.round(Number(ledger.sourceBackedCount ?? 0)));
  const renderedRows = rows.length ? rows : [{
    key: 'force-state',
    label: 'Force State',
    value: selectedCombination,
    detail: `${selectedMember} · D/C ${formatLedgerNumber(maxDcr, { digits: 2 })}`,
    tone: maxDcr >= 1 ? 'danger' : maxDcr >= 0.85 ? 'warn' : maxDcr > 0 ? 'accent' : 'neutral',
  }];
  return `<div class="drawing-force-handoff-ledger drawing-force-handoff-ledger--${escapeHtml(status)}" data-drawing-force-handoff-ledger data-drawing-force-handoff-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_FORCE_HANDOFF_LEDGER_SCHEMA_VERSION)}" data-drawing-force-handoff-status="${escapeHtml(status)}" data-drawing-force-handoff-selected-combination="${escapeHtml(selectedCombination)}" data-drawing-force-handoff-selected-member="${escapeHtml(selectedMember)}" data-drawing-force-handoff-active-sheet="${escapeHtml(activeSheet)}" data-drawing-force-handoff-row-count="${escapeHtml(String(renderedRows.length))}" data-drawing-force-handoff-force-row-count="${escapeHtml(String(forceRowCount))}" data-drawing-force-handoff-source-backed-count="${escapeHtml(String(sourceBackedCount))}" data-drawing-force-handoff-max-dcr="${escapeHtml(String(Number.isFinite(maxDcr) ? maxDcr : 0))}">
    <div class="drawing-force-handoff-ledger__head">
      <span>
        <b>Drawing Force Handoff</b>
        <em>${escapeHtml(activeSheet)} · ${escapeHtml(selectedCombination)}</em>
      </span>
      <strong>D/C ${escapeHtml(formatLedgerNumber(maxDcr, { digits: 2 }))}</strong>
    </div>
    <div class="drawing-force-handoff-ledger__summary" data-drawing-force-handoff-summary>
      <span><b>${escapeHtml(selectedMember)}</b><em>member</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(sourceBackedCount))}</b><em>source rows</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(forceRowCount))}</b><em>force rows</em></span>
    </div>
    <div class="drawing-force-handoff-ledger__rows">
      ${renderedRows.map(row => {
        const dcr = Number(row.dcr ?? 0);
        const dcrPct = Math.max(3, Math.min(100, Number.isFinite(dcr) ? dcr * 100 : 0));
        return `<span class="drawing-force-handoff-row drawing-force-handoff-row--${escapeHtml(resolveLedgerTone(row))}" data-drawing-force-handoff-row data-drawing-force-handoff-row-key="${escapeHtml(row.key || '')}" data-drawing-force-handoff-row-kind="${escapeHtml(row.kind || '')}" data-drawing-force-handoff-row-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}">
          <b>${escapeHtml(row.label || '--')}</b>
          <span class="drawing-force-handoff-row__meter" aria-hidden="true"><i style="--drawing-force-handoff:${dcrPct.toFixed(1)}%"></i></span>
          <strong title="${escapeHtml(row.value || '--')}">${escapeHtml(row.value || '--')}</strong>
          <em title="${escapeHtml(row.detail || '')}">${escapeHtml(row.detail || '')}</em>
        </span>`;
      }).join('')}
    </div>
  </div>`;
}

function resolveDrawingForceVectorKind(row = {}) {
  const text = normalizeText(row.vectorKind || row.kind || row.component || row.label).toLowerCase();
  if (text.includes('moment') || text.includes('bending') || text.includes('mx') || text.includes('my') || text.includes('mz')) return 'moment';
  if (text.includes('shear') || text.includes('vy') || text.includes('vz')) return 'shear';
  if (text.includes('axial') || text.includes('compression') || text.includes('tension') || text === 'n' || text.includes('fx')) return 'axial';
  if (text.includes('drift')) return 'drift';
  return 'check';
}

function buildDrawingForceVectorGlyphHtml(row = {}) {
  const kind = resolveDrawingForceVectorKind(row);
  const label = normalizeText(row.label || row.component || kind) || 'force vector';
  if (kind === 'moment') {
    return `<svg class="drawing-force-vector-row__svg drawing-force-vector-row__svg--moment" data-drawing-force-vector-svg viewBox="0 0 92 48" role="img" aria-label="${escapeHtml(label)} moment vector">
      <path class="drawing-force-vector-row__axis" d="M12 34H78"></path>
      <path class="drawing-force-vector-row__arc" d="M24 30C30 12 61 12 68 30"></path>
      <path class="drawing-force-vector-row__head" d="M68 30l-11-1 7-8"></path>
      <circle class="drawing-force-vector-row__node" cx="46" cy="34" r="3.2"></circle>
    </svg>`;
  }
  if (kind === 'shear') {
    return `<svg class="drawing-force-vector-row__svg drawing-force-vector-row__svg--shear" data-drawing-force-vector-svg viewBox="0 0 92 48" role="img" aria-label="${escapeHtml(label)} shear vector">
      <path class="drawing-force-vector-row__axis" d="M18 34H74"></path>
      <path class="drawing-force-vector-row__vector" d="M46 40V10"></path>
      <path class="drawing-force-vector-row__head" d="M46 10l-6 11h12z"></path>
      <path class="drawing-force-vector-row__ghost" d="M30 38V18M62 38V18"></path>
    </svg>`;
  }
  if (kind === 'axial') {
    return `<svg class="drawing-force-vector-row__svg drawing-force-vector-row__svg--axial" data-drawing-force-vector-svg viewBox="0 0 92 48" role="img" aria-label="${escapeHtml(label)} axial vector">
      <path class="drawing-force-vector-row__axis" d="M18 24H74"></path>
      <path class="drawing-force-vector-row__vector" d="M18 24H74"></path>
      <path class="drawing-force-vector-row__head" d="M74 24l-11-6v12z"></path>
      <path class="drawing-force-vector-row__tail" d="M18 24l11-6v12z"></path>
    </svg>`;
  }
  return `<svg class="drawing-force-vector-row__svg drawing-force-vector-row__svg--check" data-drawing-force-vector-svg viewBox="0 0 92 48" role="img" aria-label="${escapeHtml(label)} check vector">
    <path class="drawing-force-vector-row__axis" d="M18 34H74"></path>
    <path class="drawing-force-vector-row__diamond" d="M46 10l24 14-24 14-24-14z"></path>
    <path class="drawing-force-vector-row__vector" d="M32 24h28"></path>
    <path class="drawing-force-vector-row__head" d="M60 24l-9-5v10z"></path>
  </svg>`;
}

function buildDrawingForceVectorEvidenceHtml(forceVectorEvidence = {}) {
  const evidence = forceVectorEvidence && typeof forceVectorEvidence === 'object' ? forceVectorEvidence : {};
  const rows = Array.isArray(evidence.rows) ? evidence.rows : [];
  if (!rows.length && !normalizeText(evidence.status)) return '';
  const status = normalizeText(evidence.status) || 'pending';
  const activeSheet = normalizeText(evidence.activeSheet) || '--';
  const selectedCombination = normalizeText(evidence.selectedCombination) || '--';
  const selectedMember = normalizeText(evidence.selectedMemberId) || '--';
  const forceRowCount = Math.max(0, Math.round(Number(evidence.forceRowCount ?? 0)));
  const sourceBackedCount = Math.max(0, Math.round(Number(evidence.sourceBackedCount ?? 0)));
  const maxDcr = Number(evidence.maxDcr ?? 0);
  const materialLocked = evidence.materialLocked === true || normalizeText(evidence.materialLocked).toLowerCase() === 'true';
  const renderedRows = rows.length ? rows : [{
    key: 'force-vector-state',
    kind: 'check',
    component: 'check',
    label: 'Force vector',
    value: `D/C ${formatLedgerNumber(maxDcr, { digits: 2 })}`,
    detail: `${selectedMember} · ${selectedCombination}`,
    memberId: selectedMember,
    combination: selectedCombination,
    dcr: maxDcr,
    demand: 0,
    capacity: 0,
    sourceBacked: false,
    tone: maxDcr >= 1 ? 'danger' : maxDcr >= 0.85 ? 'warn' : maxDcr > 0 ? 'accent' : 'neutral',
  }];
  return `<div class="drawing-force-vector-evidence drawing-force-vector-evidence--${escapeHtml(status)}" data-drawing-force-vector-evidence data-drawing-force-vector-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_FORCE_VECTOR_EVIDENCE_SCHEMA_VERSION)}" data-drawing-force-vector-status="${escapeHtml(status)}" data-drawing-force-vector-active-sheet="${escapeHtml(activeSheet)}" data-drawing-force-vector-selected-combination="${escapeHtml(selectedCombination)}" data-drawing-force-vector-selected-member="${escapeHtml(selectedMember)}" data-drawing-force-vector-row-count="${escapeHtml(String(renderedRows.length))}" data-drawing-force-vector-force-row-count="${escapeHtml(String(forceRowCount))}" data-drawing-force-vector-source-backed-count="${escapeHtml(String(sourceBackedCount))}" data-drawing-force-vector-max-dcr="${escapeHtml(String(Number.isFinite(maxDcr) ? maxDcr : 0))}" data-drawing-force-vector-material-locked="${materialLocked ? 'true' : 'false'}">
    <div class="drawing-force-vector-evidence__head">
      <span>
        <b>Drawing Force Vector Evidence</b>
        <em>${escapeHtml(activeSheet)} · ${escapeHtml(selectedCombination)} · vectorized force rows</em>
      </span>
      <strong>D/C ${escapeHtml(formatLedgerNumber(maxDcr, { digits: 2 }))}</strong>
    </div>
    <div class="drawing-force-vector-evidence__summary" data-drawing-force-vector-summary>
      <span><b>${escapeHtml(selectedMember)}</b><em>member</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(sourceBackedCount))}</b><em>source rows</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(forceRowCount))}</b><em>force rows</em></span>
      <span><b>${materialLocked ? 'locked' : 'review'}</b><em>materials</em></span>
    </div>
    <div class="drawing-force-vector-evidence__rows">
      ${renderedRows.map(row => {
        const dcr = Number(row.dcr ?? 0);
        const demand = Number(row.demand ?? 0);
        const capacity = Number(row.capacity ?? 0);
        const dcrPct = Math.max(3, Math.min(100, Number.isFinite(dcr) ? dcr * 100 : 0));
        const vectorKind = resolveDrawingForceVectorKind(row);
        const memberId = normalizeText(row.memberId) || selectedMember;
        const combination = normalizeText(row.combination) || selectedCombination;
        return `<button type="button" class="drawing-force-vector-row drawing-force-vector-row--${escapeHtml(resolveLedgerTone(row))}" data-drawing-force-vector-row data-drawing-force-vector-row-key="${escapeHtml(row.key || vectorKind)}" data-drawing-force-vector-row-kind="${escapeHtml(row.kind || vectorKind)}" data-drawing-force-vector-row-vector-kind="${escapeHtml(vectorKind)}" data-drawing-force-vector-row-component="${escapeHtml(row.component || vectorKind)}" data-drawing-force-vector-row-member="${escapeHtml(memberId)}" data-drawing-force-vector-row-combination="${escapeHtml(combination)}" data-drawing-force-vector-row-sheet="${escapeHtml(activeSheet)}" data-drawing-force-vector-row-source-backed="${row.sourceBacked ? 'true' : 'false'}" data-drawing-force-vector-row-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" title="${escapeHtml(`${row.label || vectorKind} · ${combination} · ${memberId}`)}">
          ${buildDrawingForceVectorGlyphHtml(row)}
          <span class="drawing-force-vector-row__main">
            <b>${escapeHtml(row.label || vectorKind)}</b>
            <em>${escapeHtml(row.component || vectorKind)} · ${row.sourceBacked ? 'source' : 'estimated'}</em>
            <small>${escapeHtml(row.detail || `${memberId} · ${combination}`)}</small>
          </span>
          <span class="drawing-force-vector-row__meta">
            <strong>${escapeHtml(row.value || `D/C ${formatLedgerNumber(dcr, { digits: 2 })}`)}</strong>
            <em>${escapeHtml(formatLedgerNumber(Math.abs(demand), { digits: 1 }))} / ${escapeHtml(formatLedgerNumber(Math.abs(capacity), { digits: 1 }))}</em>
            <span class="drawing-force-vector-row__meter" aria-hidden="true"><i style="--drawing-force-vector:${dcrPct.toFixed(1)}%"></i></span>
          </span>
        </button>`;
      }).join('')}
    </div>
  </div>`;
}

function buildDrawingSheetForceOverlayVectorHtml(row = {}, index = 0) {
  const kind = resolveDrawingForceVectorKind(row);
  const tone = resolveLedgerTone(row);
  const label = normalizeText(row.label || row.component || kind) || kind;
  const dcr = Number(row.dcr ?? 0);
  const width = Math.max(2.4, Math.min(6.4, Number.isFinite(dcr) ? 2.4 + dcr * 2.8 : 2.4));
  const xShift = index * 9;
  if (kind === 'moment') {
    const cx = 146 + xShift;
    const cy = 60;
    return `<g class="drawing-sheet-force-overlay__vector drawing-sheet-force-overlay__vector--${escapeHtml(tone)} drawing-sheet-force-overlay__vector--moment" data-drawing-sheet-force-overlay-vector data-drawing-sheet-force-overlay-vector-kind="moment" data-drawing-sheet-force-overlay-vector-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" role="img" aria-label="${escapeHtml(`${label} force overlay`)}">
      <path class="drawing-sheet-force-overlay__moment" data-drawing-sheet-force-overlay-moment d="M${(cx - 22).toFixed(1)} ${cy.toFixed(1)}C${(cx - 18).toFixed(1)} ${(cy - 28).toFixed(1)} ${(cx + 22).toFixed(1)} ${(cy - 28).toFixed(1)} ${(cx + 26).toFixed(1)} ${cy.toFixed(1)}" style="--drawing-sheet-force-overlay-stroke:${width.toFixed(1)}"></path>
      <path class="drawing-sheet-force-overlay__head" d="M${(cx + 26).toFixed(1)} ${cy.toFixed(1)}l-11-2 7-8z"></path>
      <text x="${cx.toFixed(1)}" y="${(cy + 18).toFixed(1)}">${escapeHtml(label)}</text>
    </g>`;
  }
  if (kind === 'shear') {
    const x = 82 + xShift;
    return `<g class="drawing-sheet-force-overlay__vector drawing-sheet-force-overlay__vector--${escapeHtml(tone)} drawing-sheet-force-overlay__vector--shear" data-drawing-sheet-force-overlay-vector data-drawing-sheet-force-overlay-vector-kind="shear" data-drawing-sheet-force-overlay-vector-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" role="img" aria-label="${escapeHtml(`${label} force overlay`)}">
      <path class="drawing-sheet-force-overlay__arrow" d="M${x.toFixed(1)} 94V24" style="--drawing-sheet-force-overlay-stroke:${width.toFixed(1)}"></path>
      <path class="drawing-sheet-force-overlay__head" d="M${x.toFixed(1)} 24l-7 13h14z"></path>
      <text x="${(x + 10).toFixed(1)}" y="31">${escapeHtml(label)}</text>
    </g>`;
  }
  if (kind === 'axial') {
    const y = 58 + index * 7;
    return `<g class="drawing-sheet-force-overlay__vector drawing-sheet-force-overlay__vector--${escapeHtml(tone)} drawing-sheet-force-overlay__vector--axial" data-drawing-sheet-force-overlay-vector data-drawing-sheet-force-overlay-vector-kind="axial" data-drawing-sheet-force-overlay-vector-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" role="img" aria-label="${escapeHtml(`${label} force overlay`)}">
      <path class="drawing-sheet-force-overlay__arrow" d="M32 ${y.toFixed(1)}H132" style="--drawing-sheet-force-overlay-stroke:${width.toFixed(1)}"></path>
      <path class="drawing-sheet-force-overlay__head" d="M132 ${y.toFixed(1)}l-13-7v14z"></path>
      <path class="drawing-sheet-force-overlay__tail" d="M32 ${y.toFixed(1)}l13-7v14z"></path>
      <text x="38" y="${(y - 8).toFixed(1)}">${escapeHtml(label)}</text>
    </g>`;
  }
  const y = 82 + index * 5;
  return `<g class="drawing-sheet-force-overlay__vector drawing-sheet-force-overlay__vector--${escapeHtml(tone)} drawing-sheet-force-overlay__vector--check" data-drawing-sheet-force-overlay-vector data-drawing-sheet-force-overlay-vector-kind="${escapeHtml(kind)}" data-drawing-sheet-force-overlay-vector-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" role="img" aria-label="${escapeHtml(`${label} force overlay`)}">
    <path class="drawing-sheet-force-overlay__arrow" d="M122 ${y.toFixed(1)}H184" style="--drawing-sheet-force-overlay-stroke:${width.toFixed(1)}"></path>
    <path class="drawing-sheet-force-overlay__head" d="M184 ${y.toFixed(1)}l-12-6v12z"></path>
    <text x="126" y="${(y - 8).toFixed(1)}">${escapeHtml(label)}</text>
  </g>`;
}

function buildDrawingSheetForceOverlayHtml(sheetForceOverlay = {}) {
  const overlay = sheetForceOverlay && typeof sheetForceOverlay === 'object' ? sheetForceOverlay : {};
  const rows = Array.isArray(overlay.rows) ? overlay.rows : [];
  if (!rows.length && !normalizeText(overlay.status)) return '';
  const status = normalizeText(overlay.status) || 'pending';
  const activeSheet = normalizeText(overlay.activeSheet) || '--';
  const selectedCombination = normalizeText(overlay.selectedCombination) || '--';
  const selectedMember = normalizeText(overlay.selectedMemberId) || '--';
  const revision = normalizeText(overlay.revision) || '--';
  const calloutId = normalizeText(overlay.calloutId) || '--';
  const forceRowCount = Math.max(0, Math.round(Number(overlay.forceRowCount ?? 0)));
  const sourceBackedCount = Math.max(0, Math.round(Number(overlay.sourceBackedCount ?? 0)));
  const maxDcr = Number(overlay.maxDcr ?? 0);
  const materialLocked = overlay.materialLocked === true || normalizeText(overlay.materialLocked).toLowerCase() === 'true';
  const renderedRows = rows.length ? rows : [{
    key: 'sheet-force-overlay-state',
    kind: 'check',
    vectorKind: 'check',
    component: 'check',
    label: 'Force overlay',
    memberId: selectedMember,
    combination: selectedCombination,
    dcr: maxDcr,
    sourceBacked: false,
    tone: maxDcr >= 1 ? 'danger' : maxDcr >= 0.85 ? 'warn' : maxDcr > 0 ? 'accent' : 'neutral',
  }];
  return `<div class="drawing-sheet-force-overlay drawing-sheet-force-overlay--${escapeHtml(status)}" data-drawing-sheet-force-overlay data-drawing-sheet-force-overlay-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_OVERLAY_SCHEMA_VERSION)}" data-drawing-sheet-force-overlay-status="${escapeHtml(status)}" data-drawing-sheet-force-overlay-active-sheet="${escapeHtml(activeSheet)}" data-drawing-sheet-force-overlay-selected-combination="${escapeHtml(selectedCombination)}" data-drawing-sheet-force-overlay-selected-member="${escapeHtml(selectedMember)}" data-drawing-sheet-force-overlay-row-count="${escapeHtml(String(renderedRows.length))}" data-drawing-sheet-force-overlay-vector-count="${escapeHtml(String(renderedRows.length))}" data-drawing-sheet-force-overlay-force-row-count="${escapeHtml(String(forceRowCount))}" data-drawing-sheet-force-overlay-source-backed-count="${escapeHtml(String(sourceBackedCount))}" data-drawing-sheet-force-overlay-max-dcr="${escapeHtml(String(Number.isFinite(maxDcr) ? maxDcr : 0))}" data-drawing-sheet-force-overlay-material-locked="${materialLocked ? 'true' : 'false'}">
    <div class="drawing-sheet-force-overlay__head">
      <span>
        <b>Drawing Sheet Force Overlay</b>
        <em>${escapeHtml(activeSheet)} · ${escapeHtml(selectedCombination)} · sheet vector overlay</em>
      </span>
      <strong>D/C ${escapeHtml(formatLedgerNumber(maxDcr, { digits: 2 }))}</strong>
    </div>
    <div class="drawing-sheet-force-overlay__summary" data-drawing-sheet-force-overlay-summary>
      <span><b>${escapeHtml(selectedMember)}</b><em>member</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(renderedRows.length))}</b><em>vectors</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(sourceBackedCount))}</b><em>source rows</em></span>
      <span><b>${materialLocked ? 'locked' : 'review'}</b><em>materials</em></span>
    </div>
    <svg class="drawing-sheet-force-overlay__svg" data-drawing-sheet-force-overlay-svg viewBox="0 0 220 126" role="img" aria-label="${escapeHtml(`${activeSheet} load path force overlay`)}">
      <rect class="drawing-sheet-force-overlay__page" x="8" y="8" width="204" height="110" rx="4"></rect>
      <path class="drawing-sheet-force-overlay__grid" d="M24 25H196M24 45H196M24 65H196M24 85H196M44 18V102M84 18V102M124 18V102M164 18V102"></path>
      <path class="drawing-sheet-force-overlay__member" d="M36 58H174M84 26V98M124 26V98M44 86H184"></path>
      <rect class="drawing-sheet-force-overlay__core" x="96" y="42" width="38" height="36" rx="3"></rect>
      ${renderedRows.map((row, index) => buildDrawingSheetForceOverlayVectorHtml(row, index)).join('')}
      <text class="drawing-sheet-force-overlay__sheet-label" x="18" y="116">${escapeHtml(activeSheet)}</text>
      <text class="drawing-sheet-force-overlay__rev-label" x="158" y="116">${escapeHtml(revision)} · ${escapeHtml(calloutId)}</text>
    </svg>
    <div class="drawing-sheet-force-overlay__rows">
      ${renderedRows.map(row => {
        const vectorKind = resolveDrawingForceVectorKind(row);
        const dcr = Number(row.dcr ?? 0);
        const memberId = normalizeText(row.memberId) || selectedMember;
        const combination = normalizeText(row.combination) || selectedCombination;
        return `<button type="button" class="drawing-sheet-force-overlay-row drawing-sheet-force-overlay-row--${escapeHtml(resolveLedgerTone(row))}" data-drawing-sheet-force-overlay-row data-drawing-sheet-force-overlay-row-key="${escapeHtml(row.key || vectorKind)}" data-drawing-sheet-force-overlay-row-kind="${escapeHtml(vectorKind)}" data-drawing-sheet-force-overlay-row-member="${escapeHtml(memberId)}" data-drawing-sheet-force-overlay-row-combination="${escapeHtml(combination)}" data-drawing-sheet-force-overlay-row-sheet="${escapeHtml(activeSheet)}" data-drawing-sheet-force-overlay-row-source-backed="${row.sourceBacked ? 'true' : 'false'}" data-drawing-sheet-force-overlay-row-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}">
          <b>${escapeHtml(row.label || vectorKind)}</b>
          <strong>D/C ${escapeHtml(formatLedgerNumber(dcr, { digits: 2 }))}</strong>
          <em>${escapeHtml(memberId)} · ${escapeHtml(combination)}</em>
        </button>`;
      }).join('')}
    </div>
  </div>`;
}

function buildDrawingCapacityHandoffLedgerHtml(capacityHandoff = {}) {
  const ledger = capacityHandoff && typeof capacityHandoff === 'object' ? capacityHandoff : {};
  const rows = Array.isArray(ledger.rows) ? ledger.rows : [];
  if (!rows.length && !normalizeText(ledger.status)) return '';
  const status = normalizeText(ledger.status) || 'pending';
  const selectedCombination = normalizeText(ledger.selectedCombination) || '--';
  const selectedMember = normalizeText(ledger.selectedMemberId) || '--';
  const selectedSection = normalizeText(ledger.selectedSectionId) || '--';
  const activeSheet = normalizeText(ledger.activeSheet) || '--';
  const maxDcr = Number(ledger.maxDcr ?? 0);
  const minMarginPercent = Number(ledger.minMarginPct ?? ledger.minMarginPercent ?? 0);
  const materialCount = Math.max(0, Math.round(Number(ledger.materialCount ?? rows.length)));
  const sourceCapacityCount = Math.max(0, Math.round(Number(ledger.sourceCapacityCount ?? 0)));
  const estimatedCapacityCount = Math.max(0, Math.round(Number(ledger.estimatedCapacityCount ?? 0)));
  const capacityBackedMaterialCount = Math.max(0, Math.round(Number(ledger.capacityBackedMaterialCount ?? 0)));
  const forceRowCount = Math.max(0, Math.round(Number(ledger.forceRowCount ?? 0)));
  const mappedForceRowCount = Math.max(0, Math.round(Number(ledger.mappedForceRowCount ?? 0)));
  const sourceBackedCount = Math.max(0, Math.round(Number(ledger.sourceBackedCount ?? 0)));
  const materialMatchPercent = Number(ledger.materialMatchPercent ?? 0);
  const memberAssignmentMatchPercent = Number(ledger.memberAssignmentMatchPercent ?? 0);
  const materialLocked = ledger.materialLocked === true || normalizeText(ledger.materialLocked).toLowerCase() === 'true';
  const renderedRows = rows.length ? rows : [{
    key: 'capacity-state',
    label: 'Capacity State',
    materialId: '--',
    model: 'locked material model',
    family: 'Material',
    governingCombination: selectedCombination,
    memberId: selectedMember,
    sectionId: selectedSection,
    maxDcr,
    minMarginPct: minMarginPercent,
    sourceCapacityCount,
    estimatedCapacityCount,
    capacityBasis: 'capacity pending',
    demand: 0,
    capacity: 0,
    unit: '',
    tone: maxDcr >= 1 ? 'danger' : maxDcr >= 0.85 ? 'warn' : maxDcr > 0 ? 'accent' : 'neutral',
  }];
  return `<div class="drawing-capacity-handoff-ledger drawing-capacity-handoff-ledger--${escapeHtml(status)}" data-drawing-capacity-handoff-ledger data-drawing-capacity-handoff-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_CAPACITY_HANDOFF_LEDGER_SCHEMA_VERSION)}" data-drawing-capacity-handoff-status="${escapeHtml(status)}" data-drawing-capacity-handoff-active-sheet="${escapeHtml(activeSheet)}" data-drawing-capacity-handoff-selected-combination="${escapeHtml(selectedCombination)}" data-drawing-capacity-handoff-selected-member="${escapeHtml(selectedMember)}" data-drawing-capacity-handoff-selected-section="${escapeHtml(selectedSection)}" data-drawing-capacity-handoff-row-count="${escapeHtml(String(renderedRows.length))}" data-drawing-capacity-handoff-material-count="${escapeHtml(String(materialCount))}" data-drawing-capacity-handoff-source-capacity-count="${escapeHtml(String(sourceCapacityCount))}" data-drawing-capacity-handoff-estimated-capacity-count="${escapeHtml(String(estimatedCapacityCount))}" data-drawing-capacity-handoff-capacity-backed-material-count="${escapeHtml(String(capacityBackedMaterialCount))}" data-drawing-capacity-handoff-force-row-count="${escapeHtml(String(forceRowCount))}" data-drawing-capacity-handoff-mapped-force-row-count="${escapeHtml(String(mappedForceRowCount))}" data-drawing-capacity-handoff-source-backed-count="${escapeHtml(String(sourceBackedCount))}" data-drawing-capacity-handoff-max-dcr="${escapeHtml(String(Number.isFinite(maxDcr) ? maxDcr : 0))}" data-drawing-capacity-handoff-min-margin-percent="${escapeHtml(String(Number.isFinite(minMarginPercent) ? minMarginPercent : 0))}" data-drawing-capacity-handoff-material-locked="${materialLocked ? 'true' : 'false'}" data-drawing-capacity-handoff-material-match-percent="${escapeHtml(String(Number.isFinite(materialMatchPercent) ? materialMatchPercent : 0))}" data-drawing-capacity-handoff-member-assignment-match-percent="${escapeHtml(String(Number.isFinite(memberAssignmentMatchPercent) ? memberAssignmentMatchPercent : 0))}">
    <div class="drawing-capacity-handoff-ledger__head">
      <span>
        <b>Drawing Capacity Handoff</b>
        <em>${escapeHtml(activeSheet)} · ${escapeHtml(selectedCombination)} · capacity / margin</em>
      </span>
      <strong>D/C ${escapeHtml(formatLedgerNumber(maxDcr, { digits: 2 }))}</strong>
    </div>
    <div class="drawing-capacity-handoff-ledger__summary" data-drawing-capacity-handoff-summary>
      <span><b>${escapeHtml(formatLedgerNumber(sourceCapacityCount))}</b><em>source cap</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(estimatedCapacityCount))}</b><em>section est</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(minMarginPercent, { digits: 1, unit: '%' }))}</b><em>min margin</em></span>
      <span><b>${materialLocked ? 'locked' : 'review'}</b><em>materials</em></span>
    </div>
    <div class="drawing-capacity-handoff-ledger__rows">
      ${renderedRows.map(row => {
        const dcr = Number(row.maxDcr ?? row.dcr ?? 0);
        const dcrPct = Math.max(3, Math.min(100, Number.isFinite(dcr) ? dcr * 100 : 0));
        const margin = Number(row.minMarginPct ?? row.minMarginPercent ?? 0);
        const materialId = normalizeText(row.materialId) || '--';
        const memberId = normalizeText(row.memberId || row.memberSample) || selectedMember;
        const sectionId = normalizeText(row.sectionId || row.sectionSample) || selectedSection;
        const combination = normalizeText(row.governingCombination || row.combination) || selectedCombination;
        const sourceCount = Math.max(0, Math.round(Number(row.sourceCapacityCount ?? 0)));
        const estimatedCount = Math.max(0, Math.round(Number(row.estimatedCapacityCount ?? 0)));
        const demand = Number(row.demand ?? row.governingDemand ?? 0);
        const capacity = Number(row.capacity ?? row.governingCapacity ?? 0);
        const unit = normalizeText(row.unit || row.governingUnit);
        const demandCapacity = demand || capacity
          ? `${formatLedgerNumber(Math.abs(demand), { digits: 0, unit })}/${formatLedgerNumber(Math.abs(capacity), { digits: 0, unit })}`
          : 'demand/capacity';
        return `<button type="button" class="drawing-capacity-handoff-row drawing-capacity-handoff-row--${escapeHtml(resolveLedgerTone(row))}" data-drawing-capacity-handoff-row data-drawing-capacity-handoff-row-key="${escapeHtml(row.key || materialId)}" data-drawing-capacity-handoff-row-material-id="${escapeHtml(materialId)}" data-drawing-capacity-handoff-row-member="${escapeHtml(memberId)}" data-drawing-capacity-handoff-row-section="${escapeHtml(sectionId)}" data-drawing-capacity-handoff-row-combination="${escapeHtml(combination)}" data-drawing-capacity-handoff-row-sheet="${escapeHtml(activeSheet)}" data-drawing-capacity-handoff-row-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" data-drawing-capacity-handoff-row-margin-percent="${escapeHtml(String(Number.isFinite(margin) ? margin : 0))}" data-drawing-capacity-handoff-row-source-capacity-count="${escapeHtml(String(sourceCount))}" data-drawing-capacity-handoff-row-estimated-capacity-count="${escapeHtml(String(estimatedCount))}">
          <span class="drawing-capacity-handoff-row__main">
            <b>${escapeHtml(row.label || materialId)}</b>
            <em title="${escapeHtml(`${row.model || 'model'} · ${row.family || 'family'}`)}">${escapeHtml(compactDrawingMaterialModel(row.model || 'model'))} · ${escapeHtml(compactDrawingMaterialFamily(row.family || 'family'))}</em>
          </span>
          <span class="drawing-capacity-handoff-row__meter" aria-hidden="true"><i style="--drawing-capacity-handoff:${dcrPct.toFixed(1)}%"></i></span>
          <strong>D/C ${escapeHtml(formatLedgerNumber(dcr, { digits: 2 }))}</strong>
          <small title="${escapeHtml(`${demandCapacity} · margin ${formatLedgerNumber(margin, { digits: 1, unit: '%' })} · ${row.capacityBasis || 'capacity basis'}`)}">${escapeHtml(combination)} · ${escapeHtml(memberId)} · ${escapeHtml(sectionId)} · margin ${escapeHtml(formatLedgerNumber(margin, { digits: 1, unit: '%' }))}</small>
          <em title="${escapeHtml(row.capacityBasis || '')}">${escapeHtml(formatLedgerNumber(sourceCount))} src / ${escapeHtml(formatLedgerNumber(estimatedCount))} est · ${escapeHtml(row.capacityBasis || 'capacity pending')}</em>
        </button>`;
      }).join('')}
    </div>
  </div>`;
}

function buildDrawingMaterialModelMatrixHtml(materialModelMatrix = {}) {
  const matrix = materialModelMatrix && typeof materialModelMatrix === 'object' ? materialModelMatrix : {};
  const rows = Array.isArray(matrix.rows) ? matrix.rows : [];
  if (!rows.length && !normalizeText(matrix.status)) return '';
  const status = normalizeText(matrix.status) || 'pending';
  const activeSheet = normalizeText(matrix.activeSheet) || '--';
  const selectedCombination = normalizeText(matrix.selectedCombination) || '--';
  const materialCount = Math.max(0, Math.round(Number(matrix.materialCount ?? rows.length)));
  const lockedCount = Math.max(0, Math.round(Number(matrix.lockedCount ?? 0)));
  const changedCount = Math.max(0, Math.round(Number(matrix.changedCount ?? 0)));
  const forceBackedMaterialCount = Math.max(0, Math.round(Number(matrix.forceBackedMaterialCount ?? 0)));
  const materialMatchPercent = Number(matrix.materialMatchPercent ?? 0);
  const memberAssignmentMatchPercent = Number(matrix.memberAssignmentMatchPercent ?? 0);
  const renderedRows = rows.length ? rows : [{
    materialId: '--',
    label: 'Material model',
    family: 'Material',
    model: 'source model',
    status: changedCount ? 'changed' : 'locked',
    usageCount: 0,
    tokenCount: 0,
    maxDcr: 0,
    forceBacked: false,
    detail: 'source material model lock pending',
    tone: changedCount ? 'danger' : 'neutral',
  }];
  return `<div class="drawing-material-model-matrix drawing-material-model-matrix--${escapeHtml(status)}" data-drawing-material-model-matrix data-drawing-material-model-matrix-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_MATERIAL_MODEL_MATRIX_SCHEMA_VERSION)}" data-drawing-material-model-matrix-status="${escapeHtml(status)}" data-drawing-material-model-matrix-active-sheet="${escapeHtml(activeSheet)}" data-drawing-material-model-matrix-selected-combination="${escapeHtml(selectedCombination)}" data-drawing-material-model-matrix-row-count="${escapeHtml(String(renderedRows.length))}" data-drawing-material-model-matrix-material-count="${escapeHtml(String(materialCount))}" data-drawing-material-model-matrix-locked-count="${escapeHtml(String(lockedCount))}" data-drawing-material-model-matrix-changed-count="${escapeHtml(String(changedCount))}" data-drawing-material-model-matrix-force-backed-material-count="${escapeHtml(String(forceBackedMaterialCount))}" data-drawing-material-model-matrix-material-match-percent="${escapeHtml(String(Number.isFinite(materialMatchPercent) ? materialMatchPercent : 0))}" data-drawing-material-model-matrix-member-assignment-match-percent="${escapeHtml(String(Number.isFinite(memberAssignmentMatchPercent) ? memberAssignmentMatchPercent : 0))}">
    <div class="drawing-material-model-matrix__head">
      <span>
        <b>Drawing Material Models</b>
        <em>${escapeHtml(activeSheet)} · ${escapeHtml(selectedCombination)} · 100% material lock target</em>
      </span>
      <strong>${escapeHtml(formatLedgerNumber(lockedCount))}/${escapeHtml(formatLedgerNumber(materialCount))} locked</strong>
    </div>
    <div class="drawing-material-model-matrix__summary" data-drawing-material-model-matrix-summary>
      <span><b>${escapeHtml(formatLedgerNumber(materialMatchPercent, { digits: 1, unit: '%' }))}</b><em>library match</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(memberAssignmentMatchPercent, { digits: 1, unit: '%' }))}</b><em>member id match</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(forceBackedMaterialCount))}</b><em>force-backed models</em></span>
    </div>
    <div class="drawing-material-model-matrix__rows">
      ${renderedRows.map(row => {
        const dcr = Number(row.maxDcr ?? 0);
        const dcrPct = Math.max(3, Math.min(100, Number.isFinite(dcr) ? dcr * 100 : 0));
        const tone = resolveLedgerTone(row);
        const familyLabel = compactDrawingMaterialFamily(row.family || 'Material');
        const modelLabel = compactDrawingMaterialModel(row.model || 'source model');
        return `<button type="button" class="drawing-material-model-row drawing-material-model-row--${escapeHtml(tone)}" data-drawing-material-model-row data-drawing-material-model-row-material-id="${escapeHtml(row.materialId || '')}" data-drawing-material-model-row-status="${escapeHtml(row.status || '')}" data-drawing-material-model-row-force-backed="${row.forceBacked ? 'true' : 'false'}" data-drawing-material-model-row-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}">
          <span class="drawing-material-model-row__main">
            <b>${escapeHtml(row.label || row.materialId || '--')}</b>
            <em title="${escapeHtml(`${row.family || 'Material'} · ${row.model || 'source model'}`)}">${escapeHtml(familyLabel)} · ${escapeHtml(modelLabel)}</em>
          </span>
          <span class="drawing-material-model-row__lock">
            <strong>${escapeHtml(row.status || '--')}</strong>
            <em>${escapeHtml(formatLedgerNumber(row.tokenCount || 0))} tokens</em>
          </span>
          <span class="drawing-material-model-row__meter" aria-hidden="true"><i style="--drawing-material-model-force:${dcrPct.toFixed(1)}%"></i></span>
          <small title="${escapeHtml(row.detail || '')}">${escapeHtml(row.detail || '')}</small>
        </button>`;
      }).join('')}
    </div>
  </div>`;
}

function buildDrawingMaterialConstitutiveRegisterHtml(materialConstitutiveRegister = {}) {
  const register = materialConstitutiveRegister && typeof materialConstitutiveRegister === 'object'
    ? materialConstitutiveRegister
    : {};
  const rows = Array.isArray(register.rows) ? register.rows : [];
  if (!rows.length && !normalizeText(register.status)) return '';
  const status = normalizeText(register.status) || 'pending';
  const activeSheet = normalizeText(register.activeSheet) || '--';
  const selectedCombination = normalizeText(register.selectedCombination) || '--';
  const materialCount = Math.max(0, Math.round(Number(register.materialCount ?? rows.length)));
  const rowCount = Math.max(0, Math.round(Number(register.rowCount ?? rows.length)));
  const sourceBackedCount = Math.max(0, Math.round(Number(register.sourceBackedCount ?? 0)));
  const nonlinearCount = Math.max(0, Math.round(Number(register.nonlinearCount ?? 0)));
  const curveRowCount = Math.max(0, Math.round(Number(register.curveRowCount ?? 0)));
  const capacityBackedMaterialCount = Math.max(0, Math.round(Number(register.capacityBackedMaterialCount ?? 0)));
  const materialMatchPercent = Number(register.materialMatchPercent ?? 0);
  const memberAssignmentMatchPercent = Number(register.memberAssignmentMatchPercent ?? 0);
  const maxDemandRatio = Number(register.maxDemandRatio ?? 0);
  const maxDcr = Number(register.maxDcr ?? 0);
  const materialLocked = Boolean(register.materialLocked);
  const renderedRows = rows.length ? rows : [{
    materialId: '--',
    label: 'Material model',
    family: 'Material',
    model: 'constitutive law pending',
    hardening: '--',
    state: 'pending',
    usageCount: 0,
    sourceStatus: 'missing',
    sectionLinkCount: 0,
    demandRatio: 0,
    maxDcr: 0,
    curveBacked: false,
    capacityBacked: false,
    tone: 'neutral',
  }];
  return `<div class="drawing-material-constitutive-register drawing-material-constitutive-register--${escapeHtml(status)}" data-drawing-material-constitutive-register data-drawing-material-constitutive-register-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_MATERIAL_CONSTITUTIVE_REGISTER_SCHEMA_VERSION)}" data-drawing-material-constitutive-register-status="${escapeHtml(status)}" data-drawing-material-constitutive-register-active-sheet="${escapeHtml(activeSheet)}" data-drawing-material-constitutive-register-selected-combination="${escapeHtml(selectedCombination)}" data-drawing-material-constitutive-register-row-count="${escapeHtml(String(rowCount))}" data-drawing-material-constitutive-register-material-count="${escapeHtml(String(materialCount))}" data-drawing-material-constitutive-register-source-backed-count="${escapeHtml(String(sourceBackedCount))}" data-drawing-material-constitutive-register-nonlinear-count="${escapeHtml(String(nonlinearCount))}" data-drawing-material-constitutive-register-curve-row-count="${escapeHtml(String(curveRowCount))}" data-drawing-material-constitutive-register-capacity-backed-material-count="${escapeHtml(String(capacityBackedMaterialCount))}" data-drawing-material-constitutive-register-material-locked="${materialLocked ? 'true' : 'false'}" data-drawing-material-constitutive-register-material-match-percent="${escapeHtml(String(Number.isFinite(materialMatchPercent) ? materialMatchPercent : 0))}" data-drawing-material-constitutive-register-member-assignment-match-percent="${escapeHtml(String(Number.isFinite(memberAssignmentMatchPercent) ? memberAssignmentMatchPercent : 0))}" data-drawing-material-constitutive-register-max-demand-ratio="${escapeHtml(String(Number.isFinite(maxDemandRatio) ? maxDemandRatio : 0))}" data-drawing-material-constitutive-register-max-dcr="${escapeHtml(String(Number.isFinite(maxDcr) ? maxDcr : 0))}">
    <div class="drawing-material-constitutive-register__head">
      <span>
        <b>Drawing Material Constitutive Register</b>
        <em>${escapeHtml(activeSheet)} · ${escapeHtml(selectedCombination)} · all source material laws</em>
      </span>
      <strong>${escapeHtml(formatLedgerNumber(materialMatchPercent, { digits: 1, unit: '%' }))}</strong>
    </div>
    <div class="drawing-material-constitutive-register__summary" data-drawing-material-constitutive-summary>
      <span><b>${escapeHtml(formatLedgerNumber(rowCount))}/${escapeHtml(formatLedgerNumber(materialCount))}</b><em>shown / source</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(sourceBackedCount))}</b><em>source-backed</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(nonlinearCount))}</b><em>nonlinear watch</em></span>
      <span><b>${materialLocked ? 'locked' : 'review'}</b><em>${escapeHtml(formatLedgerNumber(memberAssignmentMatchPercent, { digits: 1, unit: '%' }))} members</em></span>
    </div>
    <div class="drawing-material-constitutive-register__rows">
      ${renderedRows.map(row => {
        const materialId = normalizeText(row.materialId || row.material_id) || '--';
        const demandRatio = Number(row.demandRatio ?? 0);
        const dcr = Number(row.maxDcr ?? 0);
        const meter = Math.max(3, Math.min(100, Number.isFinite(demandRatio) ? demandRatio * 100 : 0));
        const sectionLabel = normalizeText(row.primarySectionLabel || row.primarySectionId || row.sectionId) || '--';
        const memberId = normalizeText(row.governingMemberId || row.memberId) || '--';
        const combination = normalizeText(row.governingCombination || row.combination || selectedCombination) || '--';
        const curveBacked = Boolean(row.curveBacked);
        const capacityBacked = Boolean(row.capacityBacked);
        const fyLabel = formatLedgerNumber(row.yieldStrength, { digits: 0, unit: ' MPa' });
        const strainLabel = formatLedgerNumber(row.yieldStrain, { digits: 5 });
        const dcrLabel = formatLedgerNumber(dcr, { digits: 2 });
        return `<button type="button" class="drawing-material-constitutive-row drawing-material-constitutive-row--${escapeHtml(resolveLedgerTone(row))}" data-drawing-material-constitutive-row data-drawing-material-constitutive-row-material-id="${escapeHtml(materialId)}" data-drawing-material-constitutive-row-state="${escapeHtml(row.state || '')}" data-drawing-material-constitutive-row-model="${escapeHtml(row.model || '')}" data-drawing-material-constitutive-row-source-status="${escapeHtml(row.sourceStatus || '')}" data-drawing-material-constitutive-row-lock-status="${escapeHtml(row.lockStatus || '')}" data-drawing-material-constitutive-row-curve-backed="${curveBacked ? 'true' : 'false'}" data-drawing-material-constitutive-row-capacity-backed="${capacityBacked ? 'true' : 'false'}" data-drawing-material-constitutive-row-combination="${escapeHtml(combination)}" data-drawing-material-constitutive-row-member="${escapeHtml(memberId)}" data-drawing-material-constitutive-row-section="${escapeHtml(sectionLabel)}" data-drawing-material-constitutive-row-demand-ratio="${escapeHtml(String(Number.isFinite(demandRatio) ? demandRatio : 0))}" data-drawing-material-constitutive-row-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" title="${escapeHtml(`${row.label || materialId} · ${row.model || 'model'} · ${row.hardening || '--'}`)}">
          <span class="drawing-material-constitutive-row__main">
            <b>${escapeHtml(row.label || materialId)}</b>
            <em>${escapeHtml(compactDrawingMaterialFamily(row.family || 'Material'))} · ${escapeHtml(compactDrawingMaterialModel(row.model || 'model'))}</em>
          </span>
          <span class="drawing-material-constitutive-row__law">
            <strong>${escapeHtml(row.state || '--')}</strong>
            <em>${escapeHtml(row.hardening || '--')}</em>
          </span>
          <span class="drawing-material-constitutive-row__meter" aria-hidden="true"><i style="--drawing-material-constitutive:${meter.toFixed(1)}%"></i></span>
          <small>${escapeHtml(row.sourceStatus || 'source')} · ${escapeHtml(formatLedgerNumber(row.usageCount || 0))} elems · ${escapeHtml(formatLedgerNumber(row.sectionLinkCount || 0))} sections</small>
          <em>${escapeHtml(fyLabel)} · eps ${escapeHtml(strainLabel)} · D/C ${escapeHtml(dcrLabel)} · ${curveBacked ? 'curve' : 'curve pending'} · ${capacityBacked ? 'capacity' : 'capacity pending'}</em>
          <small>${escapeHtml(combination)} · ${escapeHtml(memberId)} · ${escapeHtml(sectionLabel)}</small>
        </button>`;
      }).join('')}
    </div>
  </div>`;
}

function buildDrawingMaterialCurveEvidenceHtml(materialCurveEvidence = {}) {
  const evidence = materialCurveEvidence && typeof materialCurveEvidence === 'object'
    ? materialCurveEvidence
    : {};
  const rows = Array.isArray(evidence.rows) ? evidence.rows : [];
  if (!rows.length && !normalizeText(evidence.status)) return '';
  const status = normalizeText(evidence.status) || 'pending';
  const activeSheet = normalizeText(evidence.activeSheet) || '--';
  const selectedCombination = normalizeText(evidence.selectedCombination) || '--';
  const curveCount = Math.max(0, Math.round(Number(evidence.curveCount ?? rows.length)));
  const sourceBackedCount = Math.max(0, Math.round(Number(evidence.sourceBackedCount ?? 0)));
  const nonlinearCount = Math.max(0, Math.round(Number(evidence.nonlinearCount ?? 0)));
  const capacityBackedCount = Math.max(0, Math.round(Number(evidence.capacityBackedCount ?? 0)));
  const materialMatchPercent = Number(evidence.materialMatchPercent ?? 0);
  const memberAssignmentMatchPercent = Number(evidence.memberAssignmentMatchPercent ?? 0);
  const maxDemandRatio = Number(evidence.maxDemandRatio ?? 0);
  const maxDcr = Number(evidence.maxDcr ?? 0);
  const materialLocked = Boolean(evidence.materialLocked);
  const renderedRows = rows.length ? rows : [{
    materialId: '--',
    label: 'Material curve',
    family: 'Material',
    model: 'curve pending',
    state: 'pending',
    hardening: '--',
    sourceBacked: false,
    capacityBacked: false,
    demandRatio: 0,
    maxDcr: 0,
    curvePath: 'M8 48 L94 12',
    yieldPoint: { x: 54, y: 24 },
    demandPoint: { x: 42, y: 30 },
    tone: 'neutral',
  }];
  return `<div class="drawing-material-curve-evidence drawing-material-curve-evidence--${escapeHtml(status)}" data-drawing-material-curve-evidence data-drawing-material-curve-evidence-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_MATERIAL_CURVE_EVIDENCE_SCHEMA_VERSION)}" data-drawing-material-curve-evidence-status="${escapeHtml(status)}" data-drawing-material-curve-evidence-active-sheet="${escapeHtml(activeSheet)}" data-drawing-material-curve-evidence-selected-combination="${escapeHtml(selectedCombination)}" data-drawing-material-curve-evidence-curve-count="${escapeHtml(String(curveCount))}" data-drawing-material-curve-evidence-source-backed-count="${escapeHtml(String(sourceBackedCount))}" data-drawing-material-curve-evidence-nonlinear-count="${escapeHtml(String(nonlinearCount))}" data-drawing-material-curve-evidence-capacity-backed-count="${escapeHtml(String(capacityBackedCount))}" data-drawing-material-curve-evidence-material-locked="${materialLocked ? 'true' : 'false'}" data-drawing-material-curve-evidence-material-match-percent="${escapeHtml(String(Number.isFinite(materialMatchPercent) ? materialMatchPercent : 0))}" data-drawing-material-curve-evidence-member-assignment-match-percent="${escapeHtml(String(Number.isFinite(memberAssignmentMatchPercent) ? memberAssignmentMatchPercent : 0))}" data-drawing-material-curve-evidence-max-demand-ratio="${escapeHtml(String(Number.isFinite(maxDemandRatio) ? maxDemandRatio : 0))}" data-drawing-material-curve-evidence-max-dcr="${escapeHtml(String(Number.isFinite(maxDcr) ? maxDcr : 0))}">
    <div class="drawing-material-curve-evidence__head">
      <span>
        <b>Drawing Material Curve Evidence</b>
        <em>${escapeHtml(activeSheet)} · ${escapeHtml(selectedCombination)} · source curve + demand point</em>
      </span>
      <strong>D/C ${escapeHtml(formatLedgerNumber(maxDcr, { digits: 2 }))}</strong>
    </div>
    <div class="drawing-material-curve-evidence__summary" data-drawing-material-curve-summary>
      <span><b>${escapeHtml(formatLedgerNumber(curveCount))}</b><em>curves</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(sourceBackedCount))}</b><em>source-backed</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(capacityBackedCount))}</b><em>capacity-backed</em></span>
      <span><b>${materialLocked ? 'locked' : 'review'}</b><em>${escapeHtml(formatLedgerNumber(materialMatchPercent, { digits: 1, unit: '%' }))} materials</em></span>
    </div>
    <div class="drawing-material-curve-evidence__rows">
      ${renderedRows.map(row => {
        const materialId = normalizeText(row.materialId || row.material_id) || '--';
        const demandRatio = Number(row.demandRatio ?? 0);
        const dcr = Number(row.maxDcr ?? 0);
        const combination = normalizeText(row.governingCombination || row.combination || selectedCombination) || '--';
        const memberId = normalizeText(row.governingMemberId || row.memberId) || '--';
        const sectionLabel = normalizeText(row.primarySectionLabel || row.primarySectionId || row.sectionId) || '--';
        const curvePath = normalizeText(row.curvePath) || 'M8 48 L94 12';
        const yieldPoint = row.yieldPoint && typeof row.yieldPoint === 'object' ? row.yieldPoint : { x: 54, y: 24 };
        const demandPoint = row.demandPoint && typeof row.demandPoint === 'object' ? row.demandPoint : { x: 42, y: 30 };
        const fyLabel = formatLedgerNumber(row.yieldStrength, { digits: 0, unit: ' MPa' });
        const strainLabel = formatLedgerNumber(row.yieldStrain, { digits: 5 });
        return `<button type="button" class="drawing-material-curve-row drawing-material-curve-row--${escapeHtml(resolveLedgerTone(row))}" data-drawing-material-curve-row data-drawing-material-curve-row-material-id="${escapeHtml(materialId)}" data-drawing-material-curve-row-sheet="${escapeHtml(activeSheet)}" data-drawing-material-curve-row-model="${escapeHtml(row.model || '')}" data-drawing-material-curve-row-source-backed="${row.sourceBacked ? 'true' : 'false'}" data-drawing-material-curve-row-capacity-backed="${row.capacityBacked ? 'true' : 'false'}" data-drawing-material-curve-row-combination="${escapeHtml(combination)}" data-drawing-material-curve-row-member="${escapeHtml(memberId)}" data-drawing-material-curve-row-section="${escapeHtml(sectionLabel)}" data-drawing-material-curve-row-demand-ratio="${escapeHtml(String(Number.isFinite(demandRatio) ? demandRatio : 0))}" data-drawing-material-curve-row-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" title="${escapeHtml(`${row.label || materialId} curve · ${row.model || 'model'} · demand ${formatLedgerNumber(demandRatio, { digits: 2 })}`)}">
          <span class="drawing-material-curve-row__main">
            <b>${escapeHtml(row.label || materialId)}</b>
            <em>${escapeHtml(compactDrawingMaterialFamily(row.family || 'Material'))} · ${escapeHtml(compactDrawingMaterialModel(row.model || 'model'))}</em>
            <small>${escapeHtml(row.state || '--')} · ${escapeHtml(row.hardening || '--')}</small>
          </span>
          <svg class="drawing-material-curve-row__svg" data-drawing-material-curve-svg viewBox="0 0 100 54" role="img" aria-label="${escapeHtml(`${row.label || materialId} drawing material curve`)}">
            <path class="drawing-material-curve-row__axis" d="M8 8 V48 H94"></path>
            <path class="drawing-material-curve-row__path" d="${escapeHtml(curvePath)}"></path>
            <circle class="drawing-material-curve-row__yield" data-drawing-material-curve-yield-marker cx="${escapeHtml(formatDrawingCurveCoord(yieldPoint.x))}" cy="${escapeHtml(formatDrawingCurveCoord(yieldPoint.y))}" r="2.1"></circle>
            <circle class="drawing-material-curve-row__demand" data-drawing-material-curve-demand-marker cx="${escapeHtml(formatDrawingCurveCoord(demandPoint.x))}" cy="${escapeHtml(formatDrawingCurveCoord(demandPoint.y))}" r="2.8"></circle>
          </svg>
          <span class="drawing-material-curve-row__meta">
            <strong>D/C ${escapeHtml(formatLedgerNumber(dcr, { digits: 2 }))}</strong>
            <em>${escapeHtml(fyLabel)} · eps ${escapeHtml(strainLabel)}</em>
            <small>${escapeHtml(combination)} · ${escapeHtml(memberId)} · ${escapeHtml(sectionLabel)}</small>
          </span>
        </button>`;
      }).join('')}
    </div>
  </div>`;
}

function buildDrawingSheetForceMatrixHtml(sheetForceMatrix = {}) {
  const matrix = sheetForceMatrix && typeof sheetForceMatrix === 'object' ? sheetForceMatrix : {};
  const rows = Array.isArray(matrix.rows) ? matrix.rows : [];
  if (!rows.length && !normalizeText(matrix.status)) return '';
  const status = normalizeText(matrix.status) || 'pending';
  const activeSheet = normalizeText(matrix.activeSheet) || '--';
  const selectedCombination = normalizeText(matrix.selectedCombination) || '--';
  const selectedMember = normalizeText(matrix.selectedMemberId) || '--';
  const sourceBackedCount = Math.max(0, Math.round(Number(matrix.sourceBackedCount ?? 0)));
  const forceRowCount = Math.max(0, Math.round(Number(matrix.forceRowCount ?? 0)));
  const maxDcr = Number(matrix.maxDcr ?? 0);
  const materialLocked = Boolean(matrix.materialLocked);
  const renderedRows = rows.length ? rows : [{
    key: 'active-sheet',
    label: activeSheet,
    sheetName: activeSheet,
    revision: '--',
    callout: '--',
    memberId: selectedMember,
    dcr: maxDcr,
    active: true,
    forceRowCount,
    sourceBackedCount,
    detail: materialLocked ? 'material locked' : 'material review',
    tone: maxDcr >= 1 ? 'danger' : maxDcr >= 0.85 ? 'warn' : maxDcr > 0 ? 'accent' : 'neutral',
  }];
  return `<div class="drawing-sheet-force-matrix drawing-sheet-force-matrix--${escapeHtml(status)}" data-drawing-sheet-force-matrix data-drawing-sheet-force-matrix-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_MATRIX_SCHEMA_VERSION)}" data-drawing-sheet-force-matrix-status="${escapeHtml(status)}" data-drawing-sheet-force-matrix-active-sheet="${escapeHtml(activeSheet)}" data-drawing-sheet-force-matrix-sheet-count="${escapeHtml(String(renderedRows.length))}" data-drawing-sheet-force-matrix-selected-combination="${escapeHtml(selectedCombination)}" data-drawing-sheet-force-matrix-selected-member="${escapeHtml(selectedMember)}" data-drawing-sheet-force-matrix-source-backed-count="${escapeHtml(String(sourceBackedCount))}" data-drawing-sheet-force-matrix-force-row-count="${escapeHtml(String(forceRowCount))}" data-drawing-sheet-force-matrix-max-dcr="${escapeHtml(String(Number.isFinite(maxDcr) ? maxDcr : 0))}" data-drawing-sheet-force-matrix-material-locked="${materialLocked ? 'true' : 'false'}">
    <div class="drawing-sheet-force-matrix__head">
      <span>
        <b>Drawing Sheet Force Matrix</b>
        <em>${escapeHtml(selectedCombination)} · ${escapeHtml(selectedMember)}</em>
      </span>
      <strong>${escapeHtml(formatLedgerNumber(renderedRows.length))} sheets</strong>
    </div>
    <div class="drawing-sheet-force-matrix__summary" data-drawing-sheet-force-matrix-summary>
      <span><b>D/C ${escapeHtml(formatLedgerNumber(maxDcr, { digits: 2 }))}</b><em>max force</em></span>
      <span><b>${escapeHtml(formatLedgerNumber(sourceBackedCount))}</b><em>source rows</em></span>
      <span><b>${materialLocked ? 'locked' : 'review'}</b><em>material ids</em></span>
    </div>
    <div class="drawing-sheet-force-matrix__rows">
      ${renderedRows.map(row => {
        const sheetName = normalizeText(row.sheetName || row.label || row.key) || '--';
        const dcr = Number(row.dcr ?? maxDcr);
        const dcrPct = Math.max(3, Math.min(100, Number.isFinite(dcr) ? dcr * 100 : 0));
        const active = Boolean(row.active) || sheetName === activeSheet;
        const tone = resolveLedgerTone(row);
        const compactCallout = compactReceiptValue(row.callout || '--');
        const compactRevision = compactDrawingRevision(row.revision || '--');
        return `<button type="button" class="drawing-sheet-force-row drawing-sheet-force-row--${escapeHtml(tone)}${active ? ' is-active' : ''}" data-drawing-sheet-force-row data-drawing-sheet-force-row-sheet="${escapeHtml(sheetName)}" data-drawing-sheet-force-row-active="${active ? 'true' : 'false'}" data-drawing-sheet-force-row-dcr="${escapeHtml(String(Number.isFinite(dcr) ? dcr : 0))}" aria-pressed="${active ? 'true' : 'false'}">
          <span>
            <b>${escapeHtml(row.label || sheetName)}</b>
            <em title="${escapeHtml(`${row.callout || '--'} · ${row.revision || '--'}`)}">${escapeHtml(compactCallout)} · ${escapeHtml(compactRevision)}</em>
          </span>
          <span class="drawing-sheet-force-row__meter" aria-hidden="true"><i style="--drawing-sheet-force:${dcrPct.toFixed(1)}%"></i></span>
          <strong>D/C ${escapeHtml(formatLedgerNumber(dcr, { digits: 2 }))}</strong>
          <small title="${escapeHtml(row.detail || '')}">${escapeHtml(row.detail || '')}</small>
        </button>`;
      }).join('')}
    </div>
  </div>`;
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
  materialParity = {},
  sourceDetailLedger = {},
  sheetDetailMatrix = {},
  forceHandoff = {},
  forceVectorEvidence = {},
  sheetForceOverlay = {},
  capacityHandoff = {},
  materialConstitutiveRegister = {},
  materialCurveEvidence = {},
  sheetForceMatrix = {},
  materialModelMatrix = {},
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
  const deepLinkReady = Boolean(deepLinkUrl);
  const selectionSyncReady = Boolean(memberId && memberId !== '--' && calloutId && calloutId !== '--');
  const receiptRows = [
    {
      key: 'active-sheet',
      label: 'Active Sheet',
      value: primarySheetLabel,
      detail: primarySheetHref ? 'SVG linked' : 'sheet missing',
      tone: primarySheetHref ? 'success' : 'danger',
      attr: 'sheet',
    },
    {
      key: 'callout',
      label: 'Callout',
      value: calloutId,
      detail: calloutLabel,
      tone: calloutId !== '--' ? 'success' : 'warn',
      attr: 'callout',
    },
    {
      key: 'deep-link',
      label: 'Viewer Link',
      value: deepLinkReady ? 'copy-ready' : 'missing',
      detail: deepLinkReady ? 'selection URL' : 'URL unavailable',
      tone: deepLinkReady ? 'success' : 'danger',
      attr: 'deep-link',
    },
    {
      key: 'selection-sync',
      label: 'Selection Sync',
      value: memberId,
      detail: selectionSyncReady ? 'viewport/report aligned' : 'member pending',
      tone: selectionSyncReady ? 'success' : 'warn',
      attr: 'member',
    },
  ];
  const previewHtml = buildDrawingHandoffPreviewHtml({
    sheets,
    sheetPackage,
    revision,
    calloutId,
    calloutLabel,
    memberId,
  });
  const materialParityHtml = buildDrawingMaterialParityLedgerHtml(materialParity);
  const sourceDetailLedgerHtml = buildDrawingSourceDetailLedgerHtml(sourceDetailLedger);
  const sheetDetailMatrixHtml = buildDrawingSheetDetailMatrixHtml(sheetDetailMatrix);
  const forceHandoffHtml = buildDrawingForceHandoffLedgerHtml(forceHandoff);
  const forceVectorEvidenceHtml = buildDrawingForceVectorEvidenceHtml(forceVectorEvidence);
  const sheetForceOverlayHtml = buildDrawingSheetForceOverlayHtml(sheetForceOverlay);
  const capacityHandoffHtml = buildDrawingCapacityHandoffLedgerHtml(capacityHandoff);
  const materialModelMatrixHtml = buildDrawingMaterialModelMatrixHtml(materialModelMatrix);
  const materialConstitutiveRegisterHtml = buildDrawingMaterialConstitutiveRegisterHtml(materialConstitutiveRegister);
  const materialCurveEvidenceHtml = buildDrawingMaterialCurveEvidenceHtml(materialCurveEvidence);
  const sheetForceMatrixHtml = buildDrawingSheetForceMatrixHtml(sheetForceMatrix);
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

  return `<div class="drawing-handoff-panel" data-drawing-handoff-panel data-drawing-handoff-schema="${escapeHtml(STRUCTURE_VIEWER_DRAWING_HANDOFF_PANEL_SCHEMA_VERSION)}" data-drawing-handoff-status="${escapeHtml(status)}" data-drawing-handoff-sheet-count="${escapeHtml(String(sheetPackage.sheet_count ?? sheets.length ?? 0))}" data-drawing-handoff-active-sheet="${escapeHtml(primarySheetLabel)}" data-drawing-handoff-active-callout="${escapeHtml(calloutId)}" data-drawing-handoff-selected-member="${escapeHtml(memberId)}" data-drawing-handoff-revision="${escapeHtml(revision)}" data-drawing-handoff-deep-link-ready="${deepLinkReady ? 'true' : 'false'}" data-drawing-material-parity-schema="${escapeHtml(materialParity?.schemaVersion || STRUCTURE_VIEWER_DRAWING_MATERIAL_PARITY_LEDGER_SCHEMA_VERSION)}" data-drawing-material-parity-status="${escapeHtml(materialParity?.status || 'pending')}" data-drawing-material-parity-material-match-percent="${escapeHtml(String(materialParity?.materialMatchPercent ?? 0))}" data-drawing-material-parity-member-assignment-match-percent="${escapeHtml(String(materialParity?.memberAssignmentMatchPercent ?? 0))}" data-drawing-material-parity-section-assignment-change-count="${escapeHtml(String(materialParity?.sectionAssignmentChangeCount ?? 0))}">
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
    ${materialParityHtml}
    ${sourceDetailLedgerHtml}
    ${sheetDetailMatrixHtml}
    ${materialModelMatrixHtml}
    ${materialConstitutiveRegisterHtml}
    ${materialCurveEvidenceHtml}
    ${forceHandoffHtml}
    ${forceVectorEvidenceHtml}
    ${sheetForceOverlayHtml}
    ${capacityHandoffHtml}
    ${sheetForceMatrixHtml}
    ${previewHtml}
    <div class="drawing-handoff-callout">
      <span>Active callout</span>
      <strong>${escapeHtml(calloutLabel)}</strong>
      <small>${escapeHtml(calloutId)}</small>
    </div>
    <div class="drawing-handoff-receipt" data-drawing-handoff-receipt>
      ${receiptRows.map(row => `<span class="drawing-handoff-receipt__row drawing-handoff-receipt__row--${escapeHtml(row.tone)}" data-drawing-handoff-receipt-row="${escapeHtml(row.key)}">
        <b>${escapeHtml(row.label)}</b>
        <strong title="${escapeHtml(row.value)}" data-drawing-handoff-active-${escapeHtml(row.attr)}-value data-drawing-handoff-receipt-full-value="${escapeHtml(row.value)}">${escapeHtml(compactReceiptValue(row.value))}</strong>
        <em title="${escapeHtml(row.detail)}" data-drawing-handoff-${escapeHtml(row.key)}-detail>${escapeHtml(row.detail)}</em>
      </span>`).join('')}
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
