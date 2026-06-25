import { useMemo, useState, type ReactElement } from 'react'
import {
  buildRunCommand,
  comparabilityReason,
  getBenchmarkCatalog,
  isAccuracyComparable,
  type BenchmarkCase,
  type TruthClass,
} from '../model/benchmark/benchmarkSchema'

const TRUTH_FILTERS: (TruthClass | 'all')[] = [
  'all',
  'analytic',
  'independent_solver',
  'commercial_reference',
  'experimental',
  'geometry_only',
]

function CaseCard({ c }: { c: BenchmarkCase }): ReactElement {
  const comparable = isAccuracyComparable(c)
  return (
    <article className="wb2-bench-card" data-bench-id={c.id} data-truth={c.truthClass}>
      <header className="wb2-bench-card__head">
        <h3>{c.title}</h3>
        <span className={`wb2-bench-truth wb2-bench-truth--${c.truthClass}`}>{c.truthClass}</span>
      </header>
      <p className="wb2-bench-family">{c.structureFamily}</p>

      <dl className="wb2-evidence-kv">
        <dt>Source</dt>
        <dd>
          {c.sourceUrl ? (
            <a href={c.sourceUrl} target="_blank" rel="noreferrer">{c.sourceUrl}</a>
          ) : (
            'unknown'
          )}
        </dd>
        <dt>License</dt>
        <dd>{c.license}{c.licenseVerified ? '' : ' (unverified)'}</dd>
        <dt>Checksum</dt>
        <dd>{c.checksum ? <code className="wb2-mono" title={c.checksum}>{c.checksum.slice(0, 20)}…</code> : 'unavailable'}</dd>
        <dt>Availability</dt>
        <dd>{c.localAvailability}</dd>
        <dt>Size (by file)</dt>
        <dd>{c.sizeClass ?? 'unknown'}</dd>
      </dl>

      <p className={`wb2-bench-comparable${comparable ? ' is-yes' : ' is-no'}`}>
        {comparable ? 'Accuracy-comparable' : 'Not accuracy-comparable'} — {comparabilityReason(c)}
      </p>

      <div className="wb2-bench-run">
        <span className="wb2-bench-run__label">Example run command</span>
        <code className="wb2-mono wb2-bench-run__cmd">{buildRunCommand(c)}</code>
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
  const [query, setQuery] = useState<string>('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return catalog.cases.filter((c) => {
      if (truth !== 'all' && c.truthClass !== truth) return false
      if (size !== 'all' && (c.sizeClass ?? 'unknown') !== size) return false
      if (q && !`${c.title} ${c.structureFamily} ${c.sourceUrl} ${c.license}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [catalog, truth, size, query])

  const comparableCount = catalog.cases.filter((c) => isAccuracyComparable(c)).length

  return (
    <section className="wb2-panel wb2-bench" aria-labelledby="wb2-bench-title">
      <h2 id="wb2-bench-title" className="wb2-panel__title">Public benchmark case browser</h2>

      <p className="wb2-note">
        {catalog.cases.length} candidate case(s) · {comparableCount} accuracy-comparable.{' '}
        <span className="wb2-bench-kind">catalog: {catalog.catalogKind}</span>
      </p>
      {catalog.disclaimer ? <p className="wb2-bench-disclaimer">{catalog.disclaimer}</p> : null}

      <div className="wb2-bench-filters" role="group" aria-label="Benchmark filters">
        <label>
          <span>Truth class</span>
          <select value={truth} onChange={(e) => setTruth(e.target.value as TruthClass | 'all')}>
            {TRUTH_FILTERS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Size (by file)</span>
          <select value={size} onChange={(e) => setSize(e.target.value)}>
            {['all', 'small', 'medium', 'large', 'unknown'].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="wb2-bench-search">
          <span>Search source / license</span>
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. github, opensees…" />
        </label>
      </div>

      {filtered.length ? (
        <div className="wb2-bench-grid">
          {filtered.map((c) => (
            <CaseCard key={c.id} c={c} />
          ))}
        </div>
      ) : (
        <p className="wb2-empty">No cases match the current filters.</p>
      )}
    </section>
  )
}
