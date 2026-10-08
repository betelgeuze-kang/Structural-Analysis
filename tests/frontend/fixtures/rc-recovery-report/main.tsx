import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { RcQuantityReportPanel } from '../../../../src/workbench-v2/components/RcQuantityReportPanel'
import { createJobWorkflowTransport, type RcJobTransport } from '../../../../src/workbench-v2/model/jobTransport'
import type { WorkbenchJobView } from '../../../../src/workbench-v2/model/jobSchema'
import type { RcJobReview } from '../../../../src/workbench-v2/model/rcJobReview'
import { parseRcDeclaredPrices } from '../../../../src/workbench-v2/model/rcQuantityReportSchema'

// Test-only orchestration boundary. No numerical artifact or worker exists.
// The real panel/provider checks reference identities and raw hashes; the mock
// reviewer exercises UI admission without claiming source or physical validity.
interface HarnessHost { tenantId: string; bearerToken: string }
interface HarnessControl { host: HarnessHost; reviewCalls: string[]; rejectReview: boolean; open(jobId: string): void }
declare global { interface Window { __rcReportRecoveryHost?: HarnessHost; __rcReportRecovery?: HarnessControl; __rcReportRecoveryInitialReport?: string } }
const firstId = `job_${'a'.repeat(32)}`
const hash = `sha256:${'c'.repeat(64)}`
function sourceJob(jobId: string): WorkbenchJobView {
  return {
    schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: jobId, status: 'succeeded', revision: 1, attempt: 1,
    progress: { completed_steps: 1, total_steps: 1 }, created_at: '2026-10-03T00:00:00Z', updated_at: '2026-10-03T00:00:00Z',
    lease_expires_at: null, error_code: null, can_resume: false,
    request: { role: 'request', content_hash: hash, byte_length: 1, media_type: 'application/json' }, checkpoint: null,
    result: { role: 'result', content_hash: hash, byte_length: 1, media_type: 'application/vnd.structural-analysis.rc-fiber-job-result+json' },
    evidence: { role: 'evidence', content_hash: hash, byte_length: 1, media_type: 'application/json' }, resume_contract_hash: null,
    solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only', terminal_event_hash: hash,
    claim_boundary: 'Test-only metadata envelope; no result bytes, worker, physical quantity or structural authority is present.',
  }
}
function mockReview(transport: RcJobTransport, job: WorkbenchJobView, control: HarnessControl): RcJobReview {
  const unavailable = async (): Promise<never> => { throw new Error('synthetic_numerical_review_unavailable') }
  return {
    // The report panel never consumes summary. This empty mock cannot serve a
    // structural review surface or gain authority in the production entrypoint.
    summary: {} as RcJobReview['summary'], epoch: unavailable, material: unavailable, download: unavailable,
    onFailure: () => () => {}, dispose: () => {},
    verifyQuantityReport: async (bytes, reference) => {
      await transport.verifyAuthorizationScope()
      if (!reference) throw new Error('synthetic_reference_required')
      const payload = JSON.parse(new TextDecoder().decode(bytes))
      if (control.rejectReview || payload.synthetic !== 'rc-report-ui-only') throw new Error('synthetic_review_rejected')
      const declaration = parseRcDeclaredPrices(payload.declared_prices)
      await transport.verifyAuthorizationScope()
      control.reviewCalls.push(reference.report_id)
      return {
        report_id: reference.report_id, content_hash: reference.content_hash, report_hash: hash, revision: reference.revision,
        bindings: { job_id: job.job_id, tenant_id: transport.tenantId, ui_test_only: true },
        quantities: { members: [], totals: { gross_concrete_volume_m3: 'not computed', longitudinal_rebar_mass_kg: 'not computed' },
          excluded_items: ['All structural quantities are unavailable in this UI-only harness'] },
        declared_prices: declaration, price_table_hash: null, material_estimate: null,
        claim_boundary: 'Synthetic review response for UI orchestration only; no physical or structural qualification.',
      }
    },
  }
}
function Harness() {
  const [jobId, setJobId] = useState(firstId)
  const [epoch, setEpoch] = useState(0)
  const [denied, setDenied] = useState(false)
  const [session, setSession] = useState<{ transport: RcJobTransport; job: WorkbenchJobView; review: RcJobReview; controller: AbortController } | null>(null)
  const [control] = useState<HarnessControl>(() => ({
    host: window.__rcReportRecoveryHost ?? { tenantId: 'rc-report-ui-synthetic', bearerToken: 'synthetic-report-memory-only' },
    reviewCalls: [], rejectReview: false, open: id => { setJobId(id); setEpoch(value => value + 1) },
  }))
  window.__rcReportRecovery = control
  useEffect(() => {
    const controller = new AbortController()
    setSession(null); setDenied(false)
    void createJobWorkflowTransport('/api/v1/jobs', controller.signal, () => control.host).then(transport => {
      if (controller.signal.aborted) return
      const job = sourceJob(jobId)
      setSession({ transport, job, review: mockReview(transport, job, control), controller })
    })
    return () => controller.abort()
  }, [jobId, epoch, control])
  return <main>
    <p data-rc-report-harness-boundary>UI-only injected review: no numerical artifacts, worker or structural qualification.</p>
    {denied ? <p data-rc-report-harness-denied>Authentication changed; the prior report panel was removed.</p> : null}
    {session && !denied ? <RcQuantityReportPanel key={`${jobId}:${epoch}`} transport={session.transport} job={session.job} review={session.review} initialReportId={window.__rcReportRecoveryInitialReport}
      onAuthorizationFailure={() => { session.controller.abort(); setDenied(true); setSession(null) }} /> : null}
  </main>
}
createRoot(document.getElementById('root')!).render(<Harness />)
