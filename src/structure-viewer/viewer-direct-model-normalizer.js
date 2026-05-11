import {
  estimateStoryCount,
  extractModelPayload,
  normalizeElementType,
  rgbArrayToHex,
  safeNumber,
} from './viewer-model-normalizer.js';

const DEFAULT_NORMALIZATION_CHUNK_SIZE = 1200;

function normalizeSelectionValue(value) {
  const text = String(value ?? '').trim();
  return text || '';
}

function buildReviewRowIsolationToken(data) {
  return [
    normalizeSelectionValue(data?.review_case_id) || '--',
    normalizeSelectionValue(data?.review_row_label) || '--',
    normalizeSelectionValue(data?.member_id) || '--',
    normalizeSelectionValue(data?.target_element_id ?? data?.id) || '--',
  ].join('::');
}

export function buildSectionFamilySummary(sectionUsageRows) {
  const summaryByFamily = new Map();
  (Array.isArray(sectionUsageRows) ? sectionUsageRows : []).forEach(row => {
    const family = normalizeSelectionValue(row?.inferred_family) || 'unclassified';
    const shape = normalizeSelectionValue(row?.inferred_shape) || '--';
    const next = summaryByFamily.get(family) || {
      family,
      shapeMix: new Set(),
      sectionCount: 0,
      usageCount: 0,
      representativeSectionName: '',
    };
    next.sectionCount += 1;
    next.usageCount += safeNumber(row?.usage_count, 0);
    if (shape && shape !== '--') next.shapeMix.add(shape);
    if (!next.representativeSectionName) next.representativeSectionName = normalizeSelectionValue(row?.name);
    summaryByFamily.set(family, next);
  });
  return [...summaryByFamily.values()]
    .map(row => ({
      family: row.family,
      section_count: row.sectionCount,
      usage_count: row.usageCount,
      shape_mix_label: [...row.shapeMix].sort().join(', ') || '--',
      representative_section_name: row.representativeSectionName || '--',
    }))
    .sort((a, b) => b.usage_count - a.usage_count || b.section_count - a.section_count || a.family.localeCompare(b.family))
    .slice(0, 12);
}

export function buildGroupSummary(groupRows) {
  return (Array.isArray(groupRows) ? groupRows : [])
    .map(row => ({
      group_name: normalizeSelectionValue(row?.name) || '--',
      element_count: safeNumber(row?.element_count, 0),
      node_count: safeNumber(row?.node_count, 0),
      physical_line_span: safeNumber(row?.physical_line_span, 0),
      representative_element_id: Array.isArray(row?.element_ids_head) && row.element_ids_head.length ? row.element_ids_head[0] : null,
    }))
    .sort((a, b) => b.element_count - a.element_count || b.node_count - a.node_count || a.group_name.localeCompare(b.group_name))
    .slice(0, 12);
}

export function buildSectionCatalogSummary(sectionRows, sectionUsageRows) {
  const usageById = new Map(
    (Array.isArray(sectionUsageRows) ? sectionUsageRows : [])
      .map(row => [normalizeSelectionValue(row?.section_id), row])
      .filter(([sectionId]) => Boolean(sectionId))
  );
  return (Array.isArray(sectionRows) ? sectionRows : [])
    .map(row => {
      const sectionId = normalizeSelectionValue(row?.id);
      if (!sectionId) return null;
      const rawTokens = (Array.isArray(row?.raw_tokens) ? row.raw_tokens : [])
        .map(value => normalizeSelectionValue(value))
        .filter(Boolean);
      const usageRow = usageById.get(sectionId) || {};
      return {
        section_id: sectionId,
        section_name: normalizeSelectionValue(row?.section_name || row?.label || row?.name),
        display_label: normalizeSelectionValue(rawTokens[0] || row?.section_name || row?.label || row?.name || sectionId),
        raw_tokens_head: rawTokens.slice(0, 4),
        inferred_family: normalizeSelectionValue(usageRow?.inferred_family),
        inferred_shape: normalizeSelectionValue(usageRow?.inferred_shape),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.display_label.localeCompare(b.display_label) || a.section_id.localeCompare(b.section_id));
}

export function buildReviewRowSummary(bridgeRows) {
  return (Array.isArray(bridgeRows) ? bridgeRows : [])
    .map(row => ({
      review_case_id: normalizeSelectionValue(row?.review_case_id) || '--',
      member_id: normalizeSelectionValue(row?.baseline_focus_member_id || row?.review_member_id) || '',
      target_element_id: normalizeSelectionValue(row?.full_crosswalk_target_element_id),
      review_row_label: normalizeSelectionValue(row?.row_provenance_top_row_label) || '--',
      review_summary_label: normalizeSelectionValue(row?.row_provenance_summary_label) || '--',
      combination_names: Array.isArray(row?.full_crosswalk_load_combination_names) ? row.full_crosswalk_load_combination_names.slice(0, 6) : [],
      group_names: Array.isArray(row?.full_crosswalk_member_groups) ? row.full_crosswalk_member_groups.slice(0, 6) : [],
      isolation_token: buildReviewRowIsolationToken({
        review_case_id: row?.review_case_id,
        review_row_label: row?.row_provenance_top_row_label,
        member_id: row?.baseline_focus_member_id || row?.review_member_id,
        target_element_id: row?.full_crosswalk_target_element_id,
      }),
    }))
    .slice(0, 12);
}

export function extractLoadCaseInventory(modelPayload, metadata) {
  const labels = [];
  const pushLabel = value => {
    const label = normalizeSelectionValue(value);
    if (label && !labels.includes(label)) labels.push(label);
  };
  const loadPatternLibrary = metadata?.load_pattern_library && typeof metadata.load_pattern_library === 'object'
    ? metadata.load_pattern_library
    : {};
  const semanticRows = Array.isArray(loadPatternLibrary.case_semantic_rows) ? loadPatternLibrary.case_semantic_rows : [];
  semanticRows.forEach(row => pushLabel(row?.label || row?.case_name || row?.case_id || row?.pattern_id));
  const patternRows = Array.isArray(loadPatternLibrary.pattern_summary?.patterns) ? loadPatternLibrary.pattern_summary.patterns : [];
  patternRows.forEach(row => pushLabel(row?.label || row?.case_name || row?.pattern_id));
  const loads = Array.isArray(modelPayload?.loads) ? modelPayload.loads : [];
  loads.forEach(row => pushLabel(row?.case_name || row?.load_case_name || row?.name || row?.case_id));
  return labels;
}

export function extractLoadCombinationInventory(modelPayload, metadata) {
  const rows = [];
  const pushRow = row => {
    const name = normalizeSelectionValue(row?.name || row?.combination_name || row?.id);
    if (!name || rows.some(item => item.name === name)) return;
    const entryRows = Array.isArray(row?.entry_rows)
      ? row.entry_rows
      : Array.isArray(row?.entries)
        ? row.entries
        : [];
    const factorMap = row?.factor_map && typeof row.factor_map === 'object'
      ? row.factor_map
      : row?.expanded_factor_map && typeof row.expanded_factor_map === 'object'
        ? row.expanded_factor_map
        : {};
    rows.push({
      name,
      combination_type: normalizeSelectionValue(row?.combination_type) || 'GEN',
      limit_state: normalizeSelectionValue(row?.limit_state) || 'ACTIVE',
      expression: normalizeSelectionValue(row?.expression) || 'expression n/a',
      entry_count: safeNumber(row?.entry_count, entryRows.length),
      factor_map: { ...factorMap },
      referenced_combinations: Array.isArray(row?.referenced_combinations) ? row.referenced_combinations.filter(Boolean) : [],
      referenced_leaf_cases: Array.isArray(row?.referenced_leaf_cases) ? row.referenced_leaf_cases.filter(Boolean) : [],
      entry_rows: entryRows
        .filter(entry => entry && typeof entry === 'object')
        .map(entry => ({
          reference_kind: normalizeSelectionValue(entry?.reference_kind).toUpperCase() || 'ST',
          reference_name: normalizeSelectionValue(entry?.reference_name),
          factor: safeNumber(entry?.factor, 0),
        }))
        .filter(entry => entry.reference_name),
    });
  };
  const loadRows = Array.isArray(modelPayload?.loads?.load_combinations) ? modelPayload.loads.load_combinations : [];
  loadRows.forEach(pushRow);
  const editorSeed = metadata?.load_combination_editor_seed && typeof metadata.load_combination_editor_seed === 'object'
    ? metadata.load_combination_editor_seed
    : {};
  const seedRows = Array.isArray(editorSeed.combination_nodes) ? editorSeed.combination_nodes : [];
  seedRows.forEach(pushRow);
  return rows;
}

export function buildRealDrawingAssetRegistry(rootMeta) {
  return (Array.isArray(rootMeta?.real_drawing_asset_registry) ? rootMeta.real_drawing_asset_registry : [])
    .map(row => ({
      asset_ref: normalizeSelectionValue(row?.asset_ref),
      file_type: normalizeSelectionValue(row?.file_type),
      route: normalizeSelectionValue(row?.route),
      status: normalizeSelectionValue(row?.status),
      solver_exact: Boolean(row?.solver_exact),
      geometry_mode: normalizeSelectionValue(row?.geometry_mode),
      geometry_available: Boolean(row?.geometry_available),
      segment_count: safeNumber(row?.segment_count, 0),
      model_asset_count: safeNumber(row?.model_asset_count, 0),
      warning_label: normalizeSelectionValue(row?.warning_label),
      quality_flags: Array.isArray(row?.quality_flags)
        ? row.quality_flags.map(value => normalizeSelectionValue(value)).filter(Boolean)
        : [],
      quality_notice: normalizeSelectionValue(row?.quality_notice),
      node_count: safeNumber(row?.node_count, 0),
      element_count: safeNumber(row?.element_count, 0),
      renderable_segment_count: safeNumber(row?.renderable_segment_count, row?.segment_count ?? 0),
      lod_evidence_status: normalizeSelectionValue(row?.lod_evidence_status),
      full_detail_segment_count: safeNumber(row?.full_detail_segment_count, 0),
      viewer_sample_segment_count: safeNumber(row?.viewer_sample_segment_count, 0),
      lod_sample_ratio: safeNumber(row?.lod_sample_ratio, 0),
    }))
    .filter(row => row.asset_ref)
    .slice(0, 128);
}

export function buildRealDrawingRegistrySummary(rootMeta, assetRegistry) {
  const summary = rootMeta?.real_drawing_registry_summary && typeof rootMeta.real_drawing_registry_summary === 'object'
    ? rootMeta.real_drawing_registry_summary
    : {};
  return {
    asset_count: safeNumber(summary.asset_count, rootMeta?.real_drawing_asset_count ?? assetRegistry.length),
    renderable_asset_count: safeNumber(summary.renderable_asset_count, rootMeta?.real_drawing_renderable_asset_count ?? 0),
    solver_exact_asset_count: safeNumber(summary.solver_exact_asset_count, rootMeta?.real_drawing_solver_exact_asset_count ?? 0),
    proxy_or_preview_asset_count: safeNumber(summary.proxy_or_preview_asset_count, rootMeta?.real_drawing_proxy_or_preview_asset_count ?? 0),
    route_counts: summary.route_counts && typeof summary.route_counts === 'object' ? { ...summary.route_counts } : {},
    status_counts: summary.status_counts && typeof summary.status_counts === 'object' ? { ...summary.status_counts } : {},
    quality_flag_counts: summary.quality_flag_counts && typeof summary.quality_flag_counts === 'object'
      ? { ...summary.quality_flag_counts }
      : {},
  };
}

function compactStringList(value, limit = 8) {
  return (Array.isArray(value) ? value : [])
    .map(item => normalizeSelectionValue(item))
    .filter(Boolean)
    .slice(0, limit);
}

function normalizeRealDrawingPromotionItem(row) {
  return {
    promotion_id: normalizeSelectionValue(row?.promotion_id),
    asset_ref: normalizeSelectionValue(row?.asset_ref),
    promotion_family: normalizeSelectionValue(row?.promotion_family),
    effort_label: normalizeSelectionValue(row?.effort_label),
    quality_tier: normalizeSelectionValue(row?.quality_tier),
    file_type: normalizeSelectionValue(row?.file_type),
    route: normalizeSelectionValue(row?.route),
    status: normalizeSelectionValue(row?.status),
    priority_rank: safeNumber(row?.priority_rank, 0),
    expected_solver_exact_delta: safeNumber(row?.expected_solver_exact_delta, 0),
    node_count: safeNumber(row?.node_count, 0),
    element_count: safeNumber(row?.element_count, 0),
    segment_count: safeNumber(row?.segment_count, 0),
    renderable_segment_count: safeNumber(row?.renderable_segment_count, 0),
    quality_flags: compactStringList(row?.quality_flags),
    closure_evidence_required: compactStringList(row?.closure_evidence_required),
    recommended_action: normalizeSelectionValue(row?.recommended_action),
    blocker_family: normalizeSelectionValue(row?.blocker_family),
    blocker_reason_code: normalizeSelectionValue(row?.blocker_reason_code),
    reconstruction_plan_status: normalizeSelectionValue(row?.reconstruction_plan_status),
    commercial_claim_blocked: Boolean(row?.commercial_claim_blocked),
    edge_coverage_ratio: safeNumber(row?.edge_coverage_ratio, 0),
  };
}

export function buildRealDrawingSolverExactPromotionQueue(rootMeta) {
  const queue = rootMeta?.real_drawing_solver_exact_promotion_queue && typeof rootMeta.real_drawing_solver_exact_promotion_queue === 'object'
    ? rootMeta.real_drawing_solver_exact_promotion_queue
    : {};
  const summary = queue.summary && typeof queue.summary === 'object' ? queue.summary : {};
  const plannedUnlockBatch = (Array.isArray(queue.planned_unlock_batch) ? queue.planned_unlock_batch : [])
    .map(normalizeRealDrawingPromotionItem)
    .filter(row => row.asset_ref)
    .slice(0, 32);
  const openPromotionItemsSource = Array.isArray(queue.open_promotion_items)
    ? queue.open_promotion_items
    : Array.isArray(queue.promotion_items)
      ? queue.promotion_items
      : [];
  const openPromotionItems = openPromotionItemsSource
    .map(normalizeRealDrawingPromotionItem)
    .filter(row => row.asset_ref)
    .slice(0, 32);
  if (!Object.keys(queue).length && !plannedUnlockBatch.length && !openPromotionItems.length) return {};
  return {
    schema_version: normalizeSelectionValue(queue.schema_version),
    contract_pass: Boolean(queue.contract_pass),
    reason_code: normalizeSelectionValue(queue.reason_code),
    quality_gate_reason_code: normalizeSelectionValue(queue.quality_gate_reason_code),
    structure_viewer_href: normalizeSelectionValue(queue.structure_viewer_href),
    recommended_claim: normalizeSelectionValue(queue.recommended_claim),
    summary: {
      current_solver_exact_asset_count: safeNumber(summary.current_solver_exact_asset_count, 0),
      target_solver_exact_asset_count: safeNumber(summary.target_solver_exact_asset_count, 0),
      required_solver_exact_delta: safeNumber(summary.required_solver_exact_delta, 0),
      planned_unlock_batch_count: safeNumber(summary.planned_unlock_batch_count, plannedUnlockBatch.length),
      planned_unlock_batch_expected_delta: safeNumber(summary.planned_unlock_batch_expected_delta, 0),
      planned_solver_exact_asset_count_after_unlock_batch: safeNumber(
        summary.planned_solver_exact_asset_count_after_unlock_batch,
        0
      ),
      promotion_candidate_count: safeNumber(summary.promotion_candidate_count, plannedUnlockBatch.length),
      promotion_delta_available: safeNumber(summary.promotion_delta_available, 0),
      sufficient_unlock_batch_for_target: Boolean(summary.sufficient_unlock_batch_for_target),
      family_counts: summary.family_counts && typeof summary.family_counts === 'object' ? { ...summary.family_counts } : {},
      effort_counts: summary.effort_counts && typeof summary.effort_counts === 'object' ? { ...summary.effort_counts } : {},
    },
    planned_unlock_batch: plannedUnlockBatch,
    open_promotion_items: openPromotionItems,
  };
}

export function buildDirectModelMeta(rootPayload, modelPayload, sourceMeta = {}) {
  const metadata = modelPayload?.metadata && typeof modelPayload.metadata === 'object' ? modelPayload.metadata : {};
  const rootMeta = rootPayload?.meta && typeof rootPayload.meta === 'object' ? rootPayload.meta : {};
  const sourceInfo = rootPayload?.source && typeof rootPayload.source === 'object' ? rootPayload.source : {};
  const axisBridge = metadata.kds_geometry_bridge && typeof metadata.kds_geometry_bridge === 'object' ? metadata.kds_geometry_bridge : {};
  const axisRefs = axisBridge.axis_refs && typeof axisBridge.axis_refs === 'object' ? axisBridge.axis_refs : {};
  const sectionLibrary = metadata.section_library && typeof metadata.section_library === 'object' ? metadata.section_library : {};
  const sectionSummary = sectionLibrary.summary && typeof sectionLibrary.summary === 'object' ? sectionLibrary.summary : {};
  const loadPatternLibrary = metadata.load_pattern_library && typeof metadata.load_pattern_library === 'object' ? metadata.load_pattern_library : {};
  const loadPatternSummary = loadPatternLibrary.summary && typeof loadPatternLibrary.summary === 'object'
    ? loadPatternLibrary.summary
    : (loadPatternLibrary.pattern_summary && typeof loadPatternLibrary.pattern_summary === 'object' ? loadPatternLibrary.pattern_summary : {});
  const storySlices = Array.isArray(axisRefs.z)
    ? axisRefs.z.map(row => normalizeSelectionValue(row?.label || row?.name || row?.axis_label || row?.id)).filter(Boolean)
    : [];
  const reviewSummary = axisBridge.summary && typeof axisBridge.summary === 'object' ? axisBridge.summary : {};
  const sectionUsageRows = Array.isArray(sectionLibrary.usage_summary) ? sectionLibrary.usage_summary : [];
  const sectionCatalogSummary = buildSectionCatalogSummary(modelPayload?.sections, sectionUsageRows);
  const bridgeRows = Array.isArray(axisBridge.bridge_rows) ? axisBridge.bridge_rows : [];
  const groupRows = Array.isArray(metadata.groups) ? metadata.groups : [];
  const realDrawingAssetRegistry = buildRealDrawingAssetRegistry(rootMeta);
  const realDrawingRegistrySummary = buildRealDrawingRegistrySummary(rootMeta, realDrawingAssetRegistry);
  const realDrawingSolverExactPromotionQueue = buildRealDrawingSolverExactPromotionQueue(rootMeta);
  const sectionCount = safeNumber(sectionSummary.section_row_count, Array.isArray(modelPayload?.sections) ? modelPayload.sections.length : 0);
  const usedSectionCount = safeNumber(sectionSummary.used_section_count, 0);
  const axisLabelCount =
    (Array.isArray(axisRefs.x) ? axisRefs.x.length : 0) +
    (Array.isArray(axisRefs.y) ? axisRefs.y.length : 0) +
    (Array.isArray(axisRefs.z) ? axisRefs.z.length : 0);
  const structureTypeLabel = normalizeSelectionValue(
    Array.isArray(metadata.structure_type) && metadata.structure_type[0]?.raw
      ? metadata.structure_type[0].raw
      : (rootPayload?.source || rootPayload?.parser || 'MIDAS parsed model')
  );
  const lengthUnitsLabel = normalizeSelectionValue(
    Array.isArray(metadata.length_units) && metadata.length_units[0]?.raw ? metadata.length_units[0].raw : ''
  );
  return {
    name: String(rootPayload?.run_id || rootPayload?.source || sourceMeta.label || 'MIDAS parsed model'),
    stories: estimateStoryCount(modelPayload?.nodes, axisRefs) || '--',
    story_slices: storySlices,
    load_case_inventory: extractLoadCaseInventory(modelPayload, metadata),
    load_combination_inventory: extractLoadCombinationInventory(modelPayload, metadata),
    source_mode: String(sourceMeta.mode || 'direct_payload'),
    source_label: String(sourceMeta.label || sourceInfo.path || rootPayload?.source || 'MIDAS parsed model'),
    source_path: String(sourceMeta.resolvedPath || sourceInfo.path || ''),
    source_artifact_sha256: String(sourceInfo.sha256 || ''),
    source_artifact_size_bytes: safeNumber(sourceInfo.size_bytes, 0),
    source_artifact_format: String(sourceInfo.format || ''),
    source_artifact_family: String(sourceInfo.source_family || ''),
    loaded_at: String(sourceMeta.loadedAt || ''),
    generated_at: String(rootPayload?.generated_at || ''),
    parser_label: String(rootPayload?.parser || ''),
    structure_type_label: structureTypeLabel || '--',
    length_units_label: lengthUnitsLabel || '--',
    group_count: Array.isArray(metadata.groups) ? metadata.groups.length : 0,
    member_count: Array.isArray(metadata.members) ? metadata.members.length : 0,
    section_count: sectionCount,
    used_section_count: usedSectionCount,
    geometry_bridge_review_count: safeNumber(reviewSummary.review_id_count, 0),
    geometry_bridge_mapped_review_count: safeNumber(reviewSummary.mapped_review_id_count, 0),
    geometry_bridge_full_member_crosswalk_count: safeNumber(reviewSummary.full_member_crosswalk_count, 0),
    load_pattern_count: safeNumber(
      loadPatternSummary.pattern_count,
      Array.isArray(loadPatternLibrary.case_semantic_rows) ? loadPatternLibrary.case_semantic_rows.length : 0
    ),
    load_pattern_primitive_count: safeNumber(loadPatternSummary.primitive_count, 0),
    axis_label_count: axisLabelCount,
    axis_ref_source_mode: String(axisBridge.axis_ref_source_mode || 'none'),
    axis_ref_note: String(axisBridge.axis_ref_note || ''),
    section_catalog_summary: sectionCatalogSummary,
    section_family_summary: buildSectionFamilySummary(sectionUsageRows),
    group_summary: buildGroupSummary(groupRows),
    review_row_summary: buildReviewRowSummary(bridgeRows),
    real_drawing_asset_count: realDrawingRegistrySummary.asset_count,
    real_drawing_renderable_asset_count: realDrawingRegistrySummary.renderable_asset_count,
    real_drawing_solver_exact_asset_count: realDrawingRegistrySummary.solver_exact_asset_count,
    real_drawing_proxy_or_preview_asset_count: realDrawingRegistrySummary.proxy_or_preview_asset_count,
    real_drawing_registry_summary: realDrawingRegistrySummary,
    real_drawing_asset_registry: realDrawingAssetRegistry,
    real_drawing_solver_exact_promotion_queue: realDrawingSolverExactPromotionQueue,
  };
}

function buildDirectModelLookupContext(modelPayload) {
  const metadata = modelPayload.metadata && typeof modelPayload.metadata === 'object' ? modelPayload.metadata : {};
  const sectionRows = Array.isArray(modelPayload.sections) ? modelPayload.sections : [];
  const sectionById = new Map(sectionRows.map(row => [String(row?.id), String(row?.name || row?.label || row?.section_name || `Section ${row?.id ?? '--'}`)]));
  const sectionUsageById = new Map(
    (Array.isArray(metadata.section_library?.usage_summary) ? metadata.section_library.usage_summary : [])
      .map(row => [String(row?.section_id), row])
  );
  const sectionColorById = new Map(
    (Array.isArray(metadata.section_colors) ? metadata.section_colors : [])
      .map(row => [String(row?.section_id), rgbArrayToHex(row?.fill_rgb || row?.wire_rgb)])
      .filter(([, hex]) => Boolean(hex))
  );
  const memberByElementId = new Map();
  (Array.isArray(metadata.members) ? metadata.members : []).forEach(member => {
    const memberId = normalizeSelectionValue(member?.id);
    const elementIds = Array.isArray(member?.element_ids) ? member.element_ids : [];
    elementIds.forEach(elementId => memberByElementId.set(String(elementId), memberId));
  });
  const groupsByElementId = new Map();
  (Array.isArray(metadata.groups) ? metadata.groups : []).forEach(group => {
    const groupName = normalizeSelectionValue(group?.name);
    if (!groupName) return;
    const elementIds = Array.isArray(group?.element_ids) ? group.element_ids : [];
    elementIds.forEach(elementId => {
      const key = String(elementId);
      const current = groupsByElementId.get(key) || [];
      if (!current.includes(groupName)) current.push(groupName);
      groupsByElementId.set(key, current);
    });
  });
  const reviewByMemberId = new Map();
  const reviewByElementId = new Map();
  (Array.isArray(metadata.kds_geometry_bridge?.bridge_rows) ? metadata.kds_geometry_bridge.bridge_rows : []).forEach(row => {
    const memberId = normalizeSelectionValue(row?.baseline_focus_member_id || row?.review_member_id);
    if (!memberId || reviewByMemberId.has(memberId)) return;
    reviewByMemberId.set(memberId, row);
  });
  (Array.isArray(metadata.kds_geometry_bridge?.bridge_rows) ? metadata.kds_geometry_bridge.bridge_rows : []).forEach(row => {
    const elementId = normalizeSelectionValue(row?.full_crosswalk_target_element_id);
    if (!elementId || reviewByElementId.has(elementId)) return;
    reviewByElementId.set(elementId, row);
  });
  return { groupsByElementId, memberByElementId, reviewByElementId, reviewByMemberId, sectionById, sectionColorById, sectionUsageById };
}

function sanitizeDirectNode(node, idx) {
  return {
    id: node?.id ?? idx,
    x: safeNumber(node?.x, 0),
    y: safeNumber(node?.y, 0),
    z: safeNumber(node?.z, 0),
    dx: safeNumber(node?.dx, 0),
    dy: safeNumber(node?.dy, 0),
    dz: safeNumber(node?.dz, 0),
    disp_mag: safeNumber(node?.disp_mag, 0),
    stress_vm: safeNumber(node?.stress_vm, 0),
    dcr: safeNumber(node?.dcr, 0),
    axial: safeNumber(node?.axial, 0),
    moment: safeNumber(node?.moment, 0),
    shear: safeNumber(node?.shear, 0),
  };
}

function sanitizeDirectElement(element, idx, context) {
  const memberId = normalizeSelectionValue(element?.member_id) || context.memberByElementId.get(String(element?.id ?? idx)) || '';
  const reviewRow = context.reviewByMemberId.get(memberId) || context.reviewByElementId.get(normalizeSelectionValue(element?.id ?? idx)) || null;
  const groupNames = context.groupsByElementId.get(String(element?.id ?? idx)) || [];
  return {
    ...element,
    id: element?.id ?? idx,
    type: normalizeElementType(element?.family || element?.type),
    node_ids: Array.isArray(element?.node_ids) ? element.node_ids : [],
    member_id: memberId,
    section: String(element?.section || context.sectionById.get(String(element?.section_id)) || '--'),
    section_family: normalizeSelectionValue(context.sectionUsageById.get(String(element?.section_id))?.inferred_family) || '--',
    section_shape: normalizeSelectionValue(context.sectionUsageById.get(String(element?.section_id))?.inferred_shape) || '--',
    group_names: groupNames,
    group_label: groupNames.join(', ') || '--',
    review_case_id: normalizeSelectionValue(reviewRow?.review_case_id) || '--',
    review_row_label: normalizeSelectionValue(reviewRow?.row_provenance_top_row_label) || '--',
    review_summary_label: normalizeSelectionValue(reviewRow?.row_provenance_summary_label) || '--',
    review_combination_label: Array.isArray(reviewRow?.full_crosswalk_load_combination_names)
      ? reviewRow.full_crosswalk_load_combination_names.slice(0, 4).join(', ')
      : '--',
    dcr: safeNumber(element?.dcr, safeNumber(element?.max_dcr_after, safeNumber(element?.max_dcr_before, 0))),
    axial: safeNumber(element?.axial, 0),
    moment: safeNumber(element?.moment, 0),
    shear: safeNumber(element?.shear, 0),
    color: String(element?.color || context.sectionColorById.get(String(element?.section_id)) || '').trim(),
  };
}

function buildSanitizedDirectModel(payload, sourceMeta, nodes, elements, normalizationMode) {
  const extracted = extractModelPayload(payload);
  const modelPayload = extracted?.model || {};
  const rootPayload = extracted?.root || payload || {};
  return {
    nodes,
    elements,
    meta: {
      ...(rootPayload.meta && typeof rootPayload.meta === 'object' ? rootPayload.meta : {}),
      ...buildDirectModelMeta(rootPayload, modelPayload, sourceMeta),
      normalization_mode: normalizationMode,
    },
  };
}

export function sanitizeModelPayload(payload, sourceMeta = {}) {
  const extracted = extractModelPayload(payload);
  const modelPayload = extracted?.model || {};
  const context = buildDirectModelLookupContext(modelPayload);
  const nodes = (modelPayload.nodes || []).map(sanitizeDirectNode);
  const elements = (modelPayload.elements || []).map((element, idx) => sanitizeDirectElement(element, idx, context));
  return buildSanitizedDirectModel(payload, sourceMeta, nodes, elements, 'direct');
}

export async function sanitizeModelPayloadAsync(payload, sourceMeta = {}, {
  processInChunks,
  chunkSize = DEFAULT_NORMALIZATION_CHUNK_SIZE,
} = {}) {
  const extracted = extractModelPayload(payload);
  const modelPayload = extracted?.model || {};
  const context = buildDirectModelLookupContext(modelPayload);
  const chunker = typeof processInChunks === 'function'
    ? processInChunks
    : async (rows, handler) => {
      (Array.isArray(rows) ? rows : []).forEach((row, index) => handler(row, index, index));
    };
  const mapRows = async (rows, mapper, options = {}) => {
    const out = [];
    await chunker(rows, (item, index, globalIndex) => {
      const mapped = mapper(item, index, globalIndex);
      if (mapped !== null && mapped !== undefined) out.push(mapped);
    }, { chunkSize, ...options });
    return out;
  };
  const nodes = await mapRows(modelPayload.nodes || [], sanitizeDirectNode, { progressLabel: 'Normalizing nodes' });
  const elements = await mapRows(modelPayload.elements || [], (element, idx) => sanitizeDirectElement(element, idx, context), {
    progressLabel: 'Normalizing elements',
  });
  return buildSanitizedDirectModel(payload, sourceMeta, nodes, elements, 'chunked');
}
