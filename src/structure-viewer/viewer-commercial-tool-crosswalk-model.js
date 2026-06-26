export const STRUCTURE_VIEWER_COMMERCIAL_TOOL_CROSSWALK_SCHEMA_VERSION = 'structure-viewer-commercial-tool-crosswalk.v1';

const PROFILE_LABELS = {
  midas: 'MIDAS',
  etabs: 'ETABS/SAP2000',
  sap2000: 'ETABS/SAP2000',
  rfem: 'RFEM',
  tekla: 'Tekla',
  revit: 'Revit',
  ifc: 'IFC',
  generic: 'Generic CSV/JSON',
};

const CSV_MAPPER_PRESETS = {
  generic: {
    profile: 'generic',
    label: 'Generic CSV/JSON',
    canonicalFields: {
      member_id: ['member_id', 'id'],
      section: ['section', 'section_name'],
      dcr_after: ['dcr', 'dcr_after', 'utilization'],
      story: ['story', 'level'],
      mode: ['mode', 'mode_id', 'mode_number'],
      receipt_path: ['receipt_path', 'path'],
    },
  },
  midas: {
    profile: 'midas',
    label: 'MIDAS',
    canonicalFields: {
      member_id: ['member_id', 'element_id', 'elem', 'member'],
      section: ['section', 'section_name', 'property'],
      dcr_after: ['dcr', 'ratio', 'utilization'],
      story: ['story', 'floor', 'level'],
      mode: ['mode', 'mode_id', 'mode_number'],
      load_combo: ['load_combo', 'combination', 'lc'],
    },
  },
  etabs: {
    profile: 'etabs',
    label: 'ETABS/SAP2000',
    canonicalFields: {
      member_id: ['frame', 'frame_id', 'object_id', 'unique_name', 'member_id'],
      section: ['frame_section', 'section', 'property'],
      dcr_after: ['dcr', 'ratio', 'pm_ratio', 'utilization'],
      story: ['story', 'story_name', 'level'],
      mode: ['mode', 'mode_id', 'mode_number', 'modal_case'],
      load_combo: ['output_case', 'case', 'combo', 'load_combo'],
    },
  },
  sap2000: {
    profile: 'sap2000',
    label: 'ETABS/SAP2000',
    canonicalFields: {
      member_id: ['frame', 'frame_id', 'object_id', 'unique_name', 'member_id'],
      section: ['frame_section', 'section', 'property'],
      dcr_after: ['dcr', 'ratio', 'pm_ratio', 'utilization'],
      story: ['story', 'level'],
      mode: ['mode', 'mode_id', 'mode_number', 'modal_case'],
      load_combo: ['output_case', 'case', 'combo', 'load_combo'],
    },
  },
  rfem: {
    profile: 'rfem',
    label: 'RFEM',
    canonicalFields: {
      member_id: ['member_no', 'member_id', 'object_no', 'no'],
      section: ['cross_section', 'section', 'profile'],
      dcr_after: ['design_ratio', 'utilization', 'ratio', 'dcr'],
      story: ['story', 'level', 'location'],
      mode: ['mode', 'mode_id', 'mode_number', 'eigenmode'],
      load_combo: ['loading', 'load_combination', 'combination'],
    },
  },
  tekla: {
    profile: 'tekla',
    label: 'Tekla',
    canonicalFields: {
      member_id: ['guid', 'assembly_guid', 'part_guid', 'member_id'],
      section: ['profile', 'profile_name', 'section'],
      material: ['material', 'material_name', 'grade'],
      story: ['phase', 'floor', 'level'],
      mode: ['mode', 'mode_id', 'mode_number'],
      receipt_path: ['model_path', 'receipt_path'],
    },
  },
  revit: {
    profile: 'revit',
    label: 'Revit',
    canonicalFields: {
      member_id: ['unique_id', 'element_id', 'guid', 'global_id', 'member_id'],
      section: ['family_type', 'type_name', 'section', 'profile'],
      material: ['structural_material', 'material', 'material_name'],
      story: ['level', 'base_level', 'reference_level'],
      mode: ['mode', 'mode_id', 'mode_number'],
      receipt_path: ['source_path', 'receipt_path'],
    },
  },
  ifc: {
    profile: 'ifc',
    label: 'IFC',
    canonicalFields: {
      member_id: ['global_id', 'globalid', 'guid', 'member_id'],
      section: ['profile', 'profile_name', 'section'],
      material: ['material', 'material_name'],
      story: ['building_storey', 'storey', 'level'],
      mode: ['mode', 'mode_id', 'mode_number'],
      receipt_path: ['ifc_path', 'receipt_path'],
    },
  },
};

function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeToken(value) {
  return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

function safeNumber(value, fallback = NaN) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function firstText(...values) {
  return values.map(normalizeText).find(Boolean) || '';
}

function memberIdFromElement(element = {}) {
  return firstText(element.member_id, element.case_id, element.id, element.label);
}

function sectionFromElement(element = {}) {
  return firstText(element.section, element.section_name, element.after_section, element.optimized_section, element.section_after);
}

function dcrFromElement(element = {}) {
  return safeNumber(element.max_dcr_after, safeNumber(element.dcr_after, safeNumber(element.dcr)));
}

function sourceProfileLabel(profile = '') {
  const key = normalizeToken(profile) || 'generic';
  return PROFILE_LABELS[key] || normalizeText(profile) || PROFILE_LABELS.generic;
}

function mapperPreset(profile = '') {
  const normalized = normalizeToken(profile) || 'generic';
  return CSV_MAPPER_PRESETS[normalized] || CSV_MAPPER_PRESETS.generic;
}

function ingestRows(preview = {}) {
  return Array.isArray(preview?.normalized_rows) ? preview.normalized_rows : [];
}

function rowMemberId(row = {}) {
  return firstText(
    row.member_id,
    row.external_member_id,
    row.source_member_id,
    row.frame,
    row.frame_id,
    row.object_id,
    row.unique_name,
    row.element_id,
    row.guid,
    row.global_id,
    row.globalid,
    row.label,
    row.id,
  );
}

function rowSection(row = {}) {
  return firstText(
    row.section,
    row.section_name,
    row.frame_section,
    row.property,
    row.profile,
    row.profile_name,
    row.family_type,
    row.type_name,
  );
}

function rowDcr(row = {}) {
  return safeNumber(
    row.dcr_after,
    safeNumber(row.max_dcr_after, safeNumber(row.dcr, safeNumber(row.utilization, safeNumber(row.usage)))),
  );
}

function rowStory(row = {}) {
  return firstText(row.story, row.story_name, row.level, row.storey, row.building_storey, row.floor, row.location);
}

function rowMode(row = {}) {
  return firstText(row.mode, row.mode_id, row.mode_number, row.modal_case, row.mode_shape, row.eigenmode);
}

function buildElementIndex(elements = []) {
  const index = new Map();
  (Array.isArray(elements) ? elements : []).forEach((element) => {
    const id = memberIdFromElement(element);
    if (!id) return;
    const aliases = [
      id,
      element.id,
      element.member_id,
      element.case_id,
      element.review_member_id,
      element.full_crosswalk_target_element_id,
      element.baseline_focus_member_id,
    ].map(normalizeText).filter(Boolean);
    aliases.forEach((alias) => {
      if (!index.has(alias)) index.set(alias, element);
    });
  });
  return index;
}

function buildTraceability(row = {}, element = null) {
  const externalMemberId = rowMemberId(row);
  const viewerMemberId = element ? memberIdFromElement(element) : '';
  const story = rowStory(row);
  const mode = rowMode(row);
  const memberStatus = viewerMemberId && externalMemberId ? 'traced' : 'missing';
  const storyStatus = story ? 'traced' : 'missing';
  const modeStatus = mode ? 'traced' : 'missing';
  return {
    traceKey: [
      `member:${viewerMemberId || externalMemberId || 'missing'}`,
      `story:${story || 'missing'}`,
      `mode:${mode || 'missing'}`,
    ].join('|'),
    member: {
      status: memberStatus,
      externalId: externalMemberId || '',
      viewerId: viewerMemberId || '',
    },
    story: {
      status: storyStatus,
      label: story || '',
    },
    mode: {
      status: modeStatus,
      label: mode || '',
    },
    missingDimensions: [
      ...(memberStatus === 'missing' ? ['member'] : []),
      ...(storyStatus === 'missing' ? ['story'] : []),
      ...(modeStatus === 'missing' ? ['mode'] : []),
    ],
  };
}

function classifyRow(row = {}, element = null, {
  dcrTolerance = 0.03,
} = {}) {
  if (!element) return 'missing_viewer_member';
  const externalSection = rowSection(row);
  const viewerSection = sectionFromElement(element);
  if (externalSection && viewerSection && externalSection !== viewerSection) return 'section_mismatch';
  const externalDcr = rowDcr(row);
  const viewerDcr = dcrFromElement(element);
  if (Number.isFinite(externalDcr) && Number.isFinite(viewerDcr) && Math.abs(externalDcr - viewerDcr) > dcrTolerance) {
    return 'dcr_mismatch';
  }
  return 'matched';
}

function rowTone(status = '') {
  if (status === 'matched') return 'success';
  if (status === 'missing_viewer_member') return 'danger';
  return 'warn';
}

function buildRow(row = {}, element = null, options = {}) {
  const externalMemberId = rowMemberId(row);
  const status = classifyRow(row, element, options);
  const externalDcr = rowDcr(row);
  const viewerDcr = dcrFromElement(element || {});
  const traceability = buildTraceability(row, element);
  return {
    status,
    tone: rowTone(status),
    traceKey: traceability.traceKey,
    traceability,
    externalMemberId: externalMemberId || '--',
    viewerMemberId: element ? memberIdFromElement(element) || '--' : '--',
    sourceTool: firstText(row.source_tool, row.tool, row.source_tool_profile, row.source_family, row.source_type),
    sourceProfile: normalizeToken(row.source_tool_profile || row.source_profile || row.source_family || row.source_type) || 'generic',
    story: rowStory(row),
    mode: rowMode(row),
    externalSection: rowSection(row) || '--',
    viewerSection: element ? sectionFromElement(element) || '--' : '--',
    externalDcr: Number.isFinite(externalDcr) ? externalDcr.toFixed(3) : '--',
    viewerDcr: Number.isFinite(viewerDcr) ? viewerDcr.toFixed(3) : '--',
    receiptPath: firstText(row.receipt_path, row.receiptPath, row.path, row.artifact_path),
    evidence: element ? 'crosswalk exact id' : 'missing evidence',
  };
}

function buildTraceCoverage(rows = []) {
  const total = rows.length;
  const member = rows.filter((row) => row.traceability?.member?.status === 'traced').length;
  const story = rows.filter((row) => row.traceability?.story?.status === 'traced').length;
  const mode = rows.filter((row) => row.traceability?.mode?.status === 'traced').length;
  const full = rows.filter((row) => !row.traceability?.missingDimensions?.length).length;
  const missingDimensions = [
    ...(member === total ? [] : ['member']),
    ...(story === total ? [] : ['story']),
    ...(mode === total ? [] : ['mode']),
  ];
  return {
    total,
    member,
    story,
    mode,
    full,
    missingDimensions,
    contractPass: total > 0 && full === total,
  };
}

export function inferCommercialToolProfile(value = '') {
  const token = normalizeToken(value);
  if (!token) return 'generic';
  if (token.includes('midas')) return 'midas';
  if (token.includes('etabs')) return 'etabs';
  if (token.includes('sap2000') || token === 'sap') return 'sap2000';
  if (token.includes('rfem') || token.includes('dlubal')) return 'rfem';
  if (token.includes('tekla')) return 'tekla';
  if (token.includes('revit')) return 'revit';
  if (token.includes('ifc')) return 'ifc';
  return 'generic';
}

export function listCommercialToolCsvMapperPresets() {
  return Object.values(CSV_MAPPER_PRESETS).map((preset) => ({
    profile: preset.profile,
    label: preset.label,
    fieldCount: Object.keys(preset.canonicalFields).length,
  }));
}

export function buildCommercialToolCsvMapperModel({
  profile = 'generic',
  ingestPreview = null,
} = {}) {
  const normalizedProfile = normalizeToken(profile) || 'generic';
  const rowProfiles = ingestRows(ingestPreview).map((row) => inferCommercialToolProfile(firstText(
    row.source_tool_profile,
    row.source_profile,
    row.source_tool,
    row.tool,
    row.source_family,
    row.source_type,
  )));
  const detectedProfile = rowProfiles.find((entry) => entry && entry !== 'generic') || rowProfiles[0] || 'generic';
  const activeProfile = normalizedProfile === 'auto' ? detectedProfile : normalizedProfile;
  const preset = mapperPreset(activeProfile);
  const rows = Object.entries(preset.canonicalFields).map(([field, candidates]) => ({
    field,
    candidates,
    label: candidates.join(' / '),
  }));
  return {
    schema_version: 'structure-viewer-commercial-tool-csv-mapper.v1',
    requestedProfile: normalizedProfile,
    profile: preset.profile,
    label: preset.label,
    detectedProfile,
    rows,
    summary: `${preset.label} mapper · ${rows.length} canonical fields`,
    presets: listCommercialToolCsvMapperPresets(),
  };
}

export function buildCommercialToolCrosswalkModel({
  data = {},
  ingestPreview = null,
  memberId = '',
  limit = 40,
  dcrTolerance = 0.03,
} = {}) {
  const rows = ingestRows(ingestPreview);
  const elementIndex = buildElementIndex(data?.elements || []);
  const builtRows = rows
    .map((row) => {
      const externalMemberId = rowMemberId(row);
      const element = externalMemberId ? elementIndex.get(externalMemberId) : null;
      return buildRow(row, element, { dcrTolerance });
    })
    .filter((row) => row.externalMemberId !== '--' || row.receiptPath);
  const selectedMemberId = normalizeText(memberId);
  const selectedRows = selectedMemberId
    ? builtRows.filter((row) => row.viewerMemberId === selectedMemberId || row.externalMemberId === selectedMemberId)
    : [];
  const counts = {
    total: builtRows.length,
    matched: builtRows.filter((row) => row.status === 'matched').length,
    section_mismatch: builtRows.filter((row) => row.status === 'section_mismatch').length,
    dcr_mismatch: builtRows.filter((row) => row.status === 'dcr_mismatch').length,
    missing_viewer_member: builtRows.filter((row) => row.status === 'missing_viewer_member').length,
  };
  const traceCoverage = buildTraceCoverage(builtRows);
  const profileCounts = builtRows.reduce((acc, row) => {
    const profile = normalizeToken(row.sourceProfile) || 'generic';
    acc[profile] = (acc[profile] || 0) + 1;
    return acc;
  }, {});
  const profileLabels = Object.entries(profileCounts)
    .map(([profile, count]) => `${sourceProfileLabel(profile)} ${count}`)
    .join(', ');
  const mismatchCount = counts.section_mismatch + counts.dcr_mismatch + counts.missing_viewer_member;
  const status = !counts.total
    ? 'missing'
    : mismatchCount
      ? 'needs_review'
      : 'ready';
  return {
    schema_version: STRUCTURE_VIEWER_COMMERCIAL_TOOL_CROSSWALK_SCHEMA_VERSION,
    status,
    traceabilityStatus: traceCoverage.contractPass ? 'ready' : counts.total ? 'missing_trace_dimensions' : 'missing',
    tone: status === 'ready' ? 'success' : status === 'needs_review' ? 'warn' : 'neutral',
    summary: counts.total
      ? `${profileLabels || 'Commercial tool'} · matched ${counts.matched}/${counts.total} · mismatches ${mismatchCount}`
      : 'commercial tool crosswalk pending',
    counts,
    traceCoverage,
    profiles: Object.entries(profileCounts).map(([profile, count]) => ({
      profile,
      label: sourceProfileLabel(profile),
      count,
    })),
    selectedRows,
    rows: builtRows.slice(0, limit),
  };
}
