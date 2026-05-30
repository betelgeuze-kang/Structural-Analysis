function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeToken(value) {
  return normalizeText(value).toLowerCase();
}

function safeNumber(value, fallback = NaN) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

const STRUCTURAL_COMPONENT_DENY = /drift|residual|weight|mass|period|frequency/i;

export const CODECHECK_COMPANION_PATHS = {
  baseline: 'implementation/phase1/release/visualization/entries/midas33_original_baseline.json',
  optimized: 'implementation/phase1/release/visualization/entries/midas33_optimized_roundtrip.json',
};

export function resolveCodecheckCompanionPaths(workspace = {}) {
  const drawing = workspace?.drawing && typeof workspace.drawing === 'object' ? workspace.drawing : {};
  const lineage = Array.isArray(drawing.lineage) ? drawing.lineage : [];
  const baselineLineage = lineage.find((row) => /baseline|source/i.test(normalizeText(row.stage || row.label)));
  const optimizedLineage = lineage.find((row) => /optim/i.test(normalizeText(row.stage || row.label)));
  return {
    baseline: normalizeText(baselineLineage?.path) || CODECHECK_COMPANION_PATHS.baseline,
    optimized: normalizeText(optimizedLineage?.path)
      || normalizeText(drawing.provenance?.report_path)
      || CODECHECK_COMPANION_PATHS.optimized,
  };
}

export function parseCodecheckDcrValue(row = {}) {
  const direct = safeNumber(row.dcr, NaN);
  if (direct > 0) return direct;
  const labelled = safeNumber(row.dcr_label, NaN);
  if (labelled > 0) return labelled;
  const governing = safeNumber(row.governing_dcr, NaN);
  if (governing > 0) return governing;
  const text = normalizeText(row.governing_dcr_label || row.dcr_label);
  if (!text) return NaN;
  const match = text.match(/[+-]?\d+(?:\.\d+)?/);
  return match ? safeNumber(match[0], NaN) : NaN;
}

export function isStructuralCodecheckComponent(component = '') {
  const normalized = normalizeText(component);
  if (!normalized) return true;
  return !STRUCTURAL_COMPONENT_DENY.test(normalized);
}

function resolveElementIdFromRow(row = {}, bridgeRow = {}) {
  return normalizeText(
    row.target_element_id
    || row.baseline_focus_member_id
    || bridgeRow.full_crosswalk_target_element_id
    || bridgeRow.baseline_focus_member_id
    || row.member_id
    || row.source_member_id
    || bridgeRow.review_member_id,
  );
}

function upsertDcrEntry(map, elementId, entry) {
  const normalized = normalizeText(elementId);
  const dcr = safeNumber(entry?.dcr, NaN);
  if (!normalized || !Number.isFinite(dcr) || dcr <= 0) return;
  const existing = map.get(normalized);
  if (!existing || dcr >= existing.dcr) {
    map.set(normalized, {
      dcr,
      source: entry.source || 'codecheck',
      combination: entry.combination || '',
      component: entry.component || '',
    });
  }
}

export function buildElementDcrMapFromLoadCombinationForceRows(rows = [], {
  combination = '',
} = {}) {
  const map = new Map();
  const normalizedCombination = normalizeText(combination);
  for (const row of Array.isArray(rows) ? rows : []) {
    if (!isStructuralCodecheckComponent(row.component)) continue;
    if (normalizedCombination && normalizeText(row.combination) !== normalizedCombination) continue;
    const dcr = parseCodecheckDcrValue(row);
    if (!Number.isFinite(dcr) || dcr <= 0) continue;
    upsertDcrEntry(map, resolveElementIdFromRow(row), {
      dcr,
      source: 'load_combination_force_rows',
      combination: row.combination,
      component: row.component,
    });
  }
  return map;
}

export function buildElementDcrMapFromGeometryBridge(bridge = {}, {
  combination = '',
} = {}) {
  const map = new Map();
  const bridgeRows = Array.isArray(bridge?.bridge_rows) ? bridge.bridge_rows : [];
  const normalizedCombination = normalizeText(combination);
  for (const bridgeRow of bridgeRows) {
    const provenanceRows = Array.isArray(bridgeRow.row_provenance_rows) ? bridgeRow.row_provenance_rows : [];
    let rowMax = 0;
    let rowCombination = '';
    let rowComponent = '';
    for (const row of provenanceRows) {
      if (!isStructuralCodecheckComponent(row.component)) continue;
      if (normalizedCombination && normalizeText(row.combination) !== normalizedCombination) continue;
      const dcr = parseCodecheckDcrValue(row);
      if (!Number.isFinite(dcr) || dcr <= 0) continue;
      if (dcr >= rowMax) {
        rowMax = dcr;
        rowCombination = row.combination;
        rowComponent = row.component;
      }
    }
    if (rowMax <= 0) continue;
    const handles = Array.isArray(bridgeRow.full_crosswalk_member_handles)
      ? bridgeRow.full_crosswalk_member_handles
      : [];
    if (handles.length) {
      handles.forEach((handle) => {
        upsertDcrEntry(map, handle, {
          dcr: rowMax,
          source: 'kds_geometry_bridge_handles',
          combination: rowCombination,
          component: rowComponent,
        });
      });
      continue;
    }
    upsertDcrEntry(map, resolveElementIdFromRow({}, bridgeRow), {
      dcr: rowMax,
      source: 'kds_geometry_bridge_focus',
      combination: rowCombination,
      component: rowComponent,
    });
  }
  return map;
}

export function buildElementDcrMapFromCaseContext(caseContext = {}, {
  combination = '',
} = {}) {
  const map = new Map();
  const table = caseContext?.load_combination_codecheck_table_by_name
    && typeof caseContext.load_combination_codecheck_table_by_name === 'object'
    ? caseContext.load_combination_codecheck_table_by_name
    : {};
  const normalizedCombination = normalizeText(combination);
  Object.entries(table).forEach(([comboName, entry]) => {
    if (normalizedCombination && normalizeText(comboName) !== normalizedCombination) return;
    const rows = Array.isArray(entry?.table_rows) && entry.table_rows.length
      ? entry.table_rows
      : Array.isArray(entry?.top_rows)
        ? entry.top_rows
        : [];
    rows.forEach((row) => {
      if (!isStructuralCodecheckComponent(row.component)) return;
      const dcr = parseCodecheckDcrValue(row);
      if (!Number.isFinite(dcr) || dcr <= 0) return;
      upsertDcrEntry(map, resolveElementIdFromRow(row), {
        dcr,
        source: 'load_combination_codecheck_table',
        combination: comboName,
        component: row.component,
      });
    });
  });
  return map;
}

export function mergeElementDcrMaps(...maps) {
  const merged = new Map();
  maps.forEach((map) => {
    if (!(map instanceof Map)) return;
    map.forEach((entry, elementId) => upsertDcrEntry(merged, elementId, entry));
  });
  return merged;
}

export function buildElementDcrMapFromModelMeta(meta = {}, rootPayload = null, options = {}) {
  const combination = normalizeText(options.combination);
  const caseContext = rootPayload?.case_context && typeof rootPayload.case_context === 'object'
    ? rootPayload.case_context
    : {};
  const bridge = meta?.kds_geometry_bridge && typeof meta.kds_geometry_bridge === 'object'
    ? meta.kds_geometry_bridge
    : {};
  return mergeElementDcrMaps(
    buildElementDcrMapFromCaseContext(caseContext, { combination }),
    buildElementDcrMapFromLoadCombinationForceRows(meta.load_combination_force_rows, { combination }),
    buildElementDcrMapFromGeometryBridge(bridge, { combination }),
  );
}

export function buildElementDcrMapAllCombinations(meta = {}, rootPayload = null) {
  const caseContext = rootPayload?.case_context && typeof rootPayload.case_context === 'object'
    ? rootPayload.case_context
    : {};
  const table = caseContext?.load_combination_codecheck_table_by_name
    && typeof caseContext.load_combination_codecheck_table_by_name === 'object'
    ? caseContext.load_combination_codecheck_table_by_name
    : {};
  const combinations = Object.keys(table);
  const maps = combinations.map((combo) => buildElementDcrMapFromModelMeta(meta, rootPayload, { combination: combo }));
  const bridge = meta?.kds_geometry_bridge && typeof meta.kds_geometry_bridge === 'object'
    ? meta.kds_geometry_bridge
    : {};
  maps.push(buildElementDcrMapFromGeometryBridge(bridge, {}));
  maps.push(buildElementDcrMapFromLoadCombinationForceRows(meta.load_combination_force_rows, {}));
  return mergeElementDcrMaps(...maps);
}

export function hydrateModelElementsWithCodecheckDcr(modelData = {}, dcrMap = new Map(), {
  combination = '',
} = {}) {
  const elements = Array.isArray(modelData?.elements) ? modelData.elements : [];
  let hydratedCount = 0;
  elements.forEach((element) => {
    const keys = [
      normalizeText(element?.id),
      normalizeText(element?.member_id),
      normalizeText(element?.case_id),
    ].filter(Boolean);
    let entry = null;
    for (const key of keys) {
      if (dcrMap.has(key)) {
        entry = dcrMap.get(key);
        break;
      }
    }
    if (!entry) return;
    element.dcr = entry.dcr;
    element.max_dcr = entry.dcr;
    element.dcr_source = entry.source;
    element.codecheck_combination = entry.combination || combination;
    element.codecheck_component = entry.component;
    hydratedCount += 1;
  });
  const meta = modelData?.meta && typeof modelData.meta === 'object' ? modelData.meta : {};
  meta.codecheck_dcr_hydration = {
    status: hydratedCount > 0 ? 'hydrated' : 'missing',
    hydrated_count: hydratedCount,
    element_count: elements.length,
    map_size: dcrMap.size,
    combination: normalizeText(combination),
    coverage_pct: elements.length > 0 ? Number(((hydratedCount / elements.length) * 100).toFixed(2)) : 0,
  };
  modelData.meta = meta;
  return meta.codecheck_dcr_hydration;
}

export function buildCodecheckHydrationPlan(modelData = {}, {
  rootPayload = null,
  combination = '',
} = {}) {
  const meta = modelData?.meta && typeof modelData.meta === 'object' ? modelData.meta : {};
  const dcrMap = buildElementDcrMapFromModelMeta(meta, rootPayload, { combination });
  return {
    dcrMap,
    combination: normalizeText(combination),
    mapSize: dcrMap.size,
  };
}

export function applyCodecheckHydrationToModelData(modelData = {}, {
  rootPayload = null,
  combination = '',
} = {}) {
  const plan = buildCodecheckHydrationPlan(modelData, { rootPayload, combination });
  const summary = hydrateModelElementsWithCodecheckDcr(modelData, plan.dcrMap, {
    combination: plan.combination,
  });
  return {
    ...summary,
    map_size: plan.mapSize,
  };
}
