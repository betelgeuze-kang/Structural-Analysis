import { type ChangeEvent, startTransition, useEffect, useState } from 'react'
import {
  createInitialResources,
  type JsonRecord,
  type ResourceMap,
  type ResourceState,
} from './workbench/resourceModel'
import { DeveloperPreviewWorkflowPanel } from './workbench/DeveloperPreviewWorkflowPanel'
import { developerPreviewWorkflowSteps } from './workbench/developerPreviewWorkflow'
import { buildDeveloperPreviewWorkflowState } from './workbench/developerPreviewWorkflowState'

type StatusTone = 'ok' | 'warn' | 'missing'
type ReviewSurfaceId = 'viewer' | 'drawing-review' | 'real-drawing-3d' | 'benchmark-review' | 'committee'
type GovernanceArtifactId = 'gap' | 'registry' | 'registry-index' | 'package' | 'signature' | 'batch'

type Surface = {
  id: string
  title: string
  description: string
  href: string
  badge: string
  kind: 'html' | 'json' | 'file'
}

type ReviewSurface = Surface & {
  id: ReviewSurfaceId
}

type GovernanceArtifact = Surface & {
  id: GovernanceArtifactId
}

type Metric = {
  label: string
  value: string
  note?: string
}

type Snapshot = {
  statusLabel: string
  tone: StatusTone
  metrics: Metric[]
  note: string
  sourceLabel: string
}

type RouteStep = {
  id: string
  index: number
  title: string
  href: string
  badge: string
  tone: StatusTone
  statusLabel: string
  description: string
  note: string
}

type RoutePlan = {
  title: string
  description: string
  finishArtifactId: GovernanceArtifactId
  steps: RouteStep[]
}

type DeepLinkParams = Record<string, string | number | null | undefined>

type AuthoringControls = {
  familyId: string
  storyCount: number
  bayCount: number
  floorHeightM: number
  loadPatternCount: number
  sectionId: string
}

type AuthoringFamilyOption = {
  familyId: string
  label: string
  description: string
  defaultStoryCount: number
  defaultBayCount: number
  defaultFloorHeightM: number
  defaultLoadPatternCount: number
  defaultSectionId: string
  defaultBayWidthM: number
}

type AuthoringPortfolioFamilySnapshot = {
  familyId: string
  label: string
  draftLabel: string
  statusLabel: string
  tone: StatusTone
  comboCount: number | null
  meshRequestCount: number | null
  snapshotCount: number | null
  note: string
  workspaceHref: string
  solverHref: string
  registryHref: string
}

type AdvancedHoldoutRow = {
  id: string
  title: string
  severity: string
  status: string
  isClosed: boolean
  mode: string
  reason: string
  evidenceSnippet: string
  tone: StatusTone
}

type ReviewDecision = 'unreviewed' | 'approved' | 'rejected' | 'needs_engineer_review'

type ReviewIssueMarker =
  | 'none'
  | 'evidence_gap'
  | 'scope_gap'
  | 'modeling_gap'
  | 'handoff_gap'
  | 'contract_gap'
  | 'follow_up'

type ReviewRowState = {
  decision: ReviewDecision
  comment: string
  issueMarker: ReviewIssueMarker
  updatedAt: string
}

type ReviewableGapRow = {
  id: string
  severity: string
  gapStatus: string
  title: string
  why: string
  evidence: string
  exitCriteria: string
  statusLabel: string
  tone: StatusTone
}

type ReviewIssueMarkerOption = {
  value: ReviewIssueMarker
  label: string
}

type CommercializationDepthSignal = {
  label: string
  statusLabel: string
  detail: string
  ready: boolean
  tone: StatusTone
}

type AuthoringFamilyCoverageCell = {
  statusLabel: string
  tone: StatusTone
  summary: string
  note: string
}

type AuthoringFamilyCoverageRow = AuthoringPortfolioFamilySnapshot & {
  solver: AuthoringFamilyCoverageCell
  depth: AuthoringFamilyCoverageCell
  writeback: AuthoringFamilyCoverageCell
}

const authoringDraftStorageKey = 'structural-analysis-workbench/native-authoring-controls'
const authoringDraftDownloadName = 'native_authoring_workspace_draft.json'
const reviewStateStorageKey = 'structural-analysis-workbench/release-gap-review-state'
const reviewStateDownloadName = 'release_gap_review_state.json'

const reviewIssueMarkerOptions: ReviewIssueMarkerOption[] = [
  { value: 'none', label: 'No marker' },
  { value: 'evidence_gap', label: 'Evidence gap' },
  { value: 'scope_gap', label: 'Scope gap' },
  { value: 'modeling_gap', label: 'Modeling gap' },
  { value: 'handoff_gap', label: 'Handoff gap' },
  { value: 'contract_gap', label: 'Contract gap' },
  { value: 'follow_up', label: 'Follow-up' },
]

const reviewSurfaces: ReviewSurface[] = [
  {
    id: 'viewer',
    title: 'Structural Optimization Viewer',
    description: '행 단위 provenance, 결과 탐색, 3D traceability를 여는 메인 리뷰 표면입니다.',
    href: './implementation/phase1/release/visualization/structural_optimization_viewer.html',
    badge: 'Primary',
    kind: 'html',
  },
  {
    id: 'drawing-review',
    title: 'Optimized Drawing Review',
    description: '최적화 도면, 전문검토 handoff, SVG 기반 리뷰 흐름을 확인합니다.',
    href: './implementation/phase1/release/visualization/optimized_drawing_review.html',
    badge: 'Drawing',
    kind: 'html',
  },
  {
    id: 'real-drawing-3d',
    title: 'Real Drawing 3D Viewer',
    description: '구한 도면의 파생 topology를 기존 구조 웹뷰어 preset으로 통합해 확인합니다.',
    href: './src/structure-viewer/index.html?preset=real_drawing_private_3d',
    badge: 'Private 3D',
    kind: 'html',
  },
  {
    id: 'benchmark-review',
    title: 'Benchmark Review',
    description: 'Canton Tower와 PEER blind benchmark를 baseline / AI optimized 비교로 엽니다.',
    href: './implementation/phase1/release/visualization/benchmark_optimization_review.html',
    badge: 'Benchmark',
    kind: 'html',
  },
  {
    id: 'committee',
    title: 'Committee Dashboard',
    description: '위원회 패키지, 릴리즈 서명, 외부 벤치마크 상태를 한 화면에서 추적합니다.',
    href: './implementation/phase1/release/committee_review/committee_review_dashboard.html',
    badge: 'Governance',
    kind: 'html',
  },
]

const reviewSurfaceIdentity: Record<
  ReviewSurfaceId,
  {
    family: string
    mode: string
    track: string
    cue: string
  }
> = {
  viewer: {
    family: 'Immersive dark review',
    mode: '3D evidence desk',
    track: 'Geometry and provenance',
    cue: 'Model geometry, row provenance, and solver traces stay connected in one desk.',
  },
  'drawing-review': {
    family: 'Formal light review',
    mode: 'AI drawing desk',
    track: 'Sheet-level evidence',
    cue: 'Optimized drawing sheets, review notes, and SVG handoff stay audit-ready.',
  },
  'real-drawing-3d': {
    family: 'Private topology review',
    mode: 'Integrated real drawing preset',
    track: 'Derived geometry',
    cue: 'Anonymized derived topology opens in the shared structure viewer without raw drawing URLs or private source paths.',
  },
  'benchmark-review': {
    family: 'Validation light review',
    mode: 'Benchmark desk',
    track: 'Baseline comparison',
    cue: 'Benchmark baselines and AI-optimized deltas remain visible for validation closeout.',
  },
  committee: {
    family: 'Submission light review',
    mode: 'Governance desk',
    track: 'Authority and release boundary',
    cue: 'Committee packets, approvals, and release boundaries read like one delivery surface.',
  },
}

const governanceArtifacts: GovernanceArtifact[] = [
  {
    id: 'gap',
    title: 'Release Gap Report',
    description: '제품화 잔여 리스크와 게이트 근거를 JSON으로 확인합니다.',
    href: './implementation/phase1/release/release_gap_report.json',
    badge: 'Boundary',
    kind: 'json',
  },
  {
    id: 'registry',
    title: 'Project Registry',
    description: '서명 대상 레지스트리, 승인 정보, 패키지 SHA를 추적합니다.',
    href: './implementation/phase1/release/project_registry.json',
    badge: 'Registry',
    kind: 'json',
  },
  {
    id: 'registry-index',
    title: 'Registry Portfolio Index',
    description: '다중 프로젝트 registry 상태를 서비스형 인덱스로 집계합니다.',
    href: './implementation/phase1/release/project_registry_index.json',
    badge: 'Portfolio',
    kind: 'json',
  },
  {
    id: 'package',
    title: 'Project Package ZIP',
    description: '검토/제출용 deterministic package 아카이브를 바로 엽니다.',
    href: './implementation/phase1/release/project_package.zip',
    badge: 'Package',
    kind: 'file',
  },
  {
    id: 'signature',
    title: 'Registry Signature',
    description: 'project registry 서명 결과를 base64 artifact로 확인합니다.',
    href: './implementation/phase1/release/signing/project_registry.signature.b64',
    badge: 'Signature',
    kind: 'file',
  },
  {
    id: 'batch',
    title: 'Batch Job Report',
    description: '외부 벤치마크 재실행/대기/스냅샷 상태를 runtime report로 확인합니다.',
    href: './implementation/phase1/release/external_benchmark_kickoff/external_benchmark_batch_job_report.json',
    badge: 'Ops',
    kind: 'json',
  },
]

const legacyViewers: Surface[] = [
  {
    id: 'legacy-3d',
    title: 'Legacy 3D Viewer',
    description: 'Three.js 기반 원본 구조 viewer 프로토타입입니다.',
    href: './src/structure-viewer/index.html',
    badge: 'Legacy',
    kind: 'html',
  },
  {
    id: 'legacy-charts',
    title: 'Legacy Charts',
    description: '차트/selection handoff 프로토타입을 빠르게 점검합니다.',
    href: './src/structure-viewer/charts.html',
    badge: 'Legacy',
    kind: 'html',
  },
  {
    id: 'legacy-history',
    title: 'Optimization History',
    description: '초기 optimization history surface를 바로 엽니다.',
    href: './src/structure-viewer/optimization_history.html',
    badge: 'Legacy',
    kind: 'html',
  },
]

function createDefaultAuthoringControls(): AuthoringControls {
  return {
    familyId: 'sample_tower',
    storyCount: 5,
    bayCount: 3,
    floorHeightM: 3.9,
    loadPatternCount: 4,
    sectionId: 'steel_h_600x200',
  }
}

function createDefaultAuthoringFamilyOptions(): AuthoringFamilyOption[] {
  return [
    {
      familyId: 'sample_tower',
      label: 'Sample Tower',
      description: 'RC column + frame beam baseline scaffold.',
      defaultStoryCount: 5,
      defaultBayCount: 3,
      defaultFloorHeightM: 3.9,
      defaultLoadPatternCount: 4,
      defaultSectionId: 'steel_h_600x200',
      defaultBayWidthM: 8,
    },
    {
      familyId: 'steel_braced_frame',
      label: 'Steel Braced Frame',
      description: 'Steel frame with brace-rich lateral system.',
      defaultStoryCount: 6,
      defaultBayCount: 4,
      defaultFloorHeightM: 4.5,
      defaultLoadPatternCount: 6,
      defaultSectionId: 'steel_h_600x200',
      defaultBayWidthM: 8.5,
    },
    {
      familyId: 'rc_wall_core',
      label: 'RC Wall Core',
      description: 'Wall shell + RC gravity/coupling members.',
      defaultStoryCount: 9,
      defaultBayCount: 4,
      defaultFloorHeightM: 3.2,
      defaultLoadPatternCount: 6,
      defaultSectionId: 'rc_column_700x700',
      defaultBayWidthM: 7.2,
    },
    {
      familyId: 'composite_podium',
      label: 'Composite Podium',
      description: 'Composite podium with slabs and CFT columns.',
      defaultStoryCount: 7,
      defaultBayCount: 4,
      defaultFloorHeightM: 4.2,
      defaultLoadPatternCount: 6,
      defaultSectionId: 'deck_beam_500x250',
      defaultBayWidthM: 9,
    },
    {
      familyId: 'outrigger_transfer_tower',
      label: 'Outrigger Transfer Tower',
      description: 'Composite mega-columns with outrigger transfers and deck diaphragms.',
      defaultStoryCount: 10,
      defaultBayCount: 5,
      defaultFloorHeightM: 4.1,
      defaultLoadPatternCount: 6,
      defaultSectionId: 'steel_h_600x200',
      defaultBayWidthM: 8.8,
    },
    {
      familyId: 'dual_system_hospital',
      label: 'Dual-System Hospital',
      description: 'RC wall-core hospital scaffold with mixed RC/CFT supports and floor shells.',
      defaultStoryCount: 8,
      defaultBayCount: 5,
      defaultFloorHeightM: 4,
      defaultLoadPatternCount: 6,
      defaultSectionId: 'steel_h_600x200',
      defaultBayWidthM: 8.2,
    },
    {
      familyId: 'belt_truss_mega_frame',
      label: 'Belt-Truss Mega Frame',
      description: 'Belt-truss mega frame with perimeter transfer and belt bracing.',
      defaultStoryCount: 12,
      defaultBayCount: 6,
      defaultFloorHeightM: 4.2,
      defaultLoadPatternCount: 6,
      defaultSectionId: 'steel_h_600x200',
      defaultBayWidthM: 8.6,
    },
    {
      familyId: 'deep_transfer_basement',
      label: 'Deep Transfer Basement',
      description: 'Deep transfer basement scaffold with transfer slabs and retaining support.',
      defaultStoryCount: 6,
      defaultBayCount: 4,
      defaultFloorHeightM: 4.4,
      defaultLoadPatternCount: 6,
      defaultSectionId: 'steel_h_600x200',
      defaultBayWidthM: 7.6,
    },
  ]
}

function isRecord(value: unknown): value is JsonRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function asBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') {
    return value
  }
  if (value === 'true') {
    return true
  }
  if (value === 'false') {
    return false
  }
  return null
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = asNumber(value)
    if (parsed !== null) {
      return parsed
    }
  }
  return null
}

function firstBoolean(...values: unknown[]): boolean | null {
  for (const value of values) {
    const parsed = asBoolean(value)
    if (parsed !== null) {
      return parsed
    }
  }
  return null
}

function getRecord(source: unknown, key: string): JsonRecord {
  if (!isRecord(source)) {
    return {}
  }
  const value = source[key]
  return isRecord(value) ? value : {}
}

function getArray(source: unknown, key: string): unknown[] {
  if (!isRecord(source)) {
    return []
  }
  const value = source[key]
  return Array.isArray(value) ? value : []
}

function firstRecord(
  values: unknown[],
  predicate?: (value: JsonRecord) => boolean,
): JsonRecord {
  for (const value of values) {
    if (!isRecord(value)) {
      continue
    }
    if (!predicate || predicate(value)) {
      return value
    }
  }
  return {}
}

function tokenString(value: unknown): string {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return ''
}

function recordSize(record: JsonRecord): number {
  return Object.keys(record).length
}

function arraySize(value: unknown): number {
  return Array.isArray(value) ? value.length : 0
}

function hasAuthoringControlKeys(record: JsonRecord): boolean {
  return [
    'familyId',
    'family_id',
    'authoringFamilyId',
    'authoring_family_id',
    'default_family_id',
    'storyCount',
    'story_count',
    'bayCount',
    'bay_count',
    'floorHeightM',
    'floor_height_m',
    'loadPatternCount',
    'load_pattern_count',
    'sectionId',
    'section_id',
    'default_section_id',
  ].some((key) => record[key] !== undefined)
}

function getAuthoringControlSource(source: unknown): JsonRecord {
  return firstRecord(
    [
      getRecord(source, 'authoring_controls'),
      getRecord(source, 'authoringControls'),
      getRecord(source, 'editor_controls'),
      isRecord(source) ? source : {},
    ],
    hasAuthoringControlKeys,
  )
}

function parseAuthoringControls(
  source: unknown,
  fallback: AuthoringControls = createDefaultAuthoringControls(),
): AuthoringControls | null {
  const controlSource = getAuthoringControlSource(source)
  if (!recordSize(controlSource)) {
    return null
  }

  return {
    familyId:
      tokenString(controlSource.familyId)
      || tokenString(controlSource.family_id)
      || tokenString(controlSource.authoringFamilyId)
      || tokenString(controlSource.authoring_family_id)
      || tokenString(controlSource.default_family_id)
      || fallback.familyId,
    storyCount: clampNumber(
      firstNumber(controlSource.storyCount, controlSource.story_count),
      fallback.storyCount,
      1,
      40,
    ),
    bayCount: clampNumber(
      firstNumber(controlSource.bayCount, controlSource.bay_count),
      fallback.bayCount,
      1,
      12,
    ),
    floorHeightM: clampNumber(
      firstNumber(controlSource.floorHeightM, controlSource.floor_height_m),
      fallback.floorHeightM,
      2.5,
      6,
    ),
    loadPatternCount: clampNumber(
      firstNumber(controlSource.loadPatternCount, controlSource.load_pattern_count),
      fallback.loadPatternCount,
      1,
      12,
    ),
    sectionId:
      tokenString(controlSource.sectionId)
      || tokenString(controlSource.section_id)
      || tokenString(controlSource.default_section_id)
      || fallback.sectionId,
  }
}

function buildBaselineAuthoringControls(resource: ResourceState): AuthoringControls {
  return parseAuthoringControls(resource.data, createDefaultAuthoringControls())
    ?? createDefaultAuthoringControls()
}

function buildAuthoringFamilyOptions(resource: ResourceState): AuthoringFamilyOption[] {
  const defaultOptions = createDefaultAuthoringFamilyOptions()
  const defaultMap = new Map(defaultOptions.map((option) => [option.familyId, option]))
  const editorControls = getRecord(resource.data, 'editor_controls')
  const familyPalette = getArray(editorControls, 'family_palette').filter(isRecord)
  const selectedFamily = getRecord(resource.data, 'selected_family')

  const optionMap = new Map(defaultMap)
  for (const familyRecord of familyPalette) {
    const familyId = tokenString(familyRecord.family_id)
    if (!familyId) {
      continue
    }
    const base = optionMap.get(familyId) ?? createDefaultAuthoringFamilyOptions()[0]
    optionMap.set(familyId, {
      familyId,
      label: asString(familyRecord.label) || base.label,
      description: asString(familyRecord.description) || base.description,
      defaultStoryCount: clampNumber(asNumber(familyRecord.default_story_count), base.defaultStoryCount, 1, 40),
      defaultBayCount: clampNumber(asNumber(familyRecord.default_bay_count), base.defaultBayCount, 1, 12),
      defaultFloorHeightM: clampNumber(asNumber(familyRecord.default_floor_height_m), base.defaultFloorHeightM, 2.5, 6),
      defaultLoadPatternCount: clampNumber(
        asNumber(familyRecord.default_load_pattern_count),
        base.defaultLoadPatternCount,
        1,
        12,
      ),
      defaultSectionId:
        tokenString(familyRecord.default_section_id) || base.defaultSectionId,
      defaultBayWidthM: clampNumber(asNumber(familyRecord.default_bay_width_m), base.defaultBayWidthM, 4, 15),
    })
  }

  const selectedFamilyId = tokenString(selectedFamily.family_id)
  if (selectedFamilyId && !optionMap.has(selectedFamilyId)) {
    optionMap.set(selectedFamilyId, {
      familyId: selectedFamilyId,
      label: asString(selectedFamily.label) || selectedFamilyId,
      description: asString(selectedFamily.description) || 'Release-selected authoring family.',
      defaultStoryCount: clampNumber(asNumber(selectedFamily.default_story_count), 5, 1, 40),
      defaultBayCount: clampNumber(asNumber(selectedFamily.default_bay_count), 3, 1, 12),
      defaultFloorHeightM: clampNumber(asNumber(selectedFamily.default_floor_height_m), 3.9, 2.5, 6),
      defaultLoadPatternCount: clampNumber(asNumber(selectedFamily.default_load_pattern_count), 4, 1, 12),
      defaultSectionId: tokenString(selectedFamily.default_section_id) || 'steel_h_600x200',
      defaultBayWidthM: clampNumber(asNumber(selectedFamily.default_bay_width_m), 8, 4, 15),
    })
  }

  return [...optionMap.values()].sort((left, right) => {
    const leftIndex = defaultOptions.findIndex((option) => option.familyId === left.familyId)
    const rightIndex = defaultOptions.findIndex((option) => option.familyId === right.familyId)
    if (leftIndex >= 0 && rightIndex >= 0) {
      return leftIndex - rightIndex
    }
    if (leftIndex >= 0) {
      return -1
    }
    if (rightIndex >= 0) {
      return 1
    }
    return left.label.localeCompare(right.label)
  })
}

function findAuthoringFamilyOption(
  options: AuthoringFamilyOption[],
  familyId: string,
): AuthoringFamilyOption {
  return options.find((option) => option.familyId === familyId) ?? options[0] ?? createDefaultAuthoringFamilyOptions()[0]
}

function buildAuthoringSectionOptions(
  palette: string[],
  familyOption: AuthoringFamilyOption,
): string[] {
  return uniqueTokens([
    familyOption.defaultSectionId,
    ...palette,
  ])
}

function normalizeArtifactHref(path: unknown): string {
  const token = tokenString(path)
  if (!token) {
    return ''
  }
  if (/^(?:https?:|data:|mailto:|#|\.\/|\/)/.test(token)) {
    return token
  }
  return `./${token.replace(/^\.?\//, '')}`
}

function buildAuthoringPortfolioFamilySnapshots(
  resource: ResourceState,
  fallbackOptions: AuthoringFamilyOption[],
): AuthoringPortfolioFamilySnapshot[] {
  const rows = getArray(resource.data, 'family_rows').filter(isRecord)
  return rows.map((row) => {
    const familyId = tokenString(row.family_id)
    const familyOption = findAuthoringFamilyOption(
      fallbackOptions,
      familyId || createDefaultAuthoringControls().familyId,
    )
    const artifacts = getRecord(row, 'artifacts')
    const contractPass = firstBoolean(row.contract_pass)
    return {
      familyId: familyId || familyOption.familyId,
      label: familyOption.label,
      draftLabel: tokenString(row.draft_label) || 'baseline',
      statusLabel: contractPass ? 'lane ready' : 'lane check',
      tone: contractPass ? 'ok' : 'warn',
      comboCount: firstNumber(row.solver_combo_count),
      meshRequestCount: firstNumber(row.solver_mesh_request_count),
      snapshotCount: firstNumber(row.snapshot_count),
      note: asString(row.summary_line) || `${familyOption.label} commercialization lane`,
      workspaceHref: normalizeArtifactHref(artifacts.workspace_summary_json),
      solverHref: normalizeArtifactHref(artifacts.solver_session_json),
      registryHref: normalizeArtifactHref(artifacts.project_registry_json),
    }
  })
}

function buildFamilyRowMap(resource: ResourceState): Map<string, JsonRecord> {
  return new Map(
    getArray(resource.data, 'family_rows')
      .filter(isRecord)
      .map((row) => [tokenString(row.family_id), row] as const)
      .filter(([familyId]) => Boolean(familyId)),
  )
}

function buildCoverageCellStatus(prefix: string, ready: boolean | null): { statusLabel: string; tone: StatusTone } {
  if (ready === null) {
    return {
      statusLabel: `${prefix} missing`,
      tone: 'missing',
    }
  }

  return {
    statusLabel: ready ? `${prefix} ready` : `${prefix} check`,
    tone: ready ? 'ok' : 'warn',
  }
}

function buildAuthoringFamilyCoverageCell(
  prefix: string,
  ready: boolean | null,
  summary: string,
  note: string,
): AuthoringFamilyCoverageCell {
  const status = buildCoverageCellStatus(prefix, ready)
  const normalizedSummary = summary.trim()
  const normalizedNote = note.trim()

  return {
    statusLabel: status.statusLabel,
    tone: status.tone,
    summary: normalizedSummary || `${prefix} summary unavailable.`,
    note: normalizedNote || `${prefix} summary unavailable.`,
  }
}

function buildAuthoringSolverBreadthCoverageCell(row: JsonRecord | undefined): AuthoringFamilyCoverageCell {
  if (!row) {
    return buildAuthoringFamilyCoverageCell(
      'breadth',
      null,
      'solver breadth summary unavailable.',
      'solver breadth JSON row unavailable.',
    )
  }

  const ready =
    row.broad_solver_family_ready === true
    || row.full_solver_family_ready === true
    || row.solver_ready === true
  return buildAuthoringFamilyCoverageCell(
    'breadth',
    ready,
    [
      `${compactCount(firstNumber(row.solver_combo_count))} combos`,
      `mesh ${compactCount(firstNumber(row.solver_mesh_request_count))}`,
      `members ${compactCount(firstNumber(row.member_type_count))}`,
    ].join(' · '),
    asString(row.summary_line) || asString(row.solver_family_breadth_status) || 'solver breadth summary unavailable.',
  )
}

function buildAuthoringLocalRuntimeDepthCoverageCell(row: JsonRecord | undefined): AuthoringFamilyCoverageCell {
  if (!row) {
    return buildAuthoringFamilyCoverageCell(
      'depth',
      null,
      'runtime depth summary unavailable.',
      'local runtime depth JSON row unavailable.',
    )
  }

  const ready =
    row.scenario_ready === true
    || row.trace_ready === true
    || row.runtime_ready === true
  return buildAuthoringFamilyCoverageCell(
    'depth',
    ready,
    [
      `${compactCount(firstNumber(row.case_count))} cases`,
      `trace ${booleanLabel(firstBoolean(row.trace_ready), 'ready', 'check')}`,
      `runtime ${booleanLabel(firstBoolean(row.runtime_ready), 'ready', 'check')}`,
    ].join(' · '),
    asString(row.summary_line) || asString(row.local_runtime_scenario_depth_status) || 'runtime depth summary unavailable.',
  )
}

function buildAuthoringWritebackBreadthCoverageCell(row: JsonRecord | undefined): AuthoringFamilyCoverageCell {
  if (!row) {
    return buildAuthoringFamilyCoverageCell(
      'writeback',
      null,
      'writeback breadth summary unavailable.',
      'writeback breadth JSON row unavailable.',
    )
  }

  const ready =
    row.broad_writeback_ready === true
    || row.full_breadth_ready === true
    || row.writeback_ready === true
    || row.submission_ready === true
  return buildAuthoringFamilyCoverageCell(
    'writeback',
    ready,
    [
      `${compactCount(firstNumber(row.solver_combo_count))} combos`,
      `mesh ${compactCount(firstNumber(row.solver_mesh_request_count))}`,
      `writeback ${booleanLabel(row.writeback_ready === true || row.submission_ready === true, 'yes', 'check')}`,
    ].join(' · '),
    asString(row.summary_line) || asString(row.writeback_breadth_status) || 'writeback breadth summary unavailable.',
  )
}

function buildAuthoringFamilyCoverageRows(
  familySnapshots: AuthoringPortfolioFamilySnapshot[],
  solverResource: ResourceState,
  depthResource: ResourceState,
  writebackResource: ResourceState,
): AuthoringFamilyCoverageRow[] {
  const solverRowMap = buildFamilyRowMap(solverResource)
  const depthRowMap = buildFamilyRowMap(depthResource)
  const writebackRowMap = buildFamilyRowMap(writebackResource)

  return familySnapshots.map((familySnapshot) => ({
    ...familySnapshot,
    solver: buildAuthoringSolverBreadthCoverageCell(solverRowMap.get(familySnapshot.familyId)),
    depth: buildAuthoringLocalRuntimeDepthCoverageCell(depthRowMap.get(familySnapshot.familyId)),
    writeback: buildAuthoringWritebackBreadthCoverageCell(writebackRowMap.get(familySnapshot.familyId)),
  }))
}

function buildAuthoringFamilyCoverageSnapshot(familyRows: AuthoringFamilyCoverageRow[]): Snapshot {
  if (!familyRows.length) {
    return missingSnapshot('native authoring family coverage matrix를 아직 읽지 못했습니다.')
  }

  const solverReadyCount = familyRows.filter((row) => row.solver.tone === 'ok').length
  const depthReadyCount = familyRows.filter((row) => row.depth.tone === 'ok').length
  const writebackReadyCount = familyRows.filter((row) => row.writeback.tone === 'ok').length
  const alignedCount = familyRows.filter(
    (row) => row.solver.tone === 'ok' && row.depth.tone === 'ok' && row.writeback.tone === 'ok',
  ).length
  const allReady = alignedCount === familyRows.length
  const partiallyReady = solverReadyCount > 0 || depthReadyCount > 0 || writebackReadyCount > 0

  return {
    statusLabel: allReady ? 'family coverage aligned' : 'family coverage check',
    tone: allReady ? 'ok' : partiallyReady ? 'warn' : 'missing',
    metrics: [
      {
        label: 'Families',
        value: compactCount(familyRows.length),
      },
      {
        label: 'Solver',
        value: `${compactCount(solverReadyCount)}/${compactCount(familyRows.length)}`,
      },
      {
        label: 'Depth',
        value: `${compactCount(depthReadyCount)}/${compactCount(familyRows.length)}`,
      },
      {
        label: 'Writeback',
        value: `${compactCount(writebackReadyCount)}/${compactCount(familyRows.length)}`,
      },
      {
        label: 'Aligned',
        value: `${compactCount(alignedCount)}/${compactCount(familyRows.length)}`,
      },
    ],
    note:
      'native authoring ops portfolio를 기준으로 solver family breadth, local runtime scenario depth, writeback breadth를 family key로 조인했습니다.',
    sourceLabel: 'portfolio / solver breadth / runtime depth / writeback breadth',
  }
}

function buildEvidenceSnippet(value: unknown, max = 160): string {
  const raw =
    typeof value === 'string'
      ? value
      : Array.isArray(value) || isRecord(value)
        ? JSON.stringify(value)
        : ''
  const text = raw.replace(/\s+/g, ' ').trim()
  if (!text) {
    return 'evidence unavailable'
  }
  if (text.length <= max) {
    return text
  }
  return `${text.slice(0, max - 1).trimEnd()}…`
}

function buildAdvancedHoldoutRows(resource: ResourceState): AdvancedHoldoutRow[] {
  const rows = getArray(resource.data, 'advanced_holdouts').filter(isRecord)
  return rows.map((row, index) => {
    const ready = firstBoolean(row.ready)
    const statusLabel = asString(row.status_label)
    const releaseBlocking = firstBoolean(row.release_blocking)
    const advisoryOnly = firstBoolean(row.advisory_only)
    const baseStatus = statusLabel
      || (ready === true ? 'closed' : ready === false ? 'open' : 'scoped')
    const isClosed =
      ready === true
      || /(?:closed|ready|pass)/i.test(baseStatus)
    const tone: StatusTone = !isClosed || releaseBlocking ? 'warn' : 'ok'
    const noteSuffix = advisoryOnly ? ' | advisory' : releaseBlocking ? ' | blocking' : ''
    return {
      id: tokenString(row.id) || `advanced-holdout-${index + 1}`,
      title: asString(row.title) || 'Untitled holdout',
      severity: asString(row.severity) || 'n/a',
      status: `${baseStatus}${noteSuffix}`,
      isClosed,
      mode: asString(row.mode) || 'n/a',
      reason: asString(row.reason) || 'reason unavailable',
      evidenceSnippet: buildEvidenceSnippet(row.evidence),
      tone,
    }
  })
}

function buildGapSeveritySnapshot(resource: ResourceState, severity: string): {
  totalCount: number
  readyCount: number
  openCount: number
} {
  const rows = getArray(resource.data, 'remaining_gaps').filter(isRecord)
  const severityRows = rows.filter((row) => asString(row.severity) === severity)
  const readyCount = severityRows.filter((row) => asString(row.status) === 'closed').length
  return {
    totalCount: severityRows.length,
    readyCount,
    openCount: Math.max(severityRows.length - readyCount, 0),
  }
}

function createDefaultReviewRowState(): ReviewRowState {
  return {
    decision: 'unreviewed',
    comment: '',
    issueMarker: 'none',
    updatedAt: '',
  }
}

function isPriorityReviewSeverity(severity: string): boolean {
  return /^P[0-4]$/.test(severity)
}

function buildReviewableGapRows(resource: ResourceState): ReviewableGapRow[] {
  const rows = getArray(resource.data, 'remaining_gaps').filter(isRecord)
  return rows
    .filter((row) => isPriorityReviewSeverity(asString(row.severity)))
    .map((row, index) => {
      const severity = asString(row.severity) || 'P0'
      const gapStatus = asString(row.status) || 'open'
      const isClosed = gapStatus === 'closed'
      return {
        id: tokenString(row.id) || `review-gap-${index + 1}`,
        severity,
        gapStatus,
        title: asString(row.title) || 'Untitled gap',
        why: asString(row.why) || 'Why unavailable',
        evidence: buildEvidenceSnippet(row.evidence, 220),
        exitCriteria: asString(row.exit_criteria) || 'Exit criteria unavailable.',
        statusLabel: isClosed ? 'closed' : 'open',
        tone: isClosed ? 'ok' : 'warn',
      }
    })
}

function reviewDecisionLabel(decision: ReviewDecision): string {
  switch (decision) {
    case 'approved':
      return 'approved'
    case 'rejected':
      return 'rejected'
    case 'needs_engineer_review':
      return 'needs engineer review'
    case 'unreviewed':
    default:
      return 'unreviewed'
  }
}

function reviewDecisionTone(decision: ReviewDecision): StatusTone {
  switch (decision) {
    case 'approved':
      return 'ok'
    case 'rejected':
    case 'needs_engineer_review':
      return 'warn'
    case 'unreviewed':
    default:
      return 'missing'
  }
}

function reviewIssueMarkerLabel(marker: ReviewIssueMarker): string {
  switch (marker) {
    case 'evidence_gap':
      return 'evidence gap'
    case 'scope_gap':
      return 'scope gap'
    case 'modeling_gap':
      return 'modeling gap'
    case 'handoff_gap':
      return 'handoff gap'
    case 'contract_gap':
      return 'contract gap'
    case 'follow_up':
      return 'follow-up'
    case 'none':
    default:
      return 'none'
  }
}

function normalizeReviewDecision(value: unknown): ReviewDecision {
  const token = tokenString(value).toLowerCase().replace(/\s+/g, '_')
  if (token === 'approved' || token === 'rejected' || token === 'needs_engineer_review') {
    return token
  }
  return 'unreviewed'
}

function normalizeReviewIssueMarker(value: unknown): ReviewIssueMarker {
  const token = tokenString(value).toLowerCase().replace(/\s+/g, '_')
  if (
    token === 'evidence_gap'
    || token === 'scope_gap'
    || token === 'modeling_gap'
    || token === 'handoff_gap'
    || token === 'contract_gap'
    || token === 'follow_up'
  ) {
    return token
  }
  return 'none'
}

function parseReviewRowState(source: unknown): ReviewRowState {
  if (!isRecord(source)) {
    return createDefaultReviewRowState()
  }

  return {
    decision: normalizeReviewDecision(
      source.decision ?? source.review_decision ?? source.status ?? source.review_status,
    ),
    comment: asString(source.comment ?? source.review_comment ?? source.note),
    issueMarker: normalizeReviewIssueMarker(
      source.issueMarker ?? source.issue_marker ?? source.marker ?? source.issue_tag,
    ),
    updatedAt:
      asString(source.updatedAt)
      || asString(source.updated_at)
      || asString(source.reviewed_at)
      || asString(source.saved_at),
  }
}

function buildReviewStateMapFromSource(source: unknown): Record<string, ReviewRowState> | null {
  if (!isRecord(source)) {
    return null
  }

  const map: Record<string, ReviewRowState> = {}

  if (Array.isArray(source.rows)) {
    for (const row of source.rows.filter(isRecord)) {
      const id = tokenString(row.id ?? row.row_id ?? row.gap_id)
      if (!id) {
        continue
      }
      map[id] = parseReviewRowState(isRecord(row.review_state) ? row.review_state : row)
    }
    return map
  }

  const rowStates = firstRecord(
    [
      getRecord(source, 'row_states'),
      getRecord(source, 'review_state'),
      getRecord(source, 'review_rows'),
    ],
    (value) => recordSize(value) > 0,
  )

  if (!recordSize(rowStates)) {
    if ('row_states' in source || 'review_state' in source || 'review_rows' in source) {
      return {}
    }
    return null
  }

  for (const [rowId, rowState] of Object.entries(rowStates)) {
    const id = tokenString(rowId)
    if (!id) {
      continue
    }
    map[id] = parseReviewRowState(rowState)
  }

  return map
}

function buildReviewStateSummary(
  reviewRows: ReviewableGapRow[],
  reviewStateMap: Record<string, ReviewRowState>,
): Snapshot {
  if (!reviewRows.length) {
    return missingSnapshot('priority review rows를 아직 읽지 못했습니다.')
  }

  const approvedCount = reviewRows.filter((row) => reviewStateMap[row.id]?.decision === 'approved').length
  const rejectedCount = reviewRows.filter((row) => reviewStateMap[row.id]?.decision === 'rejected').length
  const engineerReviewCount = reviewRows.filter(
    (row) => reviewStateMap[row.id]?.decision === 'needs_engineer_review',
  ).length
  const reviewedCount = reviewRows.filter((row) => reviewStateMap[row.id]?.decision !== 'unreviewed').length
  const commentCount = reviewRows.filter((row) => Boolean(reviewStateMap[row.id]?.comment.trim())).length
  const issueMarkerCount = reviewRows.filter((row) => reviewStateMap[row.id]?.issueMarker !== 'none').length
  const allReviewed = reviewedCount === reviewRows.length
  const partlyReviewed = reviewedCount > 0

  return {
    statusLabel: allReviewed ? 'review board captured' : partlyReviewed ? 'review board active' : 'review board open',
    tone: allReviewed ? 'ok' : partlyReviewed ? 'warn' : 'missing',
    metrics: [
      { label: 'Rows', value: compactCount(reviewRows.length) },
      { label: 'Reviewed', value: `${compactCount(reviewedCount)}/${compactCount(reviewRows.length)}` },
      { label: 'Approved', value: compactCount(approvedCount) },
      { label: 'Rejected', value: compactCount(rejectedCount) },
      { label: 'Needs review', value: compactCount(engineerReviewCount) },
      { label: 'Comments', value: compactCount(commentCount) },
      { label: 'Markers', value: compactCount(issueMarkerCount) },
    ],
    note:
      'browser storage에만 남는 local review state입니다. export/import로 row-level approvals, rejects, engineer review flags, comments, issue markers를 보존합니다.',
    sourceLabel: 'local review state',
  }
}

function buildReviewStateStoragePayload(reviewStateMap: Record<string, ReviewRowState>): JsonRecord {
  const orderedRowStates = Object.fromEntries(
    Object.entries(reviewStateMap)
      .sort(([leftId], [rightId]) => leftId.localeCompare(rightId))
      .map(([rowId, rowState]) => [rowId, rowState] as const),
  )

  return {
    format: 'release-gap-local-review-state',
    version: 1,
    saved_at: new Date().toISOString(),
    row_states: orderedRowStates,
  }
}

function buildReviewStateExportPayload(
  reviewRows: ReviewableGapRow[],
  reviewStateMap: Record<string, ReviewRowState>,
  sourceHref: string,
): JsonRecord {
  const orderedRowStates = reviewRows.map((row) => {
    const rowState = reviewStateMap[row.id] ?? createDefaultReviewRowState()
    return {
      id: row.id,
      title: row.title,
      severity: row.severity,
      gap_status: row.gapStatus,
      status_label: row.statusLabel,
      why: row.why,
      evidence: row.evidence,
      exit_criteria: row.exitCriteria,
      decision: rowState.decision,
      decision_label: reviewDecisionLabel(rowState.decision),
      comment: rowState.comment,
      issue_marker: rowState.issueMarker,
      issue_marker_label: reviewIssueMarkerLabel(rowState.issueMarker),
      updated_at: rowState.updatedAt,
    }
  })

  const summary = buildReviewStateSummary(reviewRows, reviewStateMap)

  return {
    format: 'release-gap-local-review-state',
    version: 1,
    generated_at: new Date().toISOString(),
    source: {
      href: sourceHref,
      label: sourceLabel(sourceHref),
    },
    scope: 'P0-P4',
    summary: {
      status_label: summary.statusLabel,
      reviewed_rows: summary.metrics[1]?.value ?? 'n/a',
      approved_count: summary.metrics[2]?.value ?? 'n/a',
      rejected_count: summary.metrics[3]?.value ?? 'n/a',
      needs_review_count: summary.metrics[4]?.value ?? 'n/a',
      comment_count: summary.metrics[5]?.value ?? 'n/a',
      issue_marker_count: summary.metrics[6]?.value ?? 'n/a',
    },
    rows: orderedRowStates,
  }
}

function buildReviewStateExportHref(
  reviewRows: ReviewableGapRow[],
  reviewStateMap: Record<string, ReviewRowState>,
  sourceHref: string,
): string {
  return `data:application/json;charset=utf-8,${encodeURIComponent(
    JSON.stringify(buildReviewStateExportPayload(reviewRows, reviewStateMap, sourceHref), null, 2),
  )}`
}

function buildCommercializationDepthSignal(
  label: string,
  detail: string,
  readyHint: boolean | null,
  requiredTokens: string[] = [],
): CommercializationDepthSignal {
  const normalizedDetail = detail.trim()
  const loweredDetail = normalizedDetail.toLowerCase()
  const readyByTokens = !requiredTokens.length || requiredTokens.every((token) => loweredDetail.includes(token))
  const ready =
    readyHint === true
    || ((/\bpass\b/i.test(normalizedDetail) || /\bready\b/i.test(normalizedDetail)) && readyByTokens)
  const missing = !normalizedDetail && readyHint === null
  return {
    label,
    statusLabel: missing ? 'missing' : ready ? 'ready' : 'check',
    detail: normalizedDetail || `${label} summary unavailable.`,
    ready,
    tone: missing ? 'missing' : ready ? 'ok' : 'warn',
  }
}

function buildCommercializationDepthSignals(resource: ResourceState): CommercializationDepthSignal[] {
  const summary = getRecord(resource.data, 'summary')
  const loadDetail = asString(summary.load_combination_editor_commercialization_summary_line)
    || asString(summary.load_combination_engine_summary_line)
  const windDetail = asString(summary.wind_workflow_summary_line)
    || [asString(summary.wind_tunnel_mapping_mode), asString(summary.wind_tunnel_mapping_reason)]
      .filter(Boolean)
      .join(' | ')
  const advancedSsiDetail = asString(summary.advanced_ssi_summary_line)
    || asString(summary.foundation_soil_link_summary_line)
  const referenceRegressionDetail = asString(summary.reference_regression_summary_line)

  return [
    buildCommercializationDepthSignal(
      'Material',
      asString(summary.material_constitutive_summary_line),
      firstBoolean(summary.material_constitutive_pass),
    ),
    buildCommercializationDepthSignal(
      'Load',
      loadDetail,
      firstBoolean(summary.load_combination_editor_commercialization_pass, summary.load_combination_engine_pass),
    ),
    buildCommercializationDepthSignal(
      'Reference regression',
      referenceRegressionDetail,
      firstBoolean(summary.reference_regression_pass),
    ),
    buildCommercializationDepthSignal(
      'Advanced SSI',
      advancedSsiDetail,
      firstBoolean(summary.advanced_ssi_pass),
    ),
    buildCommercializationDepthSignal(
      'Wind',
      windDetail,
      firstBoolean(summary.wind_workflow_pass, summary.wind_tunnel_raw_mapping_ready),
    ),
  ]
}

function buildCommercialWorkflowBreadthSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('commercial workflow breadth JSON을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const checks = getRecord(resource.data, 'checks')
  const contractPass = firstBoolean(checks.pass, resource.data.contract_pass)
  const constructionReady = firstBoolean(summary.construction_stage_ready)
  const railReady = firstBoolean(summary.rail_tunnel_ready)
  const redesignReady = firstBoolean(summary.design_redesign_loop_ready)

  return {
    statusLabel: contractPass ? 'workflow breadth ready' : 'workflow breadth check',
    tone: contractPass ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Construction',
        value: constructionReady ? 'ready' : 'check',
      },
      {
        label: 'Rail',
        value: railReady ? 'ready' : 'check',
      },
      {
        label: 'Redesign',
        value: redesignReady ? 'ready' : 'check',
      },
      {
        label: 'Clauses',
        value: compactCount(firstNumber(summary.governing_clause_count)),
      },
      {
        label: 'Actions',
        value: compactCount(firstNumber(summary.rail_tunnel_recommended_action_count)),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || 'construction-stage, rail/tunnel, redesign-loop breadth summary',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildDeveloperPreviewSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('Developer Preview readiness JSON을 아직 읽지 못했습니다.')
  }
  const categories = getRecord(resource.data, 'categories')
  const numerical = getRecord(categories, 'numerical')
  const benchmark = getRecord(categories, 'benchmark')
  const softwareProduct = getRecord(categories, 'software product')
  const futureCommercial = getRecord(categories, 'future commercial')
  const ready = firstBoolean(resource.data.developer_preview_ready)
  const blockerCount = firstNumber(resource.data.blocker_count) ?? 0
  const futureCount = firstNumber(resource.data.future_commercial_blocker_count) ?? 0
  const scope = getRecord(resource.data, 'scope')
  const includedScope = getArray(scope, 'included').map(asString).filter(Boolean)
  const excludedScope = getArray(scope, 'excluded').map(asString).filter(Boolean)
  const scopeSummary = includedScope.length
    ? includedScope.slice(0, 2).join('; ')
    : 'public/open benchmark import and local GUI review'
  const exclusionSummary = excludedScope.length
    ? excludedScope.slice(0, 3).join('; ')
    : 'permit automation; engineer replacement; SaaS/account/license server'
  return {
    statusLabel: ready ? 'Developer Preview ready' : 'Developer Preview blocked',
    tone: ready ? 'ok' : 'warn',
    metrics: [
      { label: 'Numerical', value: compactCount(firstNumber(numerical.blocker_count) ?? 0) },
      { label: 'Benchmark', value: compactCount(firstNumber(benchmark.blocker_count) ?? 0) },
      { label: 'Software product', value: compactCount(firstNumber(softwareProduct.blocker_count) ?? 0) },
      { label: 'Future commercial', value: compactCount(futureCount), note: 'visible, non-blocking for Developer Preview' },
      { label: 'Scope', value: compactCount(includedScope.length), note: scopeSummary },
      { label: 'Excluded', value: compactCount(excludedScope.length), note: exclusionSummary },
    ],
    note: `Developer Preview blockers=${compactCount(blockerCount)}; scope=${scopeSummary}; excludes=${exclusionSummary}; customer shadow, license/legal approval, commercial SLA, 30-run CI streak, and external approval receipts remain Commercial Release blockers.`,
    sourceLabel: resource.source || 'developer_preview_readiness.json',
  }
}

function buildCoreApiContractSnapshot(resultResource: ResourceState, reportResource: ResourceState): Snapshot {
  if (
    resultResource.status !== 'ready'
    || reportResource.status !== 'ready'
    || !resultResource.data
    || !reportResource.data
  ) {
    return missingSnapshot('Phase 1 core API result/report JSON을 아직 읽지 못했습니다.')
  }
  const result = resultResource.data
  const report = reportResource.data
  const resultStatus = asString(result.status) || 'missing'
  const reportStatus = asString(report.status) || 'missing'
  const contractPass = firstBoolean(report.contract_pass)
  const convergenceRows = getArray(result, 'convergence_history').filter(isRecord)
  const unsupportedRows = getArray(result, 'unsupported_features').filter(isRecord)
  const blockedFields = getArray(report, 'developer_preview_blocked_fields')
  const metrics = getRecord(result, 'metrics')
  const nodeCount = firstNumber(metrics.node_count)
  const elementCount = firstNumber(metrics.element_count)
  const checksum = asString(result.input_checksum)
  return {
    statusLabel: contractPass ? 'Core API contract ready' : 'Core API contract blocked',
    tone: contractPass ? 'ok' : 'warn',
    metrics: [
      { label: 'Result', value: resultStatus },
      { label: 'Report', value: reportStatus },
      { label: 'Nodes', value: compactCount(nodeCount) },
      { label: 'Elements', value: compactCount(elementCount) },
      { label: 'Convergence', value: compactCount(convergenceRows.length) },
      { label: 'Unsupported', value: compactCount(unsupportedRows.length || blockedFields.length) },
    ],
    note: `schema=${asString(result.claim_boundary_version) || 'unknown'}; checksum=${shorten(checksum, 22)}; GUI reads stable AnalysisResult and ValidationReport JSON, not generated HTML.`,
    sourceLabel: `${sourceLabel(resultResource.source)} + ${sourceLabel(reportResource.source)}`,
  }
}

function buildAuthoringFamilyCorpusSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring family corpus summary를 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const attached = firstBoolean(summary.native_authoring_family_corpus_attached)
  const ready = firstBoolean(summary.native_authoring_family_corpus_pass)
  const familyCount = firstNumber(summary.native_authoring_family_corpus_family_count)
  const readyFamilyCount = firstNumber(summary.native_authoring_family_corpus_ready_family_count)
  const publicReferenceCount = firstNumber(summary.native_authoring_family_corpus_public_reference_count)
  const benchmarkReferenceCount = firstNumber(summary.native_authoring_family_corpus_benchmark_reference_count)
  const authorityReferenceCount = firstNumber(summary.native_authoring_family_corpus_authority_reference_count)
  const unresolvedReferenceCount = firstNumber(summary.native_authoring_family_corpus_unresolved_reference_count)

  return {
    statusLabel: attached ? (ready ? 'family corpus ready' : 'family corpus check') : 'family corpus missing',
    tone: !attached ? 'missing' : ready ? 'ok' : 'warn',
    metrics: [
      { label: 'Families', value: compactCount(familyCount) },
      { label: 'Ready', value: compactCount(readyFamilyCount) },
      { label: 'Public refs', value: compactCount(publicReferenceCount) },
      { label: 'Benchmark', value: compactCount(benchmarkReferenceCount) },
      { label: 'Authority', value: compactCount(authorityReferenceCount) },
      { label: 'Unresolved', value: compactCount(unresolvedReferenceCount) },
    ],
    note:
      asString(summary.native_authoring_family_corpus_summary_line)
      || '8-family corpus linkage summary unavailable.',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringFamilyLocalEvidenceSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring family local evidence summary를 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const attached = firstBoolean(summary.native_authoring_family_local_evidence_attached)
  const ready = firstBoolean(summary.native_authoring_family_local_evidence_pass)

  return {
    statusLabel: attached ? (ready ? 'local evidence ready' : 'local evidence check') : 'local evidence missing',
    tone: !attached ? 'missing' : ready ? 'ok' : 'warn',
    metrics: [
      { label: 'Families', value: compactCount(firstNumber(summary.native_authoring_family_local_evidence_family_count)) },
      { label: 'Concrete', value: compactCount(firstNumber(summary.native_authoring_family_local_evidence_concrete_count)) },
      { label: 'Roundtrip', value: compactCount(firstNumber(summary.native_authoring_family_local_evidence_roundtrip_count)) },
      { label: 'Benchmark', value: compactCount(firstNumber(summary.native_authoring_family_local_evidence_benchmark_concrete_count)) },
      { label: 'Review', value: compactCount(firstNumber(summary.native_authoring_family_local_evidence_review_concrete_count)) },
      { label: 'Registered-only', value: compactCount(firstNumber(summary.native_authoring_family_local_evidence_registered_only_count)) },
    ],
    note:
      asString(summary.native_authoring_family_local_evidence_summary_line)
      || 'family-local evidence summary unavailable.',
    sourceLabel: sourceLabel(resource.source),
  }
}

function estimateAuthoringMemberCount(familyId: string, storyCount: number, bayCount: number): number {
  switch (familyId) {
    case 'steel_braced_frame':
      return storyCount * (4 * bayCount + 1)
    case 'rc_wall_core':
      return storyCount * (2 * bayCount + 1)
    case 'composite_podium':
      return storyCount * (3 * bayCount + 1)
    case 'belt_truss_mega_frame':
      return storyCount * (3 * bayCount + 5)
    case 'deep_transfer_basement':
      return storyCount * (3 * bayCount + 4)
    case 'sample_tower':
    default:
      return storyCount * (2 * bayCount + 1)
  }
}

function buildAuthoringDraftPayload(controls: AuthoringControls): JsonRecord {
  return {
    format: 'native-authoring-workspace-draft',
    version: 1,
    authoring_controls: {
      family_id: controls.familyId,
      story_count: controls.storyCount,
      bay_count: controls.bayCount,
      floor_height_m: Number(controls.floorHeightM.toFixed(1)),
      load_pattern_count: controls.loadPatternCount,
      section_id: controls.sectionId,
    },
  }
}

function buildAuthoringExportHref(controls: AuthoringControls): string {
  return `data:application/json;charset=utf-8,${encodeURIComponent(
    JSON.stringify(buildAuthoringDraftPayload(controls), null, 2),
  )}`
}

function classifyAuthoringSectionFamily(sectionId: string): string {
  const normalized = tokenString(sectionId).toLowerCase()
  if (!normalized) {
    return 'unknown'
  }
  if (normalized.startsWith('steel') || normalized.includes('steel_')) {
    return 'steel'
  }
  if (
    normalized.startsWith('rc')
    || normalized.includes('concrete')
    || normalized.includes('wall')
    || normalized.includes('column')
  ) {
    return 'rc'
  }
  if (
    normalized.startsWith('cft')
    || normalized.startsWith('src')
    || normalized.includes('composite')
  ) {
    return 'composite'
  }
  if (
    normalized.startsWith('deck')
    || normalized.includes('slab')
    || normalized.includes('plate')
  ) {
    return 'deck/floor'
  }
  return 'other'
}

function uniqueTokens(values: string[]): string[] {
  return [...new Set(values.map((value) => tokenString(value)).filter(Boolean))].sort((left, right) =>
    left.localeCompare(right),
  )
}

function compactLabelList(values: string[], max = 4): string {
  const tokens = uniqueTokens(values)
  if (!tokens.length) {
    return 'n/a'
  }
  if (tokens.length <= max) {
    return tokens.join(', ')
  }
  return `${tokens.slice(0, max).join(', ')} +${tokens.length - max}`
}

function compactCount(value: number | null): string {
  return value === null ? 'n/a' : new Intl.NumberFormat('ko-KR').format(value)
}

function compactSigned(value: number | null, suffix = ''): string {
  if (value === null) {
    return 'n/a'
  }
  return `${value > 0 ? '+' : ''}${value.toLocaleString('ko-KR', {
    maximumFractionDigits: 2,
  })}${suffix}`
}

function compactRatio(value: number | null, digits = 3): string {
  if (value === null) {
    return 'n/a'
  }
  return value.toFixed(digits)
}

function compactMinutes(value: number | null): string {
  if (value === null) {
    return 'n/a'
  }
  return `${value.toFixed(2)} min`
}

function clampNumber(value: number | null, fallback: number, min: number, max: number): number {
  if (value === null || !Number.isFinite(value)) {
    return fallback
  }
  return Math.min(Math.max(value, min), max)
}

function booleanLabel(value: boolean | null, positive = 'yes', negative = 'no'): string {
  if (value === null) {
    return 'n/a'
  }
  return value ? positive : negative
}

function shorten(value: string, max = 18): string {
  if (!value || value.length <= max) {
    return value || 'n/a'
  }
  return `${value.slice(0, max - 1)}…`
}

function sourceLabel(path: string): string {
  const normalized = path.replace(/^\.\//, '')
  const parts = normalized.split('/').filter(Boolean)
  return parts.slice(-2).join('/') || normalized || 'release asset'
}

function missingSnapshot(note: string): Snapshot {
  return {
    statusLabel: 'summary unavailable',
    tone: 'missing',
    metrics: [
      { label: 'State', value: 'waiting' },
      { label: 'Mode', value: 'fallback' },
    ],
    note,
    sourceLabel: 'not loaded',
  }
}

async function fetchFirstJson(candidates: readonly string[]): Promise<ResourceState> {
  let lastError = ''
  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate, {
        headers: {
          Accept: 'application/json',
        },
      })
      if (!response.ok) {
        lastError = `${response.status} ${response.statusText}`
        continue
      }
      const payload: unknown = await response.json()
      if (!isRecord(payload)) {
        return {
          status: 'error',
          source: candidate,
          data: null,
          error: 'JSON root must be an object',
        }
      }
      return {
        status: 'ready',
        source: candidate,
        data: payload,
        error: '',
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error)
    }
  }
  return {
    status: 'missing',
    source: candidates[0] ?? '',
    data: null,
    error: lastError,
  }
}

function buildViewerSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('viewer summary JSON을 아직 읽지 못했습니다.')
  }

  const caseCatalogSummary = getRecord(resource.data, 'case_catalog_summary')
  const paritySummary = getRecord(resource.data, 'commercial_parity_summary')
  const heroCards = getArray(resource.data, 'hero_cards')
  const executionCard = heroCards.find(
    (card) => isRecord(card) && asString(card.label) === 'Execution Status',
  )
  const executionValue = isRecord(executionCard) ? asString(executionCard.value) : ''
  const executionNote = isRecord(executionCard) ? asString(executionCard.note) : ''

  return {
    statusLabel: 'viewer summary loaded',
    tone: 'ok',
    metrics: [
      {
        label: 'Catalog',
        value: compactCount(
          firstNumber(caseCatalogSummary.total_entry_count, resource.data.total_entry_count),
        ),
      },
      {
        label: '3D cases',
        value: compactCount(asNumber(caseCatalogSummary.viewable_3d_count)),
      },
      {
        label: 'Parity',
        value: `${compactCount(asNumber(paritySummary.overall_score))} / 100`,
      },
      {
        label: 'Execution',
        value: executionValue || 'n/a',
        note: executionNote,
      },
    ],
    note:
      asString(paritySummary.disclaimer) ||
      executionNote ||
      'viewer release payload를 기준으로 리뷰 커버리지를 집계했습니다.',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring workspace summary를 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const storyCount = asNumber(summary.story_count)
  const memberCount = asNumber(summary.member_count)
  const loadPatternCount = asNumber(summary.load_pattern_count)
  const solverReadyScore = asNumber(summary.solver_ready_score)
  const nativeAuthoringReady = firstBoolean(summary.native_authoring_ready)

  return {
    statusLabel: nativeAuthoringReady ? 'authoring draft ready' : 'authoring draft narrowing',
    tone: nativeAuthoringReady ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Stories',
        value: compactCount(storyCount),
      },
      {
        label: 'Members',
        value: compactCount(memberCount),
      },
      {
        label: 'Loads',
        value: compactCount(loadPatternCount),
      },
      {
        label: 'Score',
        value: `${compactRatio(solverReadyScore, 1)} / 100`,
      },
    ],
    note:
      asString(resource.data.summary_line)
      || 'story-node-member-load authoring scaffold summary',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringSolverSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring solver session을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const meshSession = getRecord(resource.data, 'mesh_session')
  const loadCombinationSession = getRecord(resource.data, 'load_combination_session')
  const runtimeSummary = getRecord(loadCombinationSession, 'runtime_summary')
  const comboCount = firstNumber(
    summary.combo_count,
    summary.combination_count,
    runtimeSummary.combo_count,
  )
  const meshRequestCount = firstNumber(
    summary.mesh_request_count,
    summary.mesh_plan_count,
    meshSession.request_count,
  )
  const previewLineCount = firstNumber(
    summary.loadcomb_line_count,
    summary.preview_line_count,
    loadCombinationSession.loadcomb_preview_line_count,
  )
  const caseCount = firstNumber(
    summary.load_case_count,
    summary.case_count,
    runtimeSummary.runtime_case_count,
  )
  const sessionReady = firstBoolean(resource.data.contract_pass, summary.session_ready)

  return {
    statusLabel: sessionReady ? 'solver session ready' : 'solver session check',
    tone: sessionReady ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Combos',
        value: compactCount(comboCount),
      },
      {
        label: 'Mesh plans',
        value: compactCount(meshRequestCount),
      },
      {
        label: 'Cases',
        value: compactCount(caseCount),
      },
      {
        label: 'Preview',
        value: compactCount(previewLineCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || 'native authoring solver session and loadcomb preview',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringOpsBundleSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring ops bundle을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  return {
    statusLabel: firstBoolean(resource.data.contract_pass) ? 'ops bundle ready' : 'ops bundle check',
    tone: firstBoolean(resource.data.contract_pass) ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Jobs',
        value: compactCount(asNumber(summary.job_count)),
      },
      {
        label: 'Snapshots',
        value: compactCount(asNumber(summary.snapshot_count)),
      },
      {
        label: 'Artifacts',
        value: compactCount(asNumber(summary.registry_artifact_count)),
      },
      {
        label: 'Approvals',
        value: compactCount(asNumber(summary.registry_approval_count)),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || 'native authoring ops bundle',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringServerOpsSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring server ops summary를 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const jobs = getArray(resource.data, 'jobs').filter(isRecord)
  const queueRows = getArray(resource.data, 'queue_rows').filter(isRecord)
  const snapshotRows = getArray(resource.data, 'snapshot_rows').filter(isRecord)
  const jobRows = jobs.length ? jobs : queueRows
  const jobCount = firstNumber(summary.job_count, summary.planned_count, jobRows.length, queueRows.length)
  const completedCount = firstNumber(
    summary.completed_count,
    summary.completed_task_count,
    jobRows.filter((row) => asString(row.lifecycle_status) === 'completed').length,
  )
  const queueCount = queueRows.length || jobRows.length
  const snapshotCount = firstNumber(summary.snapshot_count, snapshotRows.length)
  const artifactCount = jobRows.reduce((count, row) => count + arraySize(row.artifact_paths), 0)
  const scopeList = compactLabelList(jobRows.map((row) => asString(row.submission_scope)))
  const familyList = compactLabelList(jobRows.map((row) => asString(row.benchmark_family)))
  const contractPass = firstBoolean(
    resource.data.contract_pass,
    jobCount !== null && completedCount !== null && completedCount >= jobCount,
  )

  return {
    statusLabel: contractPass === true ? 'server ops ready' : 'server ops check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Jobs',
        value: compactCount(jobCount),
      },
      {
        label: 'Completed',
        value: compactCount(completedCount),
      },
      {
        label: 'Queue',
        value: compactCount(queueCount),
      },
      {
        label: 'Artifacts',
        value: compactCount(artifactCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || asString(resource.data.reason)
      || `scopes=${scopeList} | families=${familyList} | snapshots=${compactCount(snapshotCount)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringFamilyTrackSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring family track JSON을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const familyRows = getArray(resource.data, 'family_rows').filter(isRecord)
  const projectRows = getArray(resource.data, 'project_rows').filter(isRecord)
  const familyCount = firstNumber(summary.family_count, familyRows.length)
  const projectCount = firstNumber(summary.project_count, summary.registry_project_count, projectRows.length)
  const completeCount = firstNumber(
    summary.complete_project_count,
    summary.complete_family_count,
    summary.complete_registry_count,
  )
  const signatureCount = firstNumber(
    summary.signature_verified_count,
    summary.registry_signature_verified_count,
  )
  const reproCount = firstNumber(summary.package_reproducible_count, summary.registry_reproducible_count)
  const contractPass = firstBoolean(
    resource.data.contract_pass,
    familyCount !== null && completeCount !== null && completeCount >= familyCount,
  )

  return {
    statusLabel: contractPass === true ? 'family track ready' : 'family track check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Families',
        value: compactCount(familyCount),
      },
      {
        label: 'Projects',
        value: compactCount(projectCount),
      },
      {
        label: 'Complete',
        value: compactCount(completeCount),
      },
      {
        label: 'Signature',
        value: compactCount(signatureCount),
      },
      {
        label: 'Repro',
        value: compactCount(reproCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || asString(resource.data.reason)
      || `family_rows=${compactCount(familyRows.length)} | project_rows=${compactCount(projectRows.length)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringRuntimeSubmissionLaneSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring runtime submission lane JSON을 아직 읽지 못했습니다.')
  }

  const summarySources = [
    getRecord(resource.data, 'summary'),
    getRecord(resource.data, 'runtime_submission_lane'),
    getRecord(resource.data, 'lane_summary'),
    isRecord(resource.data) ? resource.data : {},
  ]
  const projectRows = getArray(resource.data, 'projects').filter(isRecord)
  const runtimeProjectRows = projectRows.length ? projectRows : getArray(resource.data, 'project_rows').filter(isRecord)
  const familyRows = getArray(resource.data, 'families').filter(isRecord)
  const runtimeFamilyRows = familyRows.length ? familyRows : getArray(resource.data, 'family_rows').filter(isRecord)
  const batchRows = getArray(resource.data, 'batch_rows').filter(isRecord)
  const runtimeBatchRows = batchRows.length ? batchRows : getArray(resource.data, 'jobs').filter(isRecord)

  const projectCount = firstNumber(
    ...summarySources.map((record) => record.project_count),
    ...summarySources.map((record) => record.runtime_project_count),
    ...summarySources.map((record) => record.submission_project_count),
    runtimeProjectRows.length,
  )
  const familyCount = firstNumber(
    ...summarySources.map((record) => record.family_count),
    ...summarySources.map((record) => record.runtime_family_count),
    ...summarySources.map((record) => record.submission_family_count),
    runtimeFamilyRows.length,
  )
  const readyFamilyCount = firstNumber(
    ...summarySources.map((record) => record.ready_family_count),
    ...summarySources.map((record) => record.complete_family_count),
    ...summarySources.map((record) => record.ready_project_count),
    ...summarySources.map((record) => record.complete_project_count),
    runtimeFamilyRows.filter((row) => firstBoolean(row.runtime_ready, row.ready, row.contract_pass)).length,
  )
  const batchJobCount = firstNumber(
    ...summarySources.map((record) => record.batch_job_count),
    ...summarySources.map((record) => record.job_count),
    ...summarySources.map((record) => record.planned_count),
    runtimeBatchRows.length,
    getArray(resource.data, 'queue_rows').filter(isRecord).length,
  )
  const snapshotCount = firstNumber(
    ...summarySources.map((record) => record.batch_snapshot_count),
    ...summarySources.map((record) => record.snapshot_count),
    getArray(resource.data, 'snapshots').filter(isRecord).length,
  )
  const contractPass = firstBoolean(
    ...summarySources.map((record) => record.contract_pass),
    ...summarySources.map((record) => record.runtime_ready),
    ...summarySources.map((record) => record.service_ready),
    familyCount !== null && readyFamilyCount !== null && readyFamilyCount >= familyCount,
  )
  const summaryLine =
    summarySources.map((record) => asString(record.summary_line)).find(Boolean)
    || `projects=${compactCount(projectCount)} | families=${compactCount(familyCount)} | ready_families=${compactCount(readyFamilyCount)} | batch_jobs=${compactCount(batchJobCount)}`

  return {
    statusLabel: contractPass === true ? 'runtime lane ready' : 'runtime lane check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Projects',
        value: compactCount(projectCount),
      },
      {
        label: 'Families',
        value: compactCount(familyCount),
      },
      {
        label: 'Ready families',
        value: compactCount(readyFamilyCount),
      },
      {
        label: 'Batch jobs',
        value: compactCount(batchJobCount),
      },
    ],
    note: snapshotCount === null ? summaryLine : `${summaryLine} | snapshots=${compactCount(snapshotCount)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringRuntimeWritebackDepthSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring runtime writeback depth JSON을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const familyRows = getArray(resource.data, 'family_rows').filter(isRecord)
  const familyCount = firstNumber(summary.family_count, familyRows.length)
  const fullDepthCount = firstNumber(
    summary.depth_ready_family_count,
    familyRows.filter((row) => asString(row.runtime_writeback_depth_status) === 'full').length,
  )
  const targetedCount = firstNumber(
    summary.targeted_family_count,
    familyRows.filter((row) => asString(row.runtime_writeback_depth_status) === 'targeted').length,
  )
  const signatureCount = firstNumber(
    summary.signature_verified_family_count,
    familyRows.filter((row) => firstBoolean(row.signature_verified)).length,
  )
  const reproCount = firstNumber(
    summary.package_reproducible_family_count,
    familyRows.filter((row) => firstBoolean(row.package_reproducible)).length,
  )
  const snapshotCount = firstNumber(
    summary.snapshot_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.snapshot_ready)).length,
  )
  const queueClearCount = firstNumber(
    summary.queue_clear_family_count,
    familyRows.filter((row) => firstBoolean(row.queue_clear)).length,
  )
  const contractPass = firstBoolean(
    resource.data.contract_pass,
    summary.runtime_writeback_depth_ready,
    familyCount !== null && fullDepthCount !== null && fullDepthCount >= familyCount,
  )

  return {
    statusLabel: contractPass === true ? 'runtime writeback depth ready' : 'runtime writeback depth check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Families',
        value: compactCount(familyCount),
      },
      {
        label: 'Full depth',
        value: compactCount(fullDepthCount),
      },
      {
        label: 'Targeted',
        value: compactCount(targetedCount),
      },
      {
        label: 'Signature',
        value: compactCount(signatureCount),
      },
      {
        label: 'Repro',
        value: compactCount(reproCount),
      },
      {
        label: 'Snapshots',
        value: compactCount(snapshotCount),
      },
      {
        label: 'Queue clear',
        value: compactCount(queueClearCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || `families=${compactCount(familyCount)} | full_depth=${compactCount(fullDepthCount)} | signature=${compactCount(signatureCount)} | repro=${compactCount(reproCount)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringMultiProjectRuntimeWritebackSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring multi-project runtime/writeback JSON을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const projectRows = getArray(resource.data, 'project_rows').filter(isRecord)
  const projectFamilyRows = getArray(resource.data, 'project_family_rows').filter(isRecord)
  const projectCount = firstNumber(summary.project_count, projectRows.length)
  const projectFamilyCount = firstNumber(summary.project_family_count, projectFamilyRows.length)
  const fullDepthCount = firstNumber(
    summary.full_depth_project_family_count,
    projectFamilyRows.filter((row) => asString(row.project_family_status) === 'full').length,
  )
  const readyProjectCount = firstNumber(
    summary.ready_project_count,
    projectRows.filter((row) => firstBoolean(row.ready)).length,
  )
  const signatureProjectCount = firstNumber(
    summary.signature_verified_project_count,
    projectRows.filter(
      (row) =>
        (firstNumber(row.signature_verified_count, 0) ?? 0) >= (firstNumber(row.family_count, 0) ?? 0),
    ).length,
  )
  const reproProjectCount = firstNumber(
    summary.package_reproducible_project_count,
    projectRows.filter(
      (row) =>
        (firstNumber(row.package_reproducible_count, 0) ?? 0) >= (firstNumber(row.family_count, 0) ?? 0),
    ).length,
  )
  const snapshotProjectCount = firstNumber(
    summary.snapshot_ready_project_count,
    projectRows.filter(
      (row) =>
        (firstNumber(row.snapshot_ready_count, 0) ?? 0) >= (firstNumber(row.family_count, 0) ?? 0),
    ).length,
  )
  const queueClearProjectCount = firstNumber(
    summary.queue_clear_project_count,
    projectRows.filter(
      (row) =>
        (firstNumber(row.queue_clear_count, 0) ?? 0) >= (firstNumber(row.family_count, 0) ?? 0),
    ).length,
  )
  const contractPass = firstBoolean(
    resource.data.contract_pass,
    summary.multi_project_runtime_writeback_ready,
    projectCount !== null
      && readyProjectCount !== null
      && projectCount > 0
      && readyProjectCount >= projectCount,
  )

  return {
    statusLabel: contractPass === true ? 'multi-project runtime ready' : 'multi-project runtime check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Projects',
        value: compactCount(projectCount),
      },
      {
        label: 'Project families',
        value: compactCount(projectFamilyCount),
      },
      {
        label: 'Full depth',
        value: compactCount(fullDepthCount),
      },
      {
        label: 'Ready projects',
        value: compactCount(readyProjectCount),
      },
      {
        label: 'Signature',
        value: compactCount(signatureProjectCount),
      },
      {
        label: 'Repro',
        value: compactCount(reproProjectCount),
      },
      {
        label: 'Snapshots',
        value: compactCount(snapshotProjectCount),
      },
      {
        label: 'Queue clear',
        value: compactCount(queueClearProjectCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || `projects=${compactCount(projectCount)} | project_families=${compactCount(projectFamilyCount)} | full_depth=${compactCount(fullDepthCount)} | ready_projects=${compactCount(readyProjectCount)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringSolverFamilyBreadthSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring solver family breadth JSON을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const familyRows = getArray(resource.data, 'family_rows').filter(isRecord)
  const familyCount = firstNumber(summary.family_count, familyRows.length)
  const broadReadyCount = firstNumber(
    summary.broad_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.broad_solver_family_ready)).length,
  )
  const fullBreadthCount = firstNumber(
    summary.full_breadth_family_count,
    familyRows.filter((row) => firstBoolean(row.full_solver_family_ready)).length,
  )
  const meshBroadCount = firstNumber(
    summary.mesh_broad_family_count,
    familyRows.filter((row) => asString(row.mesh_breadth_status) === 'broad').length,
  )
  const memberMultiCount = firstNumber(
    summary.member_multi_family_count,
    familyRows.filter((row) => firstBoolean(row.member_family_breadth_ready)).length,
  )
  const queueCount = firstNumber(summary.queued_submission_count, 0)
  const contractPass = firstBoolean(
    resource.data.contract_pass,
    summary.solver_family_breadth_ready,
    familyCount !== null && broadReadyCount !== null && broadReadyCount >= familyCount && (queueCount ?? 0) === 0,
  )

  return {
    statusLabel: contractPass === true ? 'solver family breadth ready' : 'solver family breadth check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Families',
        value: compactCount(familyCount),
      },
      {
        label: 'Broad ready',
        value: compactCount(broadReadyCount),
      },
      {
        label: 'Full breadth',
        value: compactCount(fullBreadthCount),
      },
      {
        label: 'Mesh broad',
        value: compactCount(meshBroadCount),
      },
      {
        label: 'Member multi',
        value: compactCount(memberMultiCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || `families=${compactCount(familyCount)} | broad_ready=${compactCount(broadReadyCount)} | full_breadth=${compactCount(fullBreadthCount)} | queue=${compactCount(queueCount)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringLocalRuntimeScenarioDepthSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring local runtime scenario depth JSON을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const familyRows = getArray(resource.data, 'family_rows').filter(isRecord)
  const familyCount = firstNumber(summary.family_count, familyRows.length)
  const deepCount = firstNumber(
    summary.depth_ready_family_count,
    familyRows.filter((row) => asString(row.local_runtime_scenario_depth_status) === 'deep').length,
  )
  const scenarioReadyCount = firstNumber(
    summary.scenario_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.scenario_ready)).length,
  )
  const traceReadyCount = firstNumber(
    summary.trace_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.trace_ready)).length,
  )
  const meshReadyCount = firstNumber(
    summary.mesh_trace_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.mesh_trace_ready)).length,
  )
  const runtimeReadyCount = firstNumber(
    summary.runtime_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.runtime_ready)).length,
  )
  const omittedCount = firstNumber(
    summary.omitted_library_family_count,
    familyRows.filter((row) => (firstNumber(row.omitted_library_combination_count, 0) ?? 0) > 0).length,
  )
  const contractPass = firstBoolean(
    resource.data.contract_pass,
    summary.local_runtime_scenario_depth_ready,
    familyCount !== null && deepCount !== null && deepCount >= familyCount,
  )

  return {
    statusLabel: contractPass === true ? 'local runtime depth ready' : 'local runtime depth check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Families',
        value: compactCount(familyCount),
      },
      {
        label: 'Deep',
        value: compactCount(deepCount),
      },
      {
        label: 'Scenario',
        value: compactCount(scenarioReadyCount),
      },
      {
        label: 'Trace',
        value: compactCount(traceReadyCount),
      },
      {
        label: 'Mesh',
        value: compactCount(meshReadyCount),
      },
      {
        label: 'Runtime',
        value: compactCount(runtimeReadyCount),
      },
      {
        label: 'Omitted',
        value: compactCount(omittedCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || `families=${compactCount(familyCount)} | deep=${compactCount(deepCount)} | scenario_ready=${compactCount(scenarioReadyCount)} | trace_ready=${compactCount(traceReadyCount)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringLocalVariantWritebackTraceSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring local variant/writeback trace JSON을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const familyRows = getArray(resource.data, 'family_rows').filter(isRecord)
  const familyCount = firstNumber(summary.family_count, familyRows.length)
  const deepCount = firstNumber(
    summary.deep_ready_family_count,
    familyRows.filter((row) => asString(row.local_variant_writeback_trace_status) === 'deep').length,
  )
  const targetedCount = firstNumber(
    summary.targeted_family_count,
    familyRows.filter((row) => asString(row.local_variant_writeback_trace_status) === 'targeted').length,
  )
  const workspaceVariantCount = firstNumber(
    summary.workspace_variant_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.workspace_variant_ready)).length,
  )
  const solverVariantCount = firstNumber(
    summary.solver_variant_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.solver_variant_ready)).length,
  )
  const writebackTraceCount = firstNumber(
    summary.writeback_trace_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.writeback_trace_ready)).length,
  )
  const signedCount = firstNumber(
    summary.signed_writeback_family_count,
    familyRows.filter((row) => firstBoolean(row.signature_verified)).length,
  )
  const omittedCount = firstNumber(
    summary.omitted_library_family_count,
    familyRows.filter((row) => (firstNumber(row.omitted_library_combination_count, 0) ?? 0) > 0).length,
  )
  const contractPass = firstBoolean(
    resource.data.contract_pass,
    summary.local_variant_writeback_trace_ready,
    familyCount !== null && deepCount !== null && deepCount >= familyCount,
  )

  return {
    statusLabel: contractPass === true ? 'local variant/writeback trace ready' : 'local variant/writeback trace check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Families',
        value: compactCount(familyCount),
      },
      {
        label: 'Deep',
        value: compactCount(deepCount),
      },
      {
        label: 'Targeted',
        value: compactCount(targetedCount),
      },
      {
        label: 'Workspace',
        value: compactCount(workspaceVariantCount),
      },
      {
        label: 'Solver',
        value: compactCount(solverVariantCount),
      },
      {
        label: 'Trace',
        value: compactCount(writebackTraceCount),
      },
      {
        label: 'Signed',
        value: compactCount(signedCount),
      },
      {
        label: 'Omitted',
        value: compactCount(omittedCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || `families=${compactCount(familyCount)} | deep=${compactCount(deepCount)} | workspace_variant=${compactCount(workspaceVariantCount)} | solver_variant=${compactCount(solverVariantCount)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringWritebackBreadthSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('native authoring writeback breadth JSON을 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const familyRows = getArray(resource.data, 'family_rows').filter(isRecord)
  const familyCount = firstNumber(summary.family_count, familyRows.length)
  const broadReadyCount = firstNumber(
    summary.broad_ready_family_count,
    familyRows.filter((row) => firstBoolean(row.broad_writeback_ready)).length,
  )
  const fullBreadthCount = firstNumber(
    summary.full_breadth_family_count,
    familyRows.filter((row) => firstBoolean(row.full_breadth_ready)).length,
  )
  const meshBroadCount = firstNumber(
    summary.mesh_broad_family_count,
    familyRows.filter((row) => asString(row.mesh_breadth_status) === 'broad').length,
  )
  const comboBroadCount = firstNumber(
    summary.combo_broad_family_count,
    familyRows.filter((row) => asString(row.solver_combo_status) === 'broad').length,
  )
  const queueCount = firstNumber(summary.queued_submission_count, 0)
  const contractPass = firstBoolean(
    resource.data.contract_pass,
    summary.writeback_breadth_ready,
    familyCount !== null && broadReadyCount !== null && broadReadyCount >= familyCount && (queueCount ?? 0) === 0,
  )

  return {
    statusLabel: contractPass === true ? 'writeback breadth ready' : 'writeback breadth check',
    tone: contractPass === true ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Families',
        value: compactCount(familyCount),
      },
      {
        label: 'Broad ready',
        value: compactCount(broadReadyCount),
      },
      {
        label: 'Full breadth',
        value: compactCount(fullBreadthCount),
      },
      {
        label: 'Mesh broad',
        value: compactCount(meshBroadCount),
      },
      {
        label: 'Combo broad',
        value: compactCount(comboBroadCount),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || `families=${compactCount(familyCount)} | broad_ready=${compactCount(broadReadyCount)} | full_breadth=${compactCount(fullBreadthCount)} | queue=${compactCount(queueCount)}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildAuthoringConsistencySnapshot(
  portfolioScopeLabel: string,
  portfolioSourceLabel: string,
  familyTrackSnapshot: Snapshot,
  runtimeSubmissionLaneSnapshot: Snapshot,
  serverOpsSnapshot: Snapshot,
): Snapshot {
  const readyLaneCount = [
    familyTrackSnapshot.tone === 'ok',
    runtimeSubmissionLaneSnapshot.tone === 'ok',
    serverOpsSnapshot.tone === 'ok',
  ].filter((ready) => ready).length
  const consistencyReady = portfolioScopeLabel !== 'missing' && readyLaneCount === 3

  return {
    statusLabel: consistencyReady ? 'consistency aligned' : 'consistency check',
    tone: consistencyReady ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Scope anchor',
        value: portfolioScopeLabel,
      },
      {
        label: 'Family-track',
        value: familyTrackSnapshot.statusLabel,
      },
      {
        label: 'Runtime',
        value: runtimeSubmissionLaneSnapshot.statusLabel,
      },
      {
        label: 'Service',
        value: serverOpsSnapshot.statusLabel,
      },
    ],
    note:
      `portfolio scope note is coverage, not readiness; current anchor is ${portfolioScopeLabel}.`
      + ` family-track/runtime/service are ${readyLaneCount}/3 ready.`,
    sourceLabel: portfolioSourceLabel,
  }
}

function buildDrawingSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('optimized drawing review summary를 아직 읽지 못했습니다.')
  }

  return {
    statusLabel: 'drawing summary loaded',
    tone: 'ok',
    metrics: [
      {
        label: 'Groups',
        value: compactCount(asNumber(resource.data.changed_group_count)),
      },
      {
        label: 'Members',
        value: compactCount(asNumber(resource.data.changed_member_count)),
      },
      {
        label: 'Max DCR',
        value: compactRatio(asNumber(resource.data.max_dcr_after_max)),
      },
      {
        label: 'Cost delta',
        value: compactSigned(asNumber(resource.data.signed_cost_proxy_delta_total)),
      },
    ],
    note:
      `${asString(resource.data.case_title) || asString(resource.data.case_id) || 'drawing review'}`
        + ` | ${asString(resource.data.status_label) || 'baseline + ai compare'}`,
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildBenchmarkSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('benchmark review summary를 아직 읽지 못했습니다.')
  }

  const artifactLinks = getRecord(resource.data, 'artifact_links')
  const peerSheetPath = asString(resource.data.peer_sheet_path)

  return {
    statusLabel: 'benchmark summary loaded',
    tone: 'ok',
    metrics: [
      {
        label: 'Canton',
        value: shorten(asString(resource.data.canton_case_id), 20),
      },
      {
        label: 'PEER',
        value: shorten(asString(resource.data.peer_case_id), 20),
      },
      {
        label: 'Sheet',
        value: peerSheetPath ? 'linked' : 'missing',
      },
      {
        label: 'Links',
        value: compactCount(recordSize(artifactLinks)),
      },
    ],
    note: asString(resource.data.peer_drawing_kind) || 'document-derived benchmark proxy review',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildCommitteeSnapshot(summaryResource: ResourceState, reportResource: ResourceState): Snapshot {
  if (summaryResource.status !== 'ready' && reportResource.status !== 'ready') {
    return missingSnapshot('committee summary/package report를 아직 읽지 못했습니다.')
  }

  const summaryData = summaryResource.data ?? {}
  const reportData = reportResource.data ?? {}
  const contractPass = firstBoolean(reportData.contract_pass)
  const acceptedCandidateCount = arraySize(reportData.accepted_candidate_rows)
  const designChangeCount = arraySize(reportData.design_change_rows)
  const authorityCount = arraySize(reportData.authority_rows)
  const chainMinutes = firstNumber(summaryData.measured_chain_total_minutes)

  return {
    statusLabel: contractPass === false ? 'committee review needed' : 'committee package pass',
    tone: contractPass === false ? 'warn' : 'ok',
    metrics: [
      {
        label: 'Chain',
        value: compactMinutes(chainMinutes),
      },
      {
        label: 'Accepted',
        value: compactCount(acceptedCandidateCount),
      },
      {
        label: 'Changes',
        value: compactCount(designChangeCount),
      },
      {
        label: 'Authority',
        value: compactCount(authorityCount),
      },
    ],
    note:
      asString(reportData.reason) ||
      asString(reportData.reason_code) ||
      'committee review package and summary are both available.',
    sourceLabel: reportResource.data ? sourceLabel(reportResource.source) : sourceLabel(summaryResource.source),
  }
}

function buildGapSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('release gap report를 아직 읽지 못했습니다.')
  }

  const p0Snapshot = buildGapSeveritySnapshot(resource, 'P0')
  const p1Snapshot = buildGapSeveritySnapshot(resource, 'P1')
  const commercializationDepthSignals = buildCommercializationDepthSignals(resource)
  const commercializationDepthReadyCount = commercializationDepthSignals.filter((signal) => signal.ready).length
  const remainingGapCount = arraySize(resource.data.remaining_gaps)
  const advancedHoldoutCount = arraySize(resource.data.advanced_holdouts)
  const commercializationSummary = commercializationDepthSignals
    .map((signal) => `${signal.label.toLowerCase().replace(/\s+/g, '_')}=${signal.statusLabel}`)
    .join(' | ')
  const severityStatusLabel =
    p0Snapshot.totalCount || p1Snapshot.totalCount
      ? `P0 ${p0Snapshot.readyCount}/${p0Snapshot.totalCount} ready · P1 ${p1Snapshot.readyCount}/${p1Snapshot.totalCount} ready`
      : remainingGapCount > 0
        ? `${remainingGapCount} gaps open`
        : 'boundary closed'

  return {
    statusLabel: severityStatusLabel,
    tone:
      remainingGapCount > 0
      || commercializationDepthReadyCount < commercializationDepthSignals.length
        ? 'warn'
        : 'ok',
    metrics: [
      {
        label: 'P0 ready',
        value: `${p0Snapshot.readyCount}/${p0Snapshot.totalCount}`,
      },
      {
        label: 'P1 ready',
        value: `${p1Snapshot.readyCount}/${p1Snapshot.totalCount}`,
      },
      {
        label: 'Depth lanes',
        value: `${commercializationDepthReadyCount}/${commercializationDepthSignals.length}`,
      },
      {
        label: 'Holdouts',
        value: compactCount(advancedHoldoutCount),
      },
    ],
    note: commercializationSummary || asString(resource.data.run_id) || 'release boundary risk inventory',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildRegistrySnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('project registry가 없어서 release registry fallback도 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const checks = getRecord(resource.data, 'checks')
  const registryBody = getRecord(resource.data, 'registry_body')
  const usingProjectRegistry = resource.source.endsWith('project_registry.json')
  const approvalCount = firstNumber(summary.approval_count, summary.project_registry_approval_count)
  const signatureVerified = firstBoolean(
    checks.signature_verified_pass,
    checks.project_registry_signature_verified_pass,
    summary.signature_verified,
  )
  const hashPresent = firstBoolean(checks.artifact_hashes_present_pass)
  const artifactCount = firstNumber(
    recordSize(getRecord(resource.data, 'artifacts')),
    arraySize(registryBody.artifacts),
  )

  return {
    statusLabel: usingProjectRegistry ? 'project registry loaded' : 'release registry fallback',
    tone: signatureVerified ? (usingProjectRegistry ? 'ok' : 'warn') : 'warn',
    metrics: [
      {
        label: 'Approvals',
        value: compactCount(approvalCount),
      },
      {
        label: 'Signature',
        value: booleanLabel(signatureVerified, 'verified', 'pending'),
      },
      {
        label: 'Hashes',
        value: booleanLabel(hashPresent, 'present', 'missing'),
      },
      {
        label: 'Artifacts',
        value: compactCount(artifactCount),
      },
    ],
    note: usingProjectRegistry
      ? 'signed package registry artifact를 직접 읽었습니다.'
      : 'checked-in project registry가 없어 release registry로 상태를 대체했습니다.',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildRegistryIndexSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('registry portfolio index를 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  return {
    statusLabel: asNumber(summary.project_count) ? 'portfolio index loaded' : 'portfolio index empty',
    tone: firstBoolean(resource.data.contract_pass) ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Projects',
        value: compactCount(asNumber(summary.project_count)),
      },
      {
        label: 'Complete',
        value: compactCount(asNumber(summary.complete_project_count)),
      },
      {
        label: 'Signature',
        value: compactCount(asNumber(summary.signature_verified_count)),
      },
      {
        label: 'Repro',
        value: compactCount(asNumber(summary.package_reproducible_count)),
      },
    ],
    note:
      asString(resource.data.summary_line)
      || 'multi-project registry portfolio summary',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildPackageSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('package metadata를 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const registryBody = getRecord(resource.data, 'registry_body')
  const usingProjectRegistry = resource.source.endsWith('project_registry.json')
  const packageBytes = firstNumber(summary.package_bytes, summary.project_registry_package_bytes)
  const packageSha =
    asString(summary.package_sha256) || asString(summary.project_registry_package_sha256)
  const packageArtifactCount = firstNumber(
    arraySize(registryBody.artifacts),
    recordSize(getRecord(resource.data, 'artifacts')),
  )
  const approvalCount = firstNumber(summary.approval_count, summary.project_registry_approval_count)

  return {
    statusLabel: usingProjectRegistry ? 'package registered' : 'package fallback state',
    tone: usingProjectRegistry ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Bytes',
        value: compactCount(packageBytes),
      },
      {
        label: 'SHA',
        value: shorten(packageSha, 14),
      },
      {
        label: 'Artifacts',
        value: compactCount(packageArtifactCount),
      },
      {
        label: 'Approvals',
        value: compactCount(approvalCount),
      },
    ],
    note: usingProjectRegistry
      ? 'deterministic package summary를 직접 읽었습니다.'
      : 'package zip 본문 대신 release registry summary를 기준으로 상태를 보여줍니다.',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildSignatureSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('signature verification metadata를 아직 읽지 못했습니다.')
  }

  const checks = getRecord(resource.data, 'checks')
  const usingProjectRegistry = resource.source.endsWith('project_registry.json')
  const signatureVerified = firstBoolean(
    checks.signature_verified_pass,
    checks.project_registry_signature_verified_pass,
  )
  const signatureGenerated = firstBoolean(checks.signature_generated_pass)
  const publicKeyWritten = firstBoolean(checks.public_key_written_pass)

  return {
    statusLabel: signatureVerified ? 'signature verified' : 'signature pending',
    tone: signatureVerified ? 'ok' : 'warn',
    metrics: [
      {
        label: 'Verified',
        value: booleanLabel(signatureVerified, 'yes', 'no'),
      },
      {
        label: 'Generated',
        value: booleanLabel(signatureGenerated, 'yes', 'no'),
      },
      {
        label: 'Public key',
        value: booleanLabel(publicKeyWritten, 'yes', 'no'),
      },
      {
        label: 'Source',
        value: usingProjectRegistry ? 'project' : 'release',
      },
    ],
    note: usingProjectRegistry
      ? 'project registry signature checks를 우선 표시합니다.'
      : 'release registry checks를 fallback으로 사용합니다.',
    sourceLabel: sourceLabel(resource.source),
  }
}

function buildBatchSnapshot(resource: ResourceState): Snapshot {
  if (resource.status !== 'ready' || !resource.data) {
    return missingSnapshot('batch job report를 아직 읽지 못했습니다.')
  }

  const summary = getRecord(resource.data, 'summary')
  const usingBatchReport = resource.source.endsWith('external_benchmark_batch_job_report.json')
  const jobCount = firstNumber(summary.job_count, summary.executable_task_count, summary.planned_task_count)
  const completedCount = firstNumber(summary.completed_count, summary.completed_task_count)
  const failedCount = firstNumber(summary.release_surface_failed_task_count, summary.failed_count, summary.failed_task_count)
  const notRunCount = firstNumber(summary.release_surface_not_run_task_count)
  const blockedCount = firstNumber(summary.blocked_count, summary.blocked_task_count)
  const statusMode = asString(summary.release_surface_status_label)
    || asString(summary.release_surface_status_mode)
    || asString(summary.status_mode)
    || asString(resource.data.reason_code)

  return {
    statusLabel: usingBatchReport ? 'batch report loaded' : 'execution status fallback',
    tone: (failedCount ?? 0) > 0 ? 'warn' : 'ok',
    metrics: [
      {
        label: 'Jobs',
        value: compactCount(jobCount),
      },
      {
        label: 'Completed',
        value: compactCount(completedCount),
      },
      {
        label: 'Failed',
        value: compactCount(failedCount),
      },
      {
        label: 'Not run',
        value: compactCount(notRunCount),
      },
      {
        label: 'Blocked',
        value: compactCount(blockedCount),
      },
    ],
    note: statusMode || 'external benchmark runtime summary',
    sourceLabel: sourceLabel(resource.source),
  }
}

function getReviewSurface(id: ReviewSurfaceId): ReviewSurface {
  return reviewSurfaces.find((surface) => surface.id === id) ?? reviewSurfaces[0]
}

function getGovernanceArtifact(id: GovernanceArtifactId): GovernanceArtifact {
  return governanceArtifacts.find((artifact) => artifact.id === id) ?? governanceArtifacts[0]
}

function routeModeKey(title: string): string {
  const normalized = String(title || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return normalized || 'review_route'
}

function buildDeepLinkHref(baseHref: string, params: DeepLinkParams): string {
  const href = String(baseHref || '').trim()
  if (!href) {
    return ''
  }

  const hashIndex = href.indexOf('#')
  const hash = hashIndex >= 0 ? href.slice(hashIndex) : ''
  const preHash = hashIndex >= 0 ? href.slice(0, hashIndex) : href
  const queryIndex = preHash.indexOf('?')
  const path = queryIndex >= 0 ? preHash.slice(0, queryIndex) : preHash
  const query = queryIndex >= 0 ? preHash.slice(queryIndex + 1) : ''
  const searchParams = new URLSearchParams(query)

  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return
    }
    searchParams.set(key, String(value))
  })

  const nextQuery = searchParams.toString()
  return `${path}${nextQuery ? `?${nextQuery}` : ''}${hash}`
}

function buildWorkbenchReturnHref(targetHref: string): string {
  const normalizedHref = String(targetHref || '')
    .trim()
    .replace(/^[.]\//, '')
    .split(/[?#]/, 1)[0]
  const segments = normalizedHref.split('/').filter(Boolean)
  const depth = Math.max(segments.length - 1, 0)
  return `${depth ? '../'.repeat(depth) : './'}index.html`
}

const routeSurfaceFocusMap: Record<ReviewSurfaceId, Record<string, string>> = {
  viewer: {
    interactive_evidence_route: 'viewer-interactive-3d',
    drawing_first_review_route: 'viewer-changed-overlay',
    benchmark_validation_route: 'viewer-results-explorer',
    submission_and_authority_route: 'viewer-results-explorer',
  },
  'drawing-review': {
    interactive_evidence_route: 'drawing-member-review',
    drawing_first_review_route: 'drawing-what-changed',
    benchmark_validation_route: 'drawing-3d-workspace',
    submission_and_authority_route: 'drawing-hero',
  },
  'real-drawing-3d': {
    interactive_evidence_route: 'viewer',
    drawing_first_review_route: 'viewer',
    benchmark_validation_route: 'viewer',
    submission_and_authority_route: 'viewer',
  },
  'benchmark-review': {
    interactive_evidence_route: 'canton-review',
    drawing_first_review_route: 'canton-review',
    benchmark_validation_route: 'peer-benchmark',
    submission_and_authority_route: 'benchmark-peer-summary',
  },
  committee: {
    interactive_evidence_route: 'committee-validation-table',
    drawing_first_review_route: 'committee-overview-cards',
    benchmark_validation_route: 'committee-authority-benchmark',
    submission_and_authority_route: 'committee-validation-table',
  },
}

function resolveSurfaceRouteFocus(surfaceId: ReviewSurfaceId, routeTitle: string): string {
  return routeSurfaceFocusMap[surfaceId]?.[routeModeKey(routeTitle)] ?? ''
}

function buildViewerSelectionParams(resource: ResourceState): DeepLinkParams {
  if (resource.status !== 'ready' || !resource.data) {
    return {}
  }

  const memberOverlay = getRecord(resource.data, 'member_overlay')
  const changeOverview = getRecord(resource.data, 'change_overview')
  const caseContext = getRecord(resource.data, 'case_context')
  const locatorRow = getArray(memberOverlay, 'member_locator_rows').find(isRecord) ?? {}
  const storyRow = getArray(changeOverview, 'story_band_rows').find(isRecord) ?? {}
  const combinationHighlight = firstRecord(
    getArray(caseContext, 'load_combination_highlights'),
    (row) => getArray(row, 'code_check_top_rows').some(isRecord),
  )
  const codecheckRow = firstRecord(getArray(combinationHighlight, 'code_check_top_rows'))
  const resultsSourceRow = recordSize(combinationHighlight)
    ? combinationHighlight
    : firstRecord(
        [
          ...getArray(caseContext, 'load_combination_graph_node_rows'),
          ...getArray(caseContext, 'load_pattern_highlights'),
        ],
        (row) => Boolean(tokenString(row.recommended_results_card)),
      )
  const memberId =
    tokenString(codecheckRow.baseline_focus_member_id)
    || tokenString(locatorRow.member_id)
  const storyBand = tokenString(locatorRow.story_band_label)
    || tokenString(locatorRow.story_band)
    || tokenString(storyRow.story_band_label)
    || tokenString(storyRow.story_band)
  const combinationName = tokenString(combinationHighlight.name)
  const reviewMemberId = tokenString(codecheckRow.member_id)
  const caseId = tokenString(codecheckRow.case_id)
  const clauseLabel = tokenString(codecheckRow.clause_label)
  const hazardType = tokenString(codecheckRow.hazard_type)
  const ruleFamily = tokenString(codecheckRow.rule_family)
  const rowIndex = firstNumber(codecheckRow.row_index)
  const recommendedResultsCard = tokenString(resultsSourceRow.recommended_results_card)
  const recommendedResultsSeriesIndex = firstNumber(
    resultsSourceRow.recommended_results_series_index,
    resultsSourceRow.recommended_results_series_index_label,
  )
  const codecheckEnabled = Boolean(combinationName && reviewMemberId)

  return {
    focus_member: memberId,
    member_id: reviewMemberId || memberId,
    baseline_focus_member_id: memberId,
    member_set: memberId,
    case_id: caseId,
    story_band: storyBand,
    combination: combinationName,
    combination_name: combinationName,
    row: rowIndex,
    row_index: rowIndex,
    row_ref: tokenString(codecheckRow.viewer_row_ref),
    clause_label: clauseLabel,
    hazard_type: hazardType,
    rule_family: ruleFamily,
    results_card: recommendedResultsCard,
    results_series_index: recommendedResultsSeriesIndex,
    results_sample_index: recommendedResultsCard ? 0 : null,
    results_companion: recommendedResultsCard ? 'interactive' : '',
    results_companion_item_index: recommendedResultsCard ? 0 : null,
    results_companion_focus_key: recommendedResultsCard ? 'chart-marker:0' : '',
    results_companion_selection_key: recommendedResultsCard
      ? 'results-companion:interactive'
      : '',
    results_detail_block: recommendedResultsCard ? 'chart' : '',
    results_detail_item_index: recommendedResultsCard ? 0 : null,
    results_detail_focus_key: recommendedResultsCard ? 'chart-marker:0' : '',
    results_detail_selection_key: recommendedResultsCard ? 'results-detail:chart' : '',
    codecheck_surface: codecheckEnabled ? 'drilldown' : '',
    codecheck_filtered_row_index: codecheckEnabled ? 0 : null,
    codecheck_companion: codecheckEnabled ? 'detail' : '',
    codecheck_companion_item_index: codecheckEnabled ? 0 : null,
    codecheck_companion_focus_key: codecheckEnabled ? 'row-provenance:jump-row' : '',
    codecheck_companion_selection_key: codecheckEnabled
      ? 'codecheck-companion:detail'
      : '',
    codecheck_detail_block: codecheckEnabled ? 'row-provenance' : '',
    codecheck_detail_item_index: codecheckEnabled ? 0 : null,
    codecheck_detail_focus_key: codecheckEnabled ? 'row-provenance:jump-row' : '',
    codecheck_detail_selection_key: codecheckEnabled
      ? 'codecheck-detail:row-provenance'
      : '',
    codecheck_appendix_block: codecheckEnabled ? 'subset-summary' : '',
    codecheck_appendix_item_index: codecheckEnabled ? 0 : null,
    codecheck_appendix_focus_key: codecheckEnabled ? 'subset:current-slice' : '',
    codecheck_appendix_selection_key: codecheckEnabled
      ? 'codecheck-appendix:subset-summary'
      : '',
    interactive_detail_more: codecheckEnabled ? 'open' : '',
    overlay_focus: memberId ? 'member' : '',
    overlay_member_id: tokenString(locatorRow.member_id),
    overlay_group_id: tokenString(locatorRow.group_id),
    overlay_group_index: tokenString(locatorRow.group_index),
    overlay_row_id: tokenString(locatorRow.overlay_row_id),
    overlay_action_name: tokenString(locatorRow.action_name),
    overlay_story_band: tokenString(locatorRow.story_band_label) || tokenString(locatorRow.story_band),
    overlay_zone_label: tokenString(locatorRow.zone_label),
    overlay_selected_event_index: tokenString(locatorRow.selected_event_index),
    overlay_detail_more: memberId ? 'open' : '',
    source: [memberId, combinationName, recommendedResultsCard].some(Boolean)
      ? 'workbench_route'
      : '',
  }
}

function buildDrawingSelectionParams(
  drawingResource: ResourceState,
  viewerResource: ResourceState,
): DeepLinkParams {
  if (drawingResource.status !== 'ready' || !drawingResource.data) {
    return {}
  }

  const diffMemberIds = getArray(
    drawingResource.data,
    'mgt_export_source_output_mgt_diff_member_ids',
  )
    .map((value) => tokenString(value))
    .filter(Boolean)
  const diffMemberId = diffMemberIds[0] ?? ''
  const diffRowIndexMap = getRecord(
    drawingResource.data,
    'mgt_export_source_output_mgt_diff_member_row_indices',
  )
  const diffRowIndexes = diffRowIndexMap[diffMemberId]
  const diffIndexes = Array.isArray(diffRowIndexes)
    ? diffRowIndexes
        .map((value: unknown) => asNumber(value))
        .filter((value): value is number => value !== null)
    : []
  const diffIndex = diffIndexes[0] ?? null
  const viewerSelection = buildViewerSelectionParams(viewerResource)

  return {
    route_member_id: diffMemberId,
    route_story_band: tokenString(viewerSelection.story_band),
    route_diff_index: diffIndex,
    route_diff_row_id:
      diffIndex === null ? '' : `mgt-diff-row-${String(Math.trunc(diffIndex)).padStart(4, '0')}`,
    source: diffMemberId ? 'workbench_route' : '',
  }
}

function buildBenchmarkSelectionParams(routeTitle: string, resource: ResourceState): DeepLinkParams {
  if (resource.status !== 'ready' || !resource.data) {
    return {}
  }

  const mode = routeModeKey(routeTitle)
  const isPeerRoute =
    mode === 'benchmark_validation_route' || mode === 'submission_and_authority_route'

  return {
    route_benchmark_family: isPeerRoute ? 'peer' : 'canton',
    route_projection: isPeerRoute ? 'detail_section.svg' : 'detail_story_change_register.svg',
    route_case_id: isPeerRoute
      ? asString(resource.data.peer_case_id)
      : asString(resource.data.canton_case_id),
    source: 'workbench_route',
  }
}

const committeeAppendixRouteMap: Record<string, string> = {
  interactive_evidence_route: 'row-provenance',
  drawing_first_review_route: 'native-roundtrip',
  benchmark_validation_route: 'irregular-structure',
  submission_and_authority_route: 'row-provenance',
}

function resolveCommitteeAppendixBlock(routeTitle: string): string {
  return committeeAppendixRouteMap[routeModeKey(routeTitle)] ?? 'row-provenance'
}

function buildCommitteeSelectionParams(
  routeTitle: string,
  summaryResource: ResourceState,
  reportResource: ResourceState,
  viewerResource: ResourceState,
): DeepLinkParams {
  const reportData = reportResource.status === 'ready' ? reportResource.data : null
  const summaryData = summaryResource.status === 'ready' ? summaryResource.data : null
  const viewerSelection = buildViewerSelectionParams(viewerResource)
  const authorityRow =
    getArray(reportData, 'authority_rows').find(isRecord)
    ?? getArray(summaryData, 'authority_rows').find(isRecord)
    ?? {}
  const candidateRow =
    getArray(reportData, 'accepted_candidate_rows').find(isRecord)
    ?? getArray(summaryData, 'accepted_candidate_rows').find(isRecord)
    ?? {}
  const designChangeRow =
    getArray(reportData, 'design_change_rows').find(isRecord)
    ?? getArray(summaryData, 'design_change_rows').find(isRecord)
    ?? {}

  const routeTrack = tokenString(authorityRow.track)
  const routeCaseId = tokenString(authorityRow.case_id)
  const routeStoryBand =
    tokenString(candidateRow.story_band) || tokenString(designChangeRow.story_band)
  const routeZoneLabel =
    tokenString(candidateRow.zone_label) || tokenString(designChangeRow.zone_label)
  const routeMemberType =
    tokenString(candidateRow.member_type) || tokenString(designChangeRow.member_type)
  const routeAppendixBlock = resolveCommitteeAppendixBlock(routeTitle)
  const routeCombinationName =
    tokenString(viewerSelection.combination_name) || tokenString(viewerSelection.combination)
  const routeClauseLabel = tokenString(viewerSelection.clause_label)
  const routeReviewMemberId = tokenString(viewerSelection.member_id)
  const routeBaselineFocusMemberId = tokenString(viewerSelection.baseline_focus_member_id)
  const routeHazardType = tokenString(viewerSelection.hazard_type)
  const routeRuleFamily = tokenString(viewerSelection.rule_family)

  return {
    route_track: routeTrack,
    route_case_id: routeCaseId,
    route_candidate_id: tokenString(candidateRow.candidate_id),
    route_story_band: routeStoryBand,
    route_zone_label: routeZoneLabel,
    route_member_type: routeMemberType,
    route_action_name: tokenString(candidateRow.action_name),
    route_appendix_block: routeAppendixBlock,
    route_combination_name: routeCombinationName,
    route_clause_label: routeClauseLabel,
    route_review_member_id: routeReviewMemberId,
    route_baseline_focus_member_id: routeBaselineFocusMemberId,
    route_hazard_type: routeHazardType,
    route_rule_family: routeRuleFamily,
    source: [
      routeTrack,
      routeCaseId,
      routeStoryBand,
      routeAppendixBlock,
      routeCombinationName,
    ].some(Boolean)
      ? 'workbench_route'
      : '',
  }
}

function App() {
  const [activeSurfaceId, setActiveSurfaceId] = useState<ReviewSurfaceId>(reviewSurfaces[0].id)
  const [resources, setResources] = useState<ResourceMap>(createInitialResources())
  const [authoringControls, setAuthoringControls] = useState<AuthoringControls>(createDefaultAuthoringControls)
  const [authoringSeeded, setAuthoringSeeded] = useState(false)
  const [authoringStorageChecked, setAuthoringStorageChecked] = useState(false)
  const [authoringDraftStatus, setAuthoringDraftStatus] = useState('Waiting for baseline or saved draft.')
  const [reviewRowStates, setReviewRowStates] = useState<Record<string, ReviewRowState>>({})
  const [reviewStorageChecked, setReviewStorageChecked] = useState(false)
  const [reviewDraftStatus, setReviewDraftStatus] = useState('Waiting for baseline or saved review state.')
  const baselineAuthoringControls = buildBaselineAuthoringControls(resources.authoring)

  useEffect(() => {
    let cancelled = false

    async function loadResources() {
      const [
        authoring,
        authoringSolver,
        authoringOpsBundle,
        authoringOpsBatch,
        authoringOpsRegistry,
        authoringPortfolio,
        authoringServerOps,
        authoringFamilyTrack,
        authoringRuntimeSubmissionLane,
        authoringRuntimeWritebackDepth,
        authoringMultiProjectRuntimeWriteback,
        authoringSolverFamilyBreadth,
        authoringLocalRuntimeScenarioDepth,
        authoringLocalVariantWritebackTrace,
        authoringWritebackBreadth,
        viewer,
        drawing,
        benchmark,
        committeeSummary,
        committeeReport,
        developerPreview,
        phase5GuiWorkflow,
        coreApiResult,
        coreApiReport,
        commercialWorkflowBreadth,
        releaseGap,
        registry,
        registryIndex,
        batch,
      ] = await Promise.all([
        fetchFirstJson([
          './implementation/phase1/release/authoring/native_authoring_workspace_summary.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/native_authoring_solver_session.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/native_authoring_ops_bundle.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/native_authoring_batch_job_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/native_authoring_project_registry.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio.json',
          './implementation/phase1/release/authoring/portfolio/native_authoring_project_registry_workspace.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/project_ops_service_snapshot.json',
          './implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio_batch.json',
          './implementation/phase1/release/authoring/native_authoring_job_manifest.json',
          './implementation/phase1/release/authoring/native_authoring_ops_bundle.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_family_tracks.json',
          './implementation/phase1/release/authoring/portfolio/native_authoring_project_registry_index.json',
          './implementation/phase1/release/authoring/portfolio/native_authoring_project_registry_workspace.json',
          './implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_runtime_submission_lane.json',
          './implementation/phase1/release/project_ops_service_snapshot.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_runtime_writeback_depth_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_multi_project_runtime_writeback_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_solver_family_breadth_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_local_runtime_scenario_depth_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_local_variant_writeback_trace_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/authoring/portfolio/native_authoring_writeback_breadth_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/visualization/structural_optimization_viewer.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/visualization/optimized_drawing_review_summary.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/visualization/benchmark_optimization_review_summary.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/committee_review/committee_summary.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/committee_review/committee_review_package_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release_evidence/productization/developer_preview_readiness.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release_evidence/productization/phase5_gui_workflow_readiness_receipt.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release_evidence/productization/phase1_core_api_model_health_result.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release_evidence/productization/phase1_core_api_model_health_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/commercial_workflow_breadth_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/release_gap_report.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/project_registry.json',
          './implementation/phase1/release/release_registry.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/project_registry_portfolio_workspace.json',
          './implementation/phase1/release/project_registry_index.json',
        ]),
        fetchFirstJson([
          './implementation/phase1/release/external_benchmark_kickoff/external_benchmark_batch_job_report.json',
          './implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json',
        ]),
      ])

      if (cancelled) {
        return
      }

      startTransition(() => {
        setResources({
          authoring,
          authoringSolver,
          authoringOpsBundle,
          authoringOpsBatch,
          authoringOpsRegistry,
          authoringPortfolio,
          authoringServerOps,
          authoringFamilyTrack,
          authoringRuntimeSubmissionLane,
          authoringRuntimeWritebackDepth,
          authoringMultiProjectRuntimeWriteback,
          authoringSolverFamilyBreadth,
          authoringLocalRuntimeScenarioDepth,
          authoringLocalVariantWritebackTrace,
          authoringWritebackBreadth,
          viewer,
          drawing,
          benchmark,
          committeeSummary,
          committeeReport,
          developerPreview,
          phase5GuiWorkflow,
          coreApiResult,
          coreApiReport,
          commercialWorkflowBreadth,
          releaseGap,
          registry,
          registryIndex,
          batch,
        })
      })
    }

    void loadResources()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (authoringStorageChecked || typeof window === 'undefined') {
      return
    }

    const savedDraft = window.localStorage.getItem(authoringDraftStorageKey)
    if (!savedDraft) {
      setAuthoringStorageChecked(true)
      return
    }

    try {
      const restoredControls = parseAuthoringControls(JSON.parse(savedDraft), createDefaultAuthoringControls())
      if (!restoredControls) {
        throw new Error('Saved draft is missing authoring controls.')
      }
      startTransition(() => {
        setAuthoringControls(restoredControls)
        setAuthoringSeeded(true)
        setAuthoringStorageChecked(true)
        setAuthoringDraftStatus('Draft restored from browser storage.')
      })
    } catch (error) {
      window.localStorage.removeItem(authoringDraftStorageKey)
      startTransition(() => {
        setAuthoringStorageChecked(true)
        setAuthoringDraftStatus('Saved draft was invalid and has been cleared.')
      })
    }
  }, [authoringStorageChecked])

  useEffect(() => {
    if (
      authoringSeeded
      || !authoringStorageChecked
      || resources.authoring.status !== 'ready'
      || !resources.authoring.data
    ) {
      return
    }

    startTransition(() => {
      setAuthoringControls(baselineAuthoringControls)
      setAuthoringSeeded(true)
      setAuthoringDraftStatus('Baseline loaded from release summary.')
    })
  }, [authoringSeeded, authoringStorageChecked, baselineAuthoringControls, resources.authoring])

  useEffect(() => {
    if (!authoringSeeded || typeof window === 'undefined') {
      return
    }

    try {
      window.localStorage.setItem(
        authoringDraftStorageKey,
        JSON.stringify(buildAuthoringDraftPayload(authoringControls)),
      )
    } catch (error) {
      startTransition(() => {
        setAuthoringDraftStatus('Browser storage is unavailable; draft stays in memory.')
      })
    }
  }, [authoringControls, authoringSeeded])

  useEffect(() => {
    if (reviewStorageChecked || typeof window === 'undefined') {
      return
    }

    const savedReviewState = window.localStorage.getItem(reviewStateStorageKey)
    if (!savedReviewState) {
      setReviewStorageChecked(true)
      return
    }

    try {
      const restoredRowStates = buildReviewStateMapFromSource(JSON.parse(savedReviewState))
      if (!restoredRowStates) {
        throw new Error('Saved review state is missing row states.')
      }
      startTransition(() => {
        setReviewRowStates(restoredRowStates)
        setReviewStorageChecked(true)
        setReviewDraftStatus('Review state restored from browser storage.')
      })
    } catch (error) {
      window.localStorage.removeItem(reviewStateStorageKey)
      startTransition(() => {
        setReviewStorageChecked(true)
        setReviewDraftStatus('Saved review state was invalid and has been cleared.')
      })
    }
  }, [reviewStorageChecked])

  useEffect(() => {
    if (!reviewStorageChecked || typeof window === 'undefined') {
      return
    }

    try {
      window.localStorage.setItem(
        reviewStateStorageKey,
        JSON.stringify(buildReviewStateStoragePayload(reviewRowStates)),
      )
    } catch (error) {
      startTransition(() => {
        setReviewDraftStatus('Browser storage is unavailable; review state stays in memory.')
      })
    }
  }, [reviewRowStates, reviewStorageChecked])

  const authoringSnapshot = buildAuthoringSnapshot(resources.authoring)
  const authoringSolverSnapshot = buildAuthoringSolverSnapshot(resources.authoringSolver)
  const authoringOpsBundleSnapshot = buildAuthoringOpsBundleSnapshot(resources.authoringOpsBundle)
  const authoringOpsBatchSnapshot = buildBatchSnapshot(resources.authoringOpsBatch)
  const authoringOpsRegistrySnapshot = buildRegistrySnapshot(resources.authoringOpsRegistry)
  const authoringFamilyCorpusSnapshot = buildAuthoringFamilyCorpusSnapshot(resources.releaseGap)
  const authoringFamilyLocalEvidenceSnapshot = buildAuthoringFamilyLocalEvidenceSnapshot(resources.releaseGap)
  const authoringServerOpsSnapshot = buildAuthoringServerOpsSnapshot(resources.authoringServerOps)
  const authoringFamilyTrackSnapshot = buildAuthoringFamilyTrackSnapshot(resources.authoringFamilyTrack)
  const authoringRuntimeSubmissionLaneSnapshot = buildAuthoringRuntimeSubmissionLaneSnapshot(
    resources.authoringRuntimeSubmissionLane,
  )
  const authoringRuntimeWritebackDepthSnapshot = buildAuthoringRuntimeWritebackDepthSnapshot(
    resources.authoringRuntimeWritebackDepth,
  )
  const authoringMultiProjectRuntimeWritebackSnapshot = buildAuthoringMultiProjectRuntimeWritebackSnapshot(
    resources.authoringMultiProjectRuntimeWriteback,
  )
  const authoringSolverFamilyBreadthSnapshot = buildAuthoringSolverFamilyBreadthSnapshot(
    resources.authoringSolverFamilyBreadth,
  )
  const authoringLocalRuntimeScenarioDepthSnapshot = buildAuthoringLocalRuntimeScenarioDepthSnapshot(
    resources.authoringLocalRuntimeScenarioDepth,
  )
  const authoringLocalVariantWritebackTraceSnapshot = buildAuthoringLocalVariantWritebackTraceSnapshot(
    resources.authoringLocalVariantWritebackTrace,
  )
  const authoringWritebackBreadthSnapshot = buildAuthoringWritebackBreadthSnapshot(
    resources.authoringWritebackBreadth,
  )
  const commercialWorkflowBreadthSnapshot = buildCommercialWorkflowBreadthSnapshot(
    resources.commercialWorkflowBreadth,
  )
  const developerPreviewSnapshot = buildDeveloperPreviewSnapshot(resources.developerPreview)
  const phase5WorkflowData = resources.phase5GuiWorkflow.data ?? {}
  const phase5WorkflowStatus = asString(phase5WorkflowData.status) || resources.phase5GuiWorkflow.status
  const phase5WorkflowTone: StatusTone =
    resources.phase5GuiWorkflow.status === 'missing' || resources.phase5GuiWorkflow.status === 'error'
      ? 'missing'
      : phase5WorkflowStatus === 'ready'
        ? 'ok'
        : 'warn'
  const phase5WorkflowStatusLabel =
    resources.phase5GuiWorkflow.status === 'ready'
      ? `workflow ${phase5WorkflowStatus}`
      : `workflow ${resources.phase5GuiWorkflow.status}`
  const phase5ShellStepCount = firstNumber(
    phase5WorkflowData.workflow_shell_step_pass_count,
    phase5WorkflowData.actual_gui_workflow_step_pass_count,
  ) ?? 0
  const phase5ExecutionStepCount = firstNumber(phase5WorkflowData.execution_workflow_step_pass_count) ?? 0
  const phase5RequiredStepCount = firstNumber(phase5WorkflowData.required_workflow_step_count) ?? developerPreviewWorkflowSteps.length
  const phase5BlockerCount = getArray(phase5WorkflowData, 'blockers').length
  const phase5ObservationPass = firstBoolean(phase5WorkflowData.human_ux_observation_claim) === true
  const phase5RouteState = buildDeveloperPreviewWorkflowState({
    workflowShellStepPassCount: phase5ShellStepCount,
    executionWorkflowStepPassCount: phase5ExecutionStepCount,
    requiredWorkflowStepCount: phase5RequiredStepCount,
    humanObservationPass: phase5ObservationPass,
    blockerCount: phase5BlockerCount,
  })
  const coreApiContractSnapshot = buildCoreApiContractSnapshot(resources.coreApiResult, resources.coreApiReport)
  const surfaceSnapshots: Record<ReviewSurfaceId, Snapshot> = {
    viewer: buildViewerSnapshot(resources.viewer),
    'drawing-review': buildDrawingSnapshot(resources.drawing),
    'real-drawing-3d': {
      statusLabel: 'Private local',
      tone: 'ok',
      metrics: [
        { label: 'Assets', value: '18' },
        { label: 'Renderable', value: '18' },
        { label: 'Solver exact', value: '7' },
      ],
      note: '구한 도면의 파생 topology를 기존 구조 웹뷰어 preset으로 엽니다.',
      sourceLabel: 'src/structure-viewer/index.real_drawing_private.data.js',
    },
    'benchmark-review': buildBenchmarkSnapshot(resources.benchmark),
    committee: buildCommitteeSnapshot(resources.committeeSummary, resources.committeeReport),
  }

  const artifactSnapshots: Record<GovernanceArtifactId, Snapshot> = {
    gap: buildGapSnapshot(resources.releaseGap),
    registry: buildRegistrySnapshot(resources.registry),
    'registry-index': buildRegistryIndexSnapshot(resources.registryIndex),
    package: buildPackageSnapshot(resources.registry),
    signature: buildSignatureSnapshot(resources.registry),
    batch: buildBatchSnapshot(resources.batch),
  }
  const gapP0Snapshot = buildGapSeveritySnapshot(resources.releaseGap, 'P0')
  const gapP1Snapshot = buildGapSeveritySnapshot(resources.releaseGap, 'P1')
  const commercializationDepthSignals = buildCommercializationDepthSignals(resources.releaseGap)
  const commercializationDepthReadyCount = commercializationDepthSignals.filter((signal) => signal.ready).length
  const commercializationDepthTone: StatusTone =
    commercializationDepthSignals.length && commercializationDepthReadyCount === commercializationDepthSignals.length
      && gapP0Snapshot.openCount === 0
      && gapP1Snapshot.openCount === 0
      ? 'ok'
      : 'warn'
  const commercializationDepthSummaryLine = commercializationDepthSignals
    .map((signal) => `${signal.label.toLowerCase().replace(/\s+/g, '_')}=${signal.statusLabel}`)
    .join(' | ')
  const advancedHoldoutRows = buildAdvancedHoldoutRows(resources.releaseGap)
  const advancedHoldoutClosedCount = advancedHoldoutRows.filter((row) => row.isClosed).length
  const advancedHoldoutOpenCount = advancedHoldoutRows.length - advancedHoldoutClosedCount

  const activeSurface =
    reviewSurfaces.find((surface) => surface.id === activeSurfaceId) ?? reviewSurfaces[0]
  const activeSnapshot = surfaceSnapshots[activeSurface.id]
  const remainingGapMetric = artifactSnapshots.gap.metrics[0]?.value ?? 'n/a'
  const viewerCatalogMetric = surfaceSnapshots.viewer.metrics[0]?.value ?? 'n/a'
  const registrySignal = artifactSnapshots.registry.statusLabel
  const authoringSummary = getRecord(resources.authoring.data, 'summary')
  const authoringSolverAuthoringSummary = getRecord(resources.authoringSolver.data, 'authoring_summary')
  const authoringEditorControls = getRecord(resources.authoring.data, 'editor_controls')
  const authoringFamilyOptions = buildAuthoringFamilyOptions(resources.authoring)
  const selectedAuthoringFamily = findAuthoringFamilyOption(
    authoringFamilyOptions,
    tokenString(authoringControls.familyId) || createDefaultAuthoringControls().familyId,
  )
  const authoringPalette = getArray(authoringEditorControls, 'section_palette')
    .map((value) => tokenString(value))
    .filter(Boolean)
  const authoringSectionOptions = buildAuthoringSectionOptions(authoringPalette, selectedAuthoringFamily)
  const authoringSectionUsageCounts = firstRecord(
    [getRecord(authoringSolverAuthoringSummary, 'section_usage_counts'), getRecord(authoringSummary, 'section_usage_counts')],
    (value) => recordSize(value) > 0,
  )
  const authoringUsedSections = uniqueTokens(Object.keys(authoringSectionUsageCounts))
  const authoringPaletteFamilies = uniqueTokens(authoringPalette.map(classifyAuthoringSectionFamily))
  const authoringActiveFamilies = uniqueTokens(authoringUsedSections.map(classifyAuthoringSectionFamily))
  const authoringMemberTypes = uniqueTokens(
    Object.keys(
      firstRecord(
        [getRecord(authoringSummary, 'member_type_counts'), getRecord(authoringSolverAuthoringSummary, 'member_type_counts')],
        (value) => recordSize(value) > 0,
      ),
    ),
  )
  const authoringPortfolioResource =
    resources.authoringPortfolio.status === 'ready' ? resources.authoringPortfolio : resources.registryIndex
  const authoringPortfolioSummary = getRecord(authoringPortfolioResource.data, 'summary')
  const authoringPortfolioBatchSummary = getRecord(authoringPortfolioResource.data, 'batch_report_summary')
  const authoringPortfolioRegistrySummary = getRecord(authoringPortfolioResource.data, 'registry_index_summary')
  const authoringPortfolioFamilyRows = getArray(authoringPortfolioResource.data, 'family_rows').filter(isRecord)
  const authoringPortfolioFamilySnapshots = buildAuthoringPortfolioFamilySnapshots(
    authoringPortfolioResource,
    authoringFamilyOptions,
  )
  const authoringFamilyCoverageRows = buildAuthoringFamilyCoverageRows(
    authoringPortfolioFamilySnapshots,
    resources.authoringSolverFamilyBreadth,
    resources.authoringLocalRuntimeScenarioDepth,
    resources.authoringWritebackBreadth,
  )
  const authoringFamilyCoverageSnapshot = buildAuthoringFamilyCoverageSnapshot(authoringFamilyCoverageRows)
  const registryPortfolioSummary = getRecord(resources.registryIndex.data, 'summary')
  const registryPortfolioScan = getRecord(resources.registryIndex.data, 'scan')
  const registryPortfolioScanSummary = getRecord(registryPortfolioScan, 'summary')
  const registryPortfolioProjectRows = getArray(resources.registryIndex.data, 'project_rows').filter(isRecord)
  const authoringPortfolioProjectCount = firstNumber(
    authoringPortfolioSummary.registry_project_count,
    registryPortfolioSummary.project_count,
    registryPortfolioProjectRows.length,
  )
  const authoringPortfolioFamilyCount = firstNumber(
    authoringPortfolioSummary.family_count,
    authoringPortfolioFamilyRows.length,
  )
  const authoringPortfolioCompleteCount = firstNumber(
    authoringPortfolioSummary.complete_family_count,
    registryPortfolioSummary.complete_project_count,
  )
  const authoringPortfolioSignatureCount = firstNumber(
    authoringPortfolioSummary.registry_signature_verified_count,
    authoringPortfolioRegistrySummary.signature_verified_count,
    registryPortfolioSummary.signature_verified_count,
  )
  const authoringPortfolioReproCount = firstNumber(
    authoringPortfolioSummary.registry_reproducible_count,
    authoringPortfolioRegistrySummary.package_reproducible_count,
    registryPortfolioSummary.package_reproducible_count,
  )
  const authoringPortfolioComboCount = firstNumber(authoringPortfolioSummary.solver_combo_count)
  const authoringPortfolioSnapshotCount = firstNumber(
    authoringPortfolioSummary.batch_snapshot_count,
    authoringPortfolioBatchSummary.snapshot_count,
  )
  const authoringPortfolioUnmatchedCount = firstNumber(registryPortfolioScanSummary.unmatched_input_count)
  const authoringBreadthReady =
    authoringPaletteFamilies.length >= 3 && (authoringPortfolioFamilyCount ?? authoringPortfolioProjectCount ?? 0) >= 1
  const authoringBreadthStatusLabel = authoringBreadthReady ? 'breadth evidence attached' : 'breadth evidence scoped'
  const authoringBreadthTone: StatusTone = authoringBreadthReady ? 'ok' : 'warn'
  const authoringBreadthNote = [
    `palette families=${authoringPaletteFamilies.length || 0} (${compactLabelList(authoringPaletteFamilies)})`,
    `active sections=${authoringUsedSections.length || 0} (${compactLabelList(authoringActiveFamilies)})`,
    `member types=${compactLabelList(authoringMemberTypes)}`,
  ].join(' | ')
  const authoringPortfolioNote = [
    `families=${compactCount(authoringPortfolioFamilyCount)}`,
    `projects=${compactCount(authoringPortfolioProjectCount)}`,
    `complete=${compactCount(authoringPortfolioCompleteCount)}`,
    `signature=${compactCount(authoringPortfolioSignatureCount)}`,
    `repro=${compactCount(authoringPortfolioReproCount)}`,
    `combos=${compactCount(authoringPortfolioComboCount)}`,
    `snapshots=${compactCount(authoringPortfolioSnapshotCount)}`,
    `unmatched_inputs=${compactCount(authoringPortfolioUnmatchedCount)}`,
  ].join(' | ')
  const authoringPortfolioScopeLabel = resources.authoringPortfolio.status === 'ready'
    ? 'manifest'
    : resources.registryIndex.status === 'ready'
      ? 'registry fallback'
      : 'missing'
  const authoringPortfolioSourceLabel = authoringPortfolioResource.source
    ? sourceLabel(authoringPortfolioResource.source)
    : 'not loaded'
  const authoringConsistencySnapshot = buildAuthoringConsistencySnapshot(
    authoringPortfolioScopeLabel,
    authoringPortfolioSourceLabel,
    authoringFamilyTrackSnapshot,
    authoringRuntimeSubmissionLaneSnapshot,
    authoringServerOpsSnapshot,
  )
  const authoringStoryCount = clampNumber(authoringControls.storyCount, 5, 1, 40)
  const authoringBayCount = clampNumber(authoringControls.bayCount, 3, 1, 12)
  const authoringFloorHeight = clampNumber(authoringControls.floorHeightM, 3.9, 2.5, 6)
  const authoringLoadPatternCount = clampNumber(authoringControls.loadPatternCount, 4, 1, 12)
  const authoringNodeCount = (authoringStoryCount + 1) * (authoringBayCount + 1)
  const authoringMemberCount = estimateAuthoringMemberCount(
    selectedAuthoringFamily.familyId,
    authoringStoryCount,
    authoringBayCount,
  )
  const authoringEstimatedScore = Math.min(
    100,
    42
      + authoringStoryCount * 4.0
      + authoringBayCount * 3.5
      + authoringLoadPatternCount * 4.5
      + (authoringControls.sectionId ? 8 : 0)
      + (selectedAuthoringFamily.familyId === 'steel_braced_frame' ? 6 : 0)
      + (selectedAuthoringFamily.familyId === 'rc_wall_core' ? 4 : 0)
      + (selectedAuthoringFamily.familyId === 'composite_podium' ? 5 : 0),
  )
  const authoringDraftSummaryLine = `Draft authoring bundle: ${authoringEstimatedScore >= 82 ? 'PASS' : 'CHECK'} | family=${selectedAuthoringFamily.label} | stories=${authoringStoryCount} | nodes=${authoringNodeCount} | members=${authoringMemberCount} | loads=${authoringLoadPatternCount} | floor=${authoringFloorHeight.toFixed(1)}m`
  const authoringJsonHref = './implementation/phase1/release/authoring/native_authoring_workspace_summary.json'
  const authoringExportHref = buildAuthoringExportHref(authoringControls)
  const authoringSolverHref = './implementation/phase1/release/authoring/native_authoring_solver_session.json'
  const authoringSolverLoadcombHref = './implementation/phase1/release/authoring/native_authoring_solver_session.loadcomb_preview.mgt'
  const authoringOpsBundleHref = './implementation/phase1/release/authoring/native_authoring_ops_bundle.json'
  const authoringOpsBatchHref = './implementation/phase1/release/authoring/native_authoring_batch_job_report.json'
  const authoringOpsRegistryHref = './implementation/phase1/release/authoring/native_authoring_project_registry.json'
  const authoringOpsPackageHref = './implementation/phase1/release/authoring/native_authoring_project_package.zip'
  const authoringOpsSignatureHref = './implementation/phase1/release/signing/native_authoring_project_registry.signature.b64'
  const authoringPortfolioHref = './implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio.json'
  const authoringFamilyCorpusHref =
    './implementation/phase1/release/authoring/portfolio/native_authoring_family_corpus_manifest.json'
  const authoringFamilyLocalEvidenceHref =
    './implementation/phase1/release/authoring/portfolio/native_authoring_family_local_evidence_manifest.json'
  const authoringPortfolioWorkspaceHref = './implementation/phase1/release/authoring/portfolio/native_authoring_project_registry_workspace.json'
  const authoringRuntimeWritebackDepthHref = './implementation/phase1/release/authoring/portfolio/native_authoring_runtime_writeback_depth_report.json'
  const authoringMultiProjectRuntimeWritebackHref = './implementation/phase1/release/authoring/portfolio/native_authoring_multi_project_runtime_writeback_report.json'
  const authoringSolverFamilyBreadthHref = './implementation/phase1/release/authoring/portfolio/native_authoring_solver_family_breadth_report.json'
  const authoringLocalRuntimeScenarioDepthHref = './implementation/phase1/release/authoring/portfolio/native_authoring_local_runtime_scenario_depth_report.json'
  const authoringLocalVariantWritebackTraceHref = './implementation/phase1/release/authoring/portfolio/native_authoring_local_variant_writeback_trace_report.json'
  const authoringWritebackBreadthHref = './implementation/phase1/release/authoring/portfolio/native_authoring_writeback_breadth_report.json'
  const reviewStateSourceHref = resources.releaseGap.source || './implementation/phase1/release/release_gap_report.json'
  const reviewableGapRows = buildReviewableGapRows(resources.releaseGap)
  const reviewBoardSnapshot = buildReviewStateSummary(reviewableGapRows, reviewRowStates)
  const reviewStateExportHref = buildReviewStateExportHref(reviewableGapRows, reviewRowStates, reviewStateSourceHref)

  function applyAuthoringControls(nextControls: AuthoringControls, statusMessage: string) {
    startTransition(() => {
      setAuthoringControls(nextControls)
      setAuthoringSeeded(true)
      setAuthoringDraftStatus(statusMessage)
    })
  }

  function handleAuthoringReset() {
    applyAuthoringControls(baselineAuthoringControls, 'Draft reset to release baseline.')
  }

  async function handleAuthoringImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (!file) {
      return
    }

    try {
      const importedPayload = JSON.parse(await file.text()) as unknown
      const importedControls = parseAuthoringControls(importedPayload, baselineAuthoringControls)
      if (!importedControls) {
        throw new Error('Imported JSON is missing authoring controls.')
      }
      applyAuthoringControls(importedControls, `Imported draft from ${file.name}.`)
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Import failed.'
      startTransition(() => {
        setAuthoringDraftStatus(`Import failed: ${reason}`)
      })
    }
  }

  function applyReviewRowState(
    rowId: string,
    updater: (current: ReviewRowState) => ReviewRowState,
    statusMessage?: string,
  ) {
    startTransition(() => {
      setReviewRowStates((current) => {
        const nextState = updater(current[rowId] ?? createDefaultReviewRowState())
        return {
          ...current,
          [rowId]: nextState,
        }
      })
      if (statusMessage) {
        setReviewDraftStatus(statusMessage)
      }
    })
  }

  function setReviewDecision(rowId: string, decision: ReviewDecision) {
    applyReviewRowState(
      rowId,
      (current) => ({
        ...current,
        decision,
        updatedAt: new Date().toISOString(),
      }),
      `Review decision for ${rowId} marked ${reviewDecisionLabel(decision)}.`,
    )
  }

  function setReviewComment(rowId: string, comment: string) {
    applyReviewRowState(rowId, (current) => ({
      ...current,
      comment,
      updatedAt: new Date().toISOString(),
    }))
  }

  function setReviewIssueMarker(rowId: string, issueMarker: ReviewIssueMarker) {
    applyReviewRowState(
      rowId,
      (current) => ({
        ...current,
        issueMarker,
        updatedAt: new Date().toISOString(),
      }),
      `Issue marker for ${rowId} set to ${reviewIssueMarkerLabel(issueMarker)}.`,
    )
  }

  function clearReviewRowState(rowId: string) {
    applyReviewRowState(
      rowId,
      () => createDefaultReviewRowState(),
      `Review row ${rowId} reset to baseline.`,
    )
  }

  function handleReviewReset() {
    startTransition(() => {
      setReviewRowStates({})
      setReviewDraftStatus('Review state reset to baseline.')
    })
  }

  async function handleReviewImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (!file) {
      return
    }

    try {
      const importedPayload = JSON.parse(await file.text()) as unknown
      const importedReviewState = buildReviewStateMapFromSource(importedPayload)
      if (!importedReviewState) {
        throw new Error('Imported JSON is missing review row states.')
      }
      startTransition(() => {
        setReviewRowStates(importedReviewState)
        setReviewDraftStatus(`Imported review state from ${file.name}.`)
      })
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Import failed.'
      startTransition(() => {
        setReviewDraftStatus(`Import failed: ${reason}`)
      })
    }
  }

  function buildSurfaceRouteHref(
    surface: ReviewSurface,
    {
      routeTitle,
      routeStepIndex,
    }: {
      routeTitle: string
      routeStepIndex: number
    },
  ): string {
    const selectionParamsBySurface: Record<ReviewSurfaceId, DeepLinkParams> = {
      viewer: buildViewerSelectionParams(resources.viewer),
      'drawing-review': buildDrawingSelectionParams(resources.drawing, resources.viewer),
      'real-drawing-3d': {},
      'benchmark-review': buildBenchmarkSelectionParams(routeTitle, resources.benchmark),
      committee: buildCommitteeSelectionParams(
        routeTitle,
        resources.committeeSummary,
        resources.committeeReport,
        resources.viewer,
      ),
    }

    return buildDeepLinkHref(surface.href, {
      route_title: routeTitle,
      review_mode: routeModeKey(routeTitle),
      route_step: routeStepIndex,
      from_surface: activeSurface.id,
      from_label: activeSurface.title,
      target_surface: surface.id,
      target_label: surface.title,
      selection_status: activeSnapshot.statusLabel,
      source_label: activeSnapshot.sourceLabel,
      route_focus: resolveSurfaceRouteFocus(surface.id, routeTitle),
      return_to: buildWorkbenchReturnHref(surface.href),
      return_label: 'Structural Optimization Workbench',
      ...selectionParamsBySurface[surface.id],
      ...(surface.id === 'viewer'
        ? {
            view: 'core',
            focus: 'interactive3d',
          }
        : {}),
    })
  }

  function buildArtifactRouteHref(
    artifact: GovernanceArtifact,
    {
      routeTitle,
      routeStepIndex,
    }: {
      routeTitle: string
      routeStepIndex: number
    },
  ): string {
    return buildDeepLinkHref(artifact.href, {
      route_title: routeTitle,
      review_mode: routeModeKey(routeTitle),
      route_step: routeStepIndex,
      from_surface: activeSurface.id,
      from_label: activeSurface.title,
      target_surface: artifact.id,
      target_label: artifact.title,
      selection_status: activeSnapshot.statusLabel,
      source_label: activeSnapshot.sourceLabel,
      return_to: buildWorkbenchReturnHref(artifact.href),
      return_label: 'Structural Optimization Workbench',
    })
  }

  function buildSurfaceRouteStep(
    index: number,
    surfaceId: ReviewSurfaceId,
    routeTitle: string,
    description: string,
  ): RouteStep {
    const surface = getReviewSurface(surfaceId)
    const snapshot = surfaceSnapshots[surfaceId]
    return {
      id: `surface-${surfaceId}`,
      index,
      title: surface.title,
      href: buildSurfaceRouteHref(surface, {
        routeTitle,
        routeStepIndex: index,
      }),
      badge: surface.badge,
      tone: snapshot.tone,
      statusLabel: snapshot.statusLabel,
      description,
      note: snapshot.note,
    }
  }

  function buildArtifactRouteStep(
    index: number,
    artifactId: GovernanceArtifactId,
    routeTitle: string,
    description: string,
  ): RouteStep {
    const artifact = getGovernanceArtifact(artifactId)
    const snapshot = artifactSnapshots[artifactId]
    return {
      id: `artifact-${artifactId}`,
      index,
      title: artifact.title,
      href: buildArtifactRouteHref(artifact, {
        routeTitle,
        routeStepIndex: index,
      }),
      badge: artifact.badge,
      tone: snapshot.tone,
      statusLabel: snapshot.statusLabel,
      description,
      note: snapshot.note,
    }
  }

  const routePlan: RoutePlan = (() => {
    switch (activeSurface.id) {
      case 'drawing-review':
        return {
          title: 'Drawing-first review route',
          description:
            '도면 패키지에서 변경 그룹과 시트 맥락을 먼저 읽고, 3D provenance와 제출 경계로 내려가는 경로입니다.',
          finishArtifactId: 'registry',
          steps: [
            buildSurfaceRouteStep(1, 'drawing-review', 'Drawing-first review route', '변경 그룹, member count, DCR 상한을 먼저 확인합니다.'),
            buildSurfaceRouteStep(2, 'viewer', 'Drawing-first review route', '문제가 보인 그룹을 3D viewer와 row provenance로 다시 따라갑니다.'),
            buildSurfaceRouteStep(3, 'committee', 'Drawing-first review route', '외부 검토/위원회 패키지 상태와 승인 경계를 확인합니다.'),
            buildArtifactRouteStep(4, 'registry', 'Drawing-first review route', '최종 제출 전 signed registry와 package 근거를 확인합니다.'),
          ],
        }
      case 'benchmark-review':
        return {
          title: 'Benchmark validation route',
          description:
            '대표 벤치마크 비교를 먼저 보고, 실행/재실행 상태와 위원회 패키지까지 이어지는 검증 경로입니다.',
          finishArtifactId: 'batch',
          steps: [
            buildSurfaceRouteStep(1, 'benchmark-review', 'Benchmark validation route', 'Canton / PEER 비교와 readiness sheet를 먼저 읽습니다.'),
            buildSurfaceRouteStep(2, 'viewer', 'Benchmark validation route', '벤치마크에서 걸린 shape/provenance를 viewer에서 재확인합니다.'),
            buildArtifactRouteStep(3, 'batch', 'Benchmark validation route', '외부 벤치마크 실행 상태와 rerun 필요 여부를 확인합니다.'),
            buildSurfaceRouteStep(4, 'committee', 'Benchmark validation route', '대외 검토 패키지와 제출 흐름으로 마무리합니다.'),
          ],
        }
      case 'committee':
        return {
          title: 'Submission and authority route',
          description:
            '위원회/승인 관점에서 패키지 상태를 먼저 보고, registry와 release boundary 근거를 닫는 경로입니다.',
          finishArtifactId: 'gap',
          steps: [
            buildSurfaceRouteStep(1, 'committee', 'Submission and authority route', 'committee packet, accepted actions, authority rows를 먼저 확인합니다.'),
            buildArtifactRouteStep(2, 'registry', 'Submission and authority route', 'registry / signature / package 상태를 검토합니다.'),
            buildArtifactRouteStep(3, 'gap', 'Submission and authority route', '남아 있는 제품화 갭과 boundary 근거를 점검합니다.'),
            buildSurfaceRouteStep(4, 'viewer', 'Submission and authority route', '필요하면 interactive viewer로 다시 내려가 상세 근거를 확인합니다.'),
          ],
        }
      case 'viewer':
      default:
        return {
          title: 'Interactive evidence route',
          description:
            '행 단위 provenance와 3D 결과를 먼저 확인하고, 도면 패키지와 제출 경계까지 순차적으로 닫는 기본 경로입니다.',
          finishArtifactId: 'gap',
          steps: [
            buildSurfaceRouteStep(1, 'viewer', 'Interactive evidence route', 'interactive 3D, results explorer, row provenance를 먼저 확인합니다.'),
            buildSurfaceRouteStep(2, 'drawing-review', 'Interactive evidence route', '문제 부재를 도면 패키지와 before/after sheet로 넘깁니다.'),
            buildSurfaceRouteStep(3, 'committee', 'Interactive evidence route', '위원회 패키지와 외부 검토용 라우팅을 확인합니다.'),
            buildArtifactRouteStep(4, 'gap', 'Interactive evidence route', 'release boundary와 잔여 상용화 갭을 최종 확인합니다.'),
          ],
        }
    }
  })()

  const activeSurfaceIdentity = reviewSurfaceIdentity[activeSurface.id]
  const finishArtifact = getGovernanceArtifact(routePlan.finishArtifactId)
  const finishArtifactSnapshot = artifactSnapshots[routePlan.finishArtifactId]
  const activeSurfaceHref = buildSurfaceRouteHref(activeSurface, {
    routeTitle: routePlan.title,
    routeStepIndex: 0,
  })
  const suiteHighlights = [
    {
      label: 'Immersive evidence',
      value: `${viewerCatalogMetric} catalog entries`,
      note: '3D viewer, optimization history, and row provenance stay one click away.',
    },
    {
      label: 'Linked review desks',
      value: `${reviewSurfaces.length} connected surfaces`,
      note: 'Drawing review, benchmark validation, and committee handoff share the same shell.',
    },
    {
      label: 'Release boundary',
      value: `${remainingGapMetric} open gaps`,
      note: `Registry and package readiness currently reads ${registrySignal.toLowerCase()}.`,
    },
  ]
  const heroStatusBlocks = [
    {
      label: 'Surface family',
      value: activeSurfaceIdentity.family,
      note: activeSurfaceIdentity.cue,
    },
    {
      label: 'Review mode',
      value: activeSurfaceIdentity.mode,
      note: routePlan.title,
    },
    {
      label: 'Finish gate',
      value: finishArtifact.title,
      note: finishArtifactSnapshot.statusLabel,
    },
  ]
  const previewContext = [
    { label: 'Mode', value: activeSurfaceIdentity.mode },
    { label: 'Track', value: activeSurfaceIdentity.track },
    { label: 'Route', value: routePlan.title },
    { label: 'Source', value: activeSnapshot.sourceLabel },
  ]

  return (
    <main className="shell">
      <div className="shell__glow shell__glow--a" />
      <div className="shell__glow shell__glow--b" />
      <section className="hero">
        <div className="hero__copy">
          <div className="hero__eyebrow-row">
            <p className="eyebrow">Structural Signal Desk</p>
            <span className="hero__suite-pill">AI-optimized review suite</span>
          </div>
          <h1>구조해석, AI 최적화 도면 검토, 제출 거버넌스를 하나의 제품 진입면으로 묶는 워크벤치</h1>
          <p className="hero__lede">
            release viewer, drawing review, benchmark validation, committee desk, registry boundary를
            하나의 진입면으로 연결했습니다. React 셸이 단순 런처가 아니라 구조 해석 근거와
            AI 최적화 검토 흐름을 함께 조망하는 front door처럼 읽히도록 정리했습니다.
          </p>
          <div className="hero__chips">
            <span>{reviewSurfaces.length} linked desks</span>
            <span>{viewerCatalogMetric} evidence catalog entries</span>
            <span>{remainingGapMetric} commercialization gaps</span>
            <span>registry {registrySignal}</span>
          </div>
          <div className="hero__overview-grid">
            {suiteHighlights.map((highlight) => (
              <article key={highlight.label} className="hero__overview-card">
                <p className="hero__overview-label">{highlight.label}</p>
                <strong>{highlight.value}</strong>
                <p>{highlight.note}</p>
              </article>
            ))}
          </div>
        </div>
        <div className="hero__status panel">
          <div className="panel__header panel__header--stacked">
            <div>
              <p className="panel__kicker">Active Desk</p>
              <h2>{activeSurface.title}</h2>
            </div>
            <span className={`status-pill status-pill--${activeSnapshot.tone}`}>
              {activeSnapshot.statusLabel}
            </span>
          </div>
          <div className="hero__status-rail">
            {heroStatusBlocks.map((block) => (
              <article key={block.label} className="hero__status-block">
                <p className="hero__status-label">{block.label}</p>
                <strong>{block.value}</strong>
                <p>{block.note}</p>
              </article>
            ))}
          </div>
          <p className="hero__surface-summary">{activeSurface.description}</p>
          <dl className="metric-list">
            {activeSnapshot.metrics.map((metric) => (
              <div key={`${activeSurface.id}-${metric.label}`}>
                <dt>{metric.label}</dt>
                <dd>{metric.value}</dd>
              </div>
            ))}
            <div>
              <dt>Asset</dt>
              <dd>{activeSurface.href}</dd>
            </div>
          </dl>
          <p className="panel__note">{activeSnapshot.note}</p>
          <p className="panel__source">source: {activeSnapshot.sourceLabel}</p>
          <a className="button button--primary" href={activeSurfaceHref} target="_blank" rel="noreferrer">
            Open active surface
          </a>
        </div>
      </section>

      <DeveloperPreviewWorkflowPanel
        statusTone={phase5WorkflowTone}
        statusLabel={phase5WorkflowStatusLabel}
        shellStepCountLabel={`${compactCount(phase5ShellStepCount)}/${compactCount(phase5RequiredStepCount)}`}
        executionStepCountLabel={`${compactCount(phase5ExecutionStepCount)}/${compactCount(phase5RequiredStepCount)}`}
        observationStatusLabel={phase5ObservationPass ? 'ready' : 'blocked'}
        blockerCountLabel={compactCount(phase5BlockerCount)}
        routeState={phase5RouteState}
        steps={developerPreviewWorkflowSteps}
        sourceLabel={resources.phase5GuiWorkflow.source || 'phase5_gui_workflow_readiness_receipt.json'}
      />

      <section className="workspace">
        <div className="panel">
          <div className="panel__header">
            <div>
              <p className="panel__kicker">Suite Desks</p>
              <h2>우선순위가 높은 구조 검토 데스크</h2>
            </div>
            <p className="panel__hint">카드를 누르면 우측 미리보기와 상태 카드가 같이 바뀝니다.</p>
          </div>
          <div className="surface-list">
            {reviewSurfaces.map((surface) => {
              const snapshot = surfaceSnapshots[surface.id]
              const identity = reviewSurfaceIdentity[surface.id]
              return (
                <button
                  key={surface.id}
                  className={`surface-card ${surface.id === activeSurface.id ? 'surface-card--active' : ''}`}
                  onClick={() => setActiveSurfaceId(surface.id)}
                  type="button"
                >
                  <div className="surface-card__top">
                    <span className="surface-card__badge">{surface.badge}</span>
                    <span className={`status-pill status-pill--${snapshot.tone}`}>
                      {snapshot.statusLabel}
                    </span>
                  </div>
                  <strong>{surface.title}</strong>
                  <p className="surface-card__mode">{identity.mode}</p>
                  <p>{surface.description}</p>
                  <div className="mini-metric-grid">
                    {snapshot.metrics.slice(0, 2).map((metric) => (
                      <div key={`${surface.id}-${metric.label}`} className="mini-metric">
                        <span>{metric.label}</span>
                        <strong>{metric.value}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="surface-card__signals">
                    <span>{identity.family}</span>
                    <span>{identity.track}</span>
                  </div>
                  <p className="surface-card__note">{snapshot.note}</p>
                  <span className="surface-card__path">{surface.href}</span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="panel preview-panel">
          <div className="panel__header">
            <div>
              <p className="panel__kicker">Embedded Preview</p>
              <h2>{activeSurface.title}</h2>
            </div>
            <a className="button button--ghost" href={activeSurfaceHref} target="_blank" rel="noreferrer">
              Open in new tab
            </a>
          </div>
          <div className="preview-panel__meta">
            {previewContext.map((item) => (
              <div key={item.label} className="preview-panel__meta-item">
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
          <div className="preview-frame">
            <iframe src={activeSurfaceHref} title={activeSurface.title} />
          </div>
        </div>
      </section>

      <section className="panel panel--authoring">
        <div className="panel__header">
          <div>
            <p className="panel__kicker">Native Authoring Workspace</p>
            <h2>story-node-member-load 초안을 바로 조정하는 편집 셸</h2>
          </div>
          <span className={`status-pill status-pill--${authoringSnapshot.tone}`}>
            {authoringSnapshot.statusLabel}
          </span>
        </div>
        <div className="authoring-grid">
          <div className="authoring-card">
            <p className="authoring-card__title">Release baseline</p>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringSnapshot.metrics.map((metric) => (
                <div key={`authoring-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringSnapshot.note}</p>
            <p className="artifact-card__source">source: {authoringSnapshot.sourceLabel}</p>
            <a className="button button--ghost" href={authoringJsonHref} target="_blank" rel="noreferrer">
              Open authoring JSON
            </a>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Interactive controls</p>
            <div className="authoring-form">
              <label className="authoring-form__wide">
                <span>Native family</span>
                <select
                  value={selectedAuthoringFamily.familyId}
                  onChange={(event) => {
                    const nextFamily = findAuthoringFamilyOption(authoringFamilyOptions, event.target.value)
                    applyAuthoringControls(
                      {
                        familyId: nextFamily.familyId,
                        storyCount: nextFamily.defaultStoryCount,
                        bayCount: nextFamily.defaultBayCount,
                        floorHeightM: nextFamily.defaultFloorHeightM,
                        loadPatternCount: nextFamily.defaultLoadPatternCount,
                        sectionId: nextFamily.defaultSectionId,
                      },
                      `Draft switched to ${nextFamily.label}.`,
                    )
                  }}
                >
                  {authoringFamilyOptions.map((option) => (
                    <option key={option.familyId} value={option.familyId}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Stories</span>
                <input
                  type="number"
                  min={1}
                  max={40}
                  value={authoringStoryCount}
                  onChange={(event) =>
                    setAuthoringControls((current) => ({
                      ...current,
                      familyId: selectedAuthoringFamily.familyId,
                      storyCount: clampNumber(asNumber(event.target.value), current.storyCount, 1, 40),
                    }))
                  }
                />
              </label>
              <label>
                <span>Bays</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={authoringBayCount}
                  onChange={(event) =>
                    setAuthoringControls((current) => ({
                      ...current,
                      familyId: selectedAuthoringFamily.familyId,
                      bayCount: clampNumber(asNumber(event.target.value), current.bayCount, 1, 12),
                    }))
                  }
                />
              </label>
              <label>
                <span>Floor height (m)</span>
                <input
                  type="number"
                  min={2.5}
                  max={6}
                  step={0.1}
                  value={authoringFloorHeight}
                  onChange={(event) =>
                    setAuthoringControls((current) => ({
                      ...current,
                      familyId: selectedAuthoringFamily.familyId,
                      floorHeightM: clampNumber(asNumber(event.target.value), current.floorHeightM, 2.5, 6),
                    }))
                  }
                />
              </label>
              <label>
                <span>Load patterns</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={authoringLoadPatternCount}
                  onChange={(event) =>
                    setAuthoringControls((current) => ({
                      ...current,
                      familyId: selectedAuthoringFamily.familyId,
                      loadPatternCount: clampNumber(asNumber(event.target.value), current.loadPatternCount, 1, 12),
                    }))
                  }
                />
              </label>
              <label className="authoring-form__wide">
                <span>Primary section palette</span>
                <select
                  value={authoringControls.sectionId}
                  onChange={(event) =>
                    setAuthoringControls((current) => ({
                      ...current,
                      familyId: selectedAuthoringFamily.familyId,
                      sectionId: event.target.value,
                    }))
                  }
                >
                  {authoringSectionOptions.map((sectionId) => (
                    <option key={sectionId} value={sectionId}>
                      {sectionId}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="authoring-card__subnote">
              {selectedAuthoringFamily.description} Default bay width {compactRatio(selectedAuthoringFamily.defaultBayWidthM, 1)} m.
            </p>
            <div className="authoring-actions">
              <button
                className="button button--ghost"
                type="button"
                onClick={handleAuthoringReset}
                disabled={resources.authoring.status !== 'ready'}
              >
                Reset to baseline
              </button>
              <a
                className="button button--ghost"
                href={authoringExportHref}
                download={authoringDraftDownloadName}
              >
                Export draft JSON
              </a>
            </div>
            <label className="authoring-import">
              <span>Import draft JSON</span>
              <input type="file" accept="application/json,.json" onChange={handleAuthoringImport} />
            </label>
            <p className="authoring-card__subnote authoring-status" aria-live="polite">
              {authoringDraftStatus} Autosave uses browser storage.
            </p>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Solver-ready draft preview</p>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              <div className="mini-metric">
                <span>Nodes</span>
                <strong>{compactCount(authoringNodeCount)}</strong>
              </div>
              <div className="mini-metric">
                <span>Members</span>
                <strong>{compactCount(authoringMemberCount)}</strong>
              </div>
              <div className="mini-metric">
                <span>Score</span>
                <strong>{compactRatio(authoringEstimatedScore, 1)} / 100</strong>
              </div>
              <div className="mini-metric">
                <span>Section</span>
                <strong>{shorten(authoringControls.sectionId, 18)}</strong>
              </div>
            </div>
            <p className="authoring-card__note">{authoringDraftSummaryLine}</p>
            <p className="authoring-card__subnote">
              baseline score {compactRatio(asNumber(authoringSummary.solver_ready_score), 1)} / 100
              를 기준으로 로컬 draft를 즉시 비교합니다. Current family is {selectedAuthoringFamily.label}.
            </p>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Commercialization breadth</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringBreadthTone}`}>
                {authoringBreadthStatusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              <div className="mini-metric">
                <span>Palette families</span>
                <strong>{compactCount(authoringPaletteFamilies.length)}</strong>
              </div>
              <div className="mini-metric">
                <span>Active families</span>
                <strong>{compactCount(authoringActiveFamilies.length)}</strong>
              </div>
              <div className="mini-metric">
                <span>Used sections</span>
                <strong>{compactCount(authoringUsedSections.length)}</strong>
              </div>
              <div className="mini-metric">
                <span>Member types</span>
                <strong>{compactCount(authoringMemberTypes.length)}</strong>
              </div>
            </div>
            <p className="authoring-card__note">{authoringBreadthNote}</p>
            <p className="authoring-card__subnote">
              palette breadth is still scaffold coverage입니다. broad native writeback coverage나 full solver replacement parity로 바로 읽으면 안 됩니다.
            </p>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Solver session</p>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringSolverSnapshot.metrics.map((metric) => (
                <div key={`authoring-solver-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringSolverSnapshot.note}</p>
            <p className="artifact-card__source">source: {authoringSolverSnapshot.sourceLabel}</p>
            <div className="authoring-actions">
              <a className="button button--ghost" href={authoringSolverHref} target="_blank" rel="noreferrer">
                Open solver session
              </a>
              <a className="button button--ghost" href={authoringSolverLoadcombHref} target="_blank" rel="noreferrer">
                Open loadcomb preview
              </a>
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Portfolio scope</p>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              <div className="mini-metric">
                <span>Families</span>
                <strong>{compactCount(authoringPortfolioFamilyCount)}</strong>
              </div>
              <div className="mini-metric">
                <span>Projects</span>
                <strong>{compactCount(authoringPortfolioProjectCount)}</strong>
              </div>
              <div className="mini-metric">
                <span>Complete</span>
                <strong>{compactCount(authoringPortfolioCompleteCount)}</strong>
              </div>
              <div className="mini-metric">
                <span>Signature</span>
                <strong>{compactCount(authoringPortfolioSignatureCount)}</strong>
              </div>
              <div className="mini-metric">
                <span>Snapshots</span>
                <strong>{compactCount(authoringPortfolioSnapshotCount)}</strong>
              </div>
            </div>
            <p className="authoring-card__note">{authoringPortfolioNote}</p>
            <p className="authoring-card__subnote">
              portfolio manifest를 우선 읽고, 없으면 shared registry portfolio index를 fallback으로 사용합니다. 현재 unmatched input은 authoring registry가 shared portfolio scan에 아직 완전히 접히지 않았다는 뜻입니다.
            </p>
            <div className="authoring-actions">
              <a className="button button--ghost" href={authoringPortfolioHref} target="_blank" rel="noreferrer">
                Open portfolio JSON
              </a>
              <a className="button button--ghost" href={authoringPortfolioWorkspaceHref} target="_blank" rel="noreferrer">
                Open portfolio workspace
              </a>
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Family corpus</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringFamilyCorpusSnapshot.tone}`}>
                {authoringFamilyCorpusSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringFamilyCorpusSnapshot.metrics.map((metric) => (
                <div key={`authoring-family-corpus-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringFamilyCorpusSnapshot.note}</p>
            <p className="authoring-card__subnote">
              8-family commercialization corpus는 local/public/benchmark/authority linkage evidence입니다. solver parity 자체가 아니라 실도면·공개 reference 연결 범위를 읽는 카드입니다.
            </p>
            <div className="authoring-actions">
              <a className="button button--ghost" href={authoringFamilyCorpusHref} target="_blank" rel="noreferrer">
                Open family corpus JSON
              </a>
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Local evidence</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringFamilyLocalEvidenceSnapshot.tone}`}>
                {authoringFamilyLocalEvidenceSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringFamilyLocalEvidenceSnapshot.metrics.map((metric) => (
                <div key={`authoring-family-local-evidence-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringFamilyLocalEvidenceSnapshot.note}</p>
            <p className="authoring-card__subnote">
              로컬 release/open_data/tests 아티팩트가 실제로 concrete하게 물질화됐는지 읽는 카드입니다. 등록만 된 reference와 실제 로컬 근거는 분리해서 봅니다.
            </p>
            <div className="authoring-actions">
              <a className="button button--ghost" href={authoringFamilyLocalEvidenceHref} target="_blank" rel="noreferrer">
                Open local evidence JSON
              </a>
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Portfolio / family / runtime / service consistency</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringConsistencySnapshot.tone}`}>
                {authoringConsistencySnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringConsistencySnapshot.metrics.map((metric) => (
                <div key={`consistency-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringConsistencySnapshot.note}</p>
            <p className="artifact-card__source">source: {authoringConsistencySnapshot.sourceLabel}</p>
          </div>
          <div className="authoring-card authoring-card--coverage-matrix">
            <p className="authoring-card__title">Family coverage matrix</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringFamilyCoverageSnapshot.tone}`}>
                {authoringFamilyCoverageSnapshot.statusLabel}
              </span>
              <span className="authoring-card__meta">
                portfolio + solver breadth + runtime depth + writeback breadth
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringFamilyCoverageSnapshot.metrics.map((metric) => (
                <div key={`coverage-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringFamilyCoverageSnapshot.note}</p>
            <p className="artifact-card__source">source: {authoringFamilyCoverageSnapshot.sourceLabel}</p>
            <div className="authoring-coverage-grid">
              {authoringFamilyCoverageRows.length ? (
                <>
                  <div className="authoring-coverage-grid__head">
                    <span>Family</span>
                    <span>Solver breadth</span>
                    <span>Runtime depth</span>
                    <span>Writeback breadth</span>
                  </div>
                  {authoringFamilyCoverageRows.map((family) => (
                    <article key={family.familyId} className="authoring-coverage-row">
                      <div className="authoring-coverage-family">
                        <div className="authoring-family-row__header">
                          <div>
                            <p className="authoring-family-row__title">{family.label}</p>
                            <p className="authoring-family-row__meta">
                              family={family.familyId} | draft={family.draftLabel}
                            </p>
                          </div>
                          <span className={`status-pill status-pill--${family.tone}`}>
                            {family.statusLabel}
                          </span>
                        </div>
                        <div className="mini-metric-grid mini-metric-grid--family authoring-coverage-family__metrics">
                          <div className="mini-metric">
                            <span>Combos</span>
                            <strong>{compactCount(family.comboCount)}</strong>
                          </div>
                          <div className="mini-metric">
                            <span>Mesh</span>
                            <strong>{compactCount(family.meshRequestCount)}</strong>
                          </div>
                          <div className="mini-metric">
                            <span>Snapshots</span>
                            <strong>{compactCount(family.snapshotCount)}</strong>
                          </div>
                        </div>
                        <p className="authoring-family-row__note">{family.note}</p>
                      </div>
                      <div className="authoring-coverage-cell">
                        <p className="authoring-coverage-cell__title">Solver breadth</p>
                        <span className={`status-pill status-pill--${family.solver.tone}`}>
                          {family.solver.statusLabel}
                        </span>
                        <p className="authoring-coverage-cell__summary">{family.solver.summary}</p>
                        <p className="authoring-coverage-cell__note">{shorten(family.solver.note, 96)}</p>
                      </div>
                      <div className="authoring-coverage-cell">
                        <p className="authoring-coverage-cell__title">Runtime depth</p>
                        <span className={`status-pill status-pill--${family.depth.tone}`}>
                          {family.depth.statusLabel}
                        </span>
                        <p className="authoring-coverage-cell__summary">{family.depth.summary}</p>
                        <p className="authoring-coverage-cell__note">{shorten(family.depth.note, 96)}</p>
                      </div>
                      <div className="authoring-coverage-cell">
                        <p className="authoring-coverage-cell__title">Writeback breadth</p>
                        <span className={`status-pill status-pill--${family.writeback.tone}`}>
                          {family.writeback.statusLabel}
                        </span>
                        <p className="authoring-coverage-cell__summary">{family.writeback.summary}</p>
                        <p className="authoring-coverage-cell__note">{shorten(family.writeback.note, 96)}</p>
                      </div>
                    </article>
                  ))}
                </>
              ) : (
                <div className="authoring-coverage-empty">
                  <p className="authoring-family-row__title">Coverage matrix unavailable</p>
                  <p className="authoring-family-row__note">
                    native authoring portfolio JSON이 아직 없어서 family breadth/depth matrix를 표시하지 못했습니다.
                  </p>
                </div>
              )}
            </div>
            <div className="authoring-actions">
              <a className="button button--ghost" href={authoringPortfolioHref} target="_blank" rel="noreferrer">
                Open portfolio JSON
              </a>
              <a
                className="button button--ghost"
                href={authoringSolverFamilyBreadthHref}
                target="_blank"
                rel="noreferrer"
              >
                Open solver breadth JSON
              </a>
              <a
                className="button button--ghost"
                href={authoringLocalRuntimeScenarioDepthHref}
                target="_blank"
                rel="noreferrer"
              >
                Open runtime depth JSON
              </a>
              <a
                className="button button--ghost"
                href={authoringWritebackBreadthHref}
                target="_blank"
                rel="noreferrer"
              >
                Open writeback breadth JSON
              </a>
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Family-track commercialization breadth</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringFamilyTrackSnapshot.tone}`}>
                {authoringFamilyTrackSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringFamilyTrackSnapshot.metrics.map((metric) => (
                <div key={`family-track-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringFamilyTrackSnapshot.note}</p>
            <p className="authoring-card__subnote">
              native authoring project registry index에서 family / project / signature / reproducibility breadth를 직접 읽습니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringFamilyTrack.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringFamilyTrack.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open family track JSON
                </a>
              ) : null}
            </div>
          </div>
          <div className="authoring-card authoring-card--portfolio-lanes">
            <p className="authoring-card__title">Family commercialization lanes</p>
            <p className="authoring-card__subnote">
              native authoring portfolio manifest에서 family별 commercialization row를 직접 읽어,
              combos, mesh requests, snapshots와 workspace/solver/registry artifact를 한 번에 보여줍니다.
            </p>
            <div className="authoring-family-matrix">
              {authoringPortfolioFamilySnapshots.length ? (
                authoringPortfolioFamilySnapshots.map((family) => (
                  <article key={family.familyId} className="authoring-family-row">
                    <div className="authoring-family-row__header">
                      <div>
                        <p className="authoring-family-row__title">{family.label}</p>
                        <p className="authoring-family-row__meta">
                          family={family.familyId} | draft={family.draftLabel}
                        </p>
                      </div>
                      <span className={`status-pill status-pill--${family.tone}`}>
                        {family.statusLabel}
                      </span>
                    </div>
                    <div className="mini-metric-grid mini-metric-grid--authoring mini-metric-grid--family">
                      <div className="mini-metric">
                        <span>Combos</span>
                        <strong>{compactCount(family.comboCount)}</strong>
                      </div>
                      <div className="mini-metric">
                        <span>Mesh</span>
                        <strong>{compactCount(family.meshRequestCount)}</strong>
                      </div>
                      <div className="mini-metric">
                        <span>Snapshots</span>
                        <strong>{compactCount(family.snapshotCount)}</strong>
                      </div>
                    </div>
                    <p className="authoring-family-row__note">{family.note}</p>
                    <div className="authoring-family-links">
                      {family.workspaceHref ? (
                        <a className="button button--ghost" href={family.workspaceHref} target="_blank" rel="noreferrer">
                          Workspace
                        </a>
                      ) : null}
                      {family.solverHref ? (
                        <a className="button button--ghost" href={family.solverHref} target="_blank" rel="noreferrer">
                          Solver
                        </a>
                      ) : null}
                      {family.registryHref ? (
                        <a className="button button--ghost" href={family.registryHref} target="_blank" rel="noreferrer">
                          Registry
                        </a>
                      ) : null}
                    </div>
                  </article>
                ))
          ) : (
                <div className="authoring-family-row authoring-family-row--empty">
                  <p className="authoring-family-row__title">Portfolio families unavailable</p>
                  <p className="authoring-family-row__note">
                    native authoring portfolio JSON이 아직 없어서 family commercialization rows를 표시하지 못했습니다.
                  </p>
                </div>
              )}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Runtime submission lane</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringRuntimeSubmissionLaneSnapshot.tone}`}>
                {authoringRuntimeSubmissionLaneSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringRuntimeSubmissionLaneSnapshot.metrics.map((metric) => (
                <div key={`runtime-submission-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringRuntimeSubmissionLaneSnapshot.note}</p>
            <p className="authoring-card__subnote">
              native authoring runtime submission lane JSON을 우선 읽고, 없으면 project ops service snapshot을 fallback으로 사용합니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringRuntimeSubmissionLane.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringRuntimeSubmissionLane.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open runtime lane JSON
                </a>
              ) : null}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Runtime writeback depth</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringRuntimeWritebackDepthSnapshot.tone}`}>
                {authoringRuntimeWritebackDepthSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringRuntimeWritebackDepthSnapshot.metrics.map((metric) => (
                <div key={`runtime-writeback-depth-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringRuntimeWritebackDepthSnapshot.note}</p>
            <p className="authoring-card__subnote">
              runtime submission 이후 registry, signature, reproducibility, snapshot, approval, queue-clear 깊이를
              family/project 단위로 분리해서 읽습니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringRuntimeWritebackDepth.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringRuntimeWritebackDepth.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open runtime writeback depth JSON
                </a>
              ) : (
                <a className="button button--ghost" href={authoringRuntimeWritebackDepthHref} target="_blank" rel="noreferrer">
                  Open runtime writeback depth JSON
                </a>
              )}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Multi-project runtime/writeback</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringMultiProjectRuntimeWritebackSnapshot.tone}`}>
                {authoringMultiProjectRuntimeWritebackSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringMultiProjectRuntimeWritebackSnapshot.metrics.map((metric) => (
                <div key={`multi-project-runtime-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringMultiProjectRuntimeWritebackSnapshot.note}</p>
            <p className="authoring-card__subnote">
              family ready 여부를 넘어서 project x family runtime/writeback depth가 실제로 얼마나 닫혔는지
              별도 JSON으로 읽습니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringMultiProjectRuntimeWriteback.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringMultiProjectRuntimeWriteback.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open multi-project runtime JSON
                </a>
              ) : (
                <a className="button button--ghost" href={authoringMultiProjectRuntimeWritebackHref} target="_blank" rel="noreferrer">
                  Open multi-project runtime JSON
                </a>
              )}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Solver family breadth</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringSolverFamilyBreadthSnapshot.tone}`}>
                {authoringSolverFamilyBreadthSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringSolverFamilyBreadthSnapshot.metrics.map((metric) => (
                <div key={`solver-family-breadth-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringSolverFamilyBreadthSnapshot.note}</p>
            <p className="authoring-card__subnote">
              commercial_gap_analysis.md의 member family breadth 확대를 authoring family별 solver combo, mesh,
              member-type breadth로 분리해서 읽습니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringSolverFamilyBreadth.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringSolverFamilyBreadth.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open solver family breadth JSON
                </a>
              ) : (
                <a className="button button--ghost" href={authoringSolverFamilyBreadthHref} target="_blank" rel="noreferrer">
                  Open solver family breadth JSON
                </a>
              )}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Local runtime scenario depth</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringLocalRuntimeScenarioDepthSnapshot.tone}`}>
                {authoringLocalRuntimeScenarioDepthSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringLocalRuntimeScenarioDepthSnapshot.metrics.map((metric) => (
                <div key={`local-runtime-depth-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringLocalRuntimeScenarioDepthSnapshot.note}</p>
            <p className="authoring-card__subnote">
              local deterministic runtime lane 안에서 case/combo/mesh/loadcomb preview trace가 실제로 얼마나 깊게 닫혔는지
              family별 JSON으로 따로 읽습니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringLocalRuntimeScenarioDepth.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringLocalRuntimeScenarioDepth.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open local runtime depth JSON
                </a>
              ) : (
                <a className="button button--ghost" href={authoringLocalRuntimeScenarioDepthHref} target="_blank" rel="noreferrer">
                  Open local runtime depth JSON
                </a>
              )}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Local variant/writeback trace</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringLocalVariantWritebackTraceSnapshot.tone}`}>
                {authoringLocalVariantWritebackTraceSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringLocalVariantWritebackTraceSnapshot.metrics.map((metric) => (
                <div key={`local-variant-trace-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringLocalVariantWritebackTraceSnapshot.note}</p>
            <p className="authoring-card__subnote">
              workspace palette 변형, solver variant, signed writeback trace를 family별로 같은 JSON에서 읽어 로컬 authoring 변형 깊이를 따로 봅니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringLocalVariantWritebackTrace.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringLocalVariantWritebackTrace.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open local variant/writeback trace JSON
                </a>
              ) : (
                <a className="button button--ghost" href={authoringLocalVariantWritebackTraceHref} target="_blank" rel="noreferrer">
                  Open local variant/writeback trace JSON
                </a>
              )}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Writeback breadth</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringWritebackBreadthSnapshot.tone}`}>
                {authoringWritebackBreadthSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringWritebackBreadthSnapshot.metrics.map((metric) => (
                <div key={`writeback-breadth-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringWritebackBreadthSnapshot.note}</p>
            <p className="authoring-card__subnote">
              runtime lane의 `writeback ready`를 palette/scaffold 신호와 분리해서, family별 broader native writeback coverage만 별도 JSON으로 읽습니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringWritebackBreadth.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringWritebackBreadth.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open writeback breadth JSON
                </a>
              ) : (
                <a className="button button--ghost" href={authoringWritebackBreadthHref} target="_blank" rel="noreferrer">
                  Open writeback breadth JSON
                </a>
              )}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Server ops summary</p>
            <div className="authoring-card__topline">
              <span className={`status-pill status-pill--${authoringServerOpsSnapshot.tone}`}>
                {authoringServerOpsSnapshot.statusLabel}
              </span>
            </div>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringServerOpsSnapshot.metrics.map((metric) => (
                <div key={`server-ops-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">{authoringServerOpsSnapshot.note}</p>
            <p className="authoring-card__subnote">
              native authoring job manifest와 portfolio batch runner를 server-style summary로 묶습니다.
            </p>
            <div className="authoring-actions">
              {resources.authoringServerOps.source ? (
                <a
                  className="button button--ghost"
                  href={resources.authoringServerOps.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open server ops JSON
                </a>
              ) : null}
            </div>
          </div>
          <div className="authoring-card">
            <p className="authoring-card__title">Ops lane</p>
            <div className="mini-metric-grid mini-metric-grid--authoring">
              {authoringOpsBundleSnapshot.metrics.slice(0, 2).map((metric) => (
                <div key={`authoring-bundle-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
              {authoringOpsBatchSnapshot.metrics.slice(0, 2).map((metric) => (
                <div key={`authoring-batch-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
              {authoringOpsRegistrySnapshot.metrics.slice(0, 2).map((metric) => (
                <div key={`authoring-registry-${metric.label}`} className="mini-metric">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            <p className="authoring-card__note">
              bundle: {authoringOpsBundleSnapshot.statusLabel} | batch: {authoringOpsBatchSnapshot.statusLabel} | registry: {authoringOpsRegistrySnapshot.statusLabel}
            </p>
            <p className="authoring-card__subnote">
              {authoringOpsBundleSnapshot.note} {authoringOpsBatchSnapshot.note} {authoringOpsRegistrySnapshot.note}
            </p>
            <div className="authoring-actions">
              <a className="button button--ghost" href={authoringOpsBundleHref} target="_blank" rel="noreferrer">
                Open ops bundle
              </a>
              <a className="button button--ghost" href={authoringOpsBatchHref} target="_blank" rel="noreferrer">
                Open authoring batch
              </a>
              <a className="button button--ghost" href={authoringOpsRegistryHref} target="_blank" rel="noreferrer">
                Open authoring registry
              </a>
              <a className="button button--ghost" href={authoringOpsPackageHref} target="_blank" rel="noreferrer">
                Open authoring package
              </a>
              <a className="button button--ghost" href={authoringOpsSignatureHref} target="_blank" rel="noreferrer">
                Open authoring signature
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="panel panel--route">
        <div className="panel__header">
          <div>
            <p className="panel__kicker">Route Choreography</p>
            <h2>{routePlan.title}</h2>
          </div>
          <p className="panel__hint">active surface에 따라 추천 검토 순서와 최종 확인 경계가 같이 바뀝니다.</p>
        </div>
        <div className="route-summary">
          <div className="route-summary__lead">
            <p className="route-summary__label">Recommended route</p>
            <p className="route-summary__text">{routePlan.description}</p>
          </div>
          <div className="route-summary__cards">
            <article className="route-summary__card">
              <p className="route-summary__card-label">Entry desk</p>
              <strong>{activeSurface.title}</strong>
              <p>{activeSurfaceIdentity.mode}</p>
            </article>
            <article className="route-summary__card route-summary__card--finish">
              <p className="route-summary__card-label">Finish gate</p>
              <strong>{finishArtifact.title}</strong>
              <span className={`status-pill status-pill--${finishArtifactSnapshot.tone}`}>
                {finishArtifactSnapshot.statusLabel}
              </span>
            </article>
            <article className="route-summary__card">
              <p className="route-summary__card-label">Route span</p>
              <strong>{`${routePlan.steps.length} linked checkpoints`}</strong>
              <p>{`${activeSurfaceIdentity.track}부터 boundary evidence까지 한 흐름으로 이어집니다.`}</p>
            </article>
          </div>
        </div>
        <div className="route-grid">
          {routePlan.steps.map((step) => (
            <a key={step.id} className="route-step" href={step.href} target="_blank" rel="noreferrer">
              <div className="route-step__top">
                <span className="route-step__index">0{step.index}</span>
                <span className={`status-pill status-pill--${step.tone}`}>{step.statusLabel}</span>
              </div>
              <span className="route-step__badge">{step.badge}</span>
              <strong>{step.title}</strong>
              <p>{step.description}</p>
              <p className="route-step__note">{step.note}</p>
              <span className="route-step__path">{step.href}</span>
            </a>
          ))}
        </div>
      </section>

      <section className="panel panel--governance">
        <div className="panel__header">
          <div>
            <p className="panel__kicker">Release Governance</p>
            <h2>운영, 제출, 상용화 경계를 닫는 검토 데스크</h2>
          </div>
          <p className="panel__hint">새 산출물이 없으면 checked-in fallback release file로 내려가서 상태를 보여줍니다.</p>
        </div>
        <div className="advanced-holdout-card review-board-card">
          <div className="advanced-holdout-card__top">
            <div>
              <p className="advanced-holdout-card__title">P0-P4 local review board</p>
              <p className="advanced-holdout-card__subnote">
                release gap report의 P0-P4 remaining_gaps를 local-only review state로 바꾸는 표면입니다.
                approve / reject / needs engineer review decisions와 comment, issue marker를 browser storage에 남깁니다.
              </p>
            </div>
            <span className={`status-pill status-pill--${reviewBoardSnapshot.tone}`}>
              {reviewBoardSnapshot.statusLabel}
            </span>
          </div>
          <div className="mini-metric-grid mini-metric-grid--artifact">
            {reviewBoardSnapshot.metrics.map((metric) => (
              <div key={`review-board-${metric.label}`} className="mini-metric">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
          <p className="advanced-holdout-card__subnote">{reviewBoardSnapshot.note}</p>
          <p className="panel__source">source: {reviewBoardSnapshot.sourceLabel}</p>
          <div className="authoring-actions">
            <button className="button button--ghost" type="button" onClick={handleReviewReset}>
              Reset review state
            </button>
            <a className="button button--ghost" href={reviewStateExportHref} download={reviewStateDownloadName}>
              Export review JSON
            </a>
          </div>
          <label className="authoring-import">
            <span>Import review JSON</span>
            <input type="file" accept="application/json,.json" onChange={handleReviewImport} />
          </label>
          <p className="authoring-card__subnote authoring-status" aria-live="polite">
            {reviewDraftStatus} Autosave uses browser storage.
          </p>
          <div className="review-board-rows">
            {reviewableGapRows.length ? (
              reviewableGapRows.map((row) => {
                const reviewState = reviewRowStates[row.id] ?? createDefaultReviewRowState()
                return (
                  <article key={row.id} className="review-board-row">
                    <div className="review-board-row__header">
                      <div>
                        <p className="review-board-row__title">{row.title}</p>
                        <div className="review-board-row__meta">
                          <span>Severity {row.severity}</span>
                          <span>Gap {row.gapStatus}</span>
                        </div>
                      </div>
                      <div className="review-board-row__badges">
                        <span className={`status-pill status-pill--${reviewDecisionTone(reviewState.decision)}`}>
                          {reviewDecisionLabel(reviewState.decision)}
                        </span>
                        <span className={`status-pill status-pill--${row.tone}`}>{row.statusLabel}</span>
                      </div>
                    </div>
                    <p className="review-board-row__why">{row.why}</p>
                    <p className="review-board-row__evidence">{row.evidence}</p>
                    <p className="review-board-row__exit">{row.exitCriteria}</p>
                    <div className="review-board-row__controls">
                      <div className="review-board-row__actions">
                        <button
                          className="button button--ghost review-board-row__action"
                          type="button"
                          onClick={() => setReviewDecision(row.id, 'approved')}
                        >
                          Approve
                        </button>
                        <button
                          className="button button--ghost review-board-row__action"
                          type="button"
                          onClick={() => setReviewDecision(row.id, 'rejected')}
                        >
                          Reject
                        </button>
                        <button
                          className="button button--ghost review-board-row__action"
                          type="button"
                          onClick={() => setReviewDecision(row.id, 'needs_engineer_review')}
                        >
                          Needs engineer review
                        </button>
                      </div>
                      <label className="review-board-row__field">
                        <span>Issue marker</span>
                        <select
                          value={reviewState.issueMarker}
                          onChange={(event) =>
                            setReviewIssueMarker(row.id, event.target.value as ReviewIssueMarker)
                          }
                        >
                          {reviewIssueMarkerOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="review-board-row__field review-board-row__field--wide">
                        <span>Comment</span>
                        <textarea
                          rows={2}
                          value={reviewState.comment}
                          onChange={(event) => setReviewComment(row.id, event.target.value)}
                          placeholder="Local review note, follow-up, owner, or condition."
                        />
                      </label>
                    </div>
                    <div className="review-board-row__footer">
                      <span>{reviewState.comment.trim() ? 'Comment saved locally' : 'No local comment yet'}</span>
                      <span>
                        Marker: {reviewIssueMarkerLabel(reviewState.issueMarker)}
                      </span>
                      <span>Updated {reviewState.updatedAt || 'pending'}</span>
                      <button
                        className="button button--ghost review-board-row__reset"
                        type="button"
                        onClick={() => clearReviewRowState(row.id)}
                      >
                        Reset row
                      </button>
                    </div>
                  </article>
                )
              })
            ) : (
              <div className="review-board-row review-board-row--empty">
                <p className="review-board-row__title">Priority review rows unavailable</p>
                <p className="review-board-row__why">
                  release gap report에 P0-P4 remaining_gaps가 아직 없어 local review board를 표시하지 못했습니다.
                </p>
              </div>
            )}
          </div>
        </div>
        <div className="advanced-holdout-card">
          <div className="advanced-holdout-card__top">
            <div>
              <p className="advanced-holdout-card__title">Phase 1 Core API Contract</p>
              <p className="advanced-holdout-card__subnote">
                GUI가 Python API의 AnalysisResult와 ValidationReport JSON을 직접 읽어 model_health 계약을 표시합니다.
              </p>
            </div>
            <span className={`status-pill status-pill--${coreApiContractSnapshot.tone}`}>
              {coreApiContractSnapshot.statusLabel}
            </span>
          </div>
          <div className="mini-metric-grid mini-metric-grid--artifact mini-metric-grid--holdout">
            {coreApiContractSnapshot.metrics.map((metric) => (
              <div key={`core-api-contract-${metric.label}`} className="mini-metric">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
          <p className="advanced-holdout-card__subnote">{coreApiContractSnapshot.note}</p>
          <p className="panel__source">source: {coreApiContractSnapshot.sourceLabel}</p>
          {resources.coreApiResult.source || resources.coreApiReport.source ? (
            <div className="authoring-actions">
              {resources.coreApiResult.source ? (
                <a
                  className="button button--ghost"
                  href={resources.coreApiResult.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Core API result JSON
                </a>
              ) : null}
              {resources.coreApiReport.source ? (
                <a
                  className="button button--ghost"
                  href={resources.coreApiReport.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Core API validation report JSON
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="advanced-holdout-card">
          <div className="advanced-holdout-card__top">
            <div>
              <p className="advanced-holdout-card__title">Open Benchmark Developer Preview</p>
              <p className="advanced-holdout-card__subnote">
                Developer Preview와 Commercial Release gate를 분리합니다. 고객 shadow, 라이선스/법무 승인,
                상용 SLA, 30-run CI streak, external approval receipt는 미래 상용 release blocker로만 표시합니다.
              </p>
            </div>
            <span className={`status-pill status-pill--${developerPreviewSnapshot.tone}`}>
              {developerPreviewSnapshot.statusLabel}
            </span>
          </div>
          <div className="mini-metric-grid mini-metric-grid--artifact mini-metric-grid--holdout">
            {developerPreviewSnapshot.metrics.map((metric) => (
              <div key={`developer-preview-${metric.label}`} className="mini-metric">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
          <p className="advanced-holdout-card__subnote">{developerPreviewSnapshot.note}</p>
          <p className="panel__source">source: {developerPreviewSnapshot.sourceLabel}</p>
          {resources.developerPreview.source ? (
            <div className="authoring-actions">
              <a
                className="button button--ghost"
                href={resources.developerPreview.source}
                target="_blank"
                rel="noreferrer"
              >
                Open Developer Preview readiness JSON
              </a>
            </div>
          ) : null}
        </div>
        <div className="advanced-holdout-card">
          <div className="advanced-holdout-card__top">
            <div>
              <p className="advanced-holdout-card__title">Commercialization depth snapshot</p>
              <p className="advanced-holdout-card__subnote">
                release gap summary의 material/load/advanced SSI/wind signals를 compact P0/P1 readiness로 묶습니다.
              </p>
            </div>
            <span className={`status-pill status-pill--${commercializationDepthTone}`}>
              {`${gapP0Snapshot.readyCount}/${gapP0Snapshot.totalCount} P0 ready · ${gapP1Snapshot.readyCount}/${gapP1Snapshot.totalCount} P1 ready`}
            </span>
          </div>
          <div className="mini-metric-grid mini-metric-grid--artifact mini-metric-grid--holdout">
            <div className="mini-metric">
              <span>P0 ready</span>
              <strong>{`${gapP0Snapshot.readyCount}/${gapP0Snapshot.totalCount}`}</strong>
            </div>
            <div className="mini-metric">
              <span>P1 ready</span>
              <strong>{`${gapP1Snapshot.readyCount}/${gapP1Snapshot.totalCount}`}</strong>
            </div>
            <div className="mini-metric">
              <span>Depth lanes</span>
              <strong>{`${commercializationDepthReadyCount}/${commercializationDepthSignals.length}`}</strong>
            </div>
            {commercializationDepthSignals.map((signal) => (
              <div key={`commercialization-depth-${signal.label}`} className="mini-metric">
                <span>{signal.label}</span>
                <strong>{signal.statusLabel}</strong>
              </div>
            ))}
          </div>
          <p className="advanced-holdout-card__subnote">{commercializationDepthSummaryLine}</p>
          <p className="panel__source">source: {artifactSnapshots.gap.sourceLabel}</p>
        </div>
        <div className="advanced-holdout-card">
          <div className="advanced-holdout-card__top">
            <div>
              <p className="advanced-holdout-card__title">Commercial workflow breadth</p>
              <p className="advanced-holdout-card__subnote">
                `commercial_gap_analysis.md`에서 마지막까지 남던 construction-stage, rail/tunnel,
                design redesign-loop breadth를 별도 JSON으로 묶어 보여줍니다.
              </p>
            </div>
            <span className={`status-pill status-pill--${commercialWorkflowBreadthSnapshot.tone}`}>
              {commercialWorkflowBreadthSnapshot.statusLabel}
            </span>
          </div>
          <div className="mini-metric-grid mini-metric-grid--artifact mini-metric-grid--holdout">
            {commercialWorkflowBreadthSnapshot.metrics.map((metric) => (
              <div key={`workflow-breadth-${metric.label}`} className="mini-metric">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
          <p className="advanced-holdout-card__subnote">{commercialWorkflowBreadthSnapshot.note}</p>
          <p className="panel__source">source: {commercialWorkflowBreadthSnapshot.sourceLabel}</p>
          {resources.commercialWorkflowBreadth.source ? (
            <div className="authoring-actions">
              <a
                className="button button--ghost"
                href={resources.commercialWorkflowBreadth.source}
                target="_blank"
                rel="noreferrer"
              >
                Open workflow breadth JSON
              </a>
            </div>
          ) : null}
        </div>
        <div className="advanced-holdout-card">
          <div className="advanced-holdout-card__top">
            <div>
              <p className="advanced-holdout-card__title">Advanced holdout commercialization</p>
              <p className="advanced-holdout-card__subnote">
                release gap report의 advanced holdout rows를 compact closeout 표면으로 바로 보여줍니다.
              </p>
            </div>
            <span className={`status-pill status-pill--${advancedHoldoutOpenCount > 0 ? 'warn' : 'ok'}`}>
              {advancedHoldoutOpenCount > 0 ? `${advancedHoldoutOpenCount} open` : 'all closed'}
            </span>
          </div>
          <div className="mini-metric-grid mini-metric-grid--artifact mini-metric-grid--holdout">
            <div className="mini-metric">
              <span>Closed</span>
              <strong>{compactCount(advancedHoldoutClosedCount)}</strong>
            </div>
            <div className="mini-metric">
              <span>Open</span>
              <strong>{compactCount(advancedHoldoutOpenCount)}</strong>
            </div>
            <div className="mini-metric">
              <span>Rows</span>
              <strong>{compactCount(advancedHoldoutRows.length)}</strong>
            </div>
          </div>
          <div className="advanced-holdout-table">
            {advancedHoldoutRows.length ? (
              advancedHoldoutRows.map((row) => (
                <article key={row.id} className="advanced-holdout-row">
                  <div className="advanced-holdout-row__header">
                    <div>
                      <p className="advanced-holdout-row__title">{row.title}</p>
                      <div className="advanced-holdout-row__fields">
                        <span>Severity {row.severity}</span>
                        <span>Mode {shorten(row.mode, 34)}</span>
                      </div>
                    </div>
                    <span className={`status-pill status-pill--${row.tone}`}>{row.status}</span>
                  </div>
                  <p className="advanced-holdout-row__reason">{row.reason}</p>
                  <p className="advanced-holdout-row__evidence">{row.evidenceSnippet}</p>
                </article>
              ))
            ) : (
              <div className="advanced-holdout-row advanced-holdout-row--empty">
                <p className="advanced-holdout-row__title">Advanced holdouts unavailable</p>
                <p className="advanced-holdout-row__reason">
                  release gap report에 advanced holdout rows가 아직 없어 compact commercialization table을 표시하지 못했습니다.
                </p>
              </div>
            )}
          </div>
          <p className="panel__source">source: {artifactSnapshots.gap.sourceLabel}</p>
        </div>
        <div className="artifact-grid">
          {governanceArtifacts.map((artifact) => {
            const snapshot = artifactSnapshots[artifact.id]
            return (
              <a
                key={artifact.id}
                className="artifact-card"
                href={artifact.href}
                target="_blank"
                rel="noreferrer"
              >
                <div className="artifact-card__top">
                  <span className="artifact-card__badge">{artifact.badge}</span>
                  <span className={`status-pill status-pill--${snapshot.tone}`}>
                    {snapshot.statusLabel}
                  </span>
                </div>
                <strong>{artifact.title}</strong>
                <p>{artifact.description}</p>
                <div className="mini-metric-grid mini-metric-grid--artifact">
                  {snapshot.metrics.slice(0, 3).map((metric) => (
                    <div key={`${artifact.id}-${metric.label}`} className="mini-metric">
                      <span>{metric.label}</span>
                      <strong>{metric.value}</strong>
                    </div>
                  ))}
                </div>
                <p className="artifact-card__note">{snapshot.note}</p>
                <span className="artifact-card__path">{artifact.href}</span>
                <span className="artifact-card__source">source: {snapshot.sourceLabel}</span>
              </a>
            )
          })}
        </div>
      </section>

      <section className="panel panel--legacy">
        <div className="panel__header">
          <div>
            <p className="panel__kicker">Heritage Probes</p>
            <h2>원본 구조 viewer 프로토타입</h2>
          </div>
          <p className="panel__hint">release 셸과 별개로, 원본 `src/structure-viewer` HTML도 바로 열 수 있습니다.</p>
        </div>
        <div className="legacy-list">
          {legacyViewers.map((surface) => (
            <a key={surface.id} className="legacy-pill" href={surface.href} target="_blank" rel="noreferrer">
              <span>{surface.title}</span>
              <small>{surface.badge}</small>
            </a>
          ))}
        </div>
      </section>
    </main>
  )
}

export default App
