import { useEffect, useState, type ReactElement } from 'react'
import { loadEvidence } from '../model/evidence/evidenceEnvelope'
import {
  detectCommitMismatch,
  interpretReadiness,
  type GateState,
  type ReadinessFacts,
} from '../model/evidence/readinessInterpreter'
import { EVIDENCE_SOURCES, type EvidenceSourceDef } from '../model/evidence/evidenceSources'
import { StateChip, type ChipState } from './StateChip'

interface SourceResult {
  def: EvidenceSourceDef
  facts: ReadinessFacts
}

const GATE_TO_CHIP: Record<GateState, ChipState> = {
  ready: 'LIVE',
  blocked: 'BLOCKED',
  missing: 'MISSING',
  unavailable: 'UNAVAILABLE',
}

function SourceCard({ result }: { result: SourceResult }): ReactElement {
  const { def, facts } = result
  return (
    <article className="wb2-evidence-card" data-evidence-id={def.id} data-gate={facts.gateState}>
      <header className="wb2-evidence-card__head">
        <h3>{def.label}</h3>
        <div className="wb2-evidence-card__chips">
          <StateChip state={GATE_TO_CHIP[facts.gateState]} srLabel={def.label} />
          {facts.freshness === 'stale' ? <StateChip state="STALE" srLabel="Freshness" /> : null}
        </div>
      </header>

      <dl className="wb2-evidence-kv">
        <dt>Source path</dt>
        <dd><code className="wb2-mono" data-evidence-source>{def.path}</code></dd>
        <dt>Source commit</dt>
        <dd>
          {facts.sourceCommitShort ? (
            <code className="wb2-mono" data-evidence-commit={facts.sourceCommitSha ?? ''} title={facts.sourceCommitSha ?? undefined}>
              {facts.sourceCommitShort}
            </code>
          ) : (
            '—'
          )}
        </dd>
        <dt>Generated at</dt>
        <dd>{facts.generatedAt ?? '—'}</dd>
        {facts.status ? (<><dt>Status</dt><dd>{facts.status}</dd></>) : null}
      </dl>

      {facts.gateState === 'missing' ? (
        <p className="wb2-unavailable" data-wb2-unavailable>
          Evidence unavailable{facts.error ? ` (${facts.error})` : ''}. Treated as not ready — nothing is inferred.
        </p>
      ) : null}

      {facts.freshness === 'stale' && facts.staleReason ? (
        <p className="wb2-note wb2-note--warn">Stale: {facts.staleReason}</p>
      ) : null}

      {facts.summaryLine ? <p className="wb2-evidence-summary">{facts.summaryLine}</p> : null}

      {facts.blockerCount > 0 ? (
        <div className="wb2-evidence-blockers">
          <p className="wb2-evidence-blockers__count">{facts.blockerCount} blocker(s)</p>
          <ul>
            {facts.blockers.slice(0, 5).map((b) => (
              <li key={b}>{b}</li>
            ))}
            {facts.blockerCount > 5 ? <li>…and {facts.blockerCount - 5} more</li> : null}
          </ul>
        </div>
      ) : null}
    </article>
  )
}

export function EvidenceReaderPanel(): ReactElement {
  const [results, setResults] = useState<SourceResult[] | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all(
      EVIDENCE_SOURCES.map(async (def) => {
        const envelope = await loadEvidence(def.path)
        return { def, facts: interpretReadiness(envelope) }
      }),
    ).then((loaded) => {
      if (!cancelled) setResults(loaded)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const productReadiness = results?.find((r) => r.def.id === 'product_readiness')?.facts ?? null
  const commit = results ? detectCommitMismatch(results.map((r) => r.facts)) : { mismatch: false, commits: [] }

  return (
    <section className="wb2-panel wb2-evidence" aria-labelledby="wb2-evidence-title">
      <h2 id="wb2-evidence-title" className="wb2-panel__title">Read-only evidence</h2>

      {productReadiness ? (
        <p className="wb2-evidence-release" data-release-ready={String(productReadiness.releaseReady)}>
          <strong>Release ready:</strong>{' '}
          {productReadiness.releaseReady === null ? 'unknown' : String(productReadiness.releaseReady)}
          {productReadiness.releaseReady === false ? ' — release is blocked.' : ''}
        </p>
      ) : null}

      {commit.mismatch ? (
        <p className="wb2-note wb2-note--warn" data-commit-mismatch>
          Source commit mismatch across evidence: {commit.commits.map((c) => c.slice(0, 8)).join(', ')}. Values are
          not from a single snapshot and must not be combined.
        </p>
      ) : null}

      {!results ? (
        <p className="wb2-empty">Loading evidence…</p>
      ) : (
        <div className="wb2-evidence-grid">
          {results.map((result) => (
            <SourceCard key={result.def.id} result={result} />
          ))}
        </div>
      )}
    </section>
  )
}
