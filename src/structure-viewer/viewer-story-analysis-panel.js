/**
 * Story-level analysis panel and utilization heatmap renderer.
 *
 * Provides commercial-tool-grade visualizations:
 * - Story shear force / moment diagrams (stacked bar or line)
 * - D/C ratio heatmap (plan-level color grid)
 * - Utilization distribution histogram
 * - Critical member rankings by story
 */

const CHART_CONFIG = {
  width: 360,
  height: 160,
  padding: { top: 8, right: 8, bottom: 28, left: 40 },
  barWidth: 18,
  font: "11px 'IBM Plex Sans KR', Pretendard, sans-serif",
  colors: {
    safe: '#2f7d5a',
    caution: '#96580e',
    danger: '#a1492e',
    beam: '#38bdf8',
    column: '#f87171',
    wall: '#34d399',
    slab: '#fbbf24',
    grid: 'rgba(148,163,184,0.1)',
    text: '#94a3b8',
    textStrong: '#e2e8f0',
    axis: 'rgba(148,163,184,0.25)',
  },
};

function getDcColor(ratio) {
  if (ratio <= 0.6) return CHART_CONFIG.colors.safe;
  if (ratio <= 0.85) return CHART_CONFIG.colors.caution;
  return CHART_CONFIG.colors.danger;
}

function drawBarChart(canvas, data, { xLabel = '', yLabel = '', stacked = false } = {}) {
  const width = canvas.width = CHART_CONFIG.width;
  const height = canvas.height = CHART_CONFIG.height;
  const pad = CHART_CONFIG.padding;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const ctx = canvas.getContext('2d');

  // Background
  ctx.fillStyle = 'rgba(15,23,42,0.6)';
  ctx.beginPath();
  ctx.roundRect(0, 0, width, height, 8);
  ctx.fill();

  const labels = data.map(d => d.label);
  const values = data.map(d => d.value);
  const maxValue = Math.max(...values.map(v => (Array.isArray(v) ? Math.max(...v) : v)), 0.001);

  const barCount = labels.length;
  const groupWidth = plotW / barCount;
  const barW = Math.min(CHART_CONFIG.barWidth, groupWidth * 0.6);

  // Grid
  ctx.strokeStyle = CHART_CONFIG.colors.grid;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
  }

  // Bars
  data.forEach((item, index) => {
    const x = pad.left + index * groupWidth + (groupWidth - barW) / 2;
    const val = Array.isArray(item.value) ? item.value[0] : item.value;
    const barH = (val / maxValue) * plotH;
    const y = pad.top + plotH - barH;

    ctx.fillStyle = item.color || CHART_CONFIG.colors.beam;
    ctx.beginPath();
    ctx.roundRect(x, y, barW, barH, [3, 3, 0, 0]);
    ctx.fill();

    // Label
    ctx.fillStyle = CHART_CONFIG.colors.text;
    ctx.font = CHART_CONFIG.font;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(String(item.label), x + barW / 2, height - 24);
  });

  // Y-axis labels
  ctx.fillStyle = CHART_CONFIG.colors.text;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const val = (maxValue * (4 - i)) / 4;
    const y = pad.top + (plotH * i) / 4;
    ctx.fillText(Math.round(val).toString(), pad.left - 6, y);
  }

  // Axis labels
  if (yLabel) {
    ctx.save();
    ctx.translate(10, height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.fillStyle = CHART_CONFIG.colors.text;
    ctx.fillText(yLabel, 0, 0);
    ctx.restore();
  }

  return canvas;
}

function drawLineChart(canvas, series, { xLabel = '', yLabel = '' } = {}) {
  const width = canvas.width = CHART_CONFIG.width;
  const height = canvas.height = CHART_CONFIG.height;
  const pad = CHART_CONFIG.padding;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = 'rgba(15,23,42,0.6)';
  ctx.beginPath();
  ctx.roundRect(0, 0, width, height, 8);
  ctx.fill();

  const allValues = series.flatMap(s => s.data);
  const maxValue = Math.max(...allValues, 0.001);
  const minValue = Math.min(...allValues, 0);
  const range = maxValue - minValue || 1;

  // Grid
  ctx.strokeStyle = CHART_CONFIG.colors.grid;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
  }

  // Zero line
  const zeroY = pad.top + ((0 - minValue) / range) * plotH;
  ctx.strokeStyle = CHART_CONFIG.colors.axis;
  ctx.beginPath();
  ctx.moveTo(pad.left, zeroY);
  ctx.lineTo(width - pad.right, zeroY);
  ctx.stroke();

  // Series
  series.forEach((s, sIndex) => {
    const stepX = plotW / (s.data.length - 1);
    ctx.strokeStyle = s.color || CHART_CONFIG.colors.beam;
    ctx.lineWidth = 2;
    ctx.beginPath();
    s.data.forEach((val, i) => {
      const x = pad.left + i * stepX;
      const y = pad.top + plotH - ((val - minValue) / range) * plotH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Dots at peaks
    s.data.forEach((val, i) => {
      const x = pad.left + i * stepX;
      const y = pad.top + plotH - ((val - minValue) / range) * plotH;
      if (val === maxValue || val === minValue) {
        ctx.fillStyle = s.color || CHART_CONFIG.colors.beam;
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    });
  });

  // Legend
  const legendY = 4;
  let legendX = pad.left;
  series.forEach(s => {
    ctx.fillStyle = s.color || CHART_CONFIG.colors.beam;
    ctx.fillRect(legendX, legendY, 10, 3);
    ctx.fillStyle = CHART_CONFIG.colors.text;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(s.label, legendX + 14, legendY - 2);
    legendX += ctx.measureText(s.label).width + 28;
  });

  return canvas;
}

/**
 * Render D/C ratio heatmap as a color grid by story and member type.
 */
export function renderUtilizationHeatmap(container, elements, { storyKey = 'story_band_label' } = {}) {
  if (!container || !Array.isArray(elements)) return;
  container.innerHTML = '';

  // Group by story then type
  const byStory = {};
  elements.forEach(el => {
    const story = el[storyKey] || el.story || 'Unknown';
    const type = (el.type || 'other').toLowerCase();
    if (!byStory[story]) byStory[story] = {};
    if (!byStory[story][type]) byStory[story][type] = [];
    byStory[story][type].push(el);
  });

  const stories = Object.keys(byStory).sort();
  const types = ['column', 'beam', 'wall', 'slab', 'brace', 'other'];

  const wrapper = document.createElement('div');
  wrapper.style.cssText = 'overflow-x:auto;';

  const table = document.createElement('table');
  table.style.cssText = 'border-collapse:collapse;font-size:10px;width:100%;';

  // Header
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  headerRow.innerHTML = `<th style="padding:4px 6px;text-align:left;color:#64748b;border-bottom:1px solid rgba(51,65,85,0.5)">Story</th>` +
    types.map(t => `<th style="padding:4px 6px;text-align:center;color:#64748b;border-bottom:1px solid rgba(51,65,85,0.5);text-transform:capitalize">${t}</th>`).join('');
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Body
  const tbody = document.createElement('tbody');
  stories.forEach(story => {
    const row = document.createElement('tr');
    const labelCell = document.createElement('td');
    labelCell.style.cssText = 'padding:4px 6px;color:#e2e8f0;border-bottom:1px solid rgba(51,65,85,0.3)';
    labelCell.textContent = story;
    row.appendChild(labelCell);

    types.forEach(type => {
      const members = byStory[story][type] || [];
      const dcrs = members.map(m => m.dcr || m.max_dcr_after || m.max_dcr_before || 0).filter(v => v > 0);
      const avgDcr = dcrs.length ? dcrs.reduce((a, b) => a + b, 0) / dcrs.length : 0;
      const maxDcr = dcrs.length ? Math.max(...dcrs) : 0;
      const cell = document.createElement('td');
      cell.style.cssText = `padding:4px 6px;text-align:center;border-bottom:1px solid rgba(51,65,85,0.3);`;

      if (dcrs.length) {
        const color = getDcColor(maxDcr);
        cell.innerHTML = `<div style="background:${color};border-radius:4px;padding:2px 4px;color:#fff;font-weight:700">${maxDcr.toFixed(2)}</div><div style="color:#64748b;font-size:9px;margin-top:2px">n=${dcrs.length}</div>`;
      } else {
        cell.innerHTML = `<span style="color:#475569">—</span>`;
      }
      row.appendChild(cell);
    });
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  wrapper.appendChild(table);
  container.appendChild(wrapper);
}

/**
 * Render story-level force summary (shear, moment) as bar charts.
 */
export function renderStoryForceSummary(container, elements, { forceField = 'shear' } = {}) {
  if (!container || !Array.isArray(elements)) return;
  container.innerHTML = '';

  const byStory = {};
  elements.forEach(el => {
    const story = el.story_band_label || el.story || 'Unknown';
    const val = el[forceField] || 0;
    if (!byStory[story]) byStory[story] = 0;
    byStory[story] += Math.abs(val);
  });

  const stories = Object.keys(byStory).sort();
  const data = stories.map(story => ({
    label: story,
    value: byStory[story],
    color: forceField === 'shear' ? '#38bdf8' : forceField === 'moment' ? '#a78bfa' : '#34d399',
  }));

  const title = document.createElement('div');
  title.className = 'section-title';
  title.style.cssText = 'margin-bottom:6px;';
  title.textContent = `Story ${forceField === 'shear' ? 'Shear' : forceField === 'moment' ? 'Moment' : 'Force'} Summary`;
  container.appendChild(title);

  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'width:100%;height:auto;margin-bottom:8px;';
  container.appendChild(canvas);

  drawBarChart(canvas, data, {
    yLabel: forceField === 'shear' ? 'Shear (kN)' : forceField === 'moment' ? 'Moment (kN·m)' : 'Force',
  });
}

/**
 * Render utilization distribution histogram.
 */
export function renderUtilizationHistogram(container, elements) {
  if (!container || !Array.isArray(elements)) return;
  container.innerHTML = '';

  const bins = [0, 0.3, 0.6, 0.8, 0.9, 1.0, 1.2, 2.0];
  const counts = new Array(bins.length - 1).fill(0);
  const dcrs = elements.map(e => e.dcr || e.max_dcr_after || e.max_dcr_before || 0).filter(v => v >= 0);

  dcrs.forEach(dcr => {
    for (let i = 0; i < bins.length - 1; i++) {
      if (dcr >= bins[i] && dcr < bins[i + 1]) {
        counts[i]++;
        break;
      }
    }
    if (dcr >= bins[bins.length - 1]) counts[counts.length - 1]++;
  });

  const labels = bins.slice(0, -1).map((b, i) => `${b.toFixed(1)}-${bins[i + 1].toFixed(1)}`);
  const maxCount = Math.max(...counts, 1);

  const title = document.createElement('div');
  title.className = 'section-title';
  title.style.cssText = 'margin-bottom:6px;';
  title.textContent = 'D/C Distribution';
  container.appendChild(title);

  const canvas = document.createElement('canvas');
  canvas.width = CHART_CONFIG.width;
  canvas.height = CHART_CONFIG.height;
  canvas.style.cssText = 'width:100%;height:auto;';
  container.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(15,23,42,0.6)';
  ctx.beginPath();
  ctx.roundRect(0, 0, canvas.width, canvas.height, 8);
  ctx.fill();

  const pad = CHART_CONFIG.padding;
  const plotW = canvas.width - pad.left - pad.right;
  const plotH = canvas.height - pad.top - pad.bottom;
  const barCount = counts.length;
  const groupW = plotW / barCount;
  const barW = groupW * 0.7;

  counts.forEach((count, i) => {
    const x = pad.left + i * groupW + (groupW - barW) / 2;
    const barH = (count / maxCount) * plotH;
    const y = pad.top + plotH - barH;

    const ratio = (bins[i] + bins[i + 1]) / 2;
    ctx.fillStyle = getDcColor(ratio);
    ctx.beginPath();
    ctx.roundRect(x, y, barW, barH, [3, 3, 0, 0]);
    ctx.fill();

    // Label
    ctx.fillStyle = CHART_CONFIG.colors.text;
    ctx.font = CHART_CONFIG.font;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(labels[i], x + barW / 2, canvas.height - 24);

    // Count on top
    if (count > 0) {
      ctx.fillStyle = CHART_CONFIG.colors.textStrong;
      ctx.textBaseline = 'bottom';
      ctx.fillText(String(count), x + barW / 2, y - 2);
    }
  });

  // Y-axis
  ctx.fillStyle = CHART_CONFIG.colors.text;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const val = Math.round((maxCount * (4 - i)) / 4);
    const y = pad.top + (plotH * i) / 4;
    ctx.fillText(String(val), pad.left - 6, y);
  }
}

/**
 * Render critical member ranking by story with micro-bars.
 */
export function renderCriticalMemberRanking(container, elements, { maxRows = 8 } = {}) {
  if (!container || !Array.isArray(elements)) return;
  container.innerHTML = '';

  const sorted = [...elements]
    .map(e => ({
      ...e,
      dcr: e.dcr || e.max_dcr_after || e.max_dcr_before || 0,
    }))
    .filter(e => e.dcr > 0)
    .sort((a, b) => b.dcr - a.dcr)
    .slice(0, maxRows);

  const title = document.createElement('div');
  title.className = 'section-title';
  title.style.cssText = 'margin-bottom:6px;';
  title.textContent = 'Critical Members';
  container.appendChild(title);

  const table = document.createElement('div');
  table.style.cssText = 'display:flex;flex-direction:column;gap:4px;';

  sorted.forEach(el => {
    const row = document.createElement('div');
    row.style.cssText = 'display:grid;grid-template-columns:1fr 40px 60px;gap:6px;align-items:center;font-size:11px;padding:4px 6px;border-radius:4px;background:rgba(15,23,42,0.4);';

    const info = document.createElement('div');
    info.style.cssText = 'min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    info.innerHTML = `<span style="color:#e2e8f0;font-weight:500">${el.member_id || el.id}</span> <span style="color:#64748b">${el.type || ''}</span>`;

    const dcr = document.createElement('div');
    dcr.style.cssText = `text-align:right;font-weight:700;color:${getDcColor(el.dcr)}`;
    dcr.textContent = el.dcr.toFixed(2);

    const barContainer = document.createElement('div');
    barContainer.style.cssText = 'height:4px;background:rgba(51,65,85,0.5);border-radius:2px;overflow:hidden;';
    const bar = document.createElement('div');
    bar.style.cssText = `height:100%;width:${Math.min(el.dcr * 100, 100)}%;background:${getDcColor(el.dcr)};border-radius:2px;`;
    barContainer.appendChild(bar);

    row.appendChild(info);
    row.appendChild(dcr);
    row.appendChild(barContainer);
    table.appendChild(row);
  });

  container.appendChild(table);
}

/**
 * Master render function for the story-analysis panel.
 */
export function renderStoryAnalysisPanel(container, modelData, options = {}) {
  if (!container || !modelData) return;
  container.innerHTML = '';

  const elements = Array.isArray(modelData.elements) ? modelData.elements : [];

  // Story force summary
  const forcePanel = document.createElement('div');
  forcePanel.style.cssText = 'margin-bottom:12px;';
  renderStoryForceSummary(forcePanel, elements, { forceField: 'shear' });
  container.appendChild(forcePanel);

  const momentPanel = document.createElement('div');
  momentPanel.style.cssText = 'margin-bottom:12px;';
  renderStoryForceSummary(momentPanel, elements, { forceField: 'moment' });
  container.appendChild(momentPanel);

  // Heatmap
  const heatmapPanel = document.createElement('div');
  heatmapPanel.style.cssText = 'margin-bottom:12px;';
  renderUtilizationHeatmap(heatmapPanel, elements);
  container.appendChild(heatmapPanel);

  // Histogram
  const histPanel = document.createElement('div');
  histPanel.style.cssText = 'margin-bottom:12px;';
  renderUtilizationHistogram(histPanel, elements);
  container.appendChild(histPanel);

  // Critical members
  const critPanel = document.createElement('div');
  renderCriticalMemberRanking(critPanel, elements, { maxRows: options.maxRows || 8 });
  container.appendChild(critPanel);
}
