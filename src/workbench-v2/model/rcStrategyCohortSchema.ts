import { sha256Bytes, sha256Hex } from './checksum'
import { check, document, fields, same, selfHash, type RcObject } from './rcJobSchema'
import { validateRcControlSearch } from './rcControlSearchSchema'
import type { StudyRead } from './rcControlDesignSchema'

const MAX = 2 * 1024 ** 2
const strategies = ['price_order', 'learned_order'] as const
const excludes = ['interpreter_startup_and_module_imports', 'runtime_sidecar_and_stdout', 'transport_and_workbench_review']
const nat = (n: unknown): n is number => Number.isSafeInteger(n) && Number(n) >= 0
const keys = (v: RcObject, expected: string[]) => v && same(Object.keys(v).sort(), [...expected].sort())
export interface RcCohortExecution {
  pair: number; strategy: string; reportPath: string; reportHash: string
  selected: string | null; estimate: number | null; cliWallNs: number; runtimePath: string
}
export interface RcCohortReview { manifest: RcObject; cost: RcObject; processCost: RcObject | null; executions: RcCohortExecution[] }

/** Independently validate every original study before deriving cohort costs. */
export async function validateRcStrategyCohort(raw: Uint8Array, sourceRead: StudyRead): Promise<RcCohortReview> {
  check(raw.byteLength <= MAX, 'cohort_manifest_too_large')
  const doc = document(raw), m = doc.value
  await selfHash(doc.raw, m, 'report_hash')
  const withProcesses = m.schema_version === 'rc-control-strategy-cohort-artifact.v2'
  check(keys(m, ['schema_version', 'source_revision', 'source_revision_is_attestation', 'pairs', 'cost_accounting', 'independent_physical_validation', 'report_hash', ...(withProcesses ? ['process_observations', 'process_cost_accounting'] : [])])
    && ['rc-control-strategy-cohort-artifact.v1', 'rc-control-strategy-cohort-artifact.v2'].includes(m.schema_version) && /^[a-f0-9]{40}$/.test(m.source_revision)
    && m.source_revision_is_attestation === false && m.independent_physical_validation === false
    && Array.isArray(m.pairs) && m.pairs.length >= 1 && m.pairs.length <= 64, 'cohort_manifest_invalid')
  let total = raw.byteLength
  const cache = new Map<string, Uint8Array>()
  const read: StudyRead = async (path, maximum, expected) => {
    check(typeof path === 'string' && /^[A-Za-z0-9_.:/-]+$/.test(path) && !path.startsWith('/')
      && !/^[A-Za-z][A-Za-z0-9+.-]*:/.test(path) && path.split('/').every(p => p && p !== '.' && p !== '..'), 'cohort_path_invalid')
    let b = cache.get(path)
    if (!b) { b = await sourceRead(path, maximum, expected); total += b.byteLength; cache.set(path, b) }
    check(b.byteLength <= maximum && (expected === undefined || b.byteLength === expected) && total <= 1024 ** 3, 'cohort_byte_budget_invalid')
    return b
  }
  const referenced = async (ref: RcObject, path: string) => {
    check(keys(ref, ['path', 'byte_length', 'sha256']) && ref.path === path && nat(ref.byte_length)
      && ref.byte_length > 0 && ref.byte_length <= MAX && /^sha256:[a-f0-9]{64}$/.test(ref.sha256), 'cohort_reference_invalid')
    const b = await read(path, MAX, ref.byte_length)
    check(await sha256Bytes(b) === ref.sha256, 'cohort_reference_bytes_invalid')
    return b
  }
  const rows: RcObject[] = [], training: RcObject = {}, executions: RcCohortExecution[] = [], seen = new Set<string>()
  for (let i = 0; i < m.pairs.length; i++) {
    const pair = m.pairs[i], values: RcObject = {}
    check(keys(pair, [...strategies]), 'cohort_pair_invalid')
    for (const strategy of strategies) {
      const record = pair[strategy], prefix = `pairs/${i}/${strategy}/`
      check(keys(record, ['report', 'report_hash', 'runtime']), 'cohort_execution_binding_invalid')
      const bytes = await referenced(record.report, `${prefix}result.json`)
      const declared = document(bytes).value
      check(declared.schema_version === 'experimental-rc-control-candidate-strategy.v1' && declared.strategy === strategy
        && declared.report_hash === record.report_hash && !seen.has(declared.report_hash), 'cohort_duplicate_or_wrong_execution')
      const review = await validateRcControlSearch(bytes, (path, maximum, expected) => read(prefix + path, maximum, expected))
      const report = review.report, plan = review.plan, arm = report.arms[strategy]
      check(report.schema_version === 'experimental-rc-control-candidate-strategy.v1' && report.strategy === strategy
        && report.report_hash === record.report_hash && !seen.has(report.report_hash), 'cohort_duplicate_or_wrong_execution')
      seen.add(report.report_hash)
      const runtime = document(await referenced(record.runtime, `${prefix}strategy-runtime.json`)).value
      check(keys(runtime, ['schema_version', 'source_revision', 'strategy', 'report_hash', 'wall_ns', 'cpu_ns', 'scope', 'excludes', 'new_training_fit_count', 'net_savings_proved'])
        && runtime.schema_version === 'experimental-rc-control-candidate-strategy-runtime.v1' && runtime.source_revision === report.source_revision
        && runtime.strategy === strategy && runtime.report_hash === report.report_hash
        && runtime.scope === 'argument_parsing_input_reads_preparation_ranking_full_reference_and_report_persistence'
        && same(runtime.excludes, excludes) && runtime.new_training_fit_count === 0 && runtime.net_savings_proved === false
        && [runtime.wall_ns, runtime.cpu_ns].every(nat) && runtime.wall_ns > 0
        && runtime.wall_ns >= report.online_and_optional_oracle_wall_ns && runtime.cpu_ns >= report.online_and_optional_oracle_cpu_ns
        && report.ranking_wall_ns + arm.wall_ns <= report.online_and_optional_oracle_wall_ns, 'cohort_runtime_invalid')
      // This schema has only constrained ASCII strings, safe integers and a string array.
      const digest = await sha256Hex(JSON.stringify(Object.fromEntries(Object.keys(runtime).sort().map(k => [k, runtime[k]]))))
      values[strategy] = { report, plan, arm, runtime, digest }
      executions.push({ pair: i, strategy, reportPath: `${prefix}result.json`, reportHash: report.report_hash,
        selected: arm.selected_candidate_id, estimate: arm.selected_estimate, cliWallNs: runtime.wall_ns, runtimePath: `${prefix}strategy-runtime.json` })
    }
    const p = values.price_order, l = values.learned_order
    for (const key of ['source_revision', 'control_request', 'pool', 'history_limits', 'material_limits', 'terminal_limits', 'price_table_hash', 'full_analysis_budget_per_arm', 'line_search_assembly_reuse'])
      check(same(p.plan[key], l.plan[key]), 'cohort_search_conditions_differ')
    const historical = l.report.historical_training_cost
    check(historical.label_generation_wall_ns + historical.fit.wall_ns <= historical.wall_ns, 'cohort_training_interval_invalid')
    training[historical.report_hash] = historical.wall_ns
    const comparable = p.arm.selected_full_reference_verified && l.arm.selected_full_reference_verified && l.arm.selected_estimate <= p.arm.selected_estimate
    rows.push({ price_report_hash: p.report.report_hash, learned_report_hash: l.report.report_hash,
      price_runtime_digest: p.digest, learned_runtime_digest: l.digest, training_report_hash: historical.report_hash,
      price_cli_wall_ns: p.runtime.wall_ns, learned_cli_wall_ns: l.runtime.wall_ns, recorded_selection_comparable: comparable,
      learned_over_price_cli_ratio: comparable && p.runtime.wall_ns > 0 ? l.runtime.wall_ns / p.runtime.wall_ns : null })
  }
  const price = rows.reduce((n, r) => n + r.price_cli_wall_ns, 0), learned = rows.reduce((n, r) => n + r.learned_cli_wall_ns, 0)
  const upfront = Object.values(training).reduce<number>((n, t) => n + Number(t), 0)
  check([price, learned, upfront, learned + upfront].every(nat), 'cohort_total_overflow')
  const cost = { schema_version: 'experimental-rc-control-strategy-cost-cohort.v1', pairs: rows, pair_count: rows.length,
    uncomparable_pair_count: rows.filter(r => !r.recorded_selection_comparable).length, distinct_historical_training_wall_ns: training,
    price_cli_interval_sum_ns: price, learned_cli_interval_sum_ns: learned, historical_training_wall_ns_counted_once: upfront,
    learned_plus_historical_interval_sum_ns: learned + upfront,
    learned_plus_historical_over_price_ratio: rows.every(r => r.recorded_selection_comparable) && price > 0 ? (learned + upfront) / price : null,
    scope: 'sum_of_cli_intervals_plus_distinct_historical_training_not_campaign_elapsed', excluded: [...excludes, 'separate_audits'],
    original_physical_artifacts_replayed: false, runtime_digest_is_attestation: false, net_savings_proved: false, independent_generalization: false }
  check(same(m.cost_accounting, cost), 'cohort_cost_accounting_invalid')
  let processCost: RcObject | null = null
  if (withProcesses) {
    const processDoc = document(await referenced(m.process_observations, 'process-observations.json')).value
    check(keys(processDoc, ['processes']) && Array.isArray(processDoc.processes) && processDoc.processes.length === 2 * rows.length, 'cohort_process_count_invalid')
    const expected = new Map<string, { digest: string; wall: number }>()
    for (const row of rows) for (const name of ['price', 'learned']) expected.set(row[`${name}_report_hash`], { digest: row[`${name}_runtime_digest`], wall: row[`${name}_cli_wall_ns`] })
    const indexed = new Map<string, RcObject>()
    for (const observation of processDoc.processes) {
      check(keys(observation, ['report_hash', 'runtime_digest', 'wall_ns', 'return_code', 'scope']) && typeof observation.report_hash === 'string', 'cohort_process_fields_invalid')
      const parent = expected.get(observation.report_hash)
      check(parent && !indexed.has(observation.report_hash) && observation.runtime_digest === parent.digest
        && observation.return_code === 0 && observation.scope === 'subprocess_launch_through_exit_including_startup_and_stdout'
        && nat(observation.wall_ns) && observation.wall_ns >= parent.wall, 'cohort_process_binding_invalid')
      // All process fields are constrained ASCII strings and safe integer clocks.
      const digest = await sha256Hex(JSON.stringify(Object.fromEntries(Object.keys(observation).sort().map(k => [k, observation[k]]))))
      indexed.set(observation.report_hash, { ...observation, digest })
    }
    const processRows = rows.map(row => {
      const p = indexed.get(row.price_report_hash)!, l = indexed.get(row.learned_report_hash)!
      return { price_report_hash: p.report_hash, learned_report_hash: l.report_hash,
        price_process_digest: p.digest, learned_process_digest: l.digest,
        price_process_wall_ns: p.wall_ns, learned_process_wall_ns: l.wall_ns,
        price_outside_cli_wall_ns: p.wall_ns - row.price_cli_wall_ns, learned_outside_cli_wall_ns: l.wall_ns - row.learned_cli_wall_ns,
        recorded_selection_comparable: row.recorded_selection_comparable,
        learned_over_price_process_ratio: row.recorded_selection_comparable && p.wall_ns > 0 ? l.wall_ns / p.wall_ns : null }
    })
    const ptotal = processRows.reduce((n, r) => n + r.price_process_wall_ns, 0), ltotal = processRows.reduce((n, r) => n + r.learned_process_wall_ns, 0)
    check([ptotal, ltotal, ltotal + upfront].every(nat), 'cohort_process_total_overflow')
    // Preserve producer numeric spelling (e.g. 1.0) in the already verified CLI object.
    const cliDigest = await sha256Hex(fields(doc.raw).get('cost_accounting')!.value)
    processCost = { schema_version: 'experimental-rc-control-process-cost-cohort.v1', cli_accounting_digest: cliDigest,
      pairs: processRows, pair_count: rows.length, uncomparable_pair_count: cost.uncomparable_pair_count,
      price_process_interval_sum_ns: ptotal, learned_process_interval_sum_ns: ltotal,
      distinct_historical_training_wall_ns: training, historical_training_wall_ns_counted_once: upfront,
      learned_plus_historical_interval_sum_ns: ltotal + upfront,
      learned_plus_historical_over_price_ratio: !cost.uncomparable_pair_count && ptotal > 0 ? (ltotal + upfront) / ptotal : null,
      scope: 'sum_of_process_intervals_plus_distinct_historical_training_not_campaign_elapsed',
      excluded: ['transport_and_workbench_review', 'separate_audits', 'campaign_preparation'],
      outside_cli_interval_is_startup_only: false, process_digest_is_attestation: false,
      original_physical_artifacts_replayed: false, net_savings_proved: false, independent_generalization: false }
    check(same(m.process_cost_accounting, processCost), 'cohort_process_cost_invalid')
  }
  return { manifest: m, cost, processCost, executions }
}
