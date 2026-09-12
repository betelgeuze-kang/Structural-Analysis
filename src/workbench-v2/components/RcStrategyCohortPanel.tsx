import { useCallback, useEffect, useRef, useState } from 'react'
import { openRcReviewWorker } from '../model/rcReviewWorker'
import type { RcCohortReview } from '../model/rcStrategyCohortSchema'
import type { JobAuthorizationProvider } from '../model/jobTransport'
import { RcControlSearchPanel } from './RcControlSearchPanel'

const seconds = (n: number) => (n / 1e9).toFixed(3)
const ratio = (n: number | null) => n === null ? 'Unavailable' : n.toFixed(6)
export function RcStrategyCohortPanel({ url, authorize }: { url: string; authorize?: JobAuthorizationProvider }) {
  const [loaded, setLoaded] = useState<{ url: string; review: RcCohortReview } | null>(null)
  const [status, setStatus] = useState('loading'), [selected, setSelected] = useState<number | null>(null)
  const connection = useRef<Awaited<ReturnType<typeof openRcReviewWorker>> | null>(null)
  const links = useRef(new Set<string>())
  const invalidate = useCallback(() => { connection.current?.dispose(); setLoaded(null); setSelected(null); setStatus('invalid') }, [])
  useEffect(() => {
    const abort = new AbortController()
    setLoaded(null); setSelected(null); setStatus('loading')
    void (async () => {
      try {
        const active = await openRcReviewWorker(() => new Worker(new URL('../model/rcStrategyCohort.worker.ts', import.meta.url), { type: 'module' }), url, abort.signal, authorize)
        if (abort.signal.aborted) { active.dispose(); return }
        connection.current = active
        active.onFailure(() => { if (!abort.signal.aborted) invalidate() })
        const review = await active.initialize<RcCohortReview>()
        if (!abort.signal.aborted) { setLoaded({ url, review }); setStatus('verified') }
      } catch { if (!abort.signal.aborted) invalidate() }
    })()
    return () => { abort.abort(); connection.current = null; for (const href of links.current) URL.revokeObjectURL(href); links.current.clear() }
  }, [url, authorize, invalidate])
  async function download(path: string) {
    try {
      const blob = await connection.current!.call<Blob>('download', { path }), href = URL.createObjectURL(blob), anchor = document.createElement('a')
      links.current.add(href); anchor.href = href; anchor.download = path.replace(/\//g, '-'); document.body.append(anchor); anchor.click(); anchor.remove()
      setTimeout(() => { URL.revokeObjectURL(href); links.current.delete(href) }, 0)
    } catch { invalidate() }
  }
  const review = loaded?.url === url ? loaded.review : null
  if (!review) return <section className="wb2-panel" data-rc-cohort={status}><h2>Repeated strategy costs</h2><p role="status">{status === 'invalid' ? 'Unavailable — the original cohort could not be verified.' : 'Checking every original design, runtime record and paired cost…'}</p></section>
  const { cost, executions } = review, active = selected === null ? null : executions[selected]
  return <section className="wb2-panel" data-rc-cohort="verified" style={{ minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>
    <h2>Repeated strategy costs</h2>
    <p>{cost.pair_count} pairs retained · {cost.uncomparable_pair_count} incomparable selections. A time ratio requires verified selections on both sides and a learned estimate no higher than the price-order estimate.</p>
    <p data-rc-cohort-totals>Price CLI total: {seconds(cost.price_cli_interval_sum_ns)} s. Learned CLI total: {seconds(cost.learned_cli_interval_sum_ns)} s. Historical training counted once per artifact: {seconds(cost.historical_training_wall_ns_counted_once)} s. Learned plus historical / price: {ratio(cost.learned_plus_historical_over_price_ratio)}.</p>
    <p>These are sums of recorded CLI and historical training intervals, not campaign elapsed time. Startup/imports, runtime-sidecar writing, transport, this review and separate audits are excluded. Ratios do not establish learned speedup or independent physical validation.</p>
    <div className="wb2-table-scroll" role="region" aria-label="Paired strategy costs" tabIndex={0}><table className="wb2-table" style={{ minWidth: 800 }}><thead><tr><th>Pair</th><th>Price CLI (s)</th><th>Learned CLI (s)</th><th>Selection comparable</th><th>Learned / price</th></tr></thead><tbody>
      {cost.pairs.map((p: any, i: number) => <tr key={i} data-rc-cohort-pair={i}><td>{i + 1}</td><td>{seconds(p.price_cli_wall_ns)}</td><td>{seconds(p.learned_cli_wall_ns)}</td><td>{p.recorded_selection_comparable ? 'Yes' : 'No'}</td><td>{ratio(p.learned_over_price_cli_ratio)}</td></tr>)}
    </tbody></table></div>
    <div className="wb2-table-scroll" role="region" aria-label="Original cohort executions" tabIndex={0}><table className="wb2-table" style={{ minWidth: 800 }}><thead><tr><th>Pair</th><th>Strategy</th><th>Selected</th><th>Scoped estimate</th><th>Original records</th></tr></thead><tbody>
      {executions.map((e, i) => <tr key={e.reportPath} data-rc-cohort-execution={i}><td>{e.pair + 1}</td><td>{e.strategy === 'price_order' ? 'Price order' : 'Learned order'}</td><td>{e.selected ?? 'None'}</td><td>{e.estimate ?? 'Unavailable'}</td><td><button className="wb2-btn" onClick={() => setSelected(i)}>Review execution {i + 1}</button><button className="wb2-btn" onClick={() => { void download(e.runtimePath) }}>Download runtime {i + 1}</button></td></tr>)}
    </tbody></table></div>
    <button className="wb2-btn" onClick={() => { void download('cohort.json') }}>Download original cohort</button>
    {active && <RcControlSearchPanel key={active.reportHash} url={new URL(active.reportPath, new URL(url, location.href)).href} authorize={authorize} expectedReportHash={active.reportHash} onInvalid={invalidate} />}
  </section>
}
