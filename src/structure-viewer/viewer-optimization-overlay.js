/**
 * AI Optimization Visual Comparison Overlay.
 *
 * Renders before/after geometry side-by-side or ghosted in the 3D viewport,
 * with color-coded change indicators:
 * - Green: improved (reduced D/C, saved material)
 * - Yellow: modified (section change, relocated)
 * - Red: worsened (increased D/C, added material)
 * - Blue: new member
 * - Gray: removed member
 */

const CHANGE_COLORS = {
  improved: 0x34d399,   // green
  modified: 0xfbbf24,     // yellow
  worsened: 0xf87171,   // red
  new: 0x60a5fa,          // blue
  removed: 0x64748b,      // gray
  unchanged: 0x94a3b8,    // muted
};

function classifyChange(before, after) {
  if (!before && after) return 'new';
  if (before && !after) return 'removed';
  if (!before && !after) return 'unchanged';

  const beforeDcr = before.dcr || before.max_dcr_before || 0;
  const afterDcr = after.dcr || after.max_dcr_after || 0;
  const beforeSection = String(before.section || '').trim();
  const afterSection = String(after.section || after.after_section || '').trim();

  if (beforeSection && afterSection && beforeSection !== afterSection) {
    if (afterDcr < beforeDcr * 0.95) return 'improved';
    if (afterDcr > beforeDcr * 1.05) return 'worsened';
    return 'modified';
  }

  const dcrChange = afterDcr - beforeDcr;
  if (Math.abs(dcrChange) < 0.02) return 'unchanged';
  if (dcrChange < -0.05) return 'improved';
  if (dcrChange > 0.05) return 'worsened';
  return 'modified';
}

export function buildOptimizationComparisonModel(baselineElements, optimizedElements) {
  const baselineMap = new Map();
  const optimizedMap = new Map();

  (baselineElements || []).forEach(el => {
    const key = el.member_id || el.id;
    if (key) baselineMap.set(String(key), el);
  });
  (optimizedElements || []).forEach(el => {
    const key = el.member_id || el.id;
    if (key) optimizedMap.set(String(key), el);
  });

  const allKeys = new Set([...baselineMap.keys(), ...optimizedMap.keys()]);
  const comparisonRows = [];

  allKeys.forEach(key => {
    const before = baselineMap.get(key);
    const after = optimizedMap.get(key);
    const change = classifyChange(before, after);
    comparisonRows.push({
      memberId: key,
      before,
      after,
      change,
      colorHex: CHANGE_COLORS[change],
    });
  });

  return {
    totalCount: allKeys.size,
    improvedCount: comparisonRows.filter(r => r.change === 'improved').length,
    modifiedCount: comparisonRows.filter(r => r.change === 'modified').length,
    worsenedCount: comparisonRows.filter(r => r.change === 'worsened').length,
    newCount: comparisonRows.filter(r => r.change === 'new').length,
    removedCount: comparisonRows.filter(r => r.change === 'removed').length,
    unchangedCount: comparisonRows.filter(r => r.change === 'unchanged').length,
    rows: comparisonRows,
  };
}

/**
 * Create a 3D overlay mesh for an optimization change indicator.
 * Returns a small colored sphere at the member midpoint.
 */
export function createChangeIndicatorMesh(THREE, nodeA, nodeB, changeType, {
  radius = 0.25,
  opacity = 0.85,
} = {}) {
  if (!THREE || !nodeA || !nodeB) return null;
  const geometry = new THREE.SphereGeometry(radius, 12, 8);
  const colorHex = CHANGE_COLORS[changeType] || CHANGE_COLORS.unchanged;
  const material = new THREE.MeshStandardMaterial({
    color: colorHex,
    transparent: true,
    opacity,
    roughness: 0.3,
    metalness: 0.5,
    emissive: colorHex,
    emissiveIntensity: 0.3,
  });
  const mesh = new THREE.Mesh(geometry, material);
  const midX = ((nodeA.x || 0) + (nodeB.x || 0)) / 2;
  const midY = ((nodeA.z || 0) + (nodeB.z || 0)) / 2; // viewer swap
  const midZ = ((nodeA.y || 0) + (nodeB.y || 0)) / 2;
  mesh.position.set(midX, midY, midZ);
  mesh.userData = {
    _changeIndicator: true,
    changeType,
    radius,
  };
  return mesh;
}

/**
 * Build a comparison legend DOM element.
 */
export function buildOptimizationLegend() {
  const container = document.createElement('div');
  container.className = 'optimization-legend';
  container.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;font-size:11px;padding:8px;background:rgba(15,23,42,0.8);border-radius:8px;border:1px solid rgba(51,65,85,0.5);';

  Object.entries(CHANGE_COLORS).forEach(([label, hex]) => {
    const item = document.createElement('div');
    item.style.cssText = 'display:flex;align-items:center;gap:4px;';
    const dot = document.createElement('span');
    dot.style.cssText = `width:8px;height:8px;border-radius:50%;background:#${hex.toString(16).padStart(6, '0')};display:inline-block;`;
    const text = document.createElement('span');
    text.style.cssText = 'color:#e2e8f0;';
    text.textContent = label;
    item.appendChild(dot);
    item.appendChild(text);
    container.appendChild(item);
  });

  return container;
}

/**
 * Render optimization comparison summary panel.
 */
export function renderOptimizationSummaryPanel(container, comparisonData) {
  if (!container || !comparisonData) return;
  container.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'section-title';
  header.textContent = 'Optimization Changes';
  container.appendChild(header);

  const summaryGrid = document.createElement('div');
  summaryGrid.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:10px;';

  const stats = [
    { label: 'Improved', value: comparisonData.improvedCount, color: '#34d399' },
    { label: 'Modified', value: comparisonData.modifiedCount, color: '#fbbf24' },
    { label: 'Worsened', value: comparisonData.worsenedCount, color: '#f87171' },
    { label: 'New', value: comparisonData.newCount, color: '#60a5fa' },
    { label: 'Removed', value: comparisonData.removedCount, color: '#64748b' },
    { label: 'Unchanged', value: comparisonData.unchangedCount, color: '#94a3b8' },
  ];

  stats.forEach(s => {
    const cell = document.createElement('div');
    cell.style.cssText = `background:rgba(15,23,42,0.6);border-radius:6px;padding:6px;text-align:center;border-left:3px solid ${s.color};`;
    cell.innerHTML = `<div style="font-size:16px;font-weight:700;color:${s.color}">${s.value}</div><div style="font-size:10px;color:#94a3b8;margin-top:2px">${s.label}</div>`;
    summaryGrid.appendChild(cell);
  });
  container.appendChild(summaryGrid);

  // Legend
  container.appendChild(buildOptimizationLegend());

  // Top changed members
  const changed = comparisonData.rows.filter(r => r.change !== 'unchanged').slice(0, 10);
  if (changed.length) {
    const listTitle = document.createElement('div');
    listTitle.className = 'section-title';
    listTitle.style.cssText = 'margin-top:10px;';
    listTitle.textContent = 'Top Changes';
    container.appendChild(listTitle);

    const list = document.createElement('div');
    list.style.cssText = 'display:flex;flex-direction:column;gap:3px;font-size:11px;';
    changed.forEach(row => {
      const item = document.createElement('div');
      item.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:3px 6px;border-radius:4px;background:rgba(15,23,42,0.4);';
      const beforeDcr = row.before ? (row.before.dcr || row.before.max_dcr_before || 0).toFixed(2) : '--';
      const afterDcr = row.after ? (row.after.dcr || row.after.max_dcr_after || 0).toFixed(2) : '--';
      const color = '#' + (CHANGE_COLORS[row.change] || CHANGE_COLORS.unchanged).toString(16).padStart(6, '0');
      item.innerHTML = `<span style="color:#e2e8f0">${row.memberId}</span><span style="color:${color};font-weight:700">${row.change}</span><span style="color:#64748b">${beforeDcr} → ${afterDcr}</span>`;
      list.appendChild(item);
    });
    container.appendChild(list);
  }
}
