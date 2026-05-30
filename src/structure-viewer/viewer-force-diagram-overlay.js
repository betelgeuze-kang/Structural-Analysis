/**
 * Force diagram overlay renderer for selected structural members.
 *
 * Renders N (axial), M (moment), V (shear) diagrams as SVG/Canvas overlays
 * attached to the selected member in the 3D viewport.
 */

const DIAGRAM_CONFIG = {
  width: 200,
  height: 80,
  padding: { top: 4, right: 4, bottom: 16, left: 32 },
  barWidth: 6,
  positiveColor: 0x38bdf8,   // teal
  negativeColor: 0xf87171,   // red
  zeroColor: 0x94a3b8,       // muted
};

function computeDiagramBounds(values) {
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const pad = Math.max((max - min) * 0.05, 0.001);
  return { min: min - pad, max: max + pad };
}

function drawForceDiagram(canvas, values, label, unit, options = {}) {
  const width = options.width || DIAGRAM_CONFIG.width;
  const height = options.height || DIAGRAM_CONFIG.height;
  const pad = DIAGRAM_CONFIG.padding;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');

  // Background
  ctx.fillStyle = 'rgba(15,23,42,0.75)';
  ctx.beginPath();
  ctx.roundRect(0, 0, width, height, 6);
  ctx.fill();

  const bounds = computeDiagramBounds(values);
  const zeroY = pad.top + ((0 - bounds.min) / (bounds.max - bounds.min)) * plotH;

  // Zero line
  ctx.strokeStyle = 'rgba(148,163,184,0.3)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, zeroY);
  ctx.lineTo(width - pad.right, zeroY);
  ctx.stroke();

  // Bars / area
  const barW = Math.max(plotW / values.length * 0.7, 2);
  const stepX = plotW / Math.max(values.length - 1, 1);

  values.forEach((val, index) => {
    const x = pad.left + index * stepX;
    const valRatio = (val - bounds.min) / (bounds.max - bounds.min);
    const y = pad.top + (1 - valRatio) * plotH;

    const isPositive = val >= 0;
    const colorHex = val === 0 ? DIAGRAM_CONFIG.zeroColor : (isPositive ? DIAGRAM_CONFIG.positiveColor : DIAGRAM_CONFIG.negativeColor);
    const r = (colorHex >> 16) & 255;
    const g = (colorHex >> 8) & 255;
    const b = colorHex & 255;

    ctx.fillStyle = `rgba(${r},${g},${b},0.7)`;
    ctx.fillRect(x - barW / 2, Math.min(y, zeroY), barW, Math.abs(zeroY - y));
  });

  // Outline envelope
  ctx.strokeStyle = 'rgba(226,232,240,0.6)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  values.forEach((val, index) => {
    const x = pad.left + index * stepX;
    const valRatio = (val - bounds.min) / (bounds.max - bounds.min);
    const y = pad.top + (1 - valRatio) * plotH;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Labels
  ctx.fillStyle = '#e2e8f0';
  ctx.font = 'bold 10px IBM Plex Sans KR, Pretendard, sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText(`${label} (${unit})`, pad.left, 2);

  // Min / max labels
  ctx.font = '9px IBM Plex Sans KR, Pretendard, sans-serif';
  ctx.fillStyle = '#94a3b8';
  ctx.textAlign = 'right';
  ctx.fillText(`max ${Math.round(bounds.max)}`, width - pad.right, 2);
  ctx.textAlign = 'left';
  ctx.fillText(`min ${Math.round(bounds.min)}`, pad.left, height - 14);

  return canvas;
}

/**
 * Build force diagram data for a line element from node forces.
 * For a 2-node element, we interpolate between end forces.
 */
export function buildMemberForceDiagram(elementData, nodeMap, { subdivisions = 10 } = {}) {
  const nodes = (elementData.node_ids || [])
    .map(id => nodeMap?.get?.(id) || null)
    .filter(Boolean);

  if (nodes.length < 2) return null;

  const n = subdivisions + 1;
  const axial = [];
  const moment = [];
  const shear = [];

  for (let i = 0; i < n; i++) {
    const t = i / subdivisions;
    // Linear interpolation between end values
    const a0 = nodes[0]?.axial || 0;
    const a1 = nodes[nodes.length - 1]?.axial || a0;
    axial.push(a0 + t * (a1 - a0));

    const m0 = nodes[0]?.moment || 0;
    const m1 = nodes[nodes.length - 1]?.moment || m0;
    moment.push(m0 + t * (m1 - m0));

    const s0 = nodes[0]?.shear || 0;
    const s1 = nodes[nodes.length - 1]?.shear || s0;
    shear.push(s0 + t * (s1 - s0));
  }

  return {
    elementId: elementData.id,
    memberId: elementData.member_id,
    type: elementData.type,
    axial,
    moment,
    shear,
    unitAxial: 'kN',
    unitMoment: 'kN·m',
    unitShear: 'kN',
    length: computeMemberLength(nodes),
  };
}

function computeMemberLength(nodes) {
  if (!nodes || nodes.length < 2) return 0;
  const dx = nodes[0].x - nodes[nodes.length - 1].x;
  const dy = nodes[0].y - nodes[nodes.length - 1].y;
  const dz = nodes[0].z - nodes[nodes.length - 1].z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/**
 * Render force diagrams into a floating overlay panel.
 */
export function renderForceDiagramOverlay(container, diagramData, options = {}) {
  if (!container || !diagramData) return;
  container.innerHTML = '';

  const wrapper = document.createElement('div');
  wrapper.className = 'force-diagram-overlay';
  wrapper.style.cssText = 'background:rgba(15,23,42,0.85);border:1px solid rgba(51,65,85,0.6);border-radius:10px;padding:10px;backdrop-filter:blur(8px);';

  const title = document.createElement('div');
  title.style.cssText = 'font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;';
  title.innerHTML = `<span>Force Diagrams · ${diagramData.memberId || diagramData.elementId}</span><span style="font-size:10px;color:#64748b;font-weight:400">${(diagramData.length || 0).toFixed(2)} m</span>`;
  wrapper.appendChild(title);

  const grids = [
    { label: 'Axial', unit: diagramData.unitAxial, values: diagramData.axial },
    { label: 'Moment', unit: diagramData.unitMoment, values: diagramData.moment },
    { label: 'Shear', unit: diagramData.unitShear, values: diagramData.shear },
  ];

  grids.forEach(g => {
    if (!Array.isArray(g.values) || !g.values.length) return;
    const canvas = document.createElement('canvas');
    canvas.style.cssText = 'width:100%;height:auto;margin-bottom:6px;';
    drawForceDiagram(canvas, g.values, g.label, g.unit, options);
    wrapper.appendChild(canvas);
  });

  container.appendChild(wrapper);
}

/**
 * Create a 3D force vector arrow using THREE.js for stress/displacement visualization.
 */
export function createForceVectorArrow(THREE, origin, vector, {
  color = 0xfbbf24,
  headLength = 0.3,
  headWidth = 0.15,
  lineWidth = 0.05,
  opacity = 0.85,
} = {}) {
  if (!THREE || !origin || !vector) return null;
  const length = vector.length();
  if (length < 1e-6) return null;

  // Shaft
  const direction = vector.clone().normalize();
  const shaftLength = Math.max(length - headLength, 0.01);
  const shaftGeo = new THREE.CylinderGeometry(lineWidth, lineWidth, shaftLength, 6, 1, false);
  const mid = origin.clone().add(direction.clone().multiplyScalar(shaftLength / 2));
  const axis = new THREE.Vector3(0, 1, 0);
  const quat = new THREE.Quaternion().setFromUnitVectors(axis, direction);
  shaftGeo.translate(0, shaftLength / 2, 0);
  shaftGeo.applyQuaternion(quat);
  shaftGeo.translate(origin.x, origin.y, origin.z);

  const material = new THREE.MeshStandardMaterial({
    color,
    transparent: true,
    opacity,
    roughness: 0.4,
    metalness: 0.3,
  });
  const shaft = new THREE.Mesh(shaftGeo, material);

  // Arrow head (cone)
  const headGeo = new THREE.ConeGeometry(headWidth, headLength, 8, 1, false);
  const headOrigin = origin.clone().add(direction.clone().multiplyScalar(shaftLength));
  headGeo.translate(0, headLength / 2, 0);
  headGeo.applyQuaternion(quat);
  headGeo.translate(headOrigin.x, headOrigin.y, headOrigin.z);
  const head = new THREE.Mesh(headGeo, material);

  const group = new THREE.Group();
  group.add(shaft);
  group.add(head);
  group.userData = { _forceVector: true, origin, vector, magnitude: length };
  return group;
}

/**
 * Build a vector field for nodal forces / displacements.
 */
export function buildNodalVectorField(THREE, nodes, field = 'displacement', {
  scale = 1.0,
  maxLength = 5.0,
  color = 0xfbbf24,
} = {}) {
  if (!THREE || !Array.isArray(nodes)) return [];
  const vectors = [];
  const isDisplacement = field === 'displacement';

  nodes.forEach(node => {
    const x = node.x || 0;
    const y = node.y || 0;
    const z = node.z || 0;
    const dx = (node.dx || 0) * scale;
    const dy = (node.dy || 0) * scale;
    const dz = (node.dz || 0) * scale;
    const vec = new THREE.Vector3(dx, dz, dy); // viewer swap
    const len = vec.length();
    if (len < 1e-4) return;
    if (len > maxLength) vec.multiplyScalar(maxLength / len);

    const origin = new THREE.Vector3(x, z, y); // viewer swap
    const arrow = createForceVectorArrow(THREE, origin, vec, { color });
    if (arrow) {
      arrow.userData.nodeId = node.id;
      arrow.userData.field = field;
      arrow.userData.magnitude = isDisplacement ? len : Math.abs(node.disp_mag || 0);
      vectors.push(arrow);
    }
  });

  return vectors;
}

/**
 * Render a capacity envelope (interaction diagram) for RC/composite members.
 */
export function renderCapacityEnvelope(canvas, points, options = {}) {
  if (!canvas || !Array.isArray(points) || points.length < 3) return;
  const width = options.width || 200;
  const height = options.height || 200;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');

  const xs = points.map(p => p.p || p.x || 0);
  const ys = points.map(p => p.m || p.y || 0);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const padX = Math.max((maxX - minX) * 0.05, 0.001);
  const padY = Math.max((maxY - minY) * 0.05, 0.001);

  ctx.fillStyle = 'rgba(15,23,42,0.75)';
  ctx.beginPath();
  ctx.roundRect(0, 0, width, height, 8);
  ctx.fill();

  const plotW = width - 32;
  const plotH = height - 32;
  const toX = v => 16 + ((v - (minX - padX)) / ((maxX + padX) - (minX - padX))) * plotW;
  const toY = v => height - 16 - ((v - (minY - padY)) / ((maxY + padY) - (minY - padY))) * plotH;

  // Grid
  ctx.strokeStyle = 'rgba(148,163,184,0.1)';
  for (let i = 0; i <= 4; i++) {
    const x = 16 + (plotW * i) / 4;
    ctx.beginPath(); ctx.moveTo(x, 8); ctx.lineTo(x, height - 24); ctx.stroke();
    const y = 8 + (plotH * i) / 4;
    ctx.beginPath(); ctx.moveTo(16, y); ctx.lineTo(width - 16, y); ctx.stroke();
  }

  // Envelope
  ctx.strokeStyle = '#38bdf8';
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = toX(p.p || p.x || 0);
    const y = toY(p.m || p.y || 0);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.stroke();
  ctx.fillStyle = 'rgba(56,189,248,0.12)';
  ctx.fill();

  // Labels
  ctx.fillStyle = '#94a3b8';
  ctx.font = '9px IBM Plex Sans KR, Pretendard, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(options.xLabel || 'P (kN)', width / 2, height - 4);
  ctx.save();
  ctx.translate(6, height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(options.yLabel || 'M (kN·m)', 0, 0);
  ctx.restore();
}
