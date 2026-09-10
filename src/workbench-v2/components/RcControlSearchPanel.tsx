import { useEffect, useRef, useState, type ReactElement } from 'react'
import { loadRcControlSearch, type RcSearchSession } from '../model/rcControlSearchProvider'
import { RC_SEARCH_ARMS, searchWork } from '../model/rcControlSearchSchema'
import type { JobAuthorizationProvider } from '../model/jobTransport'
import type { RcObject } from '../model/rcJobSchema'
import { RcControlDesignReviewPanel } from './RcControlDesignPanel'

const label = (name: string) => ({ price_order: 'Price order', learned_order: 'Learned order', exhaustive_oracle: 'Later exhaustive check' })[name] ?? name
const shown = (value: unknown) => typeof value === 'number' ? String(value) : 'Unavailable'
export function RcControlSearchPanel({ url, authorize }: { url: string; authorize?: JobAuthorizationProvider }): ReactElement {
  const [loaded, setLoaded] = useState<{ url: string; session: RcSearchSession } | null>(null)
  const [status, setStatus] = useState('loading')
  const [arm, setArm] = useState('price_order')
  const urls = useRef(new Set<string>())
  const session = loaded?.url === url ? loaded.session : null
  const invalidate = () => { setLoaded(null); setStatus('invalid') }
  useEffect(() => {
    const controller = new AbortController()
    let value: RcSearchSession | null = null
    setLoaded(null); setStatus('loading'); setArm('price_order')
    loadRcControlSearch(url, controller.signal, authorize).then(result => {
      value = result
      if (controller.signal.aborted) { result.dispose(); return }
      result.onFailure(() => { if (!controller.signal.aborted) { setLoaded(null); setStatus('invalid') } })
      setLoaded({ url, session: result }); setStatus('verified')
    }).catch(() => { if (!controller.signal.aborted) setStatus('invalid') })
    return () => { controller.abort(); value?.dispose(); for (const href of urls.current) URL.revokeObjectURL(href); urls.current.clear() }
  }, [url, authorize])
  async function download(role: 'result' | 'plan' | 'policy' | 'historical-training') {
    try {
      const blob = await session!.download(role), href = URL.createObjectURL(blob), anchor = document.createElement('a')
      urls.current.add(href); anchor.href = href; anchor.download = `rc-search-${role}.json`
      document.body.append(anchor); anchor.click(); anchor.remove()
      window.setTimeout(() => { URL.revokeObjectURL(href); urls.current.delete(href) }, 0)
    } catch { invalidate() }
  }
  if (!session) return <section className="wb2-panel" data-rc-search={status}><h2>RC candidate search</h2><p role="status">{status === 'invalid' ? 'Unavailable — the original search records could not be verified.' : 'Checking candidate models, full-path results and search accounting…'}</p></section>
  const { report, plan, costOptimality: cost } = session, audit = report.candidate_coverage_audit, training = report.historical_training_cost
  const names = [...RC_SEARCH_ARMS, ...(report.oracle ? ['exhaustive_oracle'] : [])]
  const trainingWork = searchWork([{ invocations: training.label_invocations }])
  return <section className="wb2-panel" data-rc-search="verified" style={{ minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>
    <h2>RC candidate search</h2>
    <p>{plan.pool.length - 1} alternatives · up to {plan.full_analysis_budget_per_arm} full analyses per online strategy, including its own baseline. Each analyzed model also has a fresh verification run.</p>
    <p data-rc-search-authority>Candidate models, quantities, declared prices and stored result bindings checked. Predictions remain estimates; passing caller limits is not design approval. This review does not establish independent physical validation, learned speedup or confirmed monetary savings.</p>
    <div className="wb2-table-scroll" role="region" aria-label="RC search strategies" tabIndex={0}><table className="wb2-table" style={{ minWidth: 900, overflowWrap: 'normal' }}><thead><tr><th>Strategy</th><th>Analyzed models</th><th>Selected candidate</th><th>Scoped estimate</th><th>Core calls</th><th>Newton / linear</th><th>Elapsed / CPU (s)</th><th>Review</th></tr></thead><tbody>
      {names.map(name => { const r = name === 'exhaustive_oracle' ? report.oracle : report.arms[name], work = r.execution_work.known_counters
        return <tr key={name} data-rc-search-arm={name}><td>{label(name)}</td><td>{r.request_count}</td><td>{r.selected_candidate_id ?? 'None'}</td><td>{shown(r.selected_estimate)} {session.designs[name].report.prices.currency}</td><td>{work.attempted_step_count}</td><td>{work.known_newton_iteration_count} / {work.known_linear_solve_count}</td><td>{(r.wall_ns / 1e9).toFixed(3)} / {(r.cpu_ns / 1e9).toFixed(3)}</td><td><button className="wb2-btn" type="button" style={{ whiteSpace: 'nowrap', minWidth: 120 }} aria-pressed={arm === name} onClick={() => setArm(name)}>Review {label(name)}</button></td></tr>
      })}
    </tbody></table></div>
    <p data-rc-search-training>Historical training, counted once: {training.sample_count} labels · {trainingWork.known_counters.attempted_step_count} core calls · {training.wall_ns / 1e9} s including label generation and fitting. Fit: {training.fit.wall_ns / 1e9} s. These original cost declarations are hash-bound; this review does not replay the historical training artifacts or refit the policy.</p>
    <p>Current search including preparation, ranking, both online strategies and the optional later exhaustive check: {report.online_and_optional_oracle_wall_ns / 1e9} s elapsed, {report.online_and_optional_oracle_cpu_ns / 1e9} s CPU. Ranking: {report.ranking_wall_ns / 1e9} s. These totals exclude final report writing. The exhaustive check is separate evaluation cost.</p>
    <div className="wb2-table-scroll" role="region" aria-label="RC candidate coverage" tabIndex={0}><table className="wb2-table" style={{ minWidth: 900, overflowWrap: 'normal' }}><thead><tr><th>Alternative</th><th>Recorded prediction</th><th>Price shortlist</th><th>Learned shortlist</th><th>Later exhaustive result</th></tr></thead><tbody>
      {audit.candidates.map((r: RcObject) => <tr key={r.candidate_id} data-rc-search-candidate={r.candidate_id}><td>{r.candidate_id}</td><td>{r.predicted_all_requested_limits_pass === null ? 'Abstained' : r.predicted_all_requested_limits_pass ? 'Predicted pass' : 'Predicted limit failure'}</td><td>{r.shortlisted_by.includes('price_order') ? 'Requested' : 'Not requested'}</td><td>{r.shortlisted_by.includes('learned_order') ? 'Requested' : 'Not requested'}</td><td>{r.oracle_all_requested_limits_pass === null ? report.oracle ? 'Unverifiable' : 'Not run' : r.oracle_all_requested_limits_pass ? 'Verified limits pass' : 'Verified limit failure'}</td></tr>)}
    </tbody></table></div>
    <div className="wb2-table-scroll" role="region" aria-label="RC prediction errors" tabIndex={0}><table className="wb2-table" style={{ minWidth: 900, overflowWrap: 'normal' }}><thead><tr><th>Strategy</th><th>Feasible but not requested</th><th>Predicted pass, verified failure</th><th>Predicted pass, unverifiable</th><th>Predicted failure, verified pass</th></tr></thead><tbody>
      {RC_SEARCH_ARMS.map(name => { const a = audit.arms[name]; return <tr key={name}><td>{label(name)}</td><td>{shown(a.missed_feasible_count)}</td>{['false_safe_count', 'predicted_safe_unverifiable_count', 'false_negative_count'].map(k => <td key={k}>{name === 'price_order' ? 'Not applicable' : shown(a[k])}</td>)}</tr> })}
    </tbody></table></div>
    <p>Counts cover alternatives, excluding the baseline. Unavailable counts do not mean zero. Feasible but unrequested candidates may cost more than the selected design. The exhaustive check uses the same reference solver.</p>
    <h3>Cost within this candidate pool</h3>
    <p data-rc-search-pool-minimum>{cost.status === 'complete'
      ? `Lowest verified feasible estimate: ${cost.pool_minimum_feasible_estimate} ${cost.currency} · ${cost.pool_minimum_feasible_candidate_ids.join(', ')}`
      : cost.status === 'oracle_not_run' ? 'Pool minimum unavailable: the exhaustive check was not run.'
      : cost.status === 'oracle_incomplete' ? `Pool minimum unavailable: ${cost.oracle_unverifiable_candidate_ids.join(', ')} could not be verified.`
      : 'Pool minimum unavailable: no candidate passed every requested limit.'}</p>
    <div className="wb2-table-scroll" role="region" aria-label="RC candidate pool cost" tabIndex={0}><table className="wb2-table" style={{ minWidth: 700, overflowWrap: 'normal' }}><thead><tr><th>Strategy</th><th>Estimate above pool minimum ({cost.currency})</th><th>Matches pool minimum</th><th>Cheaper feasible alternatives not requested</th></tr></thead><tbody>
      {RC_SEARCH_ARMS.map(name => { const a = cost.arms[name]; return <tr key={name} data-rc-search-cost={name}><td>{label(name)}</td><td>{shown(a.selected_minus_pool_minimum_estimate)}</td><td>{a.matches_pool_minimum === null ? 'Unavailable' : a.matches_pool_minimum ? 'Yes' : 'No'}</td><td>{a.missed_cheaper_feasible_candidate_ids === null ? 'Unavailable' : `${a.missed_cheaper_feasible_count}${a.missed_cheaper_feasible_count ? `: ${a.missed_cheaper_feasible_candidate_ids.join(', ')}` : ''}`}</td></tr> })}
    </tbody></table></div>
    <p>Recomputed from verified design records using one price table and material scope. The baseline is included. A minimum requires every candidate to be verified; unknown values do not mean zero. This finite-pool comparison does not establish a global design optimum or quoted monetary savings.</p>
    <div>{(['result', 'plan', 'policy', 'historical-training'] as const).map(role => <button className="wb2-btn" type="button" key={role} onClick={() => { void download(role) }}>Download search {role}</button>)}</div>
    <h3>{label(arm)}: verified design records</h3>
    <RcControlDesignReviewPanel key={`${report.report_hash}:${arm}`} session={session.designSession(arm)} onInvalid={invalidate} />
  </section>
}
