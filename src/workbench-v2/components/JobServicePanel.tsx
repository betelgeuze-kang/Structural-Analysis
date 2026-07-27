import type { ReactElement } from 'react'
import type { JobLoadStatus, WorkbenchJobResultSummary } from '../model/jobProvider'
import type { WorkbenchJobView } from '../model/jobSchema'
import type { ExplicitValue, TextValue } from '../model/caseSchema'
import { EngineeringValueText } from './EngineeringValueText'
import { StateChip, type ChipState } from './StateChip'

interface JobServicePanelProps {
  loadStatus: JobLoadStatus
  job: WorkbenchJobView | null
  errors: string[]
  artifactStatus?: 'not_published' | 'verified' | 'integrity_unavailable' | 'invalid'
  resultSummary?: WorkbenchJobResultSummary | null
}

function chip(job: WorkbenchJobView): ChipState {
  if (job.status === 'failed' || job.status === 'cancelled') return 'BLOCKED'
  if (job.status === 'succeeded' || job.status === 'running' || job.status === 'checkpointed' || job.status === 'queued') return 'LIVE'
  return 'UNAVAILABLE'
}

function shortHash(value: string): string {
  return `${value.slice(0, 15)}…${value.slice(-8)}`
}

function explicitText(value: TextValue): ReactElement {
  return value.state === 'available' ? (
    <span data-engineering-value-state="available">{value.value}</span>
  ) : (
    <span data-engineering-value-state={value.state} title={value.reason}>
      {value.state === 'unavailable' ? 'Unavailable' : 'Invalid'}
    </span>
  )
}

function explicitBoolean(value: ExplicitValue<boolean>): ReactElement {
  return value.state === 'available' ? (
    <span data-engineering-value-state="available">{value.value ? 'Yes' : 'No'}</span>
  ) : (
    <span data-engineering-value-state={value.state} title={value.reason}>
      {value.state === 'unavailable' ? 'Unavailable' : 'Invalid'}
    </span>
  )
}

export function JobServicePanel({ loadStatus, job, errors, artifactStatus, resultSummary }: JobServicePanelProps): ReactElement {
  if (loadStatus !== 'ready' || !job) {
    const label = loadStatus === 'loading' ? 'Loading durable job status…' : loadStatus === 'unconfigured'
      ? 'No durable job endpoint is configured for this Workbench session.'
      : `Durable job status unavailable${errors[0] ? ` (${errors[0]})` : ''}.`
    return (
      <section className="wb2-panel" aria-labelledby="wb2-job-title" data-job-service={loadStatus}>
        <h2 id="wb2-job-title" className="wb2-panel__title">Durable job service</h2>
        <StateChip state={loadStatus === 'missing' ? 'MISSING' : 'UNAVAILABLE'} srLabel="Job service" />
        <p className="wb2-unavailable" data-wb2-unavailable>{label} Solver state is not inferred.</p>
      </section>
    )
  }

  return (
    <section className="wb2-panel" aria-labelledby="wb2-job-title" data-job-service="ready" data-job-status={job.status}>
      <h2 id="wb2-job-title" className="wb2-panel__title">Durable job service</h2>
      <div className="wb2-run-head">
        <StateChip state={chip(job)} srLabel="Job state" />
        <span className="wb2-run-status-label">{job.status}</span>
      </div>
      <div className="wb2-run-progress" role="progressbar" aria-valuemin={0} aria-valuemax={job.progress.total_steps} aria-valuenow={job.progress.completed_steps} aria-label="Durably committed analysis steps">
        <div className="wb2-run-progress__bar" style={{ width: `${Math.round(100 * job.progress.completed_steps / job.progress.total_steps)}%` }} />
      </div>
      <p className="wb2-run-progress__caption">
        {job.progress.completed_steps} of {job.progress.total_steps} step(s) durably committed · attempt {job.attempt}
      </p>
      <dl className="wb2-kv">
        <dt>Job</dt><dd className="wb2-mono">{job.job_id}</dd>
        <dt>Request</dt><dd className="wb2-mono">{shortHash(job.request.content_hash)}</dd>
        <dt>Checkpoint</dt><dd className="wb2-mono">{job.checkpoint ? shortHash(job.checkpoint.content_hash) : 'none'}</dd>
        <dt>Result</dt><dd className="wb2-mono">{job.result ? shortHash(job.result.content_hash) : 'not published'}</dd>
        <dt>Evidence</dt><dd className="wb2-mono">{job.evidence ? shortHash(job.evidence.content_hash) : 'not published'}</dd>
        <dt>Published pair integrity</dt><dd>{artifactStatus ?? 'not evaluated'}</dd>
      </dl>
      <p className="wb2-muted" data-job-authority={job.result_authority}>
        Job state is orchestration evidence only. Convergence and engineering values come from the referenced core result/evidence pair.
      </p>
      {resultSummary ? (
        <>
          <h3 className="wb2-subtitle">Verified core result</h3>
          <dl className="wb2-kv" data-job-result-summary>
            <dt>Solver</dt><dd>{explicitText(resultSummary.solverId)}</dd>
            <dt>Control mode</dt><dd>{explicitText(resultSummary.controlMode)}</dd>
            <dt>Public API authority</dt><dd>{explicitText(resultSummary.publicApiAuthority)}</dd>
            <dt>External V&amp;V</dt><dd>{explicitText(resultSummary.externalVvAuthority)}</dd>
            <dt>Terminal load factor</dt><dd><EngineeringValueText value={resultSummary.terminalLoadFactor} /></dd>
            <dt>Terminal epoch</dt><dd><EngineeringValueText value={resultSummary.terminalEpoch} integer /></dd>
            <dt>Terminal control displacement (m)</dt><dd><EngineeringValueText value={resultSummary.terminalControlDisplacement} /></dd>
            <dt>Exact engineering recovery</dt><dd>{explicitBoolean(resultSummary.exactEngineeringRecovery)}</dd>
            <dt>Exact checkpoint replay</dt><dd>{explicitBoolean(resultSummary.exactCheckpointChainReplay)}</dd>
            <dt>Fallback count</dt><dd><EngineeringValueText value={resultSummary.fallbackCount} integer /></dd>
            <dt>Regularization count</dt><dd><EngineeringValueText value={resultSummary.regularizationCount} integer /></dd>
            <dt>Accepted steps</dt><dd><EngineeringValueText value={resultSummary.acceptedStepCount} integer /></dd>
            <dt>Rejected steps</dt><dd><EngineeringValueText value={resultSummary.rejectedStepCount} integer /></dd>
            <dt>Displacement rows</dt><dd><EngineeringValueText value={resultSummary.nodeDisplacementRows} integer /></dd>
            <dt>Reaction rows</dt><dd><EngineeringValueText value={resultSummary.supportReactionRows} integer /></dd>
            <dt>Member-force rows</dt><dd><EngineeringValueText value={resultSummary.memberEndForceRows} integer /></dd>
            <dt>Section-result rows</dt><dd><EngineeringValueText value={resultSummary.sectionResultRows} integer /></dd>
            <dt>Fiber-result rows</dt><dd><EngineeringValueText value={resultSummary.fiberResultRows} integer /></dd>
          </dl>
        </>
      ) : null}
    </section>
  )
}
