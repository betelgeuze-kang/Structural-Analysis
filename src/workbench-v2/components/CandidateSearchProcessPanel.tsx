import { Fragment, type ReactElement } from 'react'
import type { CandidateProcessLoadResult } from '../model/candidateProcessProvider'
import type { CandidateProcessSlot } from '../model/candidateProcessSchema'
import { DesignComparisonPanel } from './DesignComparisonPanel'
import { EngineeringValueText } from './EngineeringValueText'

interface CandidateSearchProcessPanelProps {
  load: CandidateProcessLoadResult
  selectedSlot: CandidateProcessSlot | null
  onSelect: (key: string) => void
}

type Fields = Record<string, unknown>
const fields = (value: unknown): Fields => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Fields : {}
const rows = (value: unknown): Fields[] => Array.isArray(value) ? value.map(fields) : []
const unique = <T,>(values: T[]): T[] => [...new Set(values)]
const label = (value: string): string => ({ deterministic: 'Deterministic search', learned: 'Learned search', oracle: 'Full-pool audit', measured: 'Measured', warmup: 'Warmup' })[value] ?? value
const seconds = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value / 1e9 : null

function value(value: unknown, integer = false): ReactElement {
  return <EngineeringValueText value={typeof value === 'number' && Number.isFinite(value)
    ? { status: 'available', value } : { status: 'unavailable' }} integer={integer} />
}

function Metric({ name, metric, id, integer = false }: { name: string; metric: unknown; id: string; integer?: boolean }): ReactElement {
  return <Fragment><dt>{name}</dt><dd data-candidate-cost={id}>{value(metric, integer)}</dd></Fragment>
}

function download(bytes: Uint8Array, filename: string): void {
  const url = URL.createObjectURL(new Blob([bytes.slice()], { type: 'application/json' }))
  const anchor = document.createElement('a')
  try {
    anchor.href = url
    anchor.download = filename
    document.body.append(anchor)
    anchor.click()
  } finally {
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}

/** Selection changes the viewed slot; it never reruns a search or changes the retained costs. */
export function CandidateSearchProcessPanel({ load, selectedSlot, onSelect }: CandidateSearchProcessPanelProps): ReactElement {
  if (load.status !== 'verified' || !load.bundle) {
    return <section className="wb2-panel wb2-candidate-process" data-candidate-process={load.status} aria-labelledby="wb2-candidate-process-title">
      <h2 id="wb2-candidate-process-title" className="wb2-panel__title">Candidate search · process review</h2>
      <p className="wb2-unavailable" role="status">{load.status === 'loading' ? 'Loading candidate search review…' : `UNAVAILABLE — ${load.errors[0] ?? 'No candidate search review is configured.'}`}</p>
    </section>
  }
  const bundle = load.bundle
  const suite = fields(bundle.suite)
  const declaration = fields(suite.declaration)
  const costs = fields(suite.cost_accounting)
  const resources = fields(suite.resource_accounting)
  const phases = fields(costs.phases)
  const training = fields(costs.training_artifacts_charged_once)
  const declaredCases = rows(declaration.cases)
  const onlineSlots = bundle.slots.filter((entry) => entry.strategy !== 'oracle')
  const budgets = onlineSlots.map((entry) => fields(declaredCases.find((candidate) => candidate.case_id === entry.caseId)?.input_binding).full_analysis_budget)
  const onlineBudget = budgets.every((entry) => typeof entry === 'number' && Number.isSafeInteger(entry))
    ? (budgets as number[]).reduce((sum, entry) => sum + entry, 0) : null
  const baselineCounts = onlineSlots.filter((entry) => entry.run.report_contract_pass === true)
    .map((entry) => fields(fields(fields(entry.run.report).arm).cost_accounting).baseline_analysis_request_count)
  const knownBaselineRequests = baselineCounts.every((entry) => typeof entry === 'number' && Number.isSafeInteger(entry))
    ? (baselineCounts as number[]).reduce((sum, entry) => sum + entry, 0) : null
  const slot = selectedSlot
  const run = fields(slot?.run)
  const report = run.report_contract_pass === true ? fields(run.report) : {}
  const observed = run.resource_contract_pass === true ? fields(run.resources) : {}
  const arm = fields(report.arm)
  const armCost = slot?.strategy === 'oracle' ? fields(report.cost_accounting) : fields(arm.cost_accounting)
  const declaredCase = rows(declaration.cases).find((entry) => entry.case_id === slot?.caseId)
  const binding = fields(declaredCase?.input_binding)
  const winner = fields(arm.final_selection)
  const selectedFailure = fields(run.failure)
  const failureDetails = Object.values(selectedFailure).filter((entry): entry is string => typeof entry === 'string' && entry.length > 0)

  function select(part: 'caseId' | 'phase' | 'repetition' | 'strategy', chosen: string): void {
    if (!slot) return
    const proposed = { caseId: slot.caseId, phase: slot.phase, repetition: slot.repetition, strategy: slot.strategy, [part]: part === 'repetition' ? Number(chosen) : chosen }
    const dimensions = ['caseId', 'phase', 'repetition', 'strategy'] as const
    const through = dimensions.indexOf(part)
    const eligible = bundle.slots.filter((candidate) => dimensions.slice(0, through + 1).every((key) => candidate[key] === proposed[key]))
    const next = eligible.find((candidate) => dimensions.every((key) => candidate[key] === proposed[key])) ?? eligible[0]
    if (next) onSelect(next.key)
  }

  return <section className="wb2-panel wb2-candidate-process" data-candidate-process="verified" aria-labelledby="wb2-candidate-process-title">
    <h2 id="wb2-candidate-process-title" className="wb2-panel__title">Candidate search · process review</h2>
    <p className="wb2-note">Stored bundle integrity verified. Search outcome: <strong data-candidate-suite-status>{String(suite.status)}</strong>. Each attempt uses a fresh worker. This review does not run a solver or grant engineering approval.</p>
    <p className="wb2-note">Source <code className="wb2-mono" data-candidate-source>{String(declaration.source_revision)}</code> · suite <code className="wb2-mono">{String(suite.report_hash)}</code></p>

    <h3>Whole search costs</h3>
    <p className="wb2-note">Historical data generation and fitting are charged once per distinct training artifact and were not rerun by this search. Warmups and full-pool audits remain in the totals. Material estimates appear separately in the physical comparison.</p>
    <dl className="wb2-kv">
      <Metric name="Training artifacts charged once" metric={costs.training_artifacts_charged_once !== null && typeof costs.training_artifacts_charged_once === 'object' ? Object.keys(training).length : null} id="training-artifacts" integer />
      <Metric name="Historical data generation (s)" metric={seconds(costs.historical_data_generation_wall_ns)} id="historical-generation" />
      <Metric name="Historical fitting (s)" metric={seconds(costs.historical_training_wall_ns)} id="historical-training" />
      <Metric name="Historical analysis requests" metric={costs.historical_training_analysis_request_count} id="historical-requests" integer />
      <Metric name="Declared online request budget across all phases" metric={onlineBudget} id="online-budget" integer />
      <Metric name="Known online baseline requests" metric={knownBaselineRequests} id="online-baseline-requests" integer />
      <Metric name="Current analysis requests" metric={costs.current_analysis_request_count} id="current-requests" integer />
      <Metric name="Total requests including training and audits" metric={costs.total_analysis_request_count_including_training_warmups_and_oracles} id="total-requests" integer />
      <Metric name="Current elapsed time through aggregation (s)" metric={seconds(costs.current_parent_wall_ns_through_aggregation)} id="current-wall" />
      <Metric name="Accounted time including historical training (s)" metric={seconds(costs.accounted_wall_ns_including_historical_generation_and_fit)} id="accounted-wall" />
      <Metric name="Current coordinator + workers CPU (s)" metric={seconds(resources.current_parent_plus_workers_cpu_time_ns)} id="total-cpu" />
      <Metric name="Coordinator CPU (s)" metric={seconds(resources.parent_cpu_time_ns)} id="parent-cpu" />
      <Metric name="Preflight CPU, included in coordinator CPU (s)" metric={seconds(resources.parent_preflight_cpu_ns)} id="preflight-cpu" />
      <Metric name="Known worker CPU subtotal (s)" metric={seconds(resources.worker_cpu_process_time_ns_subtotal)} id="known-worker-cpu" />
      <Metric name="Workers with verified resources" metric={resources.validated_resource_worker_count} id="observed-workers" integer />
      <Metric name="Declared attempts" metric={bundle.slots.length} id="declared-slots" integer />
    </dl>
    <div className="wb2-table-scroll" role="region" aria-label="Measured and warmup accounting" tabIndex={0}>
      <table className="wb2-table"><thead><tr><th scope="col">Phase</th><th scope="col">Slots / attempted</th><th scope="col">Online requests</th><th scope="col">Audit requests</th><th scope="col">Requests total</th><th scope="col">Unknown request slots</th><th scope="col">Not launched</th><th scope="col">Known / unknown solver executions</th></tr></thead>
        <tbody>{['measured', 'warmup'].map((phase) => { const row = fields(phases[phase]); return <tr key={phase} data-candidate-phase-cost={phase}>
          <th scope="row">{label(phase)}</th><td>{value(row.declared_worker_slots, true)} / {value(row.attempted_worker_slots, true)}</td>
          <td>{value(row.validated_online_request_subtotal, true)}</td><td>{value(row.validated_oracle_request_subtotal, true)}</td><td>{value(row.total_analysis_request_count, true)}</td>
          <td>{value(row.unknown_request_slots, true)}</td><td>{value(row.not_launched_slots, true)}</td><td>{value(row.known_solver_execution_subtotal, true)} / {value(row.unknown_solver_execution_subtotal, true)}</td>
        </tr> })}</tbody></table>
    </div>
    <p className="wb2-note">The declared online budget includes every planned online slot, including warmups and attempts not launched. It is a budget, not completed work. A request is not proof that a solver executed. Unknown totals stay unavailable; verified subtotals remain visible. Coordinator time includes waiting for workers, so elapsed intervals are not added together. Historical CPU is unavailable.</p>
    <details><summary>Training artifact identities</summary><ul>{Object.keys(training).map((hash) => <li key={hash} className="wb2-mono">{hash}</li>)}</ul></details>
    <details><summary>Resources across all attempts</summary>
      <div className="wb2-table-scroll" role="region" aria-label="Resources by strategy and phase" tabIndex={0}>
        <table className="wb2-table"><thead><tr><th scope="col">Strategy / phase</th><th scope="col">Observed / declared</th><th scope="col">Median worker CPU (s)</th><th scope="col">Median launch-to-exit (s)</th><th scope="col">Separate worker peaks, min–max (bytes)</th><th scope="col">Input / report bytes</th></tr></thead>
          <tbody>{['deterministic', 'learned', 'oracle'].flatMap((strategy) => ['measured', 'warmup'].map((phase) => {
            const row = fields(fields(fields(resources.workers_by_strategy)[strategy])[phase])
            const peaks = fields(row.peak_memory_bytes)
            return <tr key={`${strategy}-${phase}`}><th scope="row">{label(strategy)} · {label(phase)}</th><td>{value(row.observed_workers, true)} / {value(row.declared_slots, true)}</td>
              <td>{value(seconds(fields(row.worker_cpu_process_time_ns).median))}</td><td>{value(seconds(fields(row.launch_to_exit_wall_ns).median))}</td>
              <td>{value(peaks.minimum, true)}–{value(peaks.maximum, true)}</td><td>{value(row.input_bytes_read, true)} / {value(row.report_bytes_written, true)}</td></tr>
          }))}</tbody></table>
      </div>
      <p className="wb2-note">These summaries include only workers with verified resources. Missing workers remain in the declared counts. Each memory value is a separate process high-water mark.</p>
    </details>
    <details data-candidate-paired-outcomes><summary>Paired outcomes and audit quality</summary>
      <p className="wb2-note">Differences are deterministic minus learned for matched measured repetitions. A positive elapsed-time difference favors learned search within this case. The comparison includes launch and per-attempt coordinator work, excluding shared preflight, final aggregation and historical training. Projected reuse counts are conditional calculations, not observed break-even runs.</p>
      {rows(suite.case_summaries).map((summary) => <div key={String(summary.case_id)} data-candidate-case-summary={String(summary.case_id)}>
        <h4>{String(summary.case_id)}</h4>
        <dl className="wb2-kv">
          <Metric name="Median paired elapsed-time difference (s)" metric={seconds(fields(summary.paired_deterministic_minus_learned_slot_wall_ns).median)} id={`paired-wall-${summary.case_id}`} />
          <Metric name="Median paired worker CPU difference (s)" metric={seconds(fields(summary.paired_deterministic_minus_learned_worker_cpu_ns).median)} id={`paired-cpu-${summary.case_id}`} />
          <Metric name="Projected reuses to cover this training cost" metric={summary.projected_reuses_to_amortize_this_training_artifact} id={`projected-reuses-${summary.case_id}`} integer />
        </dl>
        <div className="wb2-table-scroll" role="region" aria-label={`Audit outcomes for ${summary.case_id}`} tabIndex={0}>
          <table className="wb2-table"><thead><tr><th scope="col">Repetition / strategy</th><th scope="col">Paired elapsed difference (s)</th><th scope="col">Selected candidate</th><th scope="col">Learned scoped estimate no higher</th><th scope="col">Missed feasible candidates</th><th scope="col">Predicted terminal safe, actually failed</th><th scope="col">Predicted safe but unverifiable</th><th scope="col">Oracle verified / unverifiable</th><th scope="col">Terminal + history verified / unverifiable</th></tr></thead>
            <tbody>{rows(summary.measured_pairs).flatMap((pair) => ['deterministic', 'learned'].map((strategy) => {
              const audit = fields(fields(pair.oracle_audit)[strategy])
              const selected = fields(pair.selected_candidate_ids)[strategy]
              return <tr key={`${pair.repetition}-${strategy}`}><th scope="row">{typeof pair.repetition === 'number' ? pair.repetition + 1 : 'UNAVAILABLE'} · {label(strategy)}</th>
                <td data-candidate-pair-wall={`${summary.case_id}:${pair.repetition}:${strategy}`}>{value(seconds(pair.deterministic_minus_learned_slot_wall_ns))}</td><td>{typeof selected === 'string' ? selected : 'UNAVAILABLE'}</td><td>{pair.learned_verified_scoped_material_cost_not_worse === true ? 'Yes' : 'Not established'}</td>
                <td>{value(audit.missed_feasible_count, true)}</td><td>{strategy === 'deterministic' ? 'Not applicable' : value(audit.false_safe_count, true)}</td><td>{strategy === 'deterministic' ? 'Not applicable' : value(audit.predicted_safe_unverifiable_count, true)}</td>
                <td>{value(audit.oracle_verified_candidate_count, true)} / {value(audit.oracle_unverifiable_candidate_count, true)}</td><td>{value(audit.oracle_combined_verified_candidate_count, true)} / {value(audit.oracle_combined_unverifiable_candidate_count, true)}</td></tr>
            }))}</tbody></table>
        </div>
      </div>)}
      <p className="wb2-note">Audit counts exclude the baseline and retain unverifiable candidates. Missed feasibility includes committed-history limits when requested. Predicted safety is terminal-only; deterministic search makes no predicted-safety claim. The audit does not establish independent generalization.</p>
    </details>

    {slot ? <>
      <h3>Inspect an attempt</h3>
      <div className="wb2-candidate-selectors">
        <label>Search case<select value={slot.caseId} onChange={(event) => select('caseId', event.target.value)}>{unique(bundle.slots.map((entry) => entry.caseId)).map((entry) => <option key={entry} value={entry}>{entry}</option>)}</select></label>
        <label>Phase<select value={slot.phase} onChange={(event) => select('phase', event.target.value)}>{unique(bundle.slots.filter((entry) => entry.caseId === slot.caseId).map((entry) => entry.phase)).map((entry) => <option key={entry} value={entry}>{label(entry)}</option>)}</select></label>
        <label>Repetition<select value={slot.repetition} onChange={(event) => select('repetition', event.target.value)}>{unique(bundle.slots.filter((entry) => entry.caseId === slot.caseId && entry.phase === slot.phase).map((entry) => entry.repetition)).map((entry) => <option key={entry} value={entry}>{entry + 1}</option>)}</select></label>
        <label>Search strategy<select value={slot.strategy} onChange={(event) => select('strategy', event.target.value)}>{bundle.slots.filter((entry) => entry.caseId === slot.caseId && entry.phase === slot.phase && entry.repetition === slot.repetition).map((entry) => <option key={entry.key} value={entry.strategy}>{label(entry.strategy)}{entry.run.attempted ? '' : ' · not launched'}</option>)}</select></label>
      </div>
      <p className="wb2-note" aria-live="polite" data-candidate-selected-slot={slot.key}>{slot.caseId} · {label(slot.phase)} · repetition {slot.repetition + 1} · {label(slot.strategy)}</p>
      <dl className="wb2-kv" data-candidate-attempt-status>
        <dt>Worker launch</dt><dd>{run.attempted === true ? 'Attempted' : 'Not launched'}</dd>
        <dt>Search report contract</dt><dd>{run.report_contract_pass === true ? 'Verified' : 'UNAVAILABLE'}</dd>
        <dt>Resource contract</dt><dd>{run.resource_contract_pass === true ? 'Verified' : 'UNAVAILABLE'}</dd>
        <dt>Physical selection</dt><dd data-candidate-physical-status>{slot.strategy === 'oracle' ? 'Audit only; not an online selection' : typeof winner.candidate_id === 'string' ? `${winner.candidate_id} · ${String(report.status)}` : 'UNAVAILABLE'}</dd>
        <Metric name={slot.strategy === 'oracle' ? 'Online budget (not applied to audit)' : 'Full-analysis budget including baseline'} metric={slot.strategy === 'oracle' ? null : binding.full_analysis_budget} id="arm-budget" integer />
        <Metric name="Baseline requests" metric={armCost.baseline_analysis_request_count} id="baseline-requests" integer />
        <Metric name="Candidate requests" metric={armCost.candidate_analysis_request_count} id="candidate-requests" integer />
        <Metric name="Total requests in this attempt" metric={armCost.total_analysis_request_count} id="arm-requests" integer />
        <Metric name="Known solver executions" metric={armCost.known_solver_execution_count} id="known-executions" integer />
        <Metric name="Unknown solver executions" metric={armCost.unknown_solver_execution_count} id="unknown-executions" integer />
        <Metric name="Worker CPU (s)" metric={seconds(observed.cpu_process_time_ns)} id="worker-cpu" />
        <Metric name="Worker peak RSS (bytes)" metric={observed.peak_memory_bytes} id="worker-rss" integer />
        <Metric name="Attempt elapsed time including coordinator (s)" metric={seconds(run.parent_slot_observed_wall_ns)} id="slot-wall" />
        <Metric name="Coordinator CPU for this attempt (s)" metric={seconds(run.parent_slot_cpu_time_ns)} id="slot-cpu" />
        <Metric name="Input bytes read" metric={observed.input_bytes_read} id="input-bytes" integer />
        <Metric name="Input file read time (s)" metric={seconds(observed.input_read_wall_ns)} id="input-wall" />
        <Metric name="Search report bytes written" metric={observed.report_bytes_written} id="output-bytes" integer />
        <Metric name="Report encoding time (s)" metric={seconds(observed.report_encode_wall_ns)} id="encode-wall" />
        <Metric name="Report write + flush + sync time (s)" metric={seconds(observed.report_write_flush_fsync_wall_ns)} id="output-wall" />
      </dl>
      <p className="wb2-note">The baseline consumes one online budget slot. Audit labels are obtained after both online arms and do not guide their selection. Peak RSS belongs to this worker alone, including imports and verification; peaks are never summed or subtracted. File I/O covers worker input reads and the search report, excluding sidecars, manifests and coordinator persistence.</p>
      {failureDetails.length ? <details data-candidate-attempt-failure><summary>Attempt details</summary>{unique(failureDetails).map((detail) => <p className="wb2-note" key={detail}>{detail.replace(/_/g, ' ')}</p>)}</details> : null}
      {slot.comparison ? <DesignComparisonPanel title="Selected candidate comparison" titleId="wb2-candidate-selected-comparison-title" load={{ status: 'verified', bundle: slot.comparison, errors: [] }} />
        : <p className="wb2-unavailable" data-candidate-comparison-unavailable>{slot.strategy === 'oracle' ? 'The full-pool audit has no attached online comparison.' : 'A verified physical comparison is unavailable for this attempt.'}</p>}
    </> : <p className="wb2-unavailable">No attempt is available to inspect.</p>}

    <div className="wb2-actions" aria-label="Candidate search artifact downloads">
      <button type="button" className="wb2-btn" onClick={() => download(bundle.manifestBytes, 'candidate-process-manifest.json')}>Download review manifest</button>
      <button type="button" className="wb2-btn" onClick={() => download(bundle.suiteBytes, 'candidate-process-suite.json')}>Download whole search JSON</button>
      {slot?.comparison && slot.comparisonManifestBytes && slot.comparisonReportBytes ? <>
        <button type="button" className="wb2-btn" onClick={() => download(slot.comparisonManifestBytes!, 'selected-comparison-manifest.json')}>Download selected comparison manifest</button>
        <button type="button" className="wb2-btn" onClick={() => download(slot.comparisonReportBytes!, 'selected-comparison.json')}>Download selected comparison JSON</button>
      </> : null}
    </div>
    <p className="wb2-note">Downloads preserve the verified original bytes. Selection changes only the displayed attempt and its comparison downloads. Stored integrity and local timing do not establish independent validation, general speedup or confirmed construction savings.</p>
  </section>
}
