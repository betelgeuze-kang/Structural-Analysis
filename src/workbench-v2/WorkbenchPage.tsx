import { useEffect, useMemo, useReducer, useState, type ReactElement } from 'react'
import './workbenchV2.css'
import { createWorkbenchProvider, type ProviderMode } from './model/evidenceAdapter'
import type { WorkbenchModel } from './model/caseSchema'
import { initialWorkbenchState, workbenchReducer } from './model/workbenchState'
import { WorkbenchShell } from './components/WorkbenchShell'
import { AnalysisRibbon } from './components/AnalysisRibbon'
import { CaseSummary } from './components/CaseSummary'
import { ModelViewport } from './components/ModelViewport'
import { ResidualAuditPanel } from './components/ResidualAuditPanel'
import { ReferenceComparison } from './components/ReferenceComparison'
import { ReviewDecision } from './components/ReviewDecision'
import { ExportPanel } from './components/ExportPanel'
import { EvidenceReaderPanel } from './components/EvidenceReaderPanel'

export interface WorkbenchPageProps {
  /** Initial data provider. Defaults to the offline demo provider. */
  initialProviderMode?: ProviderMode
}

export function WorkbenchPage({ initialProviderMode = 'demo' }: WorkbenchPageProps): ReactElement {
  const [providerMode, setProviderMode] = useState<ProviderMode>(initialProviderMode)
  const provider = useMemo(() => createWorkbenchProvider(providerMode), [providerMode])

  const [state, dispatch] = useReducer(workbenchReducer, initialWorkbenchState)
  const [model, setModel] = useState<WorkbenchModel | null>(null)
  const [sourceLabel, setSourceLabel] = useState<string>(provider.sourceLabel)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'missing' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    setLoadState('loading')
    setModel(null)
    provider
      .load()
      .then((result) => {
        if (cancelled) return
        setSourceLabel(result.sourcePath)
        if (result.status === 'ready' && result.model) {
          setModel(result.model)
          setLoadState('ready')
          dispatch({ type: 'model_loaded', model: result.model })
        } else {
          setLoadState(result.status)
          dispatch({ type: 'load_failed', error: result.error ?? 'Evidence unavailable.' })
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setLoadState('error')
        dispatch({ type: 'load_failed', error: String((error as Error)?.message ?? error) })
      })
    return () => {
      cancelled = true
    }
  }, [provider])

  return (
    <WorkbenchShell
      dataMode={state.dataMode}
      providerMode={providerMode}
      sourceLabel={sourceLabel}
      claimBoundary={model?.claimBoundary ?? null}
      onProviderModeChange={setProviderMode}
    >
      <EvidenceReaderPanel />
      {loadState === 'loading' ? (
        <section className="wb2-panel"><p className="wb2-empty">Loading workbench data…</p></section>
      ) : !model ? (
        <section className="wb2-panel">
          <p className="wb2-unavailable" data-wb2-unavailable>
            Workbench data unavailable{state.warnings[0] ? ` (${state.warnings[0]})` : ''}. Nothing is inferred.
          </p>
        </section>
      ) : (
        <>
          <AnalysisRibbon runStatus={state.runStatus} />
          <CaseSummary model={model} />
          <ModelViewport
            members={model.members}
            selectedMemberId={state.selectedMemberId}
            onSelectMember={(memberId) => dispatch({ type: 'select_member', memberId })}
          />
          <ResidualAuditPanel residualHistory={state.residualHistory} sourceLabel={sourceLabel} />
          <ReferenceComparison rows={model.referenceComparison} sourceLabel={sourceLabel} />
          <ReviewDecision dataMode={state.dataMode} />
          <ExportPanel
            model={model}
            dataMode={state.dataMode}
            sourceLabel={sourceLabel}
            selectedMemberId={state.selectedMemberId}
          />
        </>
      )}
    </WorkbenchShell>
  )
}

export default WorkbenchPage
