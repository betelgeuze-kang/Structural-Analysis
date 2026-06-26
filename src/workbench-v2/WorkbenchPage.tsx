import { useEffect, useMemo, useReducer, useState, type ReactElement } from 'react'
import './workbenchV2.css'
import { createWorkbenchProvider, type ProviderMode } from './model/evidenceAdapter'
import type { WorkbenchCaseV2 } from './model/caseSchema'
import { defaultDemoCaseId, type DemoCaseId } from './model/demoCases'
import { initialWorkbenchState, workbenchReducer } from './model/workbenchState'
import { WorkbenchShell } from './components/WorkbenchShell'
import { WorkbenchNav } from './components/WorkbenchNav'
import { AnalysisRibbon } from './components/AnalysisRibbon'
import { RunMonitor } from './components/RunMonitor'
import { CaseSelector } from './components/CaseSelector'
import { CaseSummary } from './components/CaseSummary'
import { ResultSummaryCard } from './components/ResultSummaryCard'
import { ModelViewport } from './components/ModelViewport'
import { ResidualAuditPanel } from './components/ResidualAuditPanel'
import { ReviewDecision } from './components/ReviewDecision'
import { ExportPanel } from './components/ExportPanel'
import { EvidenceReaderPanel } from './components/EvidenceReaderPanel'
import { BenchmarkBrowser } from './components/BenchmarkBrowser'
import { ComparePanel } from './components/ComparePanel'
import type { ComparisonRow } from './components/ExportPanel'
import { getBenchmarkCatalog, isAccuracyComparable } from './model/benchmark/benchmarkSchema'
import { buildViewerUrl } from './model/viewerBridge'

export interface WorkbenchPageProps {
  initialProviderMode?: ProviderMode
}

type LoadState = 'loading' | 'ready' | 'invalid' | 'missing' | 'error'

export function WorkbenchPage({ initialProviderMode = 'demo' }: WorkbenchPageProps): ReactElement {
  const [providerMode, setProviderMode] = useState<ProviderMode>(initialProviderMode)
  const [demoCaseId, setDemoCaseId] = useState<DemoCaseId>(defaultDemoCaseId)
  const baseUrl = (typeof import.meta !== 'undefined' && import.meta.env?.BASE_URL) || '/'
  const liveCaseUrl = `${baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`}evidence/workbench-case.json`
  const provider = useMemo(
    () => createWorkbenchProvider(providerMode, { demoCaseId, url: liveCaseUrl }),
    [providerMode, demoCaseId, liveCaseUrl],
  )

  const [state, dispatch] = useReducer(workbenchReducer, initialWorkbenchState)
  const [caseV2, setCaseV2] = useState<WorkbenchCaseV2 | null>(null)
  const [sourceLabel, setSourceLabel] = useState<string>(provider.sourceLabel)
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errors, setErrors] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const [compareIds, setCompareIds] = useState<string[]>([])

  function toggleCompare(id: string): void {
    setCompareIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  // Resolve selected benchmark ids to honest comparison rows for the export.
  const comparisonRows: ComparisonRow[] = useMemo(() => {
    if (!compareIds.length) return []
    const byId = new Map(getBenchmarkCatalog().cases.map((c) => [c.id, c]))
    return compareIds
      .map((id) => byId.get(id))
      .filter((c): c is NonNullable<typeof c> => c != null)
      .map((c) => ({
        id: c.id,
        title: c.title,
        truthClass: c.truthClass,
        comparable: isAccuracyComparable(c),
        referenceSolver: c.verification.referenceSolver,
        referenceResultsAvailable: c.verification.referenceResultsAvailable,
        referenceResultsPath: c.verification.referenceResultsPath,
        runnerId: c.verification.runnerId,
      }))
  }, [compareIds])

  const viewerDeepLink = useMemo(
    () => buildViewerUrl(`${baseUrl}src/structure-viewer/index.html`, { memberId: state.selectedMemberId }),
    [baseUrl, state.selectedMemberId],
  )

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
      : 'Live case loaded from the published evidence path. Provenance and checksums describe the source only; the review decision and release readiness are never inferred.'

  return (
    <WorkbenchShell
      dataMode={state.dataMode}
      providerMode={providerMode}
      sourceLabel={sourceLabel}
      claimBoundary={claimBoundary}
      onProviderModeChange={setProviderMode}
      nav={<WorkbenchNav />}
    >
      {/* Primary flow: Model -> Analysis -> Results -> Compare */}
      <div id="wb2-sec-project" className="wb2-section">
        {loadState === 'loading' ? (
          <section className="wb2-panel"><p className="wb2-empty">Loading case…</p></section>
        ) : caseV2 ? (
          <CaseSummary caseV2={caseV2} />
        ) : (
          <section className="wb2-panel">
            <p className="wb2-unavailable" data-wb2-unavailable>
              Case unavailable{errors[0] ? ` (${errors[0]})` : ''}. Nothing is inferred.
              {errors.length > 1 ? ` (+${errors.length - 1} more validation error(s))` : ''}
            </p>
          </section>
        )}
      </div>

      <div id="wb2-sec-model" className="wb2-section">
        {caseV2 ? (
          <ModelViewport
            model={caseV2.model}
            selectedMemberId={state.selectedMemberId}
            onMemberSelected={(id) => dispatch({ type: 'select_member', memberId: id })}
            dataMode={state.dataMode}
            sourcePath={caseV2.provenance.sourcePath}
            sourceCommit={caseV2.provenance.sourceCommitSha}
          />
        ) : (
          <section className="wb2-panel"><h2 className="wb2-panel__title">Model Health</h2><p className="wb2-unavailable" data-wb2-unavailable>No model attached.</p></section>
        )}
      </div>

      <div id="wb2-sec-analysis" className="wb2-section">
        {providerMode === 'demo' ? <CaseSelector selectedId={demoCaseId} onSelect={setDemoCaseId} /> : null}
        {caseV2 ? (
          <AnalysisRibbon runStatus={state.runStatus} analysis={caseV2.analysis} convergenceAvailable={state.convergenceAvailable} />
        ) : (
          <section className="wb2-panel"><h2 className="wb2-panel__title">Analysis</h2><p className="wb2-unavailable" data-wb2-unavailable>No analysis attached.</p></section>
        )}
      </div>

      <div id="wb2-sec-run" className="wb2-section">
        {caseV2 ? (
          <RunMonitor
            runStatus={state.runStatus}
            analysis={caseV2.analysis}
            residualHistory={caseV2.residualHistory}
            convergenceAvailable={state.convergenceAvailable}
          />
        ) : (
          <section className="wb2-panel"><h2 className="wb2-panel__title">Run Monitor</h2><p className="wb2-unavailable" data-wb2-unavailable>No run attached.</p></section>
        )}
      </div>

      <div id="wb2-sec-results" className="wb2-section">
        {caseV2 ? (
          <>
            <ResultSummaryCard caseV2={caseV2} convergenceAvailable={state.convergenceAvailable} />
            <ResidualAuditPanel
              residualHistory={caseV2.residualHistory}
              sourceLabel={sourceLabel}
              residualTolerance={caseV2.analysis?.residualTolerance}
            />
          </>
        ) : (
          <section className="wb2-panel"><h2 className="wb2-panel__title">Results</h2><p className="wb2-unavailable" data-wb2-unavailable>No results attached.</p></section>
        )}
      </div>

      <div id="wb2-sec-compare" className="wb2-section">
        <ComparePanel caseV2={caseV2} rows={comparisonRows} onClear={() => setCompareIds([])} />
      </div>

      {/* Verification layer: Evidence + Benchmarks */}
      <div id="wb2-sec-evidence" className="wb2-section">
        <EvidenceReaderPanel />
      </div>
      <div id="wb2-sec-benchmarks" className="wb2-section">
        <BenchmarkBrowser selectedCompareIds={compareIds} onToggleCompare={toggleCompare} />
      </div>

      {/* Decision: Review + Export */}
      <div id="wb2-sec-review" className="wb2-section">
        <ReviewDecision dataMode={state.dataMode} sourceCommitSha={caseV2?.provenance.sourceCommitSha ?? null} />
      </div>
      <div id="wb2-sec-export" className="wb2-section">
        {caseV2 ? (
          <ExportPanel
            caseV2={caseV2}
            dataMode={state.dataMode}
            runStatus={state.runStatus}
            selectedMemberId={state.selectedMemberId}
            convergenceAvailable={state.convergenceAvailable}
            blockers={warnings}
            comparisonRows={comparisonRows}
            viewerDeepLink={viewerDeepLink}
            baseUrl={baseUrl}
          />
        ) : (
          <section className="wb2-panel"><h2 className="wb2-panel__title">Export</h2><p className="wb2-unavailable" data-wb2-unavailable>Nothing to export until a valid case is loaded.</p></section>
        )}
      </div>

      {warnings.length ? (
        <section className="wb2-panel"><p className="wb2-note wb2-note--warn" data-wb2-warnings>{warnings.join(' · ')}</p></section>
      ) : null}
    </WorkbenchShell>
  )
}

export default WorkbenchPage
