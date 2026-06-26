import type { DeveloperPreviewWorkflowWorkerResponse } from './developerPreviewWorkflow.worker'

export const DEVELOPER_PREVIEW_WORKFLOW_STATUS_VOCABULARY = [
  'ready',
  'blocked',
  'missing',
  'error',
] as const

export type DeveloperPreviewWorkflowStatus =
  (typeof DEVELOPER_PREVIEW_WORKFLOW_STATUS_VOCABULARY)[number]

export function normalizeDeveloperPreviewWorkflowStatus(
  value: string | null | undefined,
): DeveloperPreviewWorkflowStatus {
  if (DEVELOPER_PREVIEW_WORKFLOW_STATUS_VOCABULARY.includes(value as DeveloperPreviewWorkflowStatus)) {
    return value as DeveloperPreviewWorkflowStatus
  }
  return 'missing'
}

export const DEVELOPER_PREVIEW_WORKFLOW_VALUE_KINDS = [
  'exact_value',
  'derived_proxy',
  'reference_value',
] as const

export type DeveloperPreviewWorkflowValueKind =
  (typeof DEVELOPER_PREVIEW_WORKFLOW_VALUE_KINDS)[number]

export type DeveloperPreviewWorkflowEvidenceSignal = {
  label: string
  valueKind: DeveloperPreviewWorkflowValueKind
}

export const DEVELOPER_PREVIEW_WORKFLOW_SELECTION_CHANNELS = [
  '3d',
  'table',
  'chart',
  'comparison_row',
] as const

export type DeveloperPreviewWorkflowSelectionChannel =
  (typeof DEVELOPER_PREVIEW_WORKFLOW_SELECTION_CHANNELS)[number]

export const DEVELOPER_PREVIEW_WORKFLOW_WORKER_TASKS = [
  'ifc_parse',
  'result_processing',
] as const

export type DeveloperPreviewWorkflowWorkerTask =
  (typeof DEVELOPER_PREVIEW_WORKFLOW_WORKER_TASKS)[number]

export const DEVELOPER_PREVIEW_WORKFLOW_WORKER_BOUNDARY = {
  processedOn: 'web_worker',
  claimBoundary:
    'Web Worker boundary routes large IFC parsing and result processing off the UI thread; this contract does not prove execution.',
} as const

export const DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION = {
  workflowStepId: 'compare_report',
  sourceReceipt:
    'implementation/phase1/release_evidence/productization/evidence_console_scope_status.json',
  absorbedFeatures: [
    'case_list',
    'source_provenance_inspector',
    'reference_vs_engine_comparison',
    'residual_audit',
    'worst_member_story',
    'reviewer_decision',
    'reproduce_bundle_export',
  ],
  claimBoundary:
    'Evidence Console scope is absorbed into Compare & Report; this contract does not prove launch readiness, customer shadow completion, task execution, or Phase 5 closure.',
} as const

export type DeveloperPreviewWorkflowWorkerContractResponse =
  DeveloperPreviewWorkflowWorkerResponse

export function createDeveloperPreviewWorkflowWorker(): Worker {
  return new Worker(new URL('./developerPreviewWorkflow.worker.ts', import.meta.url), {
    name: 'developer-preview-workflow-worker',
    type: 'module',
  })
}

export type DeveloperPreviewWorkflowStep = {
  id: 'import' | 'model_health' | 'analysis_setup' | 'run_monitor' | 'compare_report'
  label: string
  status: DeveloperPreviewWorkflowStatus
  statusLabel: string
  phase5Anchor: string
  capabilityAnchors: string[]
  evidenceSignals: DeveloperPreviewWorkflowEvidenceSignal[]
}

export const developerPreviewWorkflowSteps: DeveloperPreviewWorkflowStep[] = [
  {
    id: 'import',
    label: 'Import',
    status: 'blocked',
    statusLabel: 'blocked',
    phase5Anchor: 'Phase5 workflow step: Import',
    capabilityAnchors: [
      'file and license/provenance review',
      'unit and coordinate-system review',
      'source-to-canonical mapping',
      'unsupported entity inventory',
    ],
    evidenceSignals: [
      { label: 'IFC/MGT/neutral input', valueKind: 'exact_value' },
      { label: 'license/provenance', valueKind: 'reference_value' },
      { label: 'canonical mapping', valueKind: 'derived_proxy' },
    ],
  },
  {
    id: 'model_health',
    label: 'Model Health',
    status: 'blocked',
    statusLabel: 'blocked',
    phase5Anchor: 'Phase5 workflow step: Model Health',
    capabilityAnchors: [
      'disconnected component checks',
      'zero-length member checks',
      'duplicate node checks',
      'unstable DOF checks',
    ],
    evidenceSignals: [
      { label: 'component graph', valueKind: 'derived_proxy' },
      { label: 'node/member checks', valueKind: 'exact_value' },
      { label: 'support/load anomalies', valueKind: 'derived_proxy' },
    ],
  },
  {
    id: 'analysis_setup',
    label: 'Analysis Setup',
    status: 'blocked',
    statusLabel: 'blocked',
    phase5Anchor: 'Phase5 workflow step: Analysis Setup',
    capabilityAnchors: [
      'analysis type selection',
      'load case and combination selection',
      'solver tolerance controls',
      'expected memory and runtime estimate',
    ],
    evidenceSignals: [
      { label: 'analysis config', valueKind: 'exact_value' },
      { label: 'load combinations', valueKind: 'reference_value' },
      { label: 'solver tolerances', valueKind: 'exact_value' },
    ],
  },
  {
    id: 'run_monitor',
    label: 'Run & Monitor',
    status: 'blocked',
    statusLabel: 'blocked',
    phase5Anchor: 'Phase5 workflow step: Run & Monitor',
    capabilityAnchors: [
      'load-step progress',
      'residual and increment trace',
      'fallback and warning visibility',
      'explicit stop reason',
    ],
    evidenceSignals: [
      { label: 'load step', valueKind: 'exact_value' },
      { label: 'residual/increment', valueKind: 'exact_value' },
      { label: 'fallback/warning', valueKind: 'derived_proxy' },
    ],
  },
  {
    id: 'compare_report',
    label: 'Compare & Report',
    status: 'blocked',
    statusLabel: 'blocked',
    phase5Anchor: 'Phase5 workflow step: Compare & Report',
    capabilityAnchors: [
      'engine versus reference comparison',
      'story/member/mode traceability',
      'worst-error and residual reporting',
      'reproduction bundle export',
      'Evidence Console absorption',
    ],
    evidenceSignals: [
      { label: 'reference comparison', valueKind: 'reference_value' },
      { label: 'story/member/mode', valueKind: 'derived_proxy' },
      { label: 'reproduction bundle', valueKind: 'exact_value' },
    ],
  },
]
