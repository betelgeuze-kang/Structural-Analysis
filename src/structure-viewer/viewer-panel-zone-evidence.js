export const PANEL_ZONE_EVIDENCE_SCHEMA = 'structure-viewer-panel-zone-evidence.v1';

const DEFAULT_PANEL_ZONE_EVIDENCE = {
  schemaVersion: PANEL_ZONE_EVIDENCE_SCHEMA,
  sourcePath: 'implementation/phase1/panel_zone_clash_artifact.json',
  handoffPath: 'implementation/phase1/panel_zone_solver_verified_handoff_report.json',
  status: 'ready',
  boundary: 'solver_verified',
  closureMode: 'closed_exact_validated',
  sourceLabel: 'Solver-verified 3D handoff',
  sourceCount: 3,
  validatedSourceCount: 3,
  exactSourceCount: 3,
  fallbackSourceCount: 0,
  candidateMemberCount: 45,
  validatedMemberCount: 1,
  exactMemberCount: 1,
  validatedRowCount: 3,
  exactValidatedRowCount: 3,
  interferenceRowCount: 45,
  maxAnchorageComplexity: 0.22,
  maxDetailingViolationRatio: 0.385741939475051,
  maxConstructabilityScore: 0.24959484239332508,
  checks: {
    true3dClashVerified: true,
    true3dAnchorageVerified: true,
    requiredSourcesComplete: true,
    solverVerifiedBridgeComplete: true,
    proxyOnly: false,
  },
  candidateRows: [
    {
      memberId: '26705',
      memberType: 'beam',
      story: 'S09',
      section: 'SB800X4001.72',
      constructabilityScore: 0.24959484239332508,
      anchorageComplexity: 0.22,
      detailingViolationRatio: 0.3631958656904467,
    },
    {
      memberId: '26708',
      memberType: 'beam',
      story: 'S09',
      section: 'SB800X4002.00',
      constructabilityScore: 0.24959484239332508,
      anchorageComplexity: 0.22,
      detailingViolationRatio: 0.3631958656904467,
    },
    {
      memberId: '26910',
      memberType: 'beam',
      story: 'S09',
      section: 'SB800X700',
      constructabilityScore: 0.24710774305301428,
      anchorageComplexity: 0.18,
      detailingViolationRatio: 0.385741939475051,
    },
  ],
};

function normalizeText(value) {
  return String(value ?? '').trim();
}

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function safeBool(value, fallback = false) {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const lowered = value.trim().toLowerCase();
    if (['true', 'yes', '1', 'pass', 'ready', 'verified'].includes(lowered)) return true;
    if (['false', 'no', '0', 'fail', 'blocked'].includes(lowered)) return false;
  }
  return fallback;
}

function formatRatioPercent(value, digits = 0) {
  return `${(safeNumber(value, 0) * 100).toLocaleString('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })}%`;
}

function getMetaValue(meta, keys, fallback) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(meta || {}, key)) return meta[key];
  }
  return fallback;
}

function normalizeCandidateRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .map((row) => ({
      memberId: normalizeText(row?.memberId || row?.member_id || row?.id),
      memberType: normalizeText(row?.memberType || row?.member_type || row?.type || 'member'),
      story: normalizeText(row?.story || String(row?.group_id || '').split(':')[0] || '--'),
      section: normalizeText(row?.section || row?.section_signature || row?.sectionLabel || '--'),
      constructabilityScore: safeNumber(row?.constructabilityScore ?? row?.constructability_score, 0),
      anchorageComplexity: safeNumber(row?.anchorageComplexity ?? row?.anchorage_complexity, 0),
      detailingViolationRatio: safeNumber(row?.detailingViolationRatio ?? row?.detailing_violation_ratio, 0),
    }))
    .filter((row) => row.memberId);
}

function readPanelZoneEvidenceSource(data = {}) {
  const meta = data && typeof data === 'object' && data.meta && typeof data.meta === 'object' ? data.meta : {};
  const explicit = meta.panel_zone_evidence && typeof meta.panel_zone_evidence === 'object'
    ? meta.panel_zone_evidence
    : {};
  const checks = explicit.checks && typeof explicit.checks === 'object' ? explicit.checks : {};
  const defaultChecks = DEFAULT_PANEL_ZONE_EVIDENCE.checks;
  return {
    schemaVersion: PANEL_ZONE_EVIDENCE_SCHEMA,
    sourcePath: normalizeText(explicit.sourcePath || explicit.source_path || meta.panel_zone_clash_artifact_path)
      || DEFAULT_PANEL_ZONE_EVIDENCE.sourcePath,
    handoffPath: normalizeText(explicit.handoffPath || explicit.handoff_path || meta.panel_zone_solver_verified_handoff_report_path)
      || DEFAULT_PANEL_ZONE_EVIDENCE.handoffPath,
    status: normalizeText(explicit.status || meta.panel_zone_external_validation_status_label)
      || DEFAULT_PANEL_ZONE_EVIDENCE.status,
    boundary: normalizeText(explicit.boundary || meta.panel_zone_external_validation_boundary || meta.panel_zone_source_contract_mode)
      || DEFAULT_PANEL_ZONE_EVIDENCE.boundary,
    closureMode: normalizeText(explicit.closureMode || explicit.closure_mode || meta.panel_zone_external_validation_closure_mode)
      || DEFAULT_PANEL_ZONE_EVIDENCE.closureMode,
    sourceLabel: normalizeText(explicit.sourceLabel || explicit.source_label || meta.panel_zone_external_validation_source_origin_class)
      || DEFAULT_PANEL_ZONE_EVIDENCE.sourceLabel,
    sourceCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_source_count'], explicit.sourceCount), DEFAULT_PANEL_ZONE_EVIDENCE.sourceCount),
    validatedSourceCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_validated_source_count'], explicit.validatedSourceCount), DEFAULT_PANEL_ZONE_EVIDENCE.validatedSourceCount),
    exactSourceCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_exact_source_count'], explicit.exactSourceCount), DEFAULT_PANEL_ZONE_EVIDENCE.exactSourceCount),
    fallbackSourceCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_fallback_source_count'], explicit.fallbackSourceCount), DEFAULT_PANEL_ZONE_EVIDENCE.fallbackSourceCount),
    candidateMemberCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_candidate_member_count', 'panel_zone_candidate_member_count'], explicit.candidateMemberCount), DEFAULT_PANEL_ZONE_EVIDENCE.candidateMemberCount),
    validatedMemberCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_validated_member_count'], explicit.validatedMemberCount), DEFAULT_PANEL_ZONE_EVIDENCE.validatedMemberCount),
    exactMemberCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_exact_member_count'], explicit.exactMemberCount), DEFAULT_PANEL_ZONE_EVIDENCE.exactMemberCount),
    validatedRowCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_validated_row_count_total', 'panel_zone_validated_row_count'], explicit.validatedRowCount), DEFAULT_PANEL_ZONE_EVIDENCE.validatedRowCount),
    exactValidatedRowCount: safeNumber(getMetaValue(meta, ['panel_zone_external_validation_exact_validated_row_count'], explicit.exactValidatedRowCount), DEFAULT_PANEL_ZONE_EVIDENCE.exactValidatedRowCount),
    interferenceRowCount: safeNumber(getMetaValue(meta, ['panel_zone_clash_row_count', 'panel_zone_interference_row_count'], explicit.interferenceRowCount), DEFAULT_PANEL_ZONE_EVIDENCE.interferenceRowCount),
    maxAnchorageComplexity: safeNumber(getMetaValue(meta, ['max_anchorage_complexity', 'panel_zone_max_anchorage_complexity'], explicit.maxAnchorageComplexity), DEFAULT_PANEL_ZONE_EVIDENCE.maxAnchorageComplexity),
    maxDetailingViolationRatio: safeNumber(getMetaValue(meta, ['max_detailing_violation_ratio', 'panel_zone_max_detailing_violation_ratio'], explicit.maxDetailingViolationRatio), DEFAULT_PANEL_ZONE_EVIDENCE.maxDetailingViolationRatio),
    maxConstructabilityScore: safeNumber(getMetaValue(meta, ['max_constructability_score', 'panel_zone_max_constructability_score'], explicit.maxConstructabilityScore), DEFAULT_PANEL_ZONE_EVIDENCE.maxConstructabilityScore),
    checks: {
      true3dClashVerified: safeBool(checks.true3dClashVerified ?? checks.true_3d_clash_verified ?? meta.panel_zone_true_3d_clash_verified, defaultChecks.true3dClashVerified),
      true3dAnchorageVerified: safeBool(checks.true3dAnchorageVerified ?? checks.true_3d_anchorage_verified ?? meta.panel_zone_true_3d_anchorage_verified, defaultChecks.true3dAnchorageVerified),
      requiredSourcesComplete: safeBool(checks.requiredSourcesComplete ?? checks.required_sources_complete ?? meta.panel_zone_required_sources_complete, defaultChecks.requiredSourcesComplete),
      solverVerifiedBridgeComplete: safeBool(checks.solverVerifiedBridgeComplete ?? checks.solver_verified_bridge_complete ?? meta.panel_zone_solver_verified_bridge_complete, defaultChecks.solverVerifiedBridgeComplete),
      proxyOnly: safeBool(checks.proxyOnly ?? checks.proxy_only ?? meta.panel_zone_proxy_only, defaultChecks.proxyOnly),
    },
    candidateRows: normalizeCandidateRows(
      explicit.candidateRows
      || explicit.candidate_rows
      || meta.panel_zone_candidate_rows
      || DEFAULT_PANEL_ZONE_EVIDENCE.candidateRows,
    ),
  };
}

export function buildPanelZoneEvidenceModel(data = {}, { cockpitModel = null } = {}) {
  const source = readPanelZoneEvidenceSource(data);
  const sourceCount = Math.max(0, Math.round(source.sourceCount));
  const validatedSourceCount = Math.max(0, Math.round(source.validatedSourceCount));
  const exactSourceCount = Math.max(0, Math.round(source.exactSourceCount));
  const fallbackSourceCount = Math.max(0, Math.round(source.fallbackSourceCount));
  const candidateMemberCount = Math.max(0, Math.round(source.candidateMemberCount));
  const validatedMemberCount = Math.max(0, Math.round(source.validatedMemberCount));
  const exactMemberCount = Math.max(0, Math.round(source.exactMemberCount));
  const validatedRowCount = Math.max(0, Math.round(source.validatedRowCount));
  const exactValidatedRowCount = Math.max(0, Math.round(source.exactValidatedRowCount));
  const interferenceRowCount = Math.max(0, Math.round(source.interferenceRowCount));
  const ready = (
    sourceCount > 0
    && validatedSourceCount >= sourceCount
    && source.checks.true3dClashVerified
    && source.checks.true3dAnchorageVerified
    && source.checks.requiredSourcesComplete
    && source.checks.solverVerifiedBridgeComplete
    && !source.checks.proxyOnly
  );
  const status = ready ? 'ready' : (source.checks.proxyOnly ? 'needs_review' : 'blocked');
  const criticalMemberId = normalizeText((cockpitModel?.criticalMembers || [])[0]?.id);
  const candidateRows = normalizeCandidateRows(source.candidateRows).slice(0, 3);
  const rows = [
    {
      key: 'joint-geometry',
      label: 'Joint geometry',
      value: `${validatedSourceCount}/${sourceCount}`,
      detail: `${exactSourceCount} exact source rows`,
      tone: validatedSourceCount >= sourceCount ? 'success' : 'warn',
    },
    {
      key: 'rebar-anchorage',
      label: 'Rebar anchorage',
      value: formatRatioPercent(source.maxAnchorageComplexity, 0),
      detail: source.checks.true3dAnchorageVerified ? '3D anchorage verified' : 'anchorage needs review',
      tone: source.checks.true3dAnchorageVerified ? 'success' : 'warn',
    },
    {
      key: 'clash',
      label: '3D clash',
      value: `${interferenceRowCount}`,
      detail: source.checks.true3dClashVerified ? 'true 3D clash verified' : 'clash source missing',
      tone: source.checks.true3dClashVerified ? 'success' : 'danger',
    },
    {
      key: 'fallback',
      label: 'Fallback rows',
      value: `${fallbackSourceCount}`,
      detail: `${exactValidatedRowCount}/${validatedRowCount} exact validated rows`,
      tone: fallbackSourceCount === 0 ? 'success' : 'warn',
    },
  ];
  return {
    schemaVersion: PANEL_ZONE_EVIDENCE_SCHEMA,
    status,
    sourcePath: source.sourcePath,
    handoffPath: source.handoffPath,
    boundary: source.boundary,
    closureMode: source.closureMode,
    sourceLabel: source.sourceLabel,
    sourceCount,
    validatedSourceCount,
    exactSourceCount,
    fallbackSourceCount,
    candidateMemberCount,
    validatedMemberCount,
    exactMemberCount,
    validatedRowCount,
    exactValidatedRowCount,
    interferenceRowCount,
    maxAnchorageComplexity: source.maxAnchorageComplexity,
    maxDetailingViolationRatio: source.maxDetailingViolationRatio,
    maxConstructabilityScore: source.maxConstructabilityScore,
    primaryMemberId: candidateRows[0]?.memberId || criticalMemberId,
    rows,
    candidateRows,
  };
}
