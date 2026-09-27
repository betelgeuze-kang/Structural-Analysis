import { canonicalJson } from './checksum'
import { DESIGN_SCOPE } from './designComparisonSchema'
import { candidateProcessSlotKey, type CandidateObject, type CandidateProcessCostSidecar, type CandidateProcessManifest, type CandidateProcessSlot, type CandidateProcessSuite } from './candidateProcessSchema'

type Row = CandidateObject
type ArmName = 'deterministic' | 'learned'
const HASH = /^sha256:[0-9a-f]{64}$/
const PHASES = ['warmup', 'measured'] as const
const ARMS = ['deterministic', 'learned'] as const
const MISSED_DEFINITION = 'oracle_verified_feasible_cheaper_than_selected_outside_planned_shortlist'
const UNREQUESTED_DEFINITION = 'oracle_verified_feasible_cheaper_than_selected_outside_attempted_candidate_prefix'

function ensure(ok: unknown, reason: string): asserts ok { if (!ok) throw new Error(`candidate_process_cost_${reason}`) }
function row(value: unknown): Row { ensure(value !== null && typeof value === 'object' && !Array.isArray(value), 'object_required'); return value as Row }
function exact(value: unknown, fields: string[]): Row { const result = row(value); same(Object.keys(result).sort(), fields.sort()); return result }
function list(value: unknown, max = 32768): unknown[] { ensure(Array.isArray(value) && value.length <= max, 'bounded_array_required'); return value }
function same(actual: unknown, expected: unknown): void { ensure(canonicalJson(actual) === canonicalJson(expected), 'source_or_arithmetic_mismatch') }
function equal(actual: unknown, expected: unknown): void { ensure(actual === expected, 'source_or_arithmetic_mismatch') }
function string(value: unknown): string { ensure(typeof value === 'string' && value.length > 0 && value.length <= 4096, 'string_required'); return value }
function hash(value: unknown): string { const result = string(value); ensure(HASH.test(result), 'hash_required'); return result }
function number(value: unknown): number { ensure(typeof value === 'number' && Number.isFinite(value) && value >= 0, 'nonnegative_number_required'); return value }
function natural(value: unknown): number { const result = number(value); ensure(Number.isSafeInteger(result), 'natural_required'); return result }
function ids(value: unknown): string[] { const result = list(value, 65).map(item => string(row(item).candidate_id)); ensure(result.length === new Set(result).size, 'duplicate_candidate'); return result }
function selection(rowValue: Row): boolean | null {
  if (rowValue.analysis_requested !== true) return null
  const checks: [string, string][] = [['full_reference_verification_pass', 'terminal_limit_status']]
  if (rowValue.full_history_requested === true) checks.push(['full_history_verification_pass', 'history_limit_status'])
  if (rowValue.full_material_history_requested === true) checks.push(['full_material_history_verification_pass', 'material_history_limit_status'])
  if (checks.some(([verification, status]) => rowValue[verification] !== true || !['pass', 'fail'].includes(String(rowValue[status])))) return null
  return checks.every(([, status]) => rowValue[status] === 'pass')
}

/** Recompute every publishable finite-pool cost value from the already validated worker rows. */
function recomputeGroupAudit(declared: Row, online: Record<ArmName, CandidateProcessSlot>, oracle: CandidateProcessSlot | undefined, oracleEnabled: boolean): Row {
  const input = row(declared.input_binding)
  const basis = exact(input.price_basis, ['concrete_per_m3', 'rebar_per_kg', 'currency', 'as_of', 'source', 'price_table_hash'])
  number(basis.concrete_per_m3); number(basis.rebar_per_kg)
  const currency = string(basis.currency); const priceHash = hash(basis.price_table_hash)
  const pool = list(row(row(declared.plans).learned).candidate_pool, 64).map(row)
  const poolIds = ids(pool); ensure(poolIds.length > 0 && !poolIds.includes('baseline'), 'pool_denominator')
  const history = input.history_limits !== undefined
  const material = input.material_history_limits !== undefined
  const stopping = input.stop_mode === 'first_verified_feasible'
  const totals = new Map<string, number>()
  const remember = (id: string, value: unknown): number => {
    const amount = number(value); const previous = totals.get(id)
    ensure(previous === undefined || previous === amount, 'estimate_disagreement')
    totals.set(id, amount); return amount
  }
  const estimate = (outcome: Row): number | null => {
    if (outcome.material_estimate === null || outcome.material_estimate === undefined) return null
    const value = row(outcome.material_estimate)
    equal(value.price_table_hash, priceHash); equal(value.currency, currency); equal(value.scope, DESIGN_SCOPE)
    return remember(string(outcome.candidate_id), value.total)
  }
  for (const candidate of pool) {
    const id = string(candidate.candidate_id)
    if (candidate.preanalysis_material_estimate !== null && candidate.preanalysis_material_estimate !== undefined) remember(id, candidate.preanalysis_material_estimate)
    else ensure(candidate.screening_status !== 'ready', 'ready_estimate_missing')
  }

  const armState = {} as Record<ArmName, { shortlist: string[]; attempted: string[]; selectedId: string | null; selectedEstimate: number | null }>
  const withScope = (outcome: Row): Row => ({ ...outcome, full_history_requested: history, full_material_history_requested: material })
  for (const name of ARMS) {
    const report = row(online[name].run.report)
    const arm = row(report.arm)
    const shortlist = list(arm.shortlist, 64).map(string)
    ensure(shortlist.length === new Set(shortlist).size && shortlist.every(id => poolIds.includes(id)), 'shortlist_coverage')
    const attempted = stopping ? list(row(arm.execution).attempted_candidate_ids, 64).map(string) : shortlist
    same(attempted, shortlist.slice(0, attempted.length))
    const baseline = row(arm.baseline)
    equal(baseline.candidate_id, 'baseline'); equal(baseline.analysis_requested, true)
    estimate(baseline)
    const outcomes = list(arm.candidate_outcomes, 64).map(row)
    same(ids(outcomes), poolIds)
    for (const outcome of outcomes) { equal(outcome.analysis_requested, attempted.includes(string(outcome.candidate_id))); estimate(outcome) }
    const byId = new Map(outcomes.map(outcome => [string(outcome.candidate_id), outcome]))
    const requested = [baseline, ...attempted.map(id => byId.get(id)!)]
    const eligible = requested.filter(outcome => selection(withScope(outcome)) === true && outcome.material_estimate !== null && outcome.material_estimate !== undefined)
    const expected = selection(withScope(baseline)) === null || eligible.length === 0 ? null : stopping ? eligible[0] : [...eligible].sort((a, b) => {
      const difference = totals.get(string(a.candidate_id))! - totals.get(string(b.candidate_id))!
      return difference || (string(a.candidate_id) < string(b.candidate_id) ? -1 : string(a.candidate_id) > string(b.candidate_id) ? 1 : 0)
    })[0]
    same(arm.final_selection, expected)
    const selectedId = expected === null ? null : string(expected.candidate_id)
    armState[name] = { shortlist, attempted, selectedId, selectedEstimate: selectedId === null ? null : totals.get(selectedId)! }
  }

  let status: string
  let unknown: string[] | null = null
  let minimum: number | null = null
  let winners: string[] | null = null
  const oracleOutcomes = new Map<string, boolean | null>()
  if (!oracleEnabled) status = 'oracle_not_run'
  else if (!oracle || oracle.run.report_contract_pass !== true) status = 'oracle_unavailable'
  else {
    const rows = list(row(oracle.run.report).rows, 65).map(row)
    same(ids(rows), ['baseline', ...poolIds])
    for (const outcome of rows) estimate(outcome)
    for (const outcome of rows) oracleOutcomes.set(string(outcome.candidate_id), selection(withScope(outcome)))
    unknown = rows.filter(outcome => {
      const result = oracleOutcomes.get(string(outcome.candidate_id))
      return result === null || (result === true && (outcome.material_estimate === null || outcome.material_estimate === undefined))
    }).map(outcome => string(outcome.candidate_id))
    const feasible = rows.filter(outcome => oracleOutcomes.get(string(outcome.candidate_id)) === true).map(outcome => string(outcome.candidate_id))
    status = unknown.length ? 'oracle_incomplete' : feasible.length ? 'complete' : 'no_feasible_candidate'
    if (status === 'complete') {
      minimum = Math.min(...feasible.map(id => totals.get(id)!))
      winners = feasible.filter(id => totals.get(id) === minimum).sort()
    }
  }

  const arms = {} as Record<ArmName, Row>
  for (const name of ARMS) {
    const { shortlist, attempted, selectedId, selectedEstimate } = armState[name]
    const armStatus = status !== 'complete' ? status : selectedId === null ? 'no_verified_selection' : oracleOutcomes.get(selectedId) !== true ? 'selection_not_confirmed_by_oracle' : 'compared'
    const gap = armStatus === 'compared' ? selectedEstimate! - minimum! : null
    ensure(gap === null || gap >= 0, 'selected_below_pool_minimum')
    const cheaper = (excluded: string[]): string[] | null => armStatus === 'compared'
      ? poolIds.filter(id => !excluded.includes(id) && oracleOutcomes.get(id) === true && totals.get(id)! < selectedEstimate!) : null
    const missed = cheaper(shortlist); const unrequested = cheaper(attempted)
    arms[name] = {
      status: armStatus, selected_candidate_id: selectedId, selected_estimate: selectedEstimate,
      selected_minus_pool_minimum_estimate: gap, matches_pool_minimum: gap === null ? null : gap === 0,
      missed_cheaper_feasible_candidate_ids: missed, missed_cheaper_feasible_count: missed === null ? null : missed.length,
      unrequested_cheaper_feasible_candidate_ids: unrequested, unrequested_cheaper_feasible_count: unrequested === null ? null : unrequested.length,
    }
  }
  return {
    schema_version: 'fiber-frame-candidate-process-pool-cost-audit.v1', status,
    candidate_denominator: poolIds.length + 1, baseline_included: true, price_table_hash: priceHash, currency,
    quantity_scope: DESIGN_SCOPE, oracle_unverifiable_candidate_ids: unknown,
    pool_minimum_feasible_estimate: minimum, pool_minimum_feasible_candidate_ids: winners, arms,
    missed_cheaper_definition: MISSED_DEFINITION, unrequested_cheaper_definition: UNREQUESTED_DEFINITION,
    global_design_optimality_proved: false, confirmed_currency_savings: false, independent_physical_validation: false,
  }
}

export function validateCandidateProcessCostSidecar(value: unknown, manifest: CandidateProcessManifest, suite: CandidateProcessSuite, slots: CandidateProcessSlot[]): CandidateProcessCostSidecar {
  ensure(manifest.schema_version === 'rc-fiber-candidate-process-review-bundle.v4', 'v4_manifest_required')
  const sidecar = exact(value, ['schema_version', 'source_suite_report_hash', 'source_suite_identity_hash', 'source_suite_sha256', 'groups', 'report_hash'])
  equal(sidecar.schema_version, 'fiber-frame-candidate-process-cost-sidecar.v1')
  equal(sidecar.source_suite_report_hash, suite.report_hash); equal(sidecar.source_suite_identity_hash, suite.suite_identity_hash)
  equal(sidecar.source_suite_sha256, manifest.suite_sha256); equal(hash(sidecar.report_hash), manifest.cost_audit_hash)
  const groups = list(sidecar.groups, 2368)
  const declaration = row(suite.declaration); const config = row(declaration.configuration)
  const cases = list(declaration.cases, 64).map(row)
  const slotMap = new Map(slots.map(slot => [slot.key, slot]))
  const expected: [Row, string, number][] = []
  for (const phase of PHASES) for (let repetition = 0; repetition < natural(phase === 'warmup' ? config.warmups : config.repetitions); repetition++) for (const declared of cases) expected.push([declared, phase, repetition])
  equal(groups.length, expected.length)
  groups.forEach((raw, index) => {
    const group = exact(raw, ['case_id', 'phase', 'repetition', 'worker_report_hashes', 'status', 'audit'])
    const [declared, phase, repetition] = expected[index]
    equal(group.case_id, declared.case_id); equal(group.phase, phase); equal(group.repetition, repetition)
    const byStrategy = Object.fromEntries((['deterministic', 'learned', 'oracle'] as const).map(strategy => [strategy, slotMap.get(candidateProcessSlotKey(string(declared.case_id), phase, repetition, strategy))])) as Record<'deterministic' | 'learned' | 'oracle', CandidateProcessSlot | undefined>
    const reportHashes = Object.fromEntries((['deterministic', 'learned', 'oracle'] as const).map(strategy => [strategy, byStrategy[strategy]?.run.report_contract_pass ? hash(byStrategy[strategy]!.run.report?.report_hash) : null]))
    same(group.worker_report_hashes, reportHashes)
    const learnedPool = list(row(row(declared.plans).learned).candidate_pool, 64).map(row)
    const costBasis = (pool: Row[]): unknown[] => pool.map(candidate => [candidate.candidate_id, candidate.screening_status, candidate.preanalysis_material_estimate])
    for (const strategy of ['deterministic', 'learned', 'oracle'] as const) {
      const slot = byStrategy[strategy]
      if (!slot?.run.report_contract_pass) continue
      const report = row(slot.run.report)
      same(report.input_binding, declared.input_binding)
      same(costBasis(list(report.candidate_pool, 64).map(row)), costBasis(learnedPool))
    }
    if (!byStrategy.deterministic?.run.report_contract_pass || !byStrategy.learned?.run.report_contract_pass) {
      equal(group.status, 'online_report_unavailable'); equal(group.audit, null)
    } else {
      const audit = recomputeGroupAudit(declared, { deterministic: byStrategy.deterministic, learned: byStrategy.learned }, byStrategy.oracle, config.oracle_audit === true)
      equal(group.status, audit.status); same(group.audit, audit)
    }
  })
  return sidecar as unknown as CandidateProcessCostSidecar
}
