import { useEffect, useRef, useState, type ReactElement } from 'react'
import type { WorkbenchJobView } from '../model/jobSchema'
import type { RcJobTransport } from '../model/jobTransport'
import { loadRcInvocationDetail, loadRcJobDiagnostics, type RcInvocationDetail, type RcJobDiagnostics } from '../model/rcJobDiagnostics'

interface Props {
  transport: RcJobTransport; job: WorkbenchJobView
  onAuthorizationFailure(error: unknown): void
  onPrepareChangedRun(): void
}
export function RcJobDiagnosticsPanel({ transport, job, onAuthorizationFailure, onPrepareChangedRun }: Props): ReactElement {
  const [diagnostics, setDiagnostics] = useState<RcJobDiagnostics | null>(null)
  const [detail, setDetail] = useState<{ ordinal: number; value: RcInvocationDetail } | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const generation = useRef(0)
  useEffect(() => {
    let active = true; generation.current++
    setDiagnostics(null); setDetail(null); setMessage(''); setBusy(true)
    loadRcJobDiagnostics(transport, job).then(value => { if (active) setDiagnostics(value) }).catch(error => {
      if (!active) return
      if (/authorization_|(?:http_|HTTP_)(?:401|403)/.test(error instanceof Error ? error.message : '')) onAuthorizationFailure(error)
      setMessage('Stored invocation observations are unavailable or could not be verified. Work and phase timing remain unknown.')
    }).finally(() => { if (active) setBusy(false) })
    return () => { active = false; generation.current++ }
  }, [transport, job.job_id, job.request.content_hash, job.revision, refresh])

  async function inspect(ordinal: number): Promise<void> {
    const observation = diagnostics?.invocations.find(r => r.ordinal === ordinal)
    if (!observation || busy) return
    const own = generation.current
    setBusy(true); setDetail(null); setMessage('')
    try { const value = await loadRcInvocationDetail(transport, job, observation); if (generation.current === own) setDetail({ ordinal, value }) }
    catch (error) {
      if (generation.current !== own) return
      if (/authorization_|(?:http_|HTTP_)(?:401|403)/.test(error instanceof Error ? error.message : '')) onAuthorizationFailure(error)
      setMessage('This invocation detail is unavailable, exceeds the review limit, or failed its binding check.')
    } finally { if (generation.current === own) setBusy(false) }
  }
  const seconds = (v: number | null): string => v === null ? 'unknown' : `${v.toPrecision(6)} s`
  const attempts = job.progress.unit === 'control_solver_attempts'
  return <section className="wb2-panel" data-rc-diagnostics>
    <h3>Recorded execution diagnostics</h3>
    <p>Stored worker observations describe this request. They do not independently verify its numerical result. A declared interval is an attempted chunk, not accepted response states.</p>
    <p>Job error code: <code>{job.error_code ?? 'none recorded'}</code> · {attempts ? 'durable control solver attempts' : 'accepted durable targets'}: {job.progress.completed_steps}/{job.progress.total_steps}</p>
    <button className="wb2-btn" type="button" disabled={busy} onClick={() => setRefresh(v => v + 1)}>Refresh recorded diagnostics</button>
    {message ? <p role="status">{message}</p> : null}
    {diagnostics ? <>
      <dl className="wb2-kv"><dt>Recorded analysis wall time sum</dt><dd>{seconds(diagnostics.analysisWallSeconds)}</dd>
        <dt>Recorded verification wall time sum</dt><dd>{seconds(diagnostics.verificationWallSeconds)}</dd>
        <dt>Recorded process CPU time sum</dt><dd>{seconds(diagnostics.processCpuSeconds)}</dd>
        <dt>Execution work</dt><dd>{diagnostics.unknownWork ? 'partly unknown' : 'all reservations have recorded work observations'}</dd>
        <dt>Reservations without outcomes</dt><dd>{diagnostics.pending.length ? diagnostics.pending.join(', ') : 'none'}</dd></dl>
      <p>Phase sums exclude queueing, polling and any reservation without an outcome. They are not total job elapsed time.</p>
      <div style={{ overflowX: 'auto' }}><table className="wb2-table"><caption>Stored invocations</caption><thead><tr><th>Ordinal</th><th>Phase</th><th>Status</th><th>Declared {attempts ? 'control attempt' : 'target'} interval</th><th>Wall time</th><th>Work</th><th>Detail</th></tr></thead>
        <tbody>{diagnostics.invocations.map(row => <tr key={row.ordinal}><td>{row.ordinal}</td><td>{row.phase}</td><td>{row.status}</td>
          <td>{row.completed_before + 1}–{row.completed_after}</td><td>{seconds(row.timing.wall_ns / 1e9)}</td><td>{row.unavailable_execution_work ? 'unknown' : 'recorded'}</td>
          <td><button type="button" className="wb2-btn" disabled={busy} onClick={() => void inspect(row.ordinal)}>Inspect invocation {row.ordinal}</button></td></tr>)}</tbody></table></div>
      {detail ? <div data-rc-invocation-detail><h4>Invocation {detail.ordinal}</h4>
        <dl className="wb2-kv"><dt>Error type</dt><dd>{detail.value.errorType ?? 'not recorded'}</dd><dt>Error code</dt><dd>{detail.value.errorCode ?? 'not recorded'}</dd>
          <dt>Observed outcome</dt><dd>{detail.value.outcomeStatus ?? 'not recorded'}</dd><dt>Failure</dt><dd>{detail.value.failure ?? 'not recorded'}</dd>
          <dt>Verification checks</dt><dd>{detail.value.checks.join(', ') || 'not recorded'}</dd></dl>
        <p>Member, DOF and residual attribution are unavailable unless the original solver record supplies them. No cause is inferred from a generic failure.</p>
        {detail.value.attempts.map((attempt, i) => <details key={i}><summary>Recorded target {attempt.targetM} m · {attempt.committed ? 'committed' : 'not committed'} · {attempt.status ?? attempt.failureType ?? 'status unavailable'}</summary>
          <table className="wb2-table"><caption>Recorded relative residual (dimensionless, augmented system)</caption><thead><tr><th>Newton iteration</th><th>Relative residual</th></tr></thead>
            <tbody>{attempt.convergence.map(row => <tr key={row.iteration}><td>{row.iteration}</td><td>{row.relativeResidual.toExponential(5)}</td></tr>)}</tbody></table>
          {!attempt.convergence.length ? <p>Convergence trace unavailable.</p> : null}
        </details>)}
        {detail.value.traceTruncated ? <p>Showing the last 16 attempts and last 128 iterations per attempt. The retained original artifact contains the complete recorded trace.</p> : null}
      </div> : null}
    </> : null}
    {job.status === 'failed' ? <><button type="button" className="wb2-btn" data-rc-prepare-changed disabled={busy} onClick={onPrepareChangedRun}>Copy failed input for a changed run</button>
      <p>Edit the copied draft, review its changes, then explicitly submit a new job. The existing failed request and checkpoint remain immutable.</p></> : null}
  </section>
}
