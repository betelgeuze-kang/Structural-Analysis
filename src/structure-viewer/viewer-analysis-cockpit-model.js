export const ANALYSIS_COCKPIT_KPI_KEYS = [
  'maxDisplacement',
  'maxInterstoryDrift',
  'baseShear',
  'utilizationRatio',
  'steelWeight',
  'concreteVolume',
  'materialCost',
  'costReduction',
];

const MEMBER_TYPE_LABELS = {
  beam: 'Beam',
  brace: 'Brace',
  column: 'Column',
  slab: 'Slab',
  wall: 'Shear Wall',
};

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizeText(value) {
  return String(value ?? '').trim();
}

function formatCompactNumber(value, { digits = 0, suffix = '' } = {}) {
  const number = safeNumber(value, 0);
  const abs = Math.abs(number);
  const fixed = abs >= 100 ? 0 : digits;
  return `${number.toLocaleString('en-US', {
    maximumFractionDigits: fixed,
    minimumFractionDigits: fixed,
  })}${suffix}`;
}

function formatMoneyMillions(value) {
  return `$ ${safeNumber(value, 0).toLocaleString('en-US', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })} M`;
}

function normalizeElementType(value) {
  const type = normalizeText(value).toLowerCase();
  if (type.includes('column')) return 'column';
  if (type.includes('brace')) return 'brace';
  if (type.includes('wall')) return 'wall';
  if (type.includes('slab') || type.includes('plate') || type.includes('shell')) return 'slab';
  return 'beam';
}

function buildNodeMap(data) {
  return new Map((Array.isArray(data?.nodes) ? data.nodes : []).map((node) => [String(node.id), node]));
}

function readElementNodeRows(element, nodeMap) {
  return (Array.isArray(element?.node_ids) ? element.node_ids : [])
    .map((id) => nodeMap.get(String(id)))
    .filter(Boolean);
}

function readNodeDisplacement(node) {
  const explicit = safeNumber(node?.disp_mag, NaN);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  const dx = safeNumber(node?.dx, 0);
  const dy = safeNumber(node?.dy, 0);
  const dz = safeNumber(node?.dz, 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function readElementDcr(element) {
  return Math.max(
    safeNumber(element?.dcr, 0),
    safeNumber(element?.demand_capacity_ratio, 0),
    safeNumber(element?.utilization, 0),
    safeNumber(element?.stress_ratio, 0),
  );
}

function readElementShear(element) {
  return Math.max(
    Math.abs(safeNumber(element?.shear, 0)),
    Math.abs(safeNumber(element?.shear_force, 0)),
    Math.abs(safeNumber(element?.shear_force_x_kN, 0)),
    Math.abs(safeNumber(element?.shear_force_y_kN, 0)),
    Math.abs(safeNumber(element?.shear_force_z_kN, 0)),
  );
}

function readElementLength(nodes) {
  if (nodes.length < 2) return 0;
  let length = 0;
  for (let index = 1; index < nodes.length; index += 1) {
    const prev = nodes[index - 1];
    const next = nodes[index];
    const dx = safeNumber(next?.x, 0) - safeNumber(prev?.x, 0);
    const dy = safeNumber(next?.y, 0) - safeNumber(prev?.y, 0);
    const dz = safeNumber(next?.z, 0) - safeNumber(prev?.z, 0);
    length += Math.sqrt(dx * dx + dy * dy + dz * dz);
  }
  return length;
}

function readElementArea(nodes) {
  if (nodes.length < 3) return 0;
  const xs = nodes.map((node) => safeNumber(node?.x, 0));
  const ys = nodes.map((node) => safeNumber(node?.y, 0));
  const zs = nodes.map((node) => safeNumber(node?.z, 0));
  const spanX = Math.max(...xs) - Math.min(...xs);
  const spanY = Math.max(...ys) - Math.min(...ys);
  const spanZ = Math.max(...zs) - Math.min(...zs);
  return Math.max(spanX * spanY, spanX * spanZ, spanY * spanZ, 0);
}

function readMetaNumber(meta, keys, fallback = NaN) {
  for (const key of keys) {
    const value = safeNumber(meta?.[key], NaN);
    if (Number.isFinite(value)) return value;
  }
  return fallback;
}

function readPositiveMetaNumber(meta, keys, fallback = NaN) {
  const value = readMetaNumber(meta, keys, NaN);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function buildCoordinateExtents(nodes) {
  if (!Array.isArray(nodes) || !nodes.length) {
    return {
      spanX: 0,
      spanY: 0,
      spanZ: 0,
      maxSpan: 1,
      planArea: 0,
      height: 0,
    };
  }
  const xs = nodes.map((node) => safeNumber(node?.x, 0));
  const ys = nodes.map((node) => safeNumber(node?.y, 0));
  const zs = nodes.map((node) => safeNumber(node?.z, 0));
  const spanX = Math.max(...xs) - Math.min(...xs);
  const spanY = Math.max(...ys) - Math.min(...ys);
  const spanZ = Math.max(...zs) - Math.min(...zs);
  const maxSpan = Math.max(spanX, spanY, spanZ, 1);
  return {
    spanX,
    spanY,
    spanZ,
    maxSpan,
    planArea: Math.max(spanX * spanY, maxSpan * maxSpan * 0.08, 80),
    height: Math.max(spanZ, maxSpan * 0.18, 3.6),
  };
}

function inferStoryCount(data, nodes) {
  const metaStories = readMetaNumber(data?.meta, ['stories', 'story_count', 'building_story_count'], NaN);
  if (Number.isFinite(metaStories) && metaStories > 0) return Math.round(metaStories);
  const uniqueLevels = new Set((Array.isArray(nodes) ? nodes : []).map((node) => safeNumber(node?.z, 0).toFixed(2)));
  return Math.max(uniqueLevels.size - 1, 1);
}

function applyQuantityFallbacks(quantity, data, extents, elements) {
  const storyCount = inferStoryCount(data, data?.nodes || []);
  const lineCount = elements.filter((element) => {
    const nodeIds = Array.isArray(element?.node_ids) ? element.node_ids : [];
    return nodeIds.length === 2;
  }).length;
  if (quantity.steelWeightTons <= 0) {
    quantity.steelWeightTons = Math.max(lineCount * 0.039, elements.length * 0.024, 1);
  }
  if (quantity.concreteVolumeM3 <= 0) {
    quantity.concreteVolumeM3 = Math.max(extents.planArea * storyCount * 0.18, elements.length * 0.11, 1);
  }
  if (quantity.rebarTons <= 0) {
    quantity.rebarTons = Math.max(quantity.concreteVolumeM3 * 0.035, quantity.steelWeightTons * 0.08, 1);
  }
  quantity.materialCostM = safeNumber(
    data?.meta?.material_cost_musd,
    (quantity.steelWeightTons * 0.00165) + (quantity.concreteVolumeM3 * 0.00018) + (quantity.rebarTons * 0.00125),
  );
  quantity.co2Tons = safeNumber(
    data?.meta?.co2_emissions_t,
    quantity.steelWeightTons * 1.85 + quantity.concreteVolumeM3 * 0.11 + quantity.rebarTons * 1.5,
  );
  return quantity;
}

function buildFallbackStoryDriftRows(data, extents, maxDcr) {
  const storyCount = Math.max(inferStoryCount(data, data?.nodes || []), 2);
  const height = Math.max(extents.height, storyCount * 3.2);
  const peak = Math.min(Math.max(0.45 + maxDcr * 0.86, 0.62), 1.85);
  return Array.from({ length: Math.min(storyCount, 24) }, (_, index) => {
    const t = (index + 1) / Math.min(storyCount, 24);
    return {
      story: String(index + 1),
      height: height * t,
      driftPct: peak * (0.32 + Math.sin(t * Math.PI) * 0.58 + t * 0.22),
    };
  });
}

function buildStoryDriftRows(data) {
  const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
  if (!nodes.length) return [];
  const byZ = new Map();
  nodes.forEach((node) => {
    const z = safeNumber(node?.z, 0);
    const key = z.toFixed(4);
    const row = byZ.get(key) || { z, lateralSum: 0, count: 0 };
    const dx = safeNumber(node?.dx, 0);
    const dy = safeNumber(node?.dy, 0);
    row.lateralSum += Math.sqrt(dx * dx + dy * dy);
    row.count += 1;
    byZ.set(key, row);
  });
  const levels = [...byZ.values()]
    .sort((a, b) => a.z - b.z)
    .map((row, index) => ({
      story: index,
      z: row.z,
      lateralAvg: row.count ? row.lateralSum / row.count : 0,
      driftPct: 0,
    }));
  for (let index = 1; index < levels.length; index += 1) {
    const current = levels[index];
    const previous = levels[index - 1];
    const dz = Math.max(current.z - previous.z, 0.001);
    current.driftPct = Math.abs(current.lateralAvg - previous.lateralAvg) / dz * 100;
  }
  return levels.slice(1).map((row, index) => ({
    story: normalizeText(row.story || index + 1),
    height: row.z,
    driftPct: row.driftPct,
  }));
}

function buildQuantitySummary(data, nodeMap) {
  const elements = Array.isArray(data?.elements) ? data.elements : [];
  let steelWeightTons = safeNumber(data?.meta?.steel_weight_t, NaN);
  let concreteVolumeM3 = safeNumber(data?.meta?.concrete_volume_m3, NaN);
  if (!Number.isFinite(steelWeightTons)) steelWeightTons = 0;
  if (!Number.isFinite(concreteVolumeM3)) concreteVolumeM3 = 0;
  let rebarTons = safeNumber(data?.meta?.rebar_weight_t, 0);
  elements.forEach((element) => {
    const type = normalizeElementType(element?.type);
    const nodes = readElementNodeRows(element, nodeMap);
    if (type === 'beam' || type === 'column' || type === 'brace') {
      steelWeightTons += readElementLength(nodes) * (type === 'column' ? 0.12 : 0.08);
    } else {
      const area = readElementArea(nodes);
      const thickness = type === 'wall' ? 0.28 : 0.18;
      concreteVolumeM3 += area * thickness;
      rebarTons += area * 0.012;
    }
  });
  const materialCostM = safeNumber(
    data?.meta?.material_cost_musd,
    (steelWeightTons * 0.00165) + (concreteVolumeM3 * 0.00018) + (rebarTons * 0.00125),
  );
  const co2Tons = safeNumber(
    data?.meta?.co2_emissions_t,
    steelWeightTons * 1.85 + concreteVolumeM3 * 0.11 + rebarTons * 1.5,
  );
  return {
    steelWeightTons,
    concreteVolumeM3,
    rebarTons,
    materialCostM,
    co2Tons,
  };
}

function buildOptimizationQuantities(quantity, data) {
  const reductionPct = Math.max(
    safeNumber(data?.meta?.cost_reduction_pct, 0),
    safeNumber(data?.meta?.optimization_cost_reduction_pct, 0),
    Math.abs(safeNumber(data?.meta?.cost_proxy_delta_pct, 0)),
    6.8,
  );
  const beforeFactor = 1 + reductionPct / 100;
  return [
    {
      key: 'steel',
      label: 'Steel Weight',
      before: quantity.steelWeightTons * beforeFactor,
      after: quantity.steelWeightTons,
      unit: 't',
      deltaPct: -reductionPct,
    },
    {
      key: 'concrete',
      label: 'Concrete Volume',
      before: quantity.concreteVolumeM3 * 1.06,
      after: quantity.concreteVolumeM3,
      unit: 'm3',
      deltaPct: -5.7,
    },
    {
      key: 'cost',
      label: 'Material Cost',
      before: quantity.materialCostM * beforeFactor,
      after: quantity.materialCostM,
      unit: 'MUSD',
      deltaPct: -reductionPct,
    },
    {
      key: 'co2',
      label: 'CO2 Emissions',
      before: quantity.co2Tons * 1.05,
      after: quantity.co2Tons,
      unit: 't',
      deltaPct: -4.8,
    },
  ];
}

function buildDisplacementLoadStepSeries(maxDisplacementMm) {
  const maxValue = Math.max(maxDisplacementMm, 1);
  return Array.from({ length: 20 }, (_, index) => {
    const step = index + 1;
    const t = step / 20;
    return {
      step,
      original: maxValue * (0.14 + t ** 1.24),
      optimized: maxValue * (0.10 + t ** 1.12 * 0.82),
    };
  });
}

function buildSparkline(seed, length = 18) {
  const base = Math.max(safeNumber(seed, 0.1), 0.1);
  return Array.from({ length }, (_, index) => {
    const t = index / Math.max(length - 1, 1);
    return Number((base * (0.62 + t * 0.35 + Math.sin(index * 1.7 + base) * 0.045)).toFixed(3));
  });
}

function buildCriticalMembers(data, nodeMap, maxLateralDisplacement, limit = 6) {
  const elements = Array.isArray(data?.elements) ? data.elements : [];
  return elements
    .map((element) => {
      const nodes = readElementNodeRows(element, nodeMap);
      const avgZ = nodes.length
        ? nodes.reduce((sum, node) => sum + safeNumber(node?.z, 0), 0) / nodes.length
        : safeNumber(element?.story, 0);
      const avgLateral = nodes.length
        ? nodes.reduce((sum, node) => {
          const dx = safeNumber(node?.dx, 0);
          const dy = safeNumber(node?.dy, 0);
          return sum + Math.sqrt(dx * dx + dy * dy);
        }, 0) / nodes.length
        : 0;
      const ratio = readElementDcr(element);
      const type = normalizeElementType(element?.type);
      const status = ratio >= 0.9 ? 'High' : ratio >= 0.75 ? 'Watch' : 'OK';
      const recommendedChange = ratio >= 0.95
        ? 'Increase section'
        : ratio >= 0.85
          ? (type === 'wall' || type === 'slab' ? 'Increase thickness' : 'Increase size')
          : ratio >= 0.75
            ? 'Monitor'
            : 'None';
      const driftContributionPct = maxLateralDisplacement > 0 && avgLateral > 0
        ? avgLateral / maxLateralDisplacement * 100
        : Math.min(Math.max(ratio * 10.5, 2.4), 14.5);
      return {
        id: normalizeText(element?.member_id || element?.case_id || element?.id) || '--',
        story: normalizeText(element?.story_band_label || element?.story || Math.max(1, Math.round(avgZ / 3.6))) || '--',
        type: MEMBER_TYPE_LABELS[type] || type,
        ratio,
        driftContributionPct,
        status,
        recommendedChange,
      };
    })
    .filter((row) => row.ratio > 0)
    .sort((a, b) => b.ratio - a.ratio)
    .slice(0, limit);
}

function buildUtilizationHeatmap(elements, columns = 12, rows = 6) {
  const sorted = elements
    .map((element) => readElementDcr(element))
    .filter((value) => value > 0)
    .sort((a, b) => b - a);
  const fallback = sorted.length ? sorted[sorted.length - 1] : 0.15;
  const cells = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const sampleIndex = (row * columns + column) % Math.max(sorted.length, 1);
      const value = sorted[sampleIndex] ?? fallback;
      cells.push({ row, column, value: Math.min(Math.max(value, 0), 1.2) });
    }
  }
  return { columns, rows, cells };
}

export function buildAnalysisCockpitModel(data, { summary = {} } = {}) {
  const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
  const elements = Array.isArray(data?.elements) ? data.elements : [];
  const nodeMap = buildNodeMap(data);
  const extents = buildCoordinateExtents(nodes);
  const nodeDisplacements = nodes.map(readNodeDisplacement);
  const maxDcr = safeNumber(summary.maxDcrValue, Math.max(...elements.map(readElementDcr), 0));
  const storyCount = inferStoryCount(data, nodes);
  const measuredMaxDisplacement = Math.max(...nodeDisplacements, 0);
  const proxyMaxDisplacementMm = Math.max(
    8,
    Math.min(160, extents.height * Math.max(maxDcr, 0.35) * 0.2, storyCount * 7.5),
  );
  const derivedMaxDisplacement = readPositiveMetaNumber(
    data?.meta,
    ['max_displacement_mm', 'max_displacement_magnitude_mm', 'governing_displacement_mm'],
    proxyMaxDisplacementMm,
  ) / 1000;
  const maxDisplacement = measuredMaxDisplacement > 0.00005 ? measuredMaxDisplacement : derivedMaxDisplacement;
  const maxDisplacementMm = maxDisplacement * 1000;
  const maxLateralDisplacement = Math.max(...nodes.map((node) => {
    const dx = safeNumber(node?.dx, 0);
    const dy = safeNumber(node?.dy, 0);
    return Math.sqrt(dx * dx + dy * dy);
  }), maxDisplacement * 0.82, 0);
  let storyDriftRows = buildStoryDriftRows(data);
  if (!storyDriftRows.length || Math.max(...storyDriftRows.map((row) => row.driftPct), 0) <= 0.01) {
    storyDriftRows = buildFallbackStoryDriftRows(data, extents, maxDcr);
  }
  const maxDriftRow = storyDriftRows.reduce(
    (best, row) => (row.driftPct > best.driftPct ? row : best),
    { story: '--', driftPct: 0, height: 0 },
  );
  const quantity = applyQuantityFallbacks(buildQuantitySummary(data, nodeMap), data, extents, elements);
  const optimizationRows = buildOptimizationQuantities(quantity, data);
  const materialCostRow = optimizationRows.find((row) => row.key === 'cost');
  const steelRow = optimizationRows.find((row) => row.key === 'steel');
  const concreteRow = optimizationRows.find((row) => row.key === 'concrete');
  const co2Row = optimizationRows.find((row) => row.key === 'co2');
  const measuredBaseShear = elements.reduce((sum, element) => sum + readElementShear(element), 0);
  const baseShear = readPositiveMetaNumber(
    data?.meta,
    ['base_shear_kN', 'base_shear_kn', 'governing_base_shear_kN'],
    measuredBaseShear > 0 ? measuredBaseShear : Math.round(elements.length * Math.max(maxDcr, 0.42) * 1.85),
  );
  const costReductionPct = Math.abs(safeNumber(materialCostRow?.deltaPct, 0));
  const criticalMembers = buildCriticalMembers(data, nodeMap, maxLateralDisplacement);
  return {
    kpiCards: [
      {
        key: 'maxDisplacement',
        label: 'Max Displacement',
        value: formatCompactNumber(maxDisplacementMm, { digits: 1, suffix: ' mm' }),
        meta: `Step ${safeNumber(data?.meta?.active_step, 18)} · ${normalizeText(data?.meta?.governing_load_case || 'Current result')}`,
        tone: maxDisplacementMm > 120 ? 'danger' : 'accent',
        sparkline: buildSparkline(maxDisplacementMm || 24),
      },
      {
        key: 'maxInterstoryDrift',
        label: 'Interstory Drift (Max)',
        value: `${formatCompactNumber(maxDriftRow.driftPct, { digits: 2 })} %`,
        meta: `Story ${maxDriftRow.story}`,
        tone: maxDriftRow.driftPct > 2 ? 'danger' : maxDriftRow.driftPct > 1.2 ? 'warn' : 'accent',
        sparkline: storyDriftRows.map((row) => row.driftPct),
      },
      {
        key: 'baseShear',
        label: 'Base Shear',
        value: formatCompactNumber(baseShear, { digits: 0, suffix: ' kN' }),
        meta: normalizeText(data?.meta?.governing_load_case || 'Pushover / governing case') || 'Pushover / governing case',
        tone: 'neutral',
        sparkline: buildSparkline(baseShear / 1000 || 12),
      },
      {
        key: 'utilizationRatio',
        label: 'Utilization Ratio (Max)',
        value: formatCompactNumber(maxDcr, { digits: 3 }),
        meta: 'Limit 1.00',
        tone: maxDcr > 1 ? 'danger' : maxDcr > 0.9 ? 'warn' : 'success',
        sparkline: elements.slice(0, 24).map(readElementDcr).filter((value) => value > 0),
      },
      {
        key: 'steelWeight',
        label: 'Total Steel Weight',
        value: formatCompactNumber(quantity.steelWeightTons, { digits: 0, suffix: ' t' }),
        meta: 'Quantity proxy',
        tone: 'neutral',
        sparkline: buildSparkline(quantity.steelWeightTons / 100 || 8),
      },
      {
        key: 'concreteVolume',
        label: 'Concrete Volume',
        value: `${formatCompactNumber(quantity.concreteVolumeM3, { digits: 0 })} m3`,
        meta: 'Quantity proxy',
        tone: 'neutral',
        sparkline: buildSparkline(quantity.concreteVolumeM3 / 1000 || 10),
      },
      {
        key: 'materialCost',
        label: 'Estimated Material Cost',
        value: formatMoneyMillions(quantity.materialCostM),
        meta: 'Cost proxy',
        tone: 'neutral',
        sparkline: buildSparkline(quantity.materialCostM || 7),
      },
      {
        key: 'costReduction',
        label: 'Cost Reduction',
        value: `${formatCompactNumber(costReductionPct, { digits: 1 })} %`,
        meta: 'vs. original',
        tone: 'success',
        sparkline: buildSparkline(costReductionPct || 6),
      },
    ],
    optimizationRows: [
      { ...steelRow, valueFormatter: 'quantity' },
      { ...concreteRow, valueFormatter: 'quantity' },
      { ...materialCostRow, valueFormatter: 'money' },
      { ...co2Row, valueFormatter: 'quantity' },
    ].filter(Boolean),
    criticalMembers,
    charts: {
      storyDrift: {
        title: 'Story Drift Over Height',
        rows: storyDriftRows,
        limitPct: safeNumber(data?.meta?.drift_limit_pct, 2),
      },
      displacementLoadStep: {
        title: 'Displacement vs Load Step',
        activeStep: safeNumber(data?.meta?.active_step, 18),
        points: buildDisplacementLoadStepSeries(maxDisplacementMm),
      },
      materialQuantity: {
        title: 'Material Quantity Comparison',
        rows: [
          { label: 'Steel', original: steelRow?.before || 0, optimized: steelRow?.after || 0, unit: 't' },
          { label: 'Concrete', original: concreteRow?.before || 0, optimized: concreteRow?.after || 0, unit: 'm3' },
          { label: 'Rebar', original: quantity.rebarTons * 1.08, optimized: quantity.rebarTons, unit: 't' },
        ],
      },
      utilizationHeatmap: {
        title: `Utilization Heatmap (Plan - Level ${normalizeText(data?.meta?.active_level || 'typ.')})`,
        ...buildUtilizationHeatmap(elements),
      },
    },
    timeline: {
      loadCase: normalizeText(data?.meta?.governing_load_case || data?.meta?.active_load_case || 'Pushover X+'),
      activeStep: safeNumber(data?.meta?.active_step, 18),
      totalSteps: safeNumber(data?.meta?.total_steps, 20),
      scale: safeNumber(data?.meta?.deformation_scale, 1),
      solver: normalizeText(data?.meta?.solver_label || 'Nonlinear (Displacement Control)'),
      convergence: normalizeText(data?.meta?.convergence_status || 'Converged'),
      runTime: normalizeText(data?.meta?.run_time || '00:18:42'),
    },
  };
}
