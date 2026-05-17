import { buildDrawingReviewModel } from './viewer-drawing-review-model.js';

export const STRUCTURE_VIEWER_PROJECT_MANIFEST_SCHEMA_VERSION = 'structure-viewer-project-manifest.v1';

export const PROJECT_WORKSPACE_STATUS_ORDER = ['ready', 'needs_review', 'blocked'];

const RELEASE_VISUALIZATION_ENTRY_ROOT = '../../implementation/phase1/release/visualization/entries';
const RELEASE_VISUALIZATION_SOURCE_ROOT = 'implementation/phase1/release/visualization/entries';

const OPSTOOL_606M_RELEASE_DRAWING_SPECS = [
  {
    stem: 'opstool_606m_outrigger',
    title: 'OpenSTOOL 606m Outrigger Compare',
    family: 'opstool_606m_outrigger',
  },
  ...['00001', '00005', '00008', '00015', '00017', '00020', '00023'].map((serial) => ({
    stem: `opstool_606m_megatall_model_${serial}`,
    title: `OpenSTOOL 606m Megatall Model ${serial}`,
    family: 'opstool_606m_megatall',
  })),
];

function buildOptimizationSummary({
  baseline_member_count = null,
  optimized_member_count = null,
  evidence_level = 'release interactive artifact counts',
  risk_delta_label = 'risk movement pending external receipt',
  source = '',
  artifact_count_source = '',
} = {}) {
  return {
    baseline_member_count,
    optimized_member_count,
    evidence_level,
    risk_delta_label,
    source,
    artifact_count_source,
  };
}

function buildReleaseVisualizationVariant(stem, variant, label, suffix) {
  return {
    variant,
    label,
    artifact_path: `${RELEASE_VISUALIZATION_ENTRY_ROOT}/${stem}_${suffix}.json`,
  };
}

export function buildReleaseVisualizationDrawing(spec = {}) {
  const stem = normalizeText(spec.stem);
  return {
    drawing_id: stem,
    drawing_title: normalizeText(spec.title) || stem,
    source_family: 'json_interactive_3d',
    artifact_path: `${RELEASE_VISUALIZATION_ENTRY_ROOT}/${stem}_ai_compare.json`,
    viewer_preset: '',
    baseline_ref: `${stem}_baseline`,
    optimized_ref: `${stem}_after_only`,
    optimization_summary: buildOptimizationSummary({
      baseline_member_count: 800,
      optimized_member_count: 96,
      source: `${RELEASE_VISUALIZATION_SOURCE_ROOT}/${stem}_ai_compare.json`,
      artifact_count_source: `${RELEASE_VISUALIZATION_SOURCE_ROOT}/${stem}_ai_compare.json`,
    }),
    quality_flags: ['large_release_artifact', 'synthetic_compare', 'external_receipt_pending'],
    commercial_review_status: 'needs_review',
    release_family: normalizeText(spec.family) || 'release_visualization',
    provenance: {
      source_path: `${RELEASE_VISUALIZATION_SOURCE_ROOT}/${stem}_ai_compare.json`,
      report_path: `${RELEASE_VISUALIZATION_SOURCE_ROOT}/${stem}_ai_compare.html`,
      evidence_level: 'release interactive artifact',
    },
    variants: [
      buildReleaseVisualizationVariant(stem, 'baseline', 'Baseline', 'baseline'),
      buildReleaseVisualizationVariant(stem, 'optimized', 'After', 'after_only'),
      buildReleaseVisualizationVariant(stem, 'compare', 'Compare', 'ai_compare'),
    ],
  };
}

export function buildReleaseVisualizationDrawings() {
  return OPSTOOL_606M_RELEASE_DRAWING_SPECS.map((spec) => buildReleaseVisualizationDrawing(spec));
}

export const DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST = {
  schema_version: STRUCTURE_VIEWER_PROJECT_MANIFEST_SCHEMA_VERSION,
  generated_at: '2026-05-17T00:00:00Z',
  projects: [
    {
      project_id: 'midas33_release',
      project_title: 'MIDAS33 Release Models',
      drawings: [
        {
          drawing_id: 'midas33_optimized',
          drawing_title: 'MIDAS33 Optimized Roundtrip',
          source_family: 'midas_mgt',
          artifact_path: 'implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json',
          viewer_preset: 'midas33_optimized',
          baseline_ref: 'midas33',
          optimized_ref: 'midas33_optimized',
          optimization_summary: buildOptimizationSummary({
            baseline_member_count: 11334,
            optimized_member_count: 2242,
            evidence_level: 'repo exact roundtrip release counts',
            risk_delta_label: 'D/C movement requires engineer-in-loop review',
            source: 'implementation/phase1/release/visualization/entries/midas33_optimized_roundtrip.json',
            artifact_count_source: 'implementation/phase1/release/visualization/entries/midas33_optimized_roundtrip.json',
          }),
          quality_flags: [],
          commercial_review_status: 'ready',
          provenance: {
            source_path: 'implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json',
            report_path: 'implementation/phase1/release/visualization/entries/midas33_optimized_roundtrip.json',
            evidence_level: 'repo exact roundtrip',
          },
          variants: [
            {
              variant: 'baseline',
              label: 'Baseline',
              viewer_preset: 'midas33',
              artifact_path: 'implementation/phase1/open_data/midas/midas_generator_33.json',
            },
            {
              variant: 'optimized',
              label: 'Optimized',
              viewer_preset: 'midas33_optimized',
              artifact_path: 'implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json',
            },
            {
              variant: 'compare',
              label: 'Compare',
              viewer_preset: 'midas33_optimized',
              artifact_path: 'implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json',
            },
          ],
        },
        {
          drawing_id: 'midas33_pr_recheck',
          drawing_title: 'MIDAS33 PR Recheck Baseline',
          source_family: 'midas_mgt',
          artifact_path: 'implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json',
          viewer_preset: 'midas33_pr',
          baseline_ref: 'midas33_pr',
          optimized_ref: 'midas33_optimized',
          optimization_summary: buildOptimizationSummary({
            baseline_member_count: 11334,
            optimized_member_count: 2242,
            evidence_level: 'derived from paired MIDAS33 roundtrip counts',
            risk_delta_label: 'PR recheck needs baseline-specific D/C review',
            source: 'implementation/phase1/release/visualization/entries/midas33_pr_recheck_baseline.json',
          }),
          quality_flags: ['optimization_pair_available'],
          commercial_review_status: 'needs_review',
          provenance: {
            source_path: 'implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json',
            report_path: 'implementation/phase1/release/visualization/entries/midas33_pr_recheck_baseline.json',
            evidence_level: 'repo exact roundtrip',
          },
          variants: [
            {
              variant: 'baseline',
              label: 'PR Recheck',
              viewer_preset: 'midas33_pr',
              artifact_path: 'implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json',
            },
            {
              variant: 'optimized',
              label: 'Optimized',
              viewer_preset: 'midas33_optimized',
              artifact_path: 'implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json',
            },
            {
              variant: 'compare',
              label: 'Compare',
              viewer_preset: 'midas33_optimized',
              artifact_path: 'implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json',
            },
          ],
        },
      ],
    },
    {
      project_id: 'real_drawing_private',
      project_title: 'Real Drawing Derived Topology',
      drawings: [
        {
          drawing_id: 'real_drawing_private_gallery',
          drawing_title: 'Private Real Drawing Gallery',
          source_family: 'ifc_midas_mixed',
          artifact_path: 'private local derived topology sidecar',
          viewer_preset: 'real_drawing_private_3d',
          baseline_ref: 'real_drawing_private_3d',
          optimized_ref: 'real_drawing_private_3d',
          quality_flags: ['load_model_missing', 'proxy_assets_present'],
          commercial_review_status: 'needs_review',
          provenance: {
            source_path: 'private local derived topology sidecar',
            report_path: 'src/structure-viewer/index.real_drawing_private.data.js',
            evidence_level: 'derived private topology',
          },
          variants: [
            {
              variant: 'optimized',
              label: 'Gallery',
              viewer_preset: 'real_drawing_private_3d',
              artifact_path: 'private local derived topology sidecar',
            },
            {
              variant: 'compare',
              label: 'Review',
              viewer_preset: 'real_drawing_private_3d',
              artifact_path: 'private local derived topology sidecar',
            },
          ],
        },
      ],
    },
    {
      project_id: 'release_visualization',
      project_title: 'Release Visualization Entries',
      drawings: buildReleaseVisualizationDrawings(),
    },
  ],
};

function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeToken(value) {
  return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function uniqueFlags(flags = []) {
  return [...new Set((Array.isArray(flags) ? flags : []).map(normalizeToken).filter(Boolean))];
}

function firstText(...values) {
  return values.map(normalizeText).find(Boolean) || '';
}

function firstNumber(...values) {
  const value = values.find((candidate) => Number.isFinite(Number(candidate)));
  return value === undefined ? NaN : Number(value);
}

function normalizeGeometrySummary(row = {}) {
  const geometry = row.geometry_summary && typeof row.geometry_summary === 'object'
    ? row.geometry_summary
    : row.geometry && typeof row.geometry === 'object'
      ? row.geometry
      : {};
  const bounds = geometry.bounds && typeof geometry.bounds === 'object'
    ? geometry.bounds
    : row.bounds && typeof row.bounds === 'object'
      ? row.bounds
      : {};
  return {
    node_count: firstNumber(geometry.node_count, geometry.nodes, row.node_count, row.nodes),
    element_count: firstNumber(geometry.element_count, geometry.elements, row.element_count, row.elements),
    member_count: firstNumber(geometry.member_count, geometry.members, row.member_count, row.members),
    bounds: {
      x: firstNumber(bounds.x, bounds.width, bounds.dx, row.bounds_x),
      y: firstNumber(bounds.y, bounds.depth, bounds.dy, row.bounds_y),
      z: firstNumber(bounds.z, bounds.height, bounds.dz, row.bounds_z),
    },
    up_axis: firstText(geometry.up_axis, row.up_axis, row.coordinate_up_axis),
    axis_flipped: Boolean(geometry.axis_flipped || row.axis_flipped || row.flipped_axis),
  };
}

function normalizeVariantRows(row = {}) {
  if (Array.isArray(row.variants) && row.variants.length) return row.variants;
  const variants = [];
  const baselinePath = firstText(row.baseline_artifact_path, row.baseline_path, row.baseline_ref);
  const optimizedPath = firstText(row.optimized_artifact_path, row.optimized_path, row.optimized_ref, row.artifact_path);
  const comparePath = firstText(row.compare_artifact_path, row.compare_path);
  if (baselinePath) {
    variants.push({
      variant: 'baseline',
      label: firstText(row.baseline_label) || 'Baseline',
      viewer_preset: firstText(row.baseline_viewer_preset),
      artifact_path: baselinePath,
    });
  }
  if (optimizedPath) {
    variants.push({
      variant: 'optimized',
      label: firstText(row.optimized_label) || 'Optimized',
      viewer_preset: firstText(row.optimized_viewer_preset, row.viewer_preset),
      artifact_path: optimizedPath,
    });
  }
  if (comparePath) {
    variants.push({
      variant: 'compare',
      label: firstText(row.compare_label) || 'Compare',
      viewer_preset: firstText(row.compare_viewer_preset, row.viewer_preset),
      artifact_path: comparePath,
    });
  }
  return variants;
}

function normalizeOptimizationSummary(row = {}) {
  const source = row.optimization_summary && typeof row.optimization_summary === 'object'
    ? row.optimization_summary
    : {};
  return {
    ...source,
    baseline_member_count: firstNumber(source.baseline_member_count, source.before_member_count, row.baseline_member_count, row.before_member_count),
    optimized_member_count: firstNumber(source.optimized_member_count, source.after_member_count, row.optimized_member_count, row.after_member_count),
    member_delta_pct: firstNumber(source.member_delta_pct, row.member_delta_pct),
    weight_delta_pct: firstNumber(source.weight_delta_pct, row.weight_delta_pct),
    cost_delta_pct: firstNumber(source.cost_delta_pct, row.cost_delta_pct),
    risk_delta_label: firstText(source.risk_delta_label, source.risk_focus, row.risk_delta_label, row.risk_focus),
    evidence_level: firstText(source.evidence_level, row.optimization_evidence_level),
    source: firstText(source.source, source.source_path, row.optimization_summary_source),
    artifact_count_source: firstText(source.artifact_count_source, row.artifact_count_source),
  };
}

function formatWorkspaceCount(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number).toLocaleString('en-US') : '--';
}

function formatWorkspacePercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const sign = number > 0 ? '+' : '';
  return `${sign}${number.toFixed(1)}%`;
}

function buildDrawingComparisonLabel(drawing = {}) {
  const summary = drawing.optimization_summary && typeof drawing.optimization_summary === 'object'
    ? drawing.optimization_summary
    : {};
  const baseline = Number(summary.baseline_member_count);
  const optimized = Number(summary.optimized_member_count);
  if (!Number.isFinite(baseline) || baseline <= 0 || !Number.isFinite(optimized)) return 'comparison pending';
  const deltaPct = Number.isFinite(Number(summary.member_delta_pct))
    ? Number(summary.member_delta_pct)
    : ((optimized - baseline) / baseline) * 100;
  return `members ${formatWorkspaceCount(baseline)} -> ${formatWorkspaceCount(optimized)} (${formatWorkspacePercent(deltaPct)})`;
}

export function buildDrawingArtifactCountVerification(drawing = {}) {
  const summary = drawing.optimization_summary && typeof drawing.optimization_summary === 'object'
    ? drawing.optimization_summary
    : {};
  const artifactCountSource = firstText(summary.artifact_count_source, drawing.artifact_count_source);
  if (artifactCountSource) {
    return {
      status: 'verified',
      label: 'Artifact count verified',
      shortLabel: 'verified counts',
      tone: 'success',
      source: artifactCountSource,
    };
  }
  const baseline = Number(summary.baseline_member_count);
  const optimized = Number(summary.optimized_member_count);
  if (Number.isFinite(baseline) && baseline > 0 && Number.isFinite(optimized)) {
    return {
      status: 'manifest_only',
      label: 'Manifest comparison only',
      shortLabel: 'manifest counts',
      tone: 'warn',
      source: firstText(summary.source, summary.source_path, drawing.provenance?.report_path, drawing.source_family),
    };
  }
  return {
    status: 'missing',
    label: 'Comparison evidence pending',
    shortLabel: 'count pending',
    tone: 'danger',
    source: firstText(summary.source, summary.source_path, drawing.provenance?.report_path, drawing.source_family),
  };
}

export function buildDrawingEvidenceDrilldownModel(drawing = null, {
  activeVariant = 'optimized',
} = {}) {
  if (!drawing || typeof drawing !== 'object') {
    return {
      title: 'No drawing selected',
      status: 'missing',
      statusTone: 'danger',
      verification: buildDrawingArtifactCountVerification({}),
      rows: [],
      variants: [],
    };
  }
  const verification = buildDrawingArtifactCountVerification(drawing);
  const review = buildDrawingReviewModel(drawing);
  const qualityFlags = Array.isArray(drawing.quality_flags) ? drawing.quality_flags : [];
  const provenance = drawing.provenance && typeof drawing.provenance === 'object' ? drawing.provenance : {};
  const normalizedActiveVariant = normalizeToken(activeVariant) || 'optimized';
  const rows = [
    { label: 'Review status', value: normalizeWorkspaceStatus(drawing.commercial_review_status) || 'needs_review', tone: getWorkspaceStatusTone(drawing.commercial_review_status) },
    { label: 'Review verdict', value: review.label, tone: review.tone },
    { label: 'Issue count', value: `${review.issueCount} total · ${review.counts.critical} critical · ${review.counts.warning} warning · ${review.counts.info} info`, tone: review.tone },
    { label: 'Count verification', value: verification.label, tone: verification.tone },
    { label: 'Count source', value: verification.source || '--', tone: verification.tone },
    { label: 'Source family', value: normalizeText(drawing.source_family) || '--', tone: 'accent' },
    { label: 'Baseline ref', value: normalizeText(drawing.baseline_ref) || '--', tone: 'neutral' },
    { label: 'Optimized ref', value: normalizeText(drawing.optimized_ref) || '--', tone: 'neutral' },
    { label: 'Artifact', value: normalizeText(drawing.artifact_path) || normalizeText(provenance.source_path) || '--', tone: 'neutral' },
    { label: 'Quality flags', value: qualityFlags.length ? qualityFlags.join(', ') : 'no quality flags', tone: qualityFlags.length ? 'warn' : 'success' },
  ];
  const variants = (Array.isArray(drawing.variants) ? drawing.variants : []).map((variant) => ({
    variant: normalizeToken(variant?.variant) || 'optimized',
    label: normalizeText(variant?.label || variant?.variant || 'Variant'),
    artifactPath: normalizeText(variant?.artifact_path),
    viewerPreset: normalizeText(variant?.viewer_preset),
    active: (normalizeToken(variant?.variant) || 'optimized') === normalizedActiveVariant,
  }));
  return {
    title: normalizeText(drawing.drawing_title || drawing.drawing_id) || 'Drawing',
    drawingId: normalizeText(drawing.drawing_id),
    status: normalizeWorkspaceStatus(drawing.commercial_review_status) || 'needs_review',
    statusTone: getWorkspaceStatusTone(drawing.commercial_review_status),
    verification,
    review,
    rows,
    variants,
  };
}

export function validateDrawingQuality(drawing = {}) {
  const flags = new Set(uniqueFlags(drawing.quality_flags));
  const provenance = drawing.provenance && typeof drawing.provenance === 'object' ? drawing.provenance : {};
  const variants = Array.isArray(drawing.variants) ? drawing.variants : [];
  const hasSource = Boolean(
    normalizeText(drawing.artifact_path)
    || normalizeText(drawing.viewer_preset)
    || normalizeText(provenance.source_path)
    || variants.some((variant) => normalizeText(variant?.artifact_path) || normalizeText(variant?.viewer_preset)),
  );
  if (!hasSource) flags.add('provenance_missing');

  const geometry = drawing.geometry_summary && typeof drawing.geometry_summary === 'object'
    ? drawing.geometry_summary
    : {};
  const nodeCount = safeNumber(geometry.node_count, NaN);
  const elementCount = safeNumber(geometry.element_count, NaN);
  const memberCount = safeNumber(geometry.member_count, NaN);
  if (Number.isFinite(nodeCount) && Number.isFinite(elementCount) && nodeCount <= 0 && elementCount <= 0) {
    flags.add('empty_geometry');
  }
  if (Number.isFinite(memberCount) && memberCount <= 0) flags.add('missing_members');

  const bounds = geometry.bounds && typeof geometry.bounds === 'object' ? geometry.bounds : {};
  const dimensions = ['x', 'y', 'z'].map((axis) => Math.abs(safeNumber(bounds[axis], NaN))).filter(Number.isFinite);
  if (dimensions.length >= 2) {
    const sorted = [...dimensions].sort((a, b) => a - b);
    const min = Math.max(sorted[0], 1e-9);
    const max = sorted[sorted.length - 1];
    if (max / min > 80) flags.add('aspect_ratio_outlier');
    if (max > 5000 || min < 0.001) flags.add('scale_outlier');
  }
  if (normalizeToken(geometry.up_axis) && normalizeToken(geometry.up_axis) !== 'z') flags.add('axis_orientation_review');
  if (geometry.axis_flipped || drawing.axis_flipped) flags.add('axis_flipped_review');
  if (normalizeToken(drawing.load_model_status).includes('missing')) {
    flags.add('load_model_missing');
  }

  const blockerFlags = new Set(['empty_geometry', 'missing_members', 'provenance_missing']);
  const status = [...flags].some((flag) => blockerFlags.has(flag))
    ? 'blocked'
    : flags.size
      ? 'needs_review'
      : 'ready';
  return {
    quality_flags: [...flags],
    commercial_review_status: normalizeWorkspaceStatus(drawing.commercial_review_status) || status,
    computed_review_status: status,
  };
}

export function normalizeProjectManifestRow(row = {}, index = 0) {
  const sourceFamily = firstText(row.source_family, row.sourceFamily, row.format, row.input_type, row.input_format) || 'unknown';
  const drawingId = normalizeToken(firstText(
    row.drawing_id,
    row.id,
    row.case_id,
    row.name,
    row.drawing_title,
    `drawing_${index + 1}`,
  ));
  const drawing = {
    drawing_id: drawingId,
    drawing_title: firstText(row.drawing_title, row.title, row.name, row.case_title) || drawingId,
    source_family: sourceFamily,
    artifact_path: firstText(row.artifact_path, row.path, row.source_path),
    viewer_preset: normalizeToken(firstText(row.viewer_preset, row.preset)),
    baseline_ref: firstText(row.baseline_ref, row.baseline_id),
    optimized_ref: firstText(row.optimized_ref, row.optimized_id),
    optimization_summary: normalizeOptimizationSummary(row),
    load_model_status: firstText(row.load_model_status, row.load_status),
    geometry_summary: normalizeGeometrySummary(row),
    quality_flags: uniqueFlags(row.quality_flags),
    commercial_review_status: normalizeWorkspaceStatus(row.commercial_review_status),
    provenance: row.provenance && typeof row.provenance === 'object'
      ? row.provenance
      : {
        source_path: firstText(row.source_path, row.artifact_path, row.path),
        report_path: firstText(row.report_path),
        evidence_level: firstText(row.evidence_level) || 'manifest row',
      },
    variants: normalizeVariantRows(row),
  };
  const quality = validateDrawingQuality(drawing);
  return {
    ...drawing,
    quality_flags: quality.quality_flags,
    commercial_review_status: drawing.commercial_review_status || quality.commercial_review_status,
    computed_review_status: quality.computed_review_status,
  };
}

export function buildProjectManifestFromRows(rows = [], {
  project_id = 'manifest_import',
  project_title = 'Imported Structure Viewer Project',
  generated_at = '2026-05-17T00:00:00Z',
} = {}) {
  const seen = new Map();
  const drawings = (Array.isArray(rows) ? rows : [])
    .map((row, index) => {
      const drawing = normalizeProjectManifestRow(row, index);
      const count = seen.get(drawing.drawing_id) || 0;
      seen.set(drawing.drawing_id, count + 1);
      return count
        ? { ...drawing, drawing_id: `${drawing.drawing_id}_${count + 1}` }
        : drawing;
    })
    .filter((drawing) => drawing.drawing_id);
  return normalizeProjectManifest({
    schema_version: STRUCTURE_VIEWER_PROJECT_MANIFEST_SCHEMA_VERSION,
    generated_at,
    projects: [
      {
        project_id,
        project_title,
        drawings,
      },
    ],
  });
}

export function normalizeWorkspaceStatus(value) {
  const status = normalizeToken(value);
  return PROJECT_WORKSPACE_STATUS_ORDER.includes(status) ? status : '';
}

export function normalizeProjectManifest(manifest = DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST) {
  const projects = (Array.isArray(manifest?.projects) ? manifest.projects : [])
    .map((project) => {
      const projectId = normalizeToken(project?.project_id || project?.id || project?.project_title);
      const drawings = (Array.isArray(project?.drawings) ? project.drawings : [])
        .map((drawing) => {
          const drawingId = normalizeToken(drawing?.drawing_id || drawing?.id || drawing?.drawing_title);
          const variants = (Array.isArray(drawing?.variants) ? drawing.variants : [])
            .map((variant) => ({
              ...variant,
              variant: normalizeToken(variant?.variant || variant?.id || variant?.label) || 'optimized',
              label: normalizeText(variant?.label) || normalizeText(variant?.variant) || 'Optimized',
              viewer_preset: normalizeToken(variant?.viewer_preset),
              artifact_path: normalizeText(variant?.artifact_path),
            }))
            .filter((variant) => variant.variant);
          const quality = validateDrawingQuality({ ...drawing, variants });
          return {
            ...drawing,
            drawing_id: drawingId,
            drawing_title: normalizeText(drawing?.drawing_title || drawing?.title) || drawingId,
            source_family: normalizeText(drawing?.source_family) || 'unknown',
            artifact_path: normalizeText(drawing?.artifact_path),
            viewer_preset: normalizeToken(drawing?.viewer_preset),
            baseline_ref: normalizeText(drawing?.baseline_ref),
            optimized_ref: normalizeText(drawing?.optimized_ref),
            optimization_summary: drawing?.optimization_summary && typeof drawing.optimization_summary === 'object'
              ? normalizeOptimizationSummary(drawing)
              : {},
            variants,
            quality_flags: quality.quality_flags,
            commercial_review_status: quality.commercial_review_status,
            computed_review_status: quality.computed_review_status,
            provenance: drawing?.provenance && typeof drawing.provenance === 'object' ? drawing.provenance : {},
          };
        })
        .filter((drawing) => drawing.drawing_id);
      return {
        ...project,
        project_id: projectId,
        project_title: normalizeText(project?.project_title || project?.title) || projectId,
        drawings,
      };
    })
    .filter((project) => project.project_id);
  return {
    schema_version: STRUCTURE_VIEWER_PROJECT_MANIFEST_SCHEMA_VERSION,
    generated_at: normalizeText(manifest?.generated_at),
    projects,
  };
}

export function summarizeProjectManifest(manifest = DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST) {
  const projects = Array.isArray(manifest?.projects) ? manifest.projects : [];
  const drawings = getAllWorkspaceDrawings(manifest).map(({ drawing }) => drawing);
  const statusCounts = { ready: 0, needs_review: 0, blocked: 0 };
  drawings.forEach((drawing) => {
    const status = normalizeWorkspaceStatus(drawing.commercial_review_status) || 'needs_review';
    statusCounts[status] = (statusCounts[status] || 0) + 1;
  });
  return {
    projectCount: projects.length,
    drawingCount: drawings.length,
    variantCount: drawings.reduce((total, drawing) => total + (Array.isArray(drawing.variants) ? drawing.variants.length : 0), 0),
    statusCounts,
  };
}

export function getAllWorkspaceDrawings(manifest = DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST) {
  return (Array.isArray(manifest?.projects) ? manifest.projects : []).flatMap((project) => (
    (Array.isArray(project?.drawings) ? project.drawings : []).map((drawing) => ({ project, drawing }))
  ));
}

export function findWorkspaceProject(manifest, projectId = '') {
  const normalized = normalizeToken(projectId);
  return (Array.isArray(manifest?.projects) ? manifest.projects : []).find((project) => project.project_id === normalized)
    || manifest?.projects?.[0]
    || null;
}

export function findWorkspaceDrawing(manifest, projectId = '', drawingId = '') {
  const project = findWorkspaceProject(manifest, projectId);
  if (!project) return { project: null, drawing: null };
  const normalizedDrawing = normalizeToken(drawingId);
  const drawing = project.drawings.find((row) => row.drawing_id === normalizedDrawing)
    || project.drawings[0]
    || null;
  return { project, drawing };
}

export function findWorkspaceVariant(drawing, variant = '') {
  if (!drawing) return null;
  const variants = Array.isArray(drawing.variants) ? drawing.variants : [];
  const normalizedVariant = normalizeToken(variant) || 'optimized';
  return variants.find((row) => row.variant === normalizedVariant)
    || variants.find((row) => row.variant === 'optimized')
    || variants[0]
    || {
      variant: normalizedVariant,
      label: normalizedVariant || 'Optimized',
      viewer_preset: drawing.viewer_preset || '',
      artifact_path: drawing.artifact_path || '',
    };
}

export function resolveWorkspaceStateFromSearch(search = '', {
  manifest = normalizeProjectManifest(),
  legacyPreset = '',
} = {}) {
  const params = new URLSearchParams(search || '');
  const explicitProject = normalizeToken(params.get('project'));
  const explicitDrawing = normalizeToken(params.get('drawing'));
  const explicitVariant = normalizeToken(params.get('variant')) || 'optimized';
  const normalizedLegacyPreset = normalizeToken(legacyPreset || params.get('preset'));
  let project = explicitProject ? findWorkspaceProject(manifest, explicitProject) : null;
  let drawing = null;
  if (project) {
    drawing = project.drawings.find((row) => row.drawing_id === explicitDrawing) || project.drawings[0] || null;
  }
  if (!drawing && normalizedLegacyPreset) {
    const match = getAllWorkspaceDrawings(manifest).find(({ drawing: row }) => (
      row.viewer_preset === normalizedLegacyPreset
      || row.variants.some((variant) => variant.viewer_preset === normalizedLegacyPreset)
    ));
    if (match) {
      project = match.project;
      drawing = match.drawing;
    }
  }
  if (!drawing) {
    project = manifest.projects[0] || null;
    drawing = project?.drawings?.[0] || null;
  }
  const variant = findWorkspaceVariant(drawing, explicitVariant);
  return {
    projectId: project?.project_id || '',
    projectTitle: project?.project_title || '',
    drawingId: drawing?.drawing_id || '',
    drawingTitle: drawing?.drawing_title || '',
    variant: variant?.variant || explicitVariant || 'optimized',
    filter: normalizeWorkspaceStatus(params.get('filter')) || normalizeToken(params.get('filter')) || 'all',
    comparisonFilter: normalizeToken(params.get('comparison_filter')) || 'changed',
    drawingQuery: normalizeText(params.get('drawing_query')),
    viewerPreset: variant?.viewer_preset || drawing?.viewer_preset || normalizedLegacyPreset || '',
    artifactPath: variant?.artifact_path || drawing?.artifact_path || '',
    project,
    drawing,
    variantRow: variant,
  };
}

export function buildWorkspaceUrl(href = '', state = {}, overrides = {}) {
  const url = new URL(href || globalThis.location?.href || 'http://127.0.0.1/');
  const manifest = state.manifest || normalizeProjectManifest();
  const projectId = normalizeToken(overrides.projectId ?? state.projectId);
  const drawingId = normalizeToken(overrides.drawingId ?? state.drawingId);
  const variantName = normalizeToken(overrides.variant ?? state.variant) || 'optimized';
  const filter = normalizeToken(overrides.filter ?? state.filter) || 'all';
  const comparisonFilter = normalizeToken(overrides.comparisonFilter ?? state.comparisonFilter);
  const drawingQuery = normalizeText(overrides.drawingQuery ?? state.drawingQuery);
  const { project, drawing } = findWorkspaceDrawing(manifest, projectId, drawingId);
  const variant = findWorkspaceVariant(drawing, variantName);
  url.searchParams.set('project', project?.project_id || projectId);
  url.searchParams.set('drawing', drawing?.drawing_id || drawingId);
  url.searchParams.set('variant', variant?.variant || variantName);
  if (filter && filter !== 'all') url.searchParams.set('filter', filter);
  else url.searchParams.delete('filter');
  if (drawingQuery) url.searchParams.set('drawing_query', drawingQuery);
  else url.searchParams.delete('drawing_query');
  if (comparisonFilter && comparisonFilter !== 'changed') url.searchParams.set('comparison_filter', comparisonFilter);
  else url.searchParams.delete('comparison_filter');
  if (Object.prototype.hasOwnProperty.call(overrides, 'memberId') || Object.prototype.hasOwnProperty.call(state, 'memberId')) {
    const memberId = normalizeText(overrides.memberId ?? state.memberId);
    if (memberId) url.searchParams.set('member', memberId);
    else url.searchParams.delete('member');
  }
  const preset = variant?.viewer_preset || drawing?.viewer_preset || '';
  if (preset) url.searchParams.set('preset', preset);
  else url.searchParams.delete('preset');
  url.searchParams.delete('artifact');
  url.searchParams.delete('data');
  const artifact = variant?.artifact_path || drawing?.artifact_path || '';
  if (artifact && !preset && !artifact.startsWith('private ')) url.searchParams.set('artifact', artifact);
  return url.href;
}

export function getWorkspaceStatusTone(status = '') {
  const normalized = normalizeWorkspaceStatus(status);
  if (normalized === 'ready') return 'success';
  if (normalized === 'needs_review') return 'warn';
  if (normalized === 'blocked') return 'danger';
  return 'accent';
}

export function buildProjectBrowserModel(manifest = normalizeProjectManifest(), state = {}) {
  const activeProject = findWorkspaceProject(manifest, state.projectId);
  const filter = normalizeToken(state.filter) || 'all';
  const drawingQuery = normalizeText(state.drawingQuery).toLowerCase();
  const drawings = (activeProject?.drawings || []).filter((drawing) => {
    if (filter !== 'all' && drawing.commercial_review_status !== filter) return false;
    if (!drawingQuery) return true;
    const verification = buildDrawingArtifactCountVerification(drawing);
    const haystack = [
      drawing.drawing_id,
      drawing.drawing_title,
      drawing.source_family,
      drawing.baseline_ref,
      drawing.optimized_ref,
      verification.label,
      verification.shortLabel,
      verification.source,
      ...(Array.isArray(drawing.quality_flags) ? drawing.quality_flags : []),
    ].join(' ').toLowerCase();
    return haystack.includes(drawingQuery);
  });
  const statusCounts = { all: activeProject?.drawings?.length || 0, ready: 0, needs_review: 0, blocked: 0 };
  (activeProject?.drawings || []).forEach((drawing) => {
    const status = normalizeWorkspaceStatus(drawing.commercial_review_status) || 'needs_review';
    statusCounts[status] = (statusCounts[status] || 0) + 1;
  });
  const activeDrawing = activeProject?.drawings?.find((drawing) => drawing.drawing_id === state.drawingId)
    || activeProject?.drawings?.[0]
    || null;
  return {
    schemaVersion: manifest.schema_version,
    summary: summarizeProjectManifest(manifest),
    projects: (manifest.projects || []).map((project) => ({
      projectId: project.project_id,
      projectTitle: project.project_title,
      active: project.project_id === activeProject?.project_id,
      drawingCount: project.drawings.length,
    })),
    filter,
    drawingQuery,
    filterOptions: [
      { key: 'all', label: `All ${statusCounts.all}` },
      { key: 'ready', label: `Ready ${statusCounts.ready}` },
      { key: 'needs_review', label: `Review ${statusCounts.needs_review}` },
      { key: 'blocked', label: `Blocked ${statusCounts.blocked}` },
    ],
    activeProject,
    activeDrawing,
    activeEvidence: buildDrawingEvidenceDrilldownModel(activeDrawing, { activeVariant: state.variant }),
    activeVariant: findWorkspaceVariant(activeDrawing, state.variant),
    drawings: drawings.map((drawing) => {
      const verification = buildDrawingArtifactCountVerification(drawing);
      const review = buildDrawingReviewModel(drawing);
      return {
        drawingId: drawing.drawing_id,
        drawingTitle: drawing.drawing_title,
        sourceFamily: drawing.source_family,
        status: drawing.commercial_review_status,
        statusTone: getWorkspaceStatusTone(drawing.commercial_review_status),
        qualityFlags: drawing.quality_flags,
        comparisonLabel: buildDrawingComparisonLabel(drawing),
        verificationStatus: verification.status,
        verificationLabel: verification.label,
        verificationShortLabel: verification.shortLabel,
        verificationTone: verification.tone,
        verificationSource: verification.source,
        reviewVerdict: review.verdict,
        reviewLabel: review.label,
        reviewTone: review.tone,
        issueCount: review.issueCount,
        issueCountLabel: `${review.issueCount} issue${review.issueCount === 1 ? '' : 's'}`,
        active: drawing.drawing_id === state.drawingId,
        variants: drawing.variants,
      };
    }),
  };
}
