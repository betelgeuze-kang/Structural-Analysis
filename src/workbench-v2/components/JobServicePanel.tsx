import { RcJobResultPanel } from './RcJobResultPanel'
import { RcCorotationalReportPanel } from './RcCorotationalReportPanel'
import type { RcCorotationalReportReview } from '../model/rcCorotationalReportReview'
import type { RcJobReview } from '../model/rcJobReview'
import type { ReactElement } from 'react'
import type { EngineeringResultIrManifest, JobLoadStatus } from '../model/jobProvider'
import type { WorkbenchJobView } from '../model/jobSchema'
import { StateChip, type ChipState } from './StateChip'
import { BooleanEvidenceValueText } from './EngineeringValueText'

interface JobServicePanelProps {
  loadStatus: JobLoadStatus
  job: WorkbenchJobView | null
  errors: string[]
  artifactStatus?: 'not_published' | 'verified' | 'report_verified' | 'integrity_unavailable' | 'invalid'
  rcReview?: RcJobReview
  rcCorotationalReview?: RcCorotationalReportReview
  expectedCorotationalReportId?: string
  engineeringResultIr?: EngineeringResultIrManifest
}

function chip(job: WorkbenchJobView): ChipState {
  if (job.status === 'failed' || job.status === 'cancelled') return 'BLOCKED'
  if (job.status === 'succeeded' || job.status === 'running' || job.status === 'checkpointed' || job.status === 'queued') return 'LIVE'
  return 'UNAVAILABLE'
}

function shortHash(value: string): string {
  return `${value.slice(0, 15)}…${value.slice(-8)}`
}

export function JobServicePanel({
  loadStatus,
  job,
  errors,
  artifactStatus,
  engineeringResultIr,
  rcReview,
  rcCorotationalReview,
  expectedCorotationalReportId,
}: JobServicePanelProps): ReactElement {
  const attemptBounded = job?.schema_version === 'structural-analysis-job-view.v2'
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
      <div className="wb2-run-progress" role="progressbar" aria-valuemin={0} aria-valuemax={job.progress.total_steps} aria-valuenow={job.progress.completed_steps} aria-label={attemptBounded ? 'Control attempts consumed from the fixed limit' : 'Durably committed analysis steps'}>
        <div className="wb2-run-progress__bar" style={{ width: `${Math.round(100 * job.progress.completed_steps / job.progress.total_steps)}%` }} />
      </div>
      <p className="wb2-run-progress__caption">
        {job.progress.completed_steps} of {job.progress.total_steps} {attemptBounded ? 'control attempts used' : 'step(s) durably committed'} · {attemptBounded ? 'worker attempt' : 'attempt'} {job.attempt}
      </p>
      <dl className="wb2-kv">
        <dt>Job</dt><dd className="wb2-mono">{job.job_id}</dd>
        <dt>Request</dt><dd className="wb2-mono">{shortHash(job.request.content_hash)}</dd>
        <dt>Checkpoint</dt><dd className="wb2-mono">{job.checkpoint ? shortHash(job.checkpoint.content_hash) : 'none'}</dd>
        <dt>Result</dt><dd className="wb2-mono">{job.result ? shortHash(job.result.content_hash) : 'not published'}</dd>
        <dt>Evidence</dt><dd className="wb2-mono">{job.evidence ? shortHash(job.evidence.content_hash) : 'not published'}</dd>
        <dt>{rcCorotationalReview ? 'Saved report integrity' : 'Published pair integrity'}</dt><dd>{artifactStatus ?? 'not evaluated'}</dd>
        <dt>Solver converged</dt>
        <dd data-job-convergence="unavailable">
          <BooleanEvidenceValueText value={{ status: 'unavailable' }} />
        </dd>
        <dt>Engineering ResultIR</dt>
        <dd className="wb2-mono" data-job-result-ir={engineeringResultIr ? 'verified' : 'unavailable'}>
          {engineeringResultIr ? shortHash(engineeringResultIr.engineering_result_hash) : 'not verified'}
        </dd>
        <dt>ResultIR authority</dt>
        <dd data-job-result-ir-authority>
          {engineeringResultIr
            ? `convergence=${engineeringResultIr.authority_axes.convergence}; displacement=${engineeringResultIr.authority_axes.displacement}; reaction=${engineeringResultIr.authority_axes.reaction}`
            : 'UNAVAILABLE'}
        </dd>
      </dl>
      {artifactStatus === 'verified' && rcReview ? <RcJobResultPanel jobId={job.job_id} review={rcReview} /> : null}
      {artifactStatus === 'report_verified' && rcCorotationalReview ? <RcCorotationalReportPanel key={rcCorotationalReview.summary.reportId} review={rcCorotationalReview} expectedReportId={expectedCorotationalReportId} /> : null}
      <p className="wb2-muted" data-job-authority={job.result_authority}>
        {rcCorotationalReview ? 'Job state is orchestration evidence only. The nodal report has a separate experimental corotational RC scope; no legacy engineering ResultIR or quantity authority is inherited.' : 'Job state is orchestration evidence only. This panel consumes only the verified embedded engineering ResultIR identity and authority axes; it never falls back to top-level result arrays.'}
      </p>
    </section>
  )
}
