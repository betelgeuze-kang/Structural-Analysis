import { useEffect, useMemo, useState, type ReactElement } from 'react'
import './evidenceConsole.css'
import { createEvidenceDataProvider, type ProviderOptions } from './dataProvider'
import { decisionAnnouncement, hasValue } from './format'
import type { DatasetResult, EvidenceCase, ProviderMode, ReadinessState } from './types'
import { missingReadiness } from './readiness'
import { CaseList } from './components/CaseList'
import { CaseDetail } from './components/CaseDetail'
import { ReadinessPanel } from './components/ReadinessPanel'
import { ClaimBoundaryPanel } from './components/ClaimBoundaryPanel'
import { Unavailable } from './components/Unavailable'

export interface EvidenceConsoleProps {
  /** Which data provider to use. Defaults to the offline mock provider. */
  mode?: ProviderMode
  /** Options forwarded to the live provider (cases/readiness URLs, fetch impl). */
  providerOptions?: ProviderOptions
}

const LOADING_RESULT: DatasetResult = { status: 'loading', dataset: null, error: null }

export function EvidenceConsole({ mode = 'mock', providerOptions }: EvidenceConsoleProps): ReactElement {
  const [activeMode, setActiveMode] = useState<ProviderMode>(mode)
  const provider = useMemo(
    () => createEvidenceDataProvider(activeMode, providerOptions ?? {}),
    [activeMode, providerOptions],
  )

  const [datasetResult, setDatasetResult] = useState<DatasetResult>(LOADING_RESULT)
  const [readiness, setReadiness] = useState<ReadinessState | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setDatasetResult(LOADING_RESULT)
    setReadiness(null)

    provider
      .loadReadiness()
      .then((value) => {
        if (!cancelled) setReadiness(value)
      })
      .catch(() => {
        if (!cancelled) setReadiness(missingReadiness('provider error'))
      })

    provider
      .loadDataset()
      .then((result) => {
        if (cancelled) return
        setDatasetResult(result)
        setActiveId(result.dataset?.cases[0]?.id ?? null)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDatasetResult({ status: 'error', dataset: null, error: String((error as Error)?.message ?? error) })
        }
      })

    return () => {
      cancelled = true
    }
  }, [provider])

  const dataset = datasetResult.dataset
  const activeCase: EvidenceCase | null = useMemo(
    () => dataset?.cases.find((c) => c.id === activeId) ?? null,
    [dataset, activeId],
  )

  const statusMessage = activeCase
    ? `Showing evidence for ${hasValue(activeCase.name) ? activeCase.name : activeCase.id}. Reviewer decision: ${decisionAnnouncement(activeCase.reviewer_decision)}.`
    : ''

  return (
    <div className="evidence-console-react" data-ec-react-root>
      <header className="ec-react-header">
        <div>
          <p className="ec-eyebrow">Structural Optimization Workbench</p>
          <h2 className="ec-react-title">Evidence Console</h2>
        </div>
        <div className="ec-mode-switch" role="group" aria-label="Data provider">
          <span className="ec-mode-label">Data provider</span>
          {(['mock', 'live'] as ProviderMode[]).map((m) => (
            <button
              key={m}
              type="button"
              className={`ec-mode-btn${activeMode === m ? ' is-active' : ''}`}
              aria-pressed={activeMode === m}
              data-ec-mode={m}
              onClick={() => setActiveMode(m)}
            >
              {m === 'mock' ? 'Mock' : 'Live'}
            </button>
          ))}
        </div>
      </header>

      <div className="ec-react-banners">
        <ClaimBoundaryPanel readiness={readiness ?? missingReadiness(null)} />
        {readiness ? <ReadinessPanel readiness={readiness} /> : <section className="ec-panel"><p className="ec-empty">Loading readiness evidence…</p></section>}
      </div>

      <div className="ec-layout">
        {datasetResult.status === 'loading' ? (
          <section className="ec-panel"><p className="ec-empty">Loading cases…</p></section>
        ) : !dataset || !dataset.cases.length ? (
          <section className="ec-panel">
            <Unavailable message={datasetResult.error ?? 'No evidence cases to display.'} />
          </section>
        ) : (
          <>
            <CaseList cases={dataset.cases} activeId={activeId} onSelect={setActiveId} />
            {activeCase ? (
              <CaseDetail caseItem={activeCase} dataset={dataset} providerMode={provider.mode} />
            ) : (
              <section className="ec-panel"><p className="ec-empty">Select a case to inspect its evidence.</p></section>
            )}
          </>
        )}
      </div>

      <div className="ec-visually-hidden" role="status" aria-live="polite" data-ec-status>
        {statusMessage}
      </div>
    </div>
  )
}

export default EvidenceConsole
