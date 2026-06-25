import { useEffect, useMemo, useReducer, useState, type ReactElement } from 'react'
import './workbenchV2.css'
import { createWorkbenchProvider, type ProviderMode } from './model/evidenceAdapter'
import type { WorkbenchCaseV2 } from './model/caseSchema'
import { initialWorkbenchState, workbenchReducer } from './model/workbenchState'
import { WorkbenchShell } from './components/WorkbenchShell'
import { AnalysisRibbon } from './components/AnalysisRibbon'
import { CaseSummary } from './components/CaseSummary'
import { ModelViewport } from './components/ModelViewport'
import { ResidualAuditPanel } from './components/ResidualAuditPanel'
import { ReviewDecision } from './components/ReviewDecision'
import { ExportPanel } from './components/ExportPanel'
import { EvidenceReaderPanel } from './components/EvidenceReaderPanel'
import { BenchmarkBrowser } from './components/BenchmarkBrowser'

export interface WorkbenchPageProps {
  initialProviderMode?: ProviderMode
}

type LoadState = 'loading' | 'ready' | 'invalid' | 'missing' | 'error'

export function WorkbenchPage({ initialProviderMode = 'demo' }: WorkbenchPageProps): ReactElement {
  const [providerMode, setProviderMode] = useState<ProviderMode>(initialProviderMode)
  const provider = useMemo(() => createWorkbenchProvider(providerMode), [providerMode])

  const [state, dispatch] = useReducer(workbenchReducer, initialWorkbenchState)
  const [caseV2, setCaseV2] = useState<WorkbenchCaseV2 | null>(null)
  const [sourceLabel, setSourceLabel] = useState<string>(provider.sourceLabel)
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errors, setErrors] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    setLoadState('loading')
    setCaseV2(null)
    provider
      .load()
      .then((res) => {
        if (cancelled) return
        setSourceLabel(res.sourcePath)
        if (res.status === 'ready' && res.caseV2) {
          const w = res.validation?.warnings ?? []
          setCaseV2(res.caseV2)
          setWarnings(w)
          setLoadState('ready')
          dispatch({
            type: 'case_loaded',
            dataMode: provider.mode,
            caseV2: res.caseV2,
            convergenceAvailable: res.validation?.convergenceAvailable ?? false,
            warnings: w,
          })
        } else {
          const errs = res.validation?.errors ?? (res.error ? [res.error] : ['unavailable'])
          setErrors(errs)
          setLoadState(res.status)
          dispatch({ type: 'load_failed', errors: errs })
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const msg = String((error as Error)?.message ?? error)
        setErrors([msg])
        setLoadState('error')
        dispatch({ type: 'load_failed', errors: [msg] })
      })
    return () => {
      cancelled = true
    }
  }, [provider])

  const claimBoundary =
    state.dataMode === 'demo'
      ? 'Demo case. Values are illustrative; the review decision is never inferred.'
      : null

  return (
    <WorkbenchShell
      dataMode={state.dataMode}
      providerMode={providerMode}
      sourceLabel={sourceLabel}
      claimBoundary={claimBoundary}
      onProviderModeChange={setProviderMode}
    >
      <EvidenceReaderPanel />
      <BenchmarkBrowser />

      {loadState === 'loading' ? (
        <section className="wb2-panel"><p className="wb2-empty">Loading case…</p></section>
      ) : !caseV2 ? (
        <section className="wb2-panel">
          <p className="wb2-unavailable" data-wb2-unavailable>
            Case unavailable{errors[0] ? ` (${errors[0]})` : ''}. Nothing is inferred.
            {errors.length > 1 ? ` (+${errors.length - 1} more validation error(s))` : ''}
          </p>
        </section>
      ) : (
        <>
          <AnalysisRibbon runStatus={state.runStatus} analysis={caseV2.analysis} convergenceAvailable={state.convergenceAvailable} />
          <CaseSummary caseV2={caseV2} />
          <ModelViewport model={caseV2.model} selectedMemberId={state.selectedMemberId} />
          <ResidualAuditPanel residualHistory={caseV2.residualHistory} sourceLabel={sourceLabel} />
          <ReviewDecision dataMode={state.dataMode} />
          <ExportPanel caseV2={caseV2} dataMode={state.dataMode} runStatus={state.runStatus} selectedMemberId={state.selectedMemberId} />
        </>
      )}

      {warnings.length ? (
        <section className="wb2-panel"><p className="wb2-note wb2-note--warn" data-wb2-warnings>{warnings.join(' · ')}</p></section>
      ) : null}
    </WorkbenchShell>
  )
}

export default WorkbenchPage
