import type { ReactElement } from 'react'
import type { ReadinessState } from '../types'
import { hasValue } from '../format'
import { Unavailable } from './Unavailable'

const GATE_PILL_CLASS: Record<string, string> = {
  BLOCKED: 'ec-pill--fail',
  READY: 'ec-pill--pass',
  UNKNOWN: 'ec-pill--unavailable',
}

function GatePill({ readiness }: { readiness: ReadinessState }): ReactElement {
  if (readiness.availability === 'missing') {
    return (
      <span className="ec-pill ec-pill--unavailable" data-ec-gate="missing">
        Readiness unavailable
      </span>
    )
  }
  const cls = GATE_PILL_CLASS[readiness.gate] ?? 'ec-pill--unavailable'
  return (
    <span className={`ec-pill ${cls}`} data-ec-gate={readiness.gate}>
      Launch: {readiness.gate}
    </span>
  )
}

function FreshnessPill({ readiness }: { readiness: ReadinessState }): ReactElement {
  const map: Record<string, { cls: string; text: string }> = {
    fresh: { cls: 'ec-pill--pass', text: 'Evidence: fresh' },
    stale: { cls: 'ec-pill--review', text: 'Evidence: stale' },
    unknown: { cls: 'ec-pill--unavailable', text: 'Evidence: age unknown' },
  }
  const entry = map[readiness.freshness] ?? map.unknown
  return (
    <span className={`ec-pill ${entry.cls}`} data-ec-freshness={readiness.freshness}>
      {entry.text}
    </span>
  )
}

export function ReadinessPanel({ readiness }: { readiness: ReadinessState }): ReactElement {
  return (
    <section className="ec-panel ec-readiness" aria-label="Launch readiness and claim boundary" aria-live="polite">
      <div className="ec-readiness-head">
        <h2 className="ec-readiness-title">Launch readiness</h2>
        <div className="ec-readiness-pills">
          <GatePill readiness={readiness} />
          <FreshnessPill readiness={readiness} />
        </div>
      </div>

      {readiness.availability === 'missing' ? (
        <Unavailable
          message={`Readiness evidence unavailable${
            readiness.error ? ` (${readiness.error})` : ''
          }. Launch state cannot be confirmed and must be treated as not ready.`}
        />
      ) : (
        <>
          <dl className="ec-kv">
            <dt>Status</dt>
            <dd>{readiness.status}</dd>
            <dt>Launch ready</dt>
            <dd>{readiness.launchReady === null ? '—' : String(readiness.launchReady)}</dd>
            <dt>Source commit</dt>
            <dd>
              {hasValue(readiness.sourceCommitShort) ? (
                <code className="ec-commit" data-ec-source-commit={readiness.sourceCommit ?? ''} title={readiness.sourceCommit ?? undefined}>
                  {readiness.sourceCommitShort}
                </code>
              ) : (
                '—'
              )}
            </dd>
            <dt>Generated at</dt>
            <dd>{readiness.generatedAt ?? '—'}</dd>
            <dt>Summary</dt>
            <dd>{readiness.summaryLine ?? '—'}</dd>
          </dl>

          {readiness.freshness === 'stale' && hasValue(readiness.staleReason) ? (
            <p className="ec-readiness-note">Stale: {readiness.staleReason}</p>
          ) : null}

          {readiness.blockers.length ? (
            <div className="ec-section">
              <h3>Blockers</h3>
              <ul className="ec-blocker-list">
                {readiness.blockers.map((blocker) => (
                  <li key={blocker}>{blocker}</li>
                ))}
              </ul>
              {hasValue(readiness.nextAction) ? (
                <p className="ec-readiness-note">Next action: {readiness.nextAction}</p>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </section>
  )
}
