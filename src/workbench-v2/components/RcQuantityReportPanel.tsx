import { useEffect, useRef, useState, type ReactElement } from 'react'
import type { RcJobTransport } from '../model/jobTransport'
import type { WorkbenchJobView } from '../model/jobSchema'
import type { RcJobReview } from '../model/rcJobReview'
import { same } from '../model/rcJobSchema'
import { parseRcDeclaredPrices, type RcQuantityReportReference, type RcQuantityReportReview } from '../model/rcQuantityReportSchema'
import { createRcQuantityReport, listRcQuantityReports, loadRcQuantityReportBytes } from '../model/rcWorkflowProvider'
import { rcProjectLink, rcWorkflowAuthorizationFailure, rcWorkflowMessage } from './RcJobWorkflowPanel'

export function RcQuantityReportPanel({ transport, job, review, initialReportId, onAuthorizationFailure }: {
  transport: RcJobTransport; job: WorkbenchJobView; review: RcJobReview; initialReportId?: string; onAuthorizationFailure(error: unknown): void
}): ReactElement {
  const [references, setReferences] = useState<RcQuantityReportReference[]>([])
  const [cursor, setCursor] = useState(0)
  const [canLoadMore, setCanLoadMore] = useState(false)
  const [selected, setSelected] = useState<RcQuantityReportReview | null>(null)
  const [selectedRef, setSelectedRef] = useState<RcQuantityReportReference | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [includePrices, setIncludePrices] = useState(false)
  const [prices, setPrices] = useState({ concrete: '', rebar: '', currency: 'KRW', asOf: '', source: '' })
  const [dirty, setDirty] = useState(false)
  const active = useRef(true)
  const sequence = useRef(0)
  const urls = useRef(new Set<string>())
  const initialHandled = useRef(false)
  function failure(error: unknown): void {
    if (!active.current) return
    setError(rcWorkflowMessage(error))
    if (rcWorkflowAuthorizationFailure(error)) onAuthorizationFailure(error)
  }
  async function admit(reference: RcQuantityReportReference, ownSequence: number, expectedDeclaration?: RcQuantityReportReview['declared_prices']): Promise<void> {
    if (!review.verifyQuantityReport) throw new Error('rc_report_verifier_unavailable')
    const raw = await loadRcQuantityReportBytes(transport, job, reference)
    if (!active.current || ownSequence !== sequence.current) return
    const verified = await review.verifyQuantityReport(raw.bytes, reference)
    if (!active.current || ownSequence !== sequence.current) return
    if (expectedDeclaration !== undefined && !same(verified.declared_prices, expectedDeclaration)) throw new Error('rc_saved_declaration_mismatch')
    setSelected(verified); setSelectedRef(reference)
  }
  async function page(afterRevision: number): Promise<void> {
    const ownSequence = ++sequence.current
    setBusy(true); setError('')
    try {
      const index = await listRcQuantityReports(transport, job, { afterRevision, limit: 20 })
      if (!active.current || ownSequence !== sequence.current) return
      setReferences(old => afterRevision === 0 ? index.reports : [...old, ...index.reports])
      setCursor(index.next_after_revision); setCanLoadMore(index.reports.length === 20)
      if (initialReportId && !initialHandled.current) {
        const reference = index.reports.find(ref => ref.report_id === initialReportId)
        if (reference) { await admit(reference, ownSequence); initialHandled.current = true }
        else setError('The requested saved report is not on this loaded page. Load more revisions; no other report has been substituted.')
      }
    } catch (error) { if (ownSequence === sequence.current) failure(error) }
    finally { if (active.current && ownSequence === sequence.current) setBusy(false) }
  }
  useEffect(() => {
    active.current = true
    void page(0)
    return () => { active.current = false; sequence.current++; for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear() }
  }, [transport, job, review])
  async function select(id: string): Promise<void> {
    if (busy) return
    const reference = references.find(ref => ref.report_id === id)
    if (!reference) return
    const ownSequence = ++sequence.current
    setBusy(true); setError('')
    try { await admit(reference, ownSequence) }
    catch (error) { if (ownSequence === sequence.current) failure(error) }
    finally { if (active.current && ownSequence === sequence.current) setBusy(false) }
  }
  async function save(): Promise<void> {
    if (busy) return
    const ownSequence = ++sequence.current
    setBusy(true); setError('')
    try {
      if (includePrices && (!prices.concrete.trim() || !prices.rebar.trim())) throw new Error('rc_prices_required')
      const declaration = parseRcDeclaredPrices(includePrices ? {
        concrete_per_m3: Number(prices.concrete), rebar_per_kg: Number(prices.rebar), currency: prices.currency, as_of: prices.asOf, source: prices.source,
      } : null)
      const reference = await createRcQuantityReport(transport, job, declaration)
      if (!active.current || ownSequence !== sequence.current) return
      await admit(reference, ownSequence, declaration)
      if (!active.current || ownSequence !== sequence.current) return
      setReferences(old => [...old.filter(ref => ref.report_id !== reference.report_id), reference].sort((a, b) => a.revision - b.revision))
      setDirty(false)
    } catch (error) { if (ownSequence === sequence.current) failure(error) }
    finally { if (active.current && ownSequence === sequence.current) setBusy(false) }
  }
  async function download(): Promise<void> {
    if (!selectedRef || !review.downloadQuantityReport || busy) return
    const reference = selectedRef, ownSequence = ++sequence.current
    setBusy(true); setError('')
    try {
      // Recheck host scope even for cached worker bytes. The scoped reviewer also
      // checks before and after its asynchronous work.
      await transport.verifyAuthorizationScope()
      let blob: Blob
      try { blob = await review.downloadQuantityReport(reference.report_id) } catch {
        await admit(reference, ownSequence)
        blob = await review.downloadQuantityReport(reference.report_id)
      }
      if (!active.current || ownSequence !== sequence.current) return
      const url = URL.createObjectURL(blob), anchor = document.createElement('a')
      urls.current.add(url); anchor.href = url; anchor.download = `${job.job_id}-${reference.report_id}.json`
      document.body.append(anchor); anchor.click(); anchor.remove()
      setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url) }, 0)
    } catch (error) { if (ownSequence === sequence.current) failure(error) }
    finally { if (active.current && ownSequence === sequence.current) setBusy(false) }
  }
  function edit(patch: Partial<typeof prices>): void { setPrices(old => ({ ...old, ...patch })); setDirty(true) }
  return <section data-rc-quantity-report={selected ? 'verified' : 'unselected'} aria-labelledby={`${job.job_id}-quantity-title`}>
    <h3 id={`${job.job_id}-quantity-title`}>Saved quantities and declared material prices</h3>
    <label><input type="checkbox" disabled={busy} checked={includePrices} onChange={e => { setIncludePrices(e.target.checked); setDirty(true) }} /> Include declared prices</label>
    {includePrices ? <fieldset disabled={busy}><legend>Price declaration</legend>
      <label>Concrete price per m³ <input type="number" min="0" step="any" value={prices.concrete} onChange={e => edit({ concrete: e.target.value })} /></label>{' '}
      <label>Rebar price per kg <input type="number" min="0" step="any" value={prices.rebar} onChange={e => edit({ rebar: e.target.value })} /></label>{' '}
      <label>Currency <input value={prices.currency} maxLength={3} onChange={e => edit({ currency: e.target.value })} /></label>{' '}
      <label>Price date <input type="date" value={prices.asOf} onChange={e => edit({ asOf: e.target.value })} /></label>{' '}
      <label>Declared source <input value={prices.source} maxLength={2000} onChange={e => edit({ source: e.target.value })} /></label>
    </fieldset> : null}
    {dirty ? <p data-rc-price-draft>These declaration changes have not been saved. The selected revision below retains its original prices.</p> : null}
    <div className="wb2-actions"><button type="button" className="wb2-btn" disabled={busy || !review.verifyQuantityReport} onClick={() => void save()}>Save quantity and price revision</button>
      <label>Saved quantity revision <select value={selectedRef?.report_id ?? ''} disabled={busy} onChange={e => void select(e.target.value)}>
        <option value="">Choose a saved revision</option>{references.map(ref => <option key={ref.report_id} value={ref.report_id}>Revision {ref.revision} · {ref.created_at}</option>)}
      </select></label>
      {canLoadMore && references.length < 640 ? <button type="button" className="wb2-btn" disabled={busy} onClick={() => void page(cursor)}>Load more saved revisions</button> : null}
    </div>
    {busy ? <p role="status">Checking this report against the stored RC source…</p> : null}
    {error ? <p role="alert" data-rc-report-error>{error}</p> : null}
    {selected && selectedRef ? <>
      <p data-rc-saved-report-id className="wb2-mono" style={{ overflowWrap: 'anywhere' }}>{selected.report_id}</p>
      <table className="wb2-table" data-rc-quantities><caption>Gross concrete and authored straight longitudinal bars</caption>
        <thead><tr><th>Member</th><th>Length (m)</th><th>Concrete (m³)</th><th>Rebar (kg)</th></tr></thead>
        <tbody>{selected.quantities.members.map((row: Record<string, unknown>) => <tr key={String(row.member_id)}><th scope="row">{String(row.member_id)}</th><td>{String(row.length_m)}</td><td>{String(row.gross_concrete_volume_m3)}</td><td>{String(row.longitudinal_rebar_mass_kg)}</td></tr>)}</tbody>
      </table>
      <dl className="wb2-kv"><dt>Concrete total (m³)</dt><dd>{selected.quantities.totals.gross_concrete_volume_m3}</dd>
        <dt>Longitudinal rebar total (kg)</dt><dd>{selected.quantities.totals.longitudinal_rebar_mass_kg}</dd>
        <dt>Saved declaration</dt><dd data-rc-saved-prices>{selected.declared_prices ? `${selected.declared_prices.currency} · ${selected.declared_prices.as_of} · ${selected.declared_prices.source}` : 'No prices declared; no material estimate'}</dd>
        <dt>Material estimate</dt><dd data-rc-material-estimate>{selected.material_estimate ? `${selected.material_estimate.total} ${selected.material_estimate.currency}` : 'Unavailable without declared prices'}</dd>
      </dl>
      <p className="wb2-muted">Gross concrete volume and straight longitudinal bars exclude detailing, transverse reinforcement and the listed cost items. A declaration is not a verified quotation or design approval.</p>
      <p data-rc-quantity-exclusions>{selected.quantities.excluded_items.join(', ')}</p>
      <div className="wb2-actions"><button type="button" className="wb2-btn" disabled={busy} onClick={() => void download()}>Download saved quantity report</button>
        <a data-rc-report-link href={rcProjectLink(job.job_id, selected.report_id)} target="_blank" rel="noopener">Reopen this saved report</a></div>
    </> : null}
  </section>
}
