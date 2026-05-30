/**
 * Material evidence panel renderer for Structure Viewer.
 *
 * Renders stress-strain curves, capacity envelopes, and material property cards
 * from the material-evidence payload produced by the Python bridge.
 */

const CANVAS_WIDTH = 280;
const CANVAS_HEIGHT = 140;
const PADDING = { top: 8, right: 8, bottom: 24, left: 36 };

function hexToRgba(hex, alpha = 1) {
  const r = (hex >> 16) & 255;
  const g = (hex >> 8) & 255;
  const b = hex & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

function computeCurveBounds(curve) {
  if (!Array.isArray(curve) || !curve.length) return { minX: -1, maxX: 1, minY: -1, maxY: 1 };
  const xs = curve.map(p => p.x);
  const ys = curve.map(p => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const padX = Math.max((maxX - minX) * 0.05, 0.001);
  const padY = Math.max((maxY - minY) * 0.05, 1);
  return { minX: minX - padX, maxX: maxX + padX, minY: minY - padY, maxY: maxY + padY };
}

function drawGrid(ctx, bounds, width, height) {
  const plotW = width - PADDING.left - PADDING.right;
  const plotH = height - PADDING.top - PADDING.bottom;
  ctx.strokeStyle = 'rgba(148,163,184,0.15)';
  ctx.lineWidth = 1;

  // Vertical grid lines (6)
  for (let i = 0; i <= 5; i++) {
    const x = PADDING.left + (plotW * i) / 5;
    ctx.beginPath();
    ctx.moveTo(x, PADDING.top);
    ctx.lineTo(x, height - PADDING.bottom);
    ctx.stroke();
  }
  // Horizontal grid lines (4)
  for (let i = 0; i <= 4; i++) {
    const y = PADDING.top + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(PADDING.left, y);
    ctx.lineTo(width - PADDING.right, y);
    ctx.stroke();
  }

  // Zero lines
  const zeroX = PADDING.left + ((0 - bounds.minX) / (bounds.maxX - bounds.minX)) * plotW;
  const zeroY = height - PADDING.bottom - ((0 - bounds.minY) / (bounds.maxY - bounds.minY)) * plotH;

  if (zeroX >= PADDING.left && zeroX <= width - PADDING.right) {
    ctx.strokeStyle = 'rgba(148,163,184,0.4)';
    ctx.beginPath();
    ctx.moveTo(zeroX, PADDING.top);
    ctx.lineTo(zeroX, height - PADDING.bottom);
    ctx.stroke();
  }
  if (zeroY >= PADDING.top && zeroY <= height - PADDING.bottom) {
    ctx.strokeStyle = 'rgba(148,163,184,0.4)';
    ctx.beginPath();
    ctx.moveTo(PADDING.left, zeroY);
    ctx.lineTo(width - PADDING.right, zeroY);
    ctx.stroke();
  }
}

function drawCurve(ctx, curve, bounds, colorHex, width, height, { fill = false } = {}) {
  const plotW = width - PADDING.left - PADDING.right;
  const plotH = height - PADDING.top - PADDING.bottom;

  const toCanvasX = (val) => PADDING.left + ((val - bounds.minX) / (bounds.maxX - bounds.minX)) * plotW;
  const toCanvasY = (val) => height - PADDING.bottom - ((val - bounds.minY) / (bounds.maxY - bounds.minY)) * plotH;

  ctx.lineWidth = 2;
  ctx.strokeStyle = hexToRgba(colorHex, 1);
  ctx.beginPath();
  curve.forEach((point, index) => {
    const x = toCanvasX(point.x);
    const y = toCanvasY(point.y);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  if (fill) {
    ctx.fillStyle = hexToRgba(colorHex, 0.12);
    ctx.beginPath();
    curve.forEach((point, index) => {
      const x = toCanvasX(point.x);
      const y = toCanvasY(point.y);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(toCanvasX(curve[curve.length - 1].x), toCanvasY(bounds.minY));
    ctx.lineTo(toCanvasX(curve[0].x), toCanvasY(bounds.minY));
    ctx.closePath();
    ctx.fill();
  }

  // Draw yield/peak markers
  const markers = curve.filter(p => p.tag && (p.tag.includes('yield') || p.tag.includes('peak') || p.tag.includes('crack')));
  markers.slice(0, 3).forEach(p => {
    const x = toCanvasX(p.x);
    const y = toCanvasY(p.y);
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
  });
}

function drawAxes(ctx, bounds, width, height, { xLabel = 'Strain', yLabel = 'Stress (MPa)' } = {}) {
  const plotW = width - PADDING.left - PADDING.right;
  const plotH = height - PADDING.top - PADDING.bottom;

  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px IBM Plex Sans KR, Pretendard, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  // X-axis labels
  for (let i = 0; i <= 4; i++) {
    const val = bounds.minX + ((bounds.maxX - bounds.minX) * i) / 4;
    const x = PADDING.left + (plotW * i) / 4;
    ctx.fillText(val.toExponential(1), x, height - PADDING.bottom + 4);
  }

  // Y-axis labels
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const val = bounds.minY + ((bounds.maxY - bounds.minY) * i) / 4;
    const y = height - PADDING.bottom - (plotH * i) / 4;
    ctx.fillText(Math.round(val).toString(), PADDING.left - 6, y);
  }

  // Axis titles
  ctx.fillStyle = '#64748b';
  ctx.font = '10px IBM Plex Sans KR, Pretendard, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(xLabel, width / 2 + PADDING.left / 2, height - 6);

  ctx.save();
  ctx.translate(10, height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center';
  ctx.fillText(yLabel, 0, 0);
  ctx.restore();
}

export function renderStressStrainCurve(container, curve, options = {}) {
  if (!container || !Array.isArray(curve) || !curve.length) return null;

  const canvas = document.createElement('canvas');
  canvas.width = options.width || CANVAS_WIDTH;
  canvas.height = options.height || CANVAS_HEIGHT;
  canvas.style.cssText = 'width:100%;height:auto;border-radius:6px;background:rgba(15,23,42,0.6);';
  container.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  const bounds = computeCurveBounds(curve);

  // Clear
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Grid
  drawGrid(ctx, bounds, canvas.width, canvas.height);

  // Curve
  drawCurve(ctx, curve, bounds, options.color || 0x38bdf8, canvas.width, canvas.height, { fill: options.fill !== false });

  // Axes
  drawAxes(ctx, bounds, canvas.width, canvas.height, {
    xLabel: options.xLabel || 'Strain',
    yLabel: options.yLabel || 'Stress (MPa)',
  });

  return canvas;
}

export function renderMaterialPropertyCard(container, material) {
  if (!container || !material) return;
  const family = String(material.family || 'unknown');
  const props = material.properties || {};

  const card = document.createElement('div');
  card.className = 'material-property-card';
  card.dataset.materialFamily = family;
  card.style.cssText = 'background:rgba(15,23,42,0.6);border:1px solid rgba(51,65,85,0.5);border-radius:8px;padding:10px;margin-bottom:8px;';

  const title = document.createElement('div');
  title.style.cssText = 'font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em;';
  title.textContent = family;
  card.appendChild(title);

  const grid = document.createElement('div');
  grid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:4px 8px;font-size:11px;';

  const entries = Object.entries(props).slice(0, 10);
  entries.forEach(([key, value]) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;justify-content:space-between;';
    const label = document.createElement('span');
    label.style.cssText = 'color:#64748b;';
    label.textContent = key.replace(/_/g, ' ');
    const val = document.createElement('span');
    val.style.cssText = 'color:#e2e8f0;font-weight:500;';
    val.textContent = typeof value === 'number' ? value.toFixed(2) : String(value ?? '--');
    row.appendChild(label);
    row.appendChild(val);
    grid.appendChild(row);
  });

  card.appendChild(grid);
  container.appendChild(card);

  // Render curve if available
  if (Array.isArray(material.curve) && material.curve.length) {
    const curveContainer = document.createElement('div');
    curveContainer.style.cssText = 'margin-top:6px;';
    card.appendChild(curveContainer);
    renderStressStrainCurve(curveContainer, material.curve, {
      color: family === 'concrete' ? 0xf87171 : family === 'steel' ? 0x38bdf8 : family === 'frp' ? 0x34d399 : 0xa78bfa,
      xLabel: family === 'lrb' ? 'Displacement (mm)' : family === 'viscous_damper' ? 'Velocity (m/s)' : 'Strain',
      yLabel: family === 'lrb' ? 'Force (kN)' : family === 'viscous_damper' ? 'Force (kN)' : 'Stress (MPa)',
    });
  }

  // Parallel/perpendicular curves for timber
  if (family === 'timber' && Array.isArray(material.curve_parallel) && Array.isArray(material.curve_perpendicular)) {
    const curveContainer = document.createElement('div');
    curveContainer.style.cssText = 'margin-top:6px;';
    card.appendChild(curveContainer);
    const bounds = computeCurveBounds([...material.curve_parallel, ...material.curve_perpendicular]);

    const canvas = document.createElement('canvas');
    canvas.width = CANVAS_WIDTH;
    canvas.height = CANVAS_HEIGHT;
    curveContainer.appendChild(canvas);
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawGrid(ctx, bounds, canvas.width, canvas.height);
    drawCurve(ctx, material.curve_parallel, bounds, 0x38bdf8, canvas.width, canvas.height);
    drawCurve(ctx, material.curve_perpendicular, bounds, 0xf87171, canvas.width, canvas.height);
    drawAxes(ctx, bounds, canvas.width, canvas.height);

    // Legend
    const legend = document.createElement('div');
    legend.style.cssText = 'display:flex;gap:12px;font-size:10px;margin-top:4px;';
    legend.innerHTML = `<span style="color:#38bdf8">● Parallel</span><span style="color:#f87171">● Perpendicular</span>`;
    curveContainer.appendChild(legend);
  }
}

export function renderMaterialEvidencePanel(container, payload) {
  if (!container || !payload) return;
  container.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'section-title';
  header.textContent = 'Material Models';
  container.appendChild(header);

  const materials = payload.materials || {};
  const capacityChecks = payload.capacity_checks || {};
  const durability = payload.durability || {};

  // Material count badge
  const countBadge = document.createElement('div');
  countBadge.style.cssText = 'font-size:11px;color:#94a3b8;margin-bottom:8px;';
  countBadge.textContent = `${Object.keys(materials).length} material families loaded`;
  container.appendChild(countBadge);

  // Render each material
  Object.values(materials).forEach(material => {
    renderMaterialPropertyCard(container, material);
  });

  // Capacity checks summary
  if (Object.keys(capacityChecks).length) {
    const capHeader = document.createElement('div');
    capHeader.className = 'section-title';
    capHeader.style.cssText = 'margin-top:12px;';
    capHeader.textContent = 'Capacity Checks';
    container.appendChild(capHeader);

    const capGrid = document.createElement('div');
    capGrid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:4px 8px;font-size:11px;background:rgba(15,23,42,0.6);border-radius:8px;padding:10px;';
    Object.entries(capacityChecks).forEach(([key, value]) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;justify-content:space-between;';
      const label = document.createElement('span');
      label.style.cssText = 'color:#64748b;';
      label.textContent = key.replace(/_/g, ' ');
      const val = document.createElement('span');
      val.style.cssText = 'color:#e2e8f0;font-weight:500;';
      val.textContent = typeof value === 'number' ? value.toFixed(2) : String(value);
      row.appendChild(label);
      row.appendChild(val);
      capGrid.appendChild(row);
    });
    container.appendChild(capGrid);
  }

  // Durability summary
  if (Object.keys(durability).length) {
    const durHeader = document.createElement('div');
    durHeader.className = 'section-title';
    durHeader.style.cssText = 'margin-top:12px;';
    durHeader.textContent = 'Durability';
    container.appendChild(durHeader);

    Object.entries(durability).forEach(([category, values]) => {
      const card = document.createElement('div');
      card.style.cssText = 'background:rgba(15,23,42,0.6);border:1px solid rgba(51,65,85,0.5);border-radius:8px;padding:10px;margin-bottom:6px;font-size:11px;';
      const title = document.createElement('div');
      title.style.cssText = 'font-weight:700;color:#e2e8f0;margin-bottom:4px;text-transform:capitalize;';
      title.textContent = category;
      card.appendChild(title);

      const grid = document.createElement('div');
      grid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:4px 8px;';
      Object.entries(values).forEach(([k, v]) => {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;justify-content:space-between;';
        const label = document.createElement('span');
        label.style.cssText = 'color:#64748b;';
        label.textContent = k.replace(/_/g, ' ');
        const val = document.createElement('span');
        val.style.cssText = 'color:#e2e8f0;font-weight:500;';
        val.textContent = typeof v === 'boolean' ? (v ? 'Yes' : 'No') : (typeof v === 'number' ? v.toFixed(2) : String(v));
        row.appendChild(label);
        row.appendChild(val);
        grid.appendChild(row);
      });
      card.appendChild(grid);
      container.appendChild(card);
    });
  }
}

export function loadMaterialEvidenceFromUrl(url) {
  return fetch(url)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    });
}

export function attachMaterialEvidenceToViewer(viewerContainer, evidencePayload) {
  const panel = viewerContainer.querySelector('#material-evidence-panel');
  if (!panel) return;
  renderMaterialEvidencePanel(panel, evidencePayload);
}
