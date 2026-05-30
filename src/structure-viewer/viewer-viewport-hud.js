/**
 * Viewport HUD: context strip, scale bar, compass, selection readout, contour legend, info overlay.
 */

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatCoord(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toFixed(2) : '--';
}

export function ensureViewportHud(viewportEl) {
  if (!viewportEl || viewportEl.querySelector('[data-viewport-hud]')) {
    return viewportEl?.querySelector('[data-viewport-hud]') || null;
  }
  const hud = document.createElement('div');
  hud.className = 'viewport-hud';
  hud.setAttribute('data-viewport-hud', '');
  hud.innerHTML = `
    <div class="viewport-hud__context" data-viewport-hud-context>
      <span class="viewport-hud__eyebrow">Structural Insight</span>
      <strong data-viewport-hud-case>Case --</strong>
      <em data-viewport-hud-mode>Model review</em>
    </div>
    <div class="viewport-hud__legend viewport-contour-legend is-hidden" data-viewport-contour-legend aria-label="Contour legend">
      <span class="viewport-contour-legend__title">Result scale</span>
      <div class="viewport-contour-legend__ramp" aria-hidden="true"></div>
      <div class="viewport-contour-legend__ticks">
        <span>0.0</span><span>0.5</span><span>1.0</span><span>1.5+</span>
      </div>
      <em data-viewport-contour-unit>D/C ratio</em>
    </div>
    <div class="viewport-hud__footer">
      <div class="viewport-hud__scale" data-viewport-scale-bar aria-hidden="true">
        <span class="viewport-hud__scale-line"></span>
        <b data-viewport-scale-label>10 m</b>
      </div>
      <div class="viewport-hud__compass" data-viewport-compass aria-label="North indicator">
        <span class="viewport-hud__compass-needle">N</span>
      </div>
      <div class="viewport-hud__readout" data-viewport-readout>
        <span data-viewport-coords>X -- · Y -- · Z --</span>
        <span data-viewport-selection>Selection --</span>
      </div>
    </div>
  `;
  viewportEl.appendChild(hud);
  return hud;
}

export function updateViewportHudContext({
  caseLabel = '',
  modeLabel = '',
  contourMode = false,
  contourUnit = 'D/C ratio',
} = {}) {
  const hud = document.querySelector('[data-viewport-hud]');
  if (!hud) return;
  const caseEl = hud.querySelector('[data-viewport-hud-case]');
  const modeEl = hud.querySelector('[data-viewport-hud-mode]');
  if (caseEl) caseEl.textContent = caseLabel || 'Case --';
  if (modeEl) modeEl.textContent = modeLabel || 'Model review';
  const legend = hud.querySelector('[data-viewport-contour-legend]');
  if (legend) {
    legend.classList.toggle('is-hidden', !contourMode);
    const unit = legend.querySelector('[data-viewport-contour-unit]');
    if (unit) unit.textContent = contourUnit;
  }
}

export function updateViewportHudScale({ metersPerPixel = null, label = '' } = {}) {
  const scaleLabel = document.querySelector('[data-viewport-scale-label]');
  const scaleBar = document.querySelector('[data-viewport-scale-bar] .viewport-hud__scale-line');
  if (scaleLabel) scaleLabel.textContent = label || (metersPerPixel ? `${Math.round(metersPerPixel * 80)} m` : '10 m');
  if (scaleBar && metersPerPixel) {
    const px = Math.min(120, Math.max(48, 10 / Math.max(metersPerPixel, 1e-6)));
    scaleBar.style.width = `${px}px`;
  }
}

export function updateViewportHudReadout({ x, y, z, selection = '' } = {}) {
  const coords = document.querySelector('[data-viewport-coords]');
  const sel = document.querySelector('[data-viewport-selection]');
  if (coords) coords.textContent = `X ${formatCoord(x)} · Y ${formatCoord(y)} · Z ${formatCoord(z)}`;
  if (sel) sel.textContent = selection ? `Sel ${selection}` : 'Selection --';
}

export function updateInfoOverlay(element = null, options = {}) {
  const overlay = document.getElementById('info-overlay');
  if (!overlay) return;
  if (!element) {
    overlay.classList.remove('is-visible');
    overlay.innerHTML = '';
    return;
  }
  const memberId = escapeHtml(element.member_id || element.id || '--');
  const type = escapeHtml(element.type || element.element_type || 'Member');
  const story = escapeHtml(element.story || element.story_id || '--');
  const section = escapeHtml(element.section || element.section_name || '--');
  const dcr = options.dcr != null ? Number(options.dcr).toFixed(2) : '--';
  const tone = options.tone || 'neutral';
  overlay.className = `info-overlay info-overlay--${tone} is-visible`;
  overlay.innerHTML = `
    <div class="info-overlay__header">
      <span class="info-overlay__eyebrow">Selected member</span>
      <strong class="info-overlay__title">${memberId}</strong>
    </div>
    <div class="info-overlay__grid">
      <span><b>Type</b><em>${type}</em></span>
      <span><b>Story</b><em>${story}</em></span>
      <span><b>Section</b><em>${section}</em></span>
      <span><b>D/C</b><em>${dcr}</em></span>
    </div>
  `;
}

export function enhanceStageResultCalloutElement(calloutEl) {
  if (!calloutEl) return;
  calloutEl.classList.add('stage-result-callout--enhanced');
  const leader = calloutEl.querySelector('[data-stage-result-callout-leader]');
  if (leader && !leader.querySelector('.stage-result-callout__anchor-dot')) {
    const dot = document.createElement('span');
    dot.className = 'stage-result-callout__anchor-dot';
    dot.setAttribute('aria-hidden', 'true');
    leader.appendChild(dot);
  }
}
