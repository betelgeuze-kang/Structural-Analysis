import { useEffect, useRef, useState } from 'react'
import type { WorkbenchJobView } from '../model/jobSchema'
import { createJobReadTransport, type JobAuthorizationProvider } from '../model/jobTransport'
import { loadFailureDiagnostic, type FailureDiagnosticReview } from '../model/failureDiagnostic'
import { FailureDiagnosticPanel } from './FailureDiagnosticPanel'

/** Read-only, explicitly requested history; never replaces current job authority. */
export function HistoricalFailurePanel({ job, url, authorize }: { job: WorkbenchJobView; url: string; authorize?: JobAuthorizationProvider }) {
  const [attempt, setAttempt] = useState(String(job.attempt - 1))
  const [status, setStatus] = useState('idle')
  const [review, setReview] = useState<FailureDiagnosticReview>()
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])
  const number = Number(attempt)
  const valid = /^[1-9][0-9]{0,3}$/.test(attempt) && Number.isSafeInteger(number) && number < job.attempt
  async function load() {
    if (!valid) return
    active.current?.abort()
    const controller = new AbortController(); active.current = controller
    setReview(undefined); setStatus('loading')
    try {
      const transport = await createJobReadTransport(url, controller.signal, authorize)
      const value = await loadFailureDiagnostic(job, transport, number)
      if (controller.signal.aborted) return
      setReview(value); setStatus(value ? 'verified' : 'missing')
    } catch {
      if (!controller.signal.aborted) { setReview(undefined); setStatus('invalid') }
    }
  }
  return <section data-failure-history={status} aria-label="Previous failure records">
    <h3>Previous failure records</h3>
    <p>Read an earlier attempt without changing the current job or its result. Some attempts have no retained diagnostic.</p>
    <label>Previous attempt <input type="number" min={1} max={job.attempt - 1} value={attempt} onChange={event => {
      active.current?.abort(); setAttempt(event.target.value); setReview(undefined); setStatus('idle')
    }} /></label>{' '}
    <button type="button" className="wb2-btn" disabled={!valid || status === 'loading'} onClick={() => { void load() }}>Review previous attempt</button>
    <p role="status">{status === 'loading' ? 'Checking original diagnostic…' : status === 'missing' ? `No retained diagnostic for attempt ${attempt}.` : status === 'invalid' ? 'Previous diagnostic unavailable: retrieval or integrity checks failed.' : ''}</p>
    {review ? <FailureDiagnosticPanel review={review} /> : null}
  </section>
}
