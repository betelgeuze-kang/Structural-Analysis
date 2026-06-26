import {
  DEVELOPER_PREVIEW_WORKFLOW_SELECTION_CHANNELS,
  DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION,
  DEVELOPER_PREVIEW_WORKFLOW_STATUS_VOCABULARY,
  DEVELOPER_PREVIEW_WORKFLOW_VALUE_KINDS,
  DEVELOPER_PREVIEW_WORKFLOW_WORKER_BOUNDARY,
  DEVELOPER_PREVIEW_WORKFLOW_WORKER_TASKS,
  type DeveloperPreviewWorkflowStep,
} from './developerPreviewWorkflow'
import type { DeveloperPreviewWorkflowState } from './developerPreviewWorkflowState'

type StatusTone = 'ok' | 'warn' | 'missing'

export type DeveloperPreviewWorkflowPanelProps = {
  statusTone: StatusTone
  statusLabel: string
  shellStepCountLabel: string
  executionStepCountLabel: string
  observationStatusLabel: string
  blockerCountLabel: string
  routeState: DeveloperPreviewWorkflowState
  steps: DeveloperPreviewWorkflowStep[]
  sourceLabel: string
}

export function DeveloperPreviewWorkflowPanel({
  statusTone,
  statusLabel,
  shellStepCountLabel,
  executionStepCountLabel,
  observationStatusLabel,
  blockerCountLabel,
  routeState,
  steps,
  sourceLabel,
}: DeveloperPreviewWorkflowPanelProps) {
  return (
    <section
      className="panel developer-preview-workflow"
      id="developer-preview-workflow"
      data-phase5-gui-workflow-shell="true"
      data-phase5-feature-module="DeveloperPreviewWorkflowPanel"
    >
      <div className="panel__header">
        <div>
          <p className="panel__kicker">Developer Preview Workflow</p>
          <h2>Import → Model Health → Analysis Setup → Run & Monitor → Compare & Report</h2>
        </div>
        <span className={`status-pill status-pill--${statusTone}`}>{statusLabel}</span>
      </div>
      <div className="developer-preview-workflow__summary">
        <div className="mini-metric">
          <span>GUI shell</span>
          <strong>{shellStepCountLabel}</strong>
        </div>
        <div className="mini-metric">
          <span>Execution pass</span>
          <strong>{executionStepCountLabel}</strong>
        </div>
        <div className="mini-metric">
          <span>UX observation</span>
          <strong>{observationStatusLabel}</strong>
        </div>
        <div className="mini-metric">
          <span>Blockers</span>
          <strong>{blockerCountLabel}</strong>
        </div>
      </div>
      <div
        className="developer-preview-workflow__status-vocabulary"
        data-phase5-status-vocabulary="ready blocked missing error"
      >
        {DEVELOPER_PREVIEW_WORKFLOW_STATUS_VOCABULARY.map((status) => (
          <span key={`phase5-status-${status}`} data-phase5-status-token={status}>
            {status}
          </span>
        ))}
      </div>
      <div
        className="developer-preview-workflow__value-kind-legend"
        data-phase5-value-kind-legend="exact_value derived_proxy reference_value"
      >
        {DEVELOPER_PREVIEW_WORKFLOW_VALUE_KINDS.map((valueKind) => (
          <span key={`phase5-value-kind-${valueKind}`} data-phase5-value-kind-token={valueKind}>
            {valueKind.replace('_', ' ')}
          </span>
        ))}
      </div>
      <div
        className="developer-preview-workflow__route-state"
        data-phase5-route-state="true"
        data-phase5-route-id={routeState.routeId}
        data-phase5-case-id={routeState.caseId}
        data-phase5-run-id={routeState.runId}
        data-phase5-route-status={routeState.status}
      >
        <div className="developer-preview-workflow__route-copy">
          <p className="developer-preview-workflow__anchor">route/case/run-centered workflow state</p>
          <strong>{routeState.statusLabel}</strong>
          <p>{routeState.claimBoundary}</p>
        </div>
        <div className="developer-preview-workflow__route-metrics">
          {routeState.metrics.map((metric) => (
            <div key={`phase5-route-${metric.label}`} className="mini-metric">
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      </div>
      <div
        className="developer-preview-workflow__selection-state"
        data-phase5-selection-state="unified"
      >
        <div>
          <p className="developer-preview-workflow__anchor">single selection state</p>
          <strong>3D/table/chart/comparison row share one selection token</strong>
        </div>
        <div
          className="developer-preview-workflow__selection-channels"
          data-phase5-selection-channel-vocabulary="3d table chart comparison_row"
        >
          {DEVELOPER_PREVIEW_WORKFLOW_SELECTION_CHANNELS.map((channel) => (
            <span key={`phase5-selection-${channel}`} data-phase5-selection-channel={channel}>
              {channel.replace('_', ' ')}
            </span>
          ))}
        </div>
      </div>
      <div
        className="developer-preview-workflow__worker-boundary"
        data-phase5-worker-boundary={DEVELOPER_PREVIEW_WORKFLOW_WORKER_BOUNDARY.processedOn}
      >
        <div>
          <p className="developer-preview-workflow__anchor">Web Worker boundary</p>
          <strong>Large IFC parsing and result processing run off the UI thread boundary</strong>
          <p>{DEVELOPER_PREVIEW_WORKFLOW_WORKER_BOUNDARY.claimBoundary}</p>
        </div>
        <div
          className="developer-preview-workflow__worker-tasks"
          data-phase5-worker-task-vocabulary="ifc_parse result_processing"
        >
          {DEVELOPER_PREVIEW_WORKFLOW_WORKER_TASKS.map((task) => (
            <span key={`phase5-worker-${task}`} data-phase5-worker-task={task}>
              {task.replace('_', ' ')}
            </span>
          ))}
        </div>
      </div>
      <div
        className="developer-preview-workflow__evidence-console"
        data-phase5-evidence-console-absorption={
          DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION.workflowStepId
        }
        data-phase5-evidence-console-source={
          DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION.sourceReceipt
        }
      >
        <div>
          <p className="developer-preview-workflow__anchor">Evidence Console absorption</p>
          <strong>Compare & Report carries the Evidence Console review scope forward</strong>
          <p>{DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION.claimBoundary}</p>
        </div>
        <div
          className="developer-preview-workflow__evidence-console-features"
          data-phase5-evidence-console-feature-vocabulary={DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION.absorbedFeatures.join(
            ' ',
          )}
        >
          {DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION.absorbedFeatures.map((feature) => (
            <span key={`phase5-evidence-console-${feature}`} data-phase5-evidence-console-feature={feature}>
              {feature.split('_').join(' ')}
            </span>
          ))}
        </div>
      </div>
      <div className="developer-preview-workflow__steps">
        {steps.map((step, index) => (
          <article
            key={step.id}
            className="developer-preview-workflow__step"
            data-phase5-workflow-step={step.id}
            data-phase5-workflow-status={step.status}
          >
            <div className="developer-preview-workflow__step-head">
              <span className="developer-preview-workflow__index">{index + 1}</span>
              <div>
                <p className="developer-preview-workflow__anchor">{step.phase5Anchor}</p>
                <h3>{step.label}</h3>
              </div>
              <span className="status-pill status-pill--warn">{step.statusLabel}</span>
            </div>
            <div className="developer-preview-workflow__signals">
              {step.evidenceSignals.map((signal) => (
                <span key={`${step.id}-${signal.label}`} data-phase5-value-kind={signal.valueKind}>
                  <b>{signal.valueKind.replace('_', ' ')}</b>
                  {signal.label}
                </span>
              ))}
            </div>
            <ul className="developer-preview-workflow__capabilities">
              {step.capabilityAnchors.map((capability) => (
                <li key={`${step.id}-${capability}`}>{capability}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
      <details
        className="developer-preview-workflow__provenance"
        data-phase5-provenance-disclosure="collapsed"
      >
        <summary data-phase5-provenance-summary="advanced provenance">
          Advanced provenance
        </summary>
        <dl data-phase5-provenance-details="true">
          <div>
            <dt>Source</dt>
            <dd>{sourceLabel}</dd>
          </div>
          <div>
            <dt>Route</dt>
            <dd>{routeState.routeId}</dd>
          </div>
          <div>
            <dt>Case</dt>
            <dd>{routeState.caseId}</dd>
          </div>
          <div>
            <dt>Run</dt>
            <dd>{routeState.runId}</dd>
          </div>
          <div>
            <dt>Status vocabulary</dt>
            <dd>{DEVELOPER_PREVIEW_WORKFLOW_STATUS_VOCABULARY.join(', ')}</dd>
          </div>
          <div>
            <dt>Value kinds</dt>
            <dd>{DEVELOPER_PREVIEW_WORKFLOW_VALUE_KINDS.join(', ')}</dd>
          </div>
          <div>
            <dt>Claim boundary</dt>
            <dd>{routeState.claimBoundary}</dd>
          </div>
          <div>
            <dt>Worker boundary</dt>
            <dd>{DEVELOPER_PREVIEW_WORKFLOW_WORKER_BOUNDARY.claimBoundary}</dd>
          </div>
          <div>
            <dt>Evidence Console</dt>
            <dd>{DEVELOPER_PREVIEW_EVIDENCE_CONSOLE_ABSORPTION.claimBoundary}</dd>
          </div>
        </dl>
      </details>
      <p className="panel__source">source: {sourceLabel}</p>
    </section>
  )
}
