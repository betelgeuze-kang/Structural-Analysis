const DEFAULT_NORMALIZATION_CHUNK_SIZE = 1200;

export function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

// Extended element type registry matching commercial structural tools
export const ELEMENT_TYPE_REGISTRY = new Set([
  'beam', 'column', 'brace', 'truss', 'cable', 'rebar', 'girder',
  'purlin', 'joist', 'tie', 'strut', 'wall', 'slab', 'shell',
  'footing', 'pile', 'mat', 'panel_zone', 'joint', 'isolator',
  'damper', 'soil', 'rock', 'terrain', 'roof', 'diaphragm',
  'retaining_wall', 'parapet', 'stairs', 'ramp', 'balcony',
  'mega_column', 'spandrel', 'lintel', 'shear_wall', 'core_wall',
  'opening', 'void', 'opening_void',
  'cold_formed_steel', 'masonry', 'frp_member',
  'composite_beam', 'src_column', 'cft_column',
  'prestressing_tendon', 'anchor', 'bolt', 'weld',
  'friction_pendulum', 'lead_rubber_bearing', 'viscous_damper',
  'spring', 'link', 'rigid_link', 'lumped_mass',
  'expansion_joint', 'bearing', 'pot_bearing', 'spherical_bearing',
  'generic', 'other', 'unknown',
]);

export function normalizeElementType(value) {
  const raw = String(value || 'beam').trim().toLowerCase();
  const type = raw || 'beam';
  if (ELEMENT_TYPE_REGISTRY.has(type)) return type;
  // Map common synonyms
  const synonyms = {
    'col': 'column', '柱': 'column',
    'bm': 'beam', '梁': 'beam',
    'br': 'brace', '지보': 'brace',
    'tr': 'truss', '트러스': 'truss',
    'cab': 'cable', '케이블': 'cable',
    'rb': 'rebar', '철근': 'rebar',
    'sl': 'slab', '슬래브': 'slab',
    'wl': 'wall', '벽체': 'wall', '벽': 'wall',
    'sh': 'shell', '쉘': 'shell',
    'ft': 'footing', '기초': 'footing',
    'pl': 'pile', '말뚝': 'pile',
    'mt': 'mat', '매트': 'mat',
    'pz': 'panel_zone', 'panel': 'panel_zone',
    'jt': 'joint', '연결부': 'joint',
    'iso': 'isolator', '절연체': 'isolator',
    'dmp': 'damper', '댐퍼': 'damper',
    'gr': 'girder', '거더': 'girder',
    'pu': 'purlin', '펄린': 'purlin',
    'sw': 'shear_wall', '내력벽': 'shear_wall',
    'cw': 'core_wall', '코어': 'core_wall',
    'rf': 'roof', '지붕': 'roof',
    'st': 'stairs', '계단': 'stairs',
    'frp': 'frp_member', '목재': 'timber',
    'timber': 'timber', 'wood': 'timber',
    'cold': 'cold_formed_steel',
    'masonry': 'masonry', '조적': 'masonry',
    'prestress': 'prestressing_tendon', '프리스트레스': 'prestressing_tendon',
    'anchor': 'anchor', '앵커': 'anchor',
    'bolt': 'bolt', '볼트': 'bolt',
    'weld': 'weld', '용접': 'weld',
    'fps': 'friction_pendulum',
    'lrb': 'lead_rubber_bearing',
    'spring': 'spring', '스프링': 'spring',
    'link': 'link', '링크': 'link',
    'rigid': 'rigid_link', '질량': 'lumped_mass',
    'bearing': 'bearing', '지지': 'bearing',
  };
  return synonyms[type] || 'other';
}

export function getElementGeometryKind(type) {
  const normalized = normalizeElementType(type);
  const lineTypes = new Set([
    'beam', 'column', 'brace', 'truss', 'cable', 'rebar', 'girder',
    'purlin', 'joist', 'tie', 'strut', 'prestressing_tendon',
    'anchor', 'bolt', 'weld', 'spring', 'link', 'rigid_link',
  ]);
  const surfaceTypes = new Set([
    'wall', 'slab', 'shell', 'roof', 'diaphragm', 'shear_wall',
    'core_wall', 'retaining_wall', 'parapet', 'stairs', 'ramp',
    'balcony', 'cold_formed_steel', 'masonry', 'frp_member',
    'opening', 'void', 'opening_void',
  ]);
  const solidTypes = new Set([
    'footing', 'pile', 'mat', 'panel_zone', 'joint', 'isolator',
    'damper', 'friction_pendulum', 'lead_rubber_bearing', 'viscous_damper',
    'bearing', 'pot_bearing', 'spherical_bearing', 'lumped_mass',
    'expansion_joint', 'generic', 'other', 'unknown',
  ]);
  const terrainTypes = new Set(['soil', 'rock', 'terrain']);
  const compositeTypes = new Set(['composite_beam', 'src_column', 'cft_column']);

  if (lineTypes.has(normalized)) return 'line';
  if (surfaceTypes.has(normalized)) return 'surface';
  if (solidTypes.has(normalized)) return 'solid';
  if (terrainTypes.has(normalized)) return 'terrain';
  if (compositeTypes.has(normalized)) return 'composite';
  return 'line';
}

export function resolveMaterialType(element) {
  const mat = String(
    element?.material_type ||
    element?.mat ||
    element?.material ||
    element?.material_family ||
    ''
  ).trim().toLowerCase();
  if (!mat) return 'steel';

  const families = {
    concrete: ['concrete', '콘크리트', 'rc', 'reinforced_concrete', 'plain_concrete', '轻质混凝土'],
    steel: ['steel', '강', 'structural_steel', 'rail_steel', 'stainless_steel', 'galvanized_steel'],
    composite: ['composite', '복합', 'src', 'cft', 'composite_beam', 'steel_concrete_composite'],
    timber: ['timber', '목재', 'wood', 'glulam', 'clt', 'lvl', 'solid_sawn'],
    masonry: ['masonry', '조적', 'brick', 'block', 'stone'],
    frp: ['frp', 'fiber', 'cfrp', 'gfrp', 'afrp', 'bfrp', 'fibre'],
    prestressing: ['prestressing', 'prestressed', 'tendon', 'strand', 'wire'],
    cable: ['cable', 'strand', 'rope', 'locked_coil'],
    soil: ['soil', '지반', 'clay', 'sand', 'silt', 'gravel', 'fill'],
    rock: ['rock', '암반', 'stone', 'masonry_rock'],
    cold_formed: ['cold_formed', 'cold_form', 'cfs', 'light_gauge'],
    rebar: ['rebar', '철근', 'reinforcing_bar', 'deformed_bar'],
    bolt: ['bolt', '볼트', 'fastener'],
    anchor: ['anchor', '앵커'],
    weld: ['weld', '용접', 'welding'],
    isolator: ['isolator', '절연체', 'bearing', 'pad', 'elastomeric'],
    damper: ['damper', '댐퍼', 'viscous', 'hysteretic', 'friction_damper'],
    glass: ['glass', '유리'],
    aluminum: ['aluminum', '알루미늄', 'aluminium'],
    asphalt: ['asphalt', '아스팔트'],
    insulation: ['insulation', '단열', 'thermal'],
    waterproofing: ['waterproofing', '방수'],
    coating: ['coating', '도장', 'paint', 'corrosion_protection'],
  };

  for (const [family, keywords] of Object.entries(families)) {
    for (const kw of keywords) {
      if (mat.includes(kw)) return family;
    }
  }
  return 'steel';
}

export function isModelPayload(payload) {
  return Boolean(extractModelPayload(payload));
}

export function extractModelPayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (Array.isArray(payload.nodes) && Array.isArray(payload.elements)) {
    return { model: payload, root: payload };
  }
  if (
    payload.model &&
    typeof payload.model === 'object' &&
    Array.isArray(payload.model.nodes) &&
    Array.isArray(payload.model.elements)
  ) {
    return { model: payload.model, root: payload };
  }
  return null;
}

export function extractInteractivePayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (payload.interactive_3d && typeof payload.interactive_3d === 'object') return payload.interactive_3d;
  if (payload.interactive_3d_payload && typeof payload.interactive_3d_payload === 'object') {
    return payload.interactive_3d_payload;
  }
  if (Array.isArray(payload.baseline_segments) || Array.isArray(payload.after_segments)) return payload;
  return null;
}

export function extractNativeModelPayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  // Support for native FE model formats (MIDAS, OpenSees, Abaqus-like)
  if (Array.isArray(payload.nodes) && Array.isArray(payload.elements)) {
    return { nodes: payload.nodes, elements: payload.elements, meta: payload.meta || {} };
  }
  if (payload.native_model && typeof payload.native_model === 'object') {
    const nm = payload.native_model;
    if (Array.isArray(nm.nodes) && Array.isArray(nm.elements)) {
      return { nodes: nm.nodes, elements: nm.elements, meta: nm.meta || payload.meta || {} };
    }
  }
  // Support for extended model with material models
  if (payload.material_models && payload.geometry) {
    return {
      nodes: payload.geometry.nodes || [],
      elements: payload.geometry.elements || [],
      material_models: payload.material_models,
      meta: payload.meta || {},
    };
  }
  return null;
}

export function normalizePoint(point) {
  if (!Array.isArray(point) || point.length < 3) return null;
  return [
    safeNumber(point[0], 0),
    safeNumber(point[1], 0),
    safeNumber(point[2], 0),
  ];
}

export function registerSegmentNode(point, nodeIndexByKey, nodes) {
  const normalized = normalizePoint(point);
  if (!normalized) return null;
  const key = normalized.map(value => value.toFixed(4)).join('|');
  if (nodeIndexByKey.has(key)) return nodeIndexByKey.get(key);
  const id = nodes.length;
  const node = {
    id,
    x: normalized[0],
    y: normalized[2],
    z: normalized[1],
    dx: 0,
    dy: 0,
    dz: 0,
    disp_mag: 0,
    stress_vm: 0,
    dcr: 0,
    axial: 0,
    moment: 0,
    shear: 0,
  };
  nodes.push(node);
  nodeIndexByKey.set(key, id);
  return id;
}

export function rgbArrayToHex(value) {
  if (!Array.isArray(value) || value.length < 3) return '';
  const channels = value
    .slice(0, 3)
    .map(entry => Math.max(0, Math.min(255, Math.round(safeNumber(entry, 0)))));
  return `#${channels.map(entry => entry.toString(16).padStart(2, '0')).join('')}`;
}

export function estimateStoryCount(nodes, axisRefs = {}) {
  const axisStoryCount = Array.isArray(axisRefs?.z) ? axisRefs.z.length : 0;
  const levels = new Set();
  (Array.isArray(nodes) ? nodes : []).forEach(node => {
    const z = safeNumber(node?.z, NaN);
    if (Number.isFinite(z)) levels.add(z.toFixed(3));
  });
  const nodeStoryCount = levels.size > 1 ? Math.max(levels.size - 1, 0) : 0;
  return Math.max(axisStoryCount, nodeStoryCount, 0);
}

// ==========================================================
// Interactive segment builder (baseline vs optimized)
// ==========================================================
function addInteractiveSegment(row, scope, index, { nodeIndexByKey, nodes, elements }) {
  const p0 = normalizePoint(row?.p0);
  const p1 = normalizePoint(row?.p1);
  if (!p0 || !p1) return;
  const n0 = registerSegmentNode(p0, nodeIndexByKey, nodes);
  const n1 = registerSegmentNode(p1, nodeIndexByKey, nodes);
  const type = normalizeElementType(row?.member_type || row?.category || row?.type);
  elements.push({
    ...row,
    id: `${scope}:${row?.member_id || index}:${index}`,
    type,
    node_ids: [n0, n1],
    section: row?.after_section || row?.before_section || row?.section_name || '--',
    color: String(row?.color || '').trim(),
    material_type: resolveMaterialType(row),
    dcr: safeNumber(row?.dcr, safeNumber(row?.max_dcr_after, safeNumber(row?.max_dcr_before, 0))),
    axial: safeNumber(row?.axial, 0),
    moment: safeNumber(row?.moment, 0),
    shear: safeNumber(row?.shear, 0),
    overlay_scope: scope,
    story_band_label: String(row?.story_band_label || '').trim(),
    zone_label: String(row?.zone_label || '').trim(),
    action_name: String(row?.action_name || '').trim(),
    optimization_meaning_label: String(row?.optimization_meaning_label || '').trim(),
    before_after_snapshot_note: String(row?.before_after_snapshot_note || '').trim(),
    geometry_kind: getElementGeometryKind(type),
  });
}

function buildInteractiveModel(payload, sourceMeta, { nodes, elements, normalizationMode }) {
  const interactive = extractInteractivePayload(payload);
  const metaSource = payload?.case_context && typeof payload.case_context === 'object' ? payload.case_context : {};
  const storyOptions = Array.isArray(interactive?.story_slice_options) ? interactive.story_slice_options : [];
  const axisRefs = interactive?.axis_refs && typeof interactive.axis_refs === 'object' ? interactive.axis_refs : {};
  const loadCombinationGraphNodeRows = Array.isArray(metaSource.load_combination_graph_node_rows)
    ? metaSource.load_combination_graph_node_rows.filter(Boolean)
    : [];
  const loadCombinationCodecheckTableByName =
    metaSource.load_combination_codecheck_table_by_name &&
    typeof metaSource.load_combination_codecheck_table_by_name === 'object'
      ? metaSource.load_combination_codecheck_table_by_name
      : {};
  const baselineSegments = Array.isArray(interactive?.baseline_segments)
    ? interactive.baseline_segments.filter(Boolean)
    : [];
  const afterSegments = Array.isArray(interactive?.after_segments)
    ? interactive.after_segments.filter(Boolean)
    : [];
  return {
    nodes,
    elements,
    meta: {
      name: String(
        metaSource.case_id ||
        metaSource.case_label ||
        payload?.meta?.name ||
        payload?.viewer_mode ||
        'Repo interactive 3D artifact'
      ),
      stories: Math.max(
        Array.isArray(axisRefs.z) ? axisRefs.z.length : 0,
        storyOptions.length
      ) || '--',
      source_mode: String(sourceMeta.mode || 'artifact_interactive_3d'),
      source_label: String(sourceMeta.label || 'interactive_3d'),
      source_path: String(sourceMeta.resolvedPath || ''),
      loaded_at: String(sourceMeta.loadedAt || payload?.generated_at || payload?.meta?.generated_at || ''),
      generated_at: String(payload?.generated_at || payload?.meta?.generated_at || ''),
      normalization_mode: normalizationMode,
      comparison_availability: String(interactive?.comparison_availability || 'baseline_vs_changed'),
      story_slices: storyOptions.map(option => String(option?.label || option?.value || '').trim()).filter(Boolean),
      baseline_segment_count: baselineSegments.length,
      optimized_segment_count: afterSegments.length,
      load_combination_count_label: String(metaSource.load_combination_count_label || ''),
      load_combination_source_label: String(metaSource.load_combination_source_label || ''),
      load_combination_contract_label: String(metaSource.load_combination_contract_label || ''),
      load_combination_graph_combo_count_label: String(metaSource.load_combination_graph_combo_count_label || ''),
      load_combination_graph_case_count_label: String(metaSource.load_combination_graph_case_count_label || ''),
      load_combination_geometry_bridge_summary_label: String(metaSource.load_combination_geometry_bridge_summary_label || ''),
      load_combination_geometry_bridge_source_label: String(metaSource.load_combination_geometry_bridge_source_label || ''),
      load_combination_geometry_bridge_contract_label: String(metaSource.load_combination_geometry_bridge_contract_label || ''),
      midas_kds_geometry_bridge_summary_line: String(metaSource.midas_kds_geometry_bridge_summary_line || ''),
      load_combination_highlights: Array.isArray(metaSource.load_combination_highlights)
        ? metaSource.load_combination_highlights.filter(Boolean)
        : [],
      load_combination_graph_node_rows: loadCombinationGraphNodeRows,
      load_combination_codecheck_table_by_name: loadCombinationCodecheckTableByName,
      // Material model evidence
      material_family_count: new Set(elements.map(e => e.material_type)).size,
      element_type_distribution: elements.reduce((acc, e) => {
        const t = e.type || 'unknown';
        acc[t] = (acc[t] || 0) + 1;
        return acc;
      }, {}),
      geometry_kind_distribution: elements.reduce((acc, e) => {
        const g = e.geometry_kind || 'unknown';
        acc[g] = (acc[g] || 0) + 1;
        return acc;
      }, {}),
    },
  };
}

export function buildModelFromInteractivePayload(payload, sourceMeta = {}) {
  const interactive = extractInteractivePayload(payload);
  if (!interactive) return null;
  const baselineSegments = Array.isArray(interactive.baseline_segments) ? interactive.baseline_segments.filter(Boolean) : [];
  const afterSegments = Array.isArray(interactive.after_segments) ? interactive.after_segments.filter(Boolean) : [];
  if (!baselineSegments.length && !afterSegments.length) return null;

  const context = { nodeIndexByKey: new Map(), nodes: [], elements: [] };
  baselineSegments.forEach((row, index) => addInteractiveSegment(row, 'baseline', index, context));
  afterSegments.forEach((row, index) => addInteractiveSegment(row, 'optimized', index, context));
  return buildInteractiveModel(payload, sourceMeta, {
    nodes: context.nodes,
    elements: context.elements,
    normalizationMode: 'direct',
  });
}

export async function buildModelFromInteractivePayloadAsync(payload, sourceMeta = {}, {
  processInChunks,
  chunkSize = DEFAULT_NORMALIZATION_CHUNK_SIZE,
} = {}) {
  const interactive = extractInteractivePayload(payload);
  if (!interactive) return null;
  const baselineSegments = Array.isArray(interactive.baseline_segments) ? interactive.baseline_segments.filter(Boolean) : [];
  const afterSegments = Array.isArray(interactive.after_segments) ? interactive.after_segments.filter(Boolean) : [];
  if (!baselineSegments.length && !afterSegments.length) return null;

  const context = { nodeIndexByKey: new Map(), nodes: [], elements: [] };
  const totalSegments = baselineSegments.length + afterSegments.length;
  const chunker = typeof processInChunks === 'function'
    ? processInChunks
    : async (rows, handler) => {
      (Array.isArray(rows) ? rows : []).forEach((row, index) => handler(row, index, index));
    };
  await chunker(baselineSegments, (row, index) => addInteractiveSegment(row, 'baseline', index, context), {
    progressLabel: 'Normalizing interactive_3d segments',
    totalCount: totalSegments,
    forceChunking: totalSegments > chunkSize,
  });
  await chunker(afterSegments, (row, index) => addInteractiveSegment(row, 'optimized', index, context), {
    progressLabel: 'Normalizing interactive_3d segments',
    startOffset: baselineSegments.length,
    totalCount: totalSegments,
    forceChunking: totalSegments > chunkSize,
  });
  return buildInteractiveModel(payload, sourceMeta, {
    nodes: context.nodes,
    elements: context.elements,
    normalizationMode: 'chunked',
  });
}

// ==========================================================
// Native model builder (nodes + elements with material)
// ==========================================================
function normalizeNativeNode(rawNode, index) {
  if (!rawNode || typeof rawNode !== 'object') return null;
  return {
    id: safeNumber(rawNode.id, index),
    x: safeNumber(rawNode.x, rawNode.X),
    y: safeNumber(rawNode.y, rawNode.Y),
    z: safeNumber(rawNode.z, rawNode.Z),
    dx: safeNumber(rawNode.dx, 0),
    dy: safeNumber(rawNode.dy, 0),
    dz: safeNumber(rawNode.dz, 0),
    disp_mag: safeNumber(rawNode.disp_mag, 0),
    stress_vm: safeNumber(rawNode.stress_vm, 0),
    dcr: safeNumber(rawNode.dcr, 0),
    axial: safeNumber(rawNode.axial, 0),
    moment: safeNumber(rawNode.moment, 0),
    shear: safeNumber(rawNode.shear, 0),
  };
}

function normalizeNativeElement(rawElement, index) {
  if (!rawElement || typeof rawElement !== 'object') return null;
  const type = normalizeElementType(rawElement.type || rawElement.element_type || rawElement.etyp);
  const nodeIds = Array.isArray(rawElement.node_ids)
    ? rawElement.node_ids
    : (Array.isArray(rawElement.nodes) ? rawElement.nodes : []);
  const materialType = resolveMaterialType(rawElement);
  const geometryKind = getElementGeometryKind(type);

  return {
    id: String(rawElement.id || rawElement.element_id || index),
    type,
    node_ids: nodeIds.map(n => safeNumber(n, -1)).filter(n => n >= 0),
    section: String(rawElement.section || rawElement.section_name || rawElement.sec || '--'),
    material_type: materialType,
    material_id: String(rawElement.material_id || rawElement.mat_id || ''),
    color: String(rawElement.color || '').trim(),
    dcr: safeNumber(rawElement.dcr, safeNumber(rawElement.ratio, 0)),
    axial: safeNumber(rawElement.axial, 0),
    moment: safeNumber(rawElement.moment, 0),
    shear: safeNumber(rawElement.shear, 0),
    torque: safeNumber(rawElement.torque, 0),
    stress_vm: safeNumber(rawElement.stress_vm, 0),
    geometry_kind: geometryKind,
    // Extended properties for commercial tool parity
    thickness_mm: safeNumber(rawElement.thickness_mm, rawElement.thickness, 0),
    width_mm: safeNumber(rawElement.width_mm, rawElement.width, 0),
    height_mm: safeNumber(rawElement.height_mm, rawElement.height, 0),
    reinforcement_ratio: safeNumber(rawElement.reinforcement_ratio, 0),
    concrete_grade: String(rawElement.concrete_grade || ''),
    steel_grade: String(rawElement.steel_grade || ''),
    story: String(rawElement.story || rawElement.story_band_label || '').trim(),
    zone: String(rawElement.zone || rawElement.zone_label || '').trim(),
    load_case: String(rawElement.load_case || rawElement.lcomb || '').trim(),
    is_optimized: Boolean(rawElement.is_optimized || rawElement.optimized),
    original_id: String(rawElement.original_id || ''),
    family: String(rawElement.family || rawElement.element_family || '').trim(),
    tags: Array.isArray(rawElement.tags) ? rawElement.tags : [],
  };
}

export function buildModelFromNativePayload(payload, sourceMeta = {}) {
  const native = extractNativeModelPayload(payload);
  if (!native) return null;

  const rawNodes = Array.isArray(native.nodes) ? native.nodes : [];
  const rawElements = Array.isArray(native.elements) ? native.elements : [];

  const nodes = rawNodes.map(normalizeNativeNode);
  const elements = rawElements.map(normalizeNativeElement);

  const meta = {
    name: String(native.meta?.name || payload?.meta?.name || 'Native structural model'),
    stories: estimateStoryCount(nodes, native.meta?.axis_refs || {}),
    source_mode: String(sourceMeta.mode || 'native_model'),
    source_label: String(sourceMeta.label || 'native'),
    source_path: String(sourceMeta.resolvedPath || ''),
    loaded_at: String(sourceMeta.loadedAt || payload?.generated_at || ''),
    node_count: nodes.length,
    element_count: elements.length,
    material_family_count: new Set(elements.map(e => e.material_type)).size,
    element_type_distribution: elements.reduce((acc, e) => {
      const t = e.type || 'unknown';
      acc[t] = (acc[t] || 0) + 1;
      return acc;
    }, {}),
    geometry_kind_distribution: elements.reduce((acc, e) => {
      const g = e.geometry_kind || 'unknown';
      acc[g] = (acc[g] || 0) + 1;
      return acc;
    }, {}),
    normalization_mode: 'native',
    material_models: native.material_models || payload?.material_models || {},
  };

  return { nodes, elements, meta };
}

export async function buildModelFromNativePayloadAsync(payload, sourceMeta = {}, {
  processInChunks,
  chunkSize = DEFAULT_NORMALIZATION_CHUNK_SIZE,
} = {}) {
  const native = extractNativeModelPayload(payload);
  if (!native) return null;

  const rawNodes = Array.isArray(native.nodes) ? native.nodes : [];
  const rawElements = Array.isArray(native.elements) ? native.elements : [];

  const chunker = typeof processInChunks === 'function'
    ? processInChunks
    : async (rows, handler) => {
      (Array.isArray(rows) ? rows : []).forEach((row, index) => handler(row, index, index));
    };

  const nodes = [];
  await chunker(rawNodes, (row, index) => {
    const node = normalizeNativeNode(row, index);
    if (node) nodes.push(node);
  }, {
    progressLabel: 'Normalizing native nodes',
    totalCount: rawNodes.length,
    forceChunking: rawNodes.length > chunkSize,
  });

  const elements = [];
  await chunker(rawElements, (row, index) => {
    const elem = normalizeNativeElement(row, index);
    if (elem) elements.push(elem);
  }, {
    progressLabel: 'Normalizing native elements',
    totalCount: rawElements.length,
    forceChunking: rawElements.length > chunkSize,
  });

  const meta = {
    name: String(native.meta?.name || payload?.meta?.name || 'Native structural model'),
    stories: estimateStoryCount(nodes, native.meta?.axis_refs || {}),
    source_mode: String(sourceMeta.mode || 'native_model'),
    source_label: String(sourceMeta.label || 'native'),
    source_path: String(sourceMeta.resolvedPath || ''),
    loaded_at: String(sourceMeta.loadedAt || payload?.generated_at || ''),
    node_count: nodes.length,
    element_count: elements.length,
    material_family_count: new Set(elements.map(e => e.material_type)).size,
    element_type_distribution: elements.reduce((acc, e) => {
      const t = e.type || 'unknown';
      acc[t] = (acc[t] || 0) + 1;
      return acc;
    }, {}),
    geometry_kind_distribution: elements.reduce((acc, e) => {
      const g = e.geometry_kind || 'unknown';
      acc[g] = (acc[g] || 0) + 1;
      return acc;
    }, {}),
    normalization_mode: 'native_chunked',
    material_models: native.material_models || payload?.material_models || {},
  };

  return { nodes, elements, meta };
}
