import { useMemo, useState, type ReactElement } from 'react'
import {
  benchmarkRunCommand,
  comparabilityReason,
  deriveLifecycle,
  getBenchmarkCatalog,
  isAccuracyComparable,
  type BenchmarkCase,
  type LifecycleStatus,
  type TruthClass,
} from '../model/benchmark/benchmarkSchema'
import { CopyButton } from './CopyButton'

const TRUTH_FILTERS: (TruthClass | 'all')[] = [
  'all',
  'analytic',
  'independent_solver',
  'commercial_reference',
  'experimental',
  'geometry_only',
]

const LIFECYCLE_FILTERS: (LifecycleStatus | 'all' | 'first-targets')[] = [
  'all',
  'first-targets',
  'DISCOVERED',
  'ACQUIRED',
  'NORMALIZED',
  'REFERENCE_ATTACHED',
  'RUNNABLE',
  'VALIDATED',
]

function yn(v: boolean): string {
  return v ? 'verified' : 'unverified'
}

function CaseCard({ c }: { c: BenchmarkCase }): ReactElement {
  const comparable = isAccuracyComparable(c)
  const lifecycle = deriveLifecycle(c)
  const run = benchmarkRunCommand(c)
  const v = c.verification
  const geometryOnly = c.truthClass === 'geometry_only'
  return (
    <article className="wb2-bench-card" data-bench-id={c.id} data-truth={c.truthClass} data-lifecycle={lifecycle} data-geometry-only={geometryOnly ? 'true' : 'false'}>
      <header className="wb2-bench-card__head">
        <h3>{c.title}</h3>
        <div className="wb2-bench-chips">
          <span className={`wb2-bench-life wb2-bench-life--${lifecycle.toLowerCase()}`}>{lifecycle}</span>
          <span className={`wb2-bench-truth wb2-bench-truth--${c.truthClass}`}>{c.truthClass}</span>
          {c.firstValidationTarget ? <span className="wb2-bench-target" title="First validation target">★ target</span> : null}
        </div>
      </header>
      <p className="wb2-bench-family">{c.structureFamily}</p>

      {geometryOnly ? (
        <p className="wb2-bench-excluded" data-geometry-excluded role="note">
          Geometry-only — excluded from accuracy validation. Used for import / geometry checks only; no
          accuracy claim is made or inferred from this case.
        </p>
      ) : null}

      <dl className="wb2-evidence-kv">
        <dt>Source</dt>
        <dd>{c.sourceUrl ? <a href={c.sourceUrl} target="_blank" rel="noreferrer">{c.sourceUrl}</a> : 'unknown'}</dd>
        <dt>License</dt>
        <dd>{c.license} ({yn(v.licenseVerified)}){v.licenseUrl ? <> · <a href={v.licenseUrl} target="_blank" rel="noreferrer">license</a></> : null}</dd>
        <dt>Truth class</dt>
        <dd>{c.truthClass} ({yn(v.truthClassVerified)}){v.truthEvidencePath ? <> · <code className="wb2-mono" title={v.truthEvidencePath}>evidence</code></> : null}</dd>
        <dt>Reference</dt>
        <dd>{v.referenceResultsAvailable ? `available${v.referenceSolver ? ` · ${v.referenceSolver}` : ''}` : 'not attached'}</dd>
        <dt>Checksum</dt>
        <dd>{c.checksum ? <code className="wb2-mono" title={c.checksum}>{c.checksum.slice(0, 20)}…</code> : 'unavailable'}</dd>
        <dt>Availability</dt>
        <dd>{c.localAvailability} · {c.sizeClass ?? 'unknown'} (by file)</dd>
        <dt>Runner</dt>
        <dd>{v.runnerId ?? 'none registered'}</dd>
      </dl>

      <p className={`wb2-bench-comparable${comparable ? ' is-yes' : ' is-no'}`}>
        {comparable ? 'Accuracy-comparable' : 'Not accuracy-comparable'} — {comparabilityReason(c)}
      </p>

      <div className="wb2-bench-run">
        {run.runnable ? (
          <>
            <span className="wb2-bench-run__label">Run command</span>
            <div className="wb2-bench-cmd-row">
              <code className="wb2-mono wb2-bench-run__cmd">{run.command}</code>
              <CopyButton value={run.command} label="Copy" />
            </div>
          </>
        ) : (
          <>
            <p className="wb2-bench-run__blocked" data-run-blocked>⛔ {run.reason}.</p>
            {v.acquisitionCommand ? (
              <div className="wb2-bench-acq">
                <span className="wb2-bench-run__label">Acquire first</span>
                <div className="wb2-bench-cmd-row">
                  <code className="wb2-mono wb2-bench-run__cmd" data-acq-cmd>{v.acquisitionCommand}</code>
                  <CopyButton value={v.acquisitionCommand} label="Copy" />
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>

      {c.sourceUrl ? (
        <a className="wb2-bench-report" href={c.sourceUrl} target="_blank" rel="noreferrer">Open source / report ↗</a>
      ) : null}
    </article>
  )
}

export function BenchmarkBrowser(): ReactElement {
  const catalog = useMemo(() => getBenchmarkCatalog(), [])
  const [truth, setTruth] = useState<TruthClass | 'all'>('all')
  const [size, setSize] = useState<string>('all')
  const [lifecycle, setLifecycle] = useState<LifecycleStatus | 'all' | 'first-targets'>('all')
  const [query, setQuery] = useState<string>('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return catalog.cases.filter((c) => {
      if (truth !== 'all' && c.truthClass !== truth) return false
      if (size !== 'all' && (c.sizeClass ?? 'unknown') !== size) return false
      if (lifecycle === 'first-targets' && !c.firstValidationTarget) return false
      if (lifecycle !== 'all' && lifecycle !== 'first-targets' && deriveLifecycle(c) !== lifecycle) return false
      if (q && !`${c.title} ${c.structureFamily} ${c.sourceUrl} ${c.license}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [catalog, truth, size, lifecycle, query])

  const comparableCount = catalog.cases.filter((c) => isAccuracyComparable(c)).length
  const validatedCount = catalog.cases.filter((c) => deriveLifecycle(c) === 'VALIDATED').length
  const runnableCount = catalog.cases.filter((c) => c.verification.runnerId).length
  const geometryOnlyCount = catalog.cases.filter((c) => c.truthClass === 'geometry_only').length

  return (
    <section className="wb2-panel wb2-bench" aria-labelledby="wb2-bench-title">
      <h2 id="wb2-bench-title" className="wb2-panel__title">Public benchmark case browser</h2>

      <p className="wb2-note">
        {catalog.cases.length} candidate(s) · {comparableCount} accuracy-comparable · {validatedCount} validated ·{' '}
        {runnableCount} runnable · <span data-geometry-excluded-count>{geometryOnlyCount} geometry-only (excluded from accuracy)</span>.{' '}
        <span className="wb2-bench-kind">catalog: {catalog.catalogKind} ({catalog.schemaVersion})</span>
      </p>
      {catalog.disclaimer ? <p className="wb2-bench-disclaimer">{catalog.disclaimer}</p> : null}

      <div className="wb2-bench-filters" role="group" aria-label="Benchmark filters">
        <label>
          <span>Lifecycle</span>
          <select value={lifecycle} onChange={(e) => setLifecycle(e.target.value as LifecycleStatus | 'all' | 'first-targets')}>
            {LIFECYCLE_FILTERS.map((l) => (<option key={l} value={l}>{l}</option>))}
          </select>
        </label>
        <label>
          <span>Truth class</span>
          <select value={truth} onChange={(e) => setTruth(e.target.value as TruthClass | 'all')}>
            {TRUTH_FILTERS.map((t) => (<option key={t} value={t}>{t}</option>))}
          </select>
        </label>
        <label>
          <span>Size (by file)</span>
          <select value={size} onChange={(e) => setSize(e.target.value)}>
            {['all', 'small', 'medium', 'large', 'unknown'].map((s) => (<option key={s} value={s}>{s}</option>))}
          </select>
        </label>
        <label className="wb2-bench-search">
          <span>Search source / license</span>
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. github, opensees…" />
        </label>
      </div>

      {filtered.length ? (
        <div className="wb2-bench-grid">
          {filtered.map((c) => (<CaseCard key={c.id} c={c} />))}
        </div>
      ) : (
        <p className="wb2-empty">No cases match the current filters.</p>
      )}
    </section>
  )
}
