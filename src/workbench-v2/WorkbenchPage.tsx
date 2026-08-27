import { useEffect, useMemo, useReducer, useRef, useState, type ReactElement } from 'react'
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
import { CapabilitySupportPanel } from './components/CapabilitySupportPanel'
import { JobServicePanel } from './components/JobServicePanel'
import { EquationScalingPanel } from './components/EquationScalingPanel'
import { NativeFrameArtifactsPanel } from './components/NativeFrameArtifactsPanel'
import { NativeFrameRunPanel } from './components/NativeFrameRunPanel'
import type { ComparisonRow } from './components/ExportPanel'
import { getBenchmarkCatalog, isAccuracyComparable } from './model/benchmark/benchmarkSchema'
import { buildViewerUrl } from './model/viewerBridge'
import {
  loadReviewDraftState,
  updateReviewDraftState,
  type ReviewDraft,
  type ReviewDraftState,
} from './model/reviewDraft'
import { loadWorkbenchJob, type JobLoadResult } from './model/jobProvider'
import {
  loadNativeFrameBundle,
  loadNativeFrameJob,
  loadNativeFrameArtifacts,
  type NativeFrameLoadResult,
} from './model/nativeFrameProvider'
import {
  loadNativeFrameComparison,
  type NativeFrameComparisonLoadResult,
} from './model/nativeFrameComparisonProvider'

export interface WorkbenchPageProps {
  initialProviderMode?: ProviderMode
  /** Same-origin authenticated status endpoint; no bearer credential is stored in the browser. */
  jobStatusUrl?: string
  /** Same-origin canonical bounded native Frame3D ResultIR artifact. */
  nativeFrameResultUrl?: string
  /** Same-origin canonical ReportIR; when configured it must bind exactly to the ResultIR. */
  nativeFrameReportUrl?: string
  /** Same-origin completed CLI bundle manifest; mutually exclusive with direct artifact URLs. */
  nativeFrameBundleUrl?: string
  /** Same-origin read-only native Frame3D job view; mutually exclusive with artifact URLs. */
  nativeFrameJobUrl?: string
  /** Same-origin loopback native Frame3D submission collection endpoint. */
  nativeFrameSubmissionUrl?: string
  /** Same-origin external ReferenceIR; configured atomically with ComparisonIR. */
  nativeFrameReferenceUrl?: string
  /** Same-origin source-bound ComparisonIR; configured atomically with ReferenceIR. */
  nativeFrameComparisonUrl?: string
}

type LoadState = 'loading' | 'ready' | 'invalid' | 'missing' | 'error'

export function WorkbenchPage({
  initialProviderMode = 'demo',
  jobStatusUrl,
  nativeFrameResultUrl,
  nativeFrameReportUrl,
  nativeFrameBundleUrl,
  nativeFrameJobUrl,
  nativeFrameSubmissionUrl,
  nativeFrameReferenceUrl,
  nativeFrameComparisonUrl,
}: WorkbenchPageProps): ReactElement {
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
  const [jobLoad, setJobLoad] = useState<JobLoadResult>({
    status: jobStatusUrl ? 'loading' : 'unconfigured',
    job: null,
    errors: [],
  })
  const [nativeFrameLoad, setNativeFrameLoad] = useState<NativeFrameLoadResult>({
    status: nativeFrameJobUrl || nativeFrameBundleUrl || nativeFrameResultUrl ? 'loading' : nativeFrameReportUrl ? 'invalid' : 'unconfigured',
    artifactStatus: nativeFrameJobUrl || nativeFrameBundleUrl || nativeFrameResultUrl ? 'not_configured' : nativeFrameReportUrl ? 'invalid' : 'not_configured',
    resultIr: null,
    reportIr: null,
    elementRecovery: null,
    errors: nativeFrameReportUrl && !nativeFrameResultUrl
      ? ['native Frame3D report URL requires a result URL']
      : [],
  })
  const [selectedNativeFrameMemberId, setSelectedNativeFrameMemberId] = useState<string | null>(null)
  const [submittedNativeFrameJobUrl, setSubmittedNativeFrameJobUrl] = useState<string>()
  const effectiveNativeFrameJobUrl = submittedNativeFrameJobUrl ?? nativeFrameJobUrl
  const [nativeFrameComparisonLoad, setNativeFrameComparisonLoad] = useState<NativeFrameComparisonLoadResult>({
    status: nativeFrameReferenceUrl || nativeFrameComparisonUrl ? 'loading' : 'unconfigured',
    referenceIr: null,
    comparisonIr: null,
    errors: [],
  })
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [reviewDraftStates, setReviewDraftStates] = useState<ReadonlyMap<string, ReviewDraftState>>(
    () => new Map(),
  )
  const reviewDraftStatesRef = useRef<ReadonlyMap<string, ReviewDraftState>>(reviewDraftStates)

  const reviewSourceCommitSha = caseV2?.provenance.sourceCommitSha ?? null

  const reviewDraftState = useMemo(() => {
    if (!reviewSourceCommitSha) return null
    return reviewDraftStates.get(reviewSourceCommitSha) ?? null
  }, [reviewDraftStates, reviewSourceCommitSha])

  useEffect(() => {
    setSelectedNativeFrameMemberId(null)
  }, [nativeFrameLoad.resultIr?.result_hash])

  function updateReviewDraft(patch: Partial<ReviewDraft>): void {
    if (!reviewSourceCommitSha) return
    const current = reviewDraftStatesRef.current.get(reviewSourceCommitSha)
      ?? loadReviewDraftState(reviewSourceCommitSha)
    const next = new Map(reviewDraftStatesRef.current)
    next.set(reviewSourceCommitSha, updateReviewDraftState(current, patch))
    reviewDraftStatesRef.current = next
    setReviewDraftStates(next)
  }

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
          const reviewCommitSha = res.caseV2.provenance.sourceCommitSha
          if (!reviewDraftStatesRef.current.has(reviewCommitSha)) {
            const nextReviewStates = new Map(reviewDraftStatesRef.current)
            nextReviewStates.set(reviewCommitSha, loadReviewDraftState(reviewCommitSha))
            reviewDraftStatesRef.current = nextReviewStates
            setReviewDraftStates(nextReviewStates)
          }
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

  useEffect(() => {
    if (!jobStatusUrl) {
      setJobLoad({ status: 'unconfigured', job: null, errors: [] })
      return undefined
    }
    const controller = new AbortController()
    setJobLoad({ status: 'loading', job: null, errors: [] })
    loadWorkbenchJob(jobStatusUrl, controller.signal).then(setJobLoad)
    return () => controller.abort()
  }, [jobStatusUrl])

  useEffect(() => {
    const controller = new AbortController()
    const configuredSources = [
      Boolean(effectiveNativeFrameJobUrl),
      Boolean(nativeFrameBundleUrl),
      Boolean(nativeFrameResultUrl || nativeFrameReportUrl),
    ].filter(Boolean).length
    if (configuredSources > 1) {
      setNativeFrameLoad({
        status: 'invalid',
        artifactStatus: 'invalid',
        resultIr: null,
        reportIr: null,
        elementRecovery: null,
        errors: ['native Frame3D job, bundle and direct artifact URLs are mutually exclusive'],
      })
      return () => controller.abort()
    }
    if (effectiveNativeFrameJobUrl || nativeFrameBundleUrl || nativeFrameResultUrl) {
      setNativeFrameLoad({
        status: 'loading',
        artifactStatus: 'not_configured',
        resultIr: null,
        reportIr: null,
        elementRecovery: null,
        errors: [],
      })
    }
    const request = effectiveNativeFrameJobUrl
      ? loadNativeFrameJob(effectiveNativeFrameJobUrl, controller.signal)
      : nativeFrameBundleUrl
        ? loadNativeFrameBundle(nativeFrameBundleUrl, controller.signal)
        : loadNativeFrameArtifacts(nativeFrameResultUrl, nativeFrameReportUrl, controller.signal)
    request
      .then(setNativeFrameLoad)
    return () => controller.abort()
  }, [effectiveNativeFrameJobUrl, nativeFrameBundleUrl, nativeFrameResultUrl, nativeFrameReportUrl])

  useEffect(() => {
    const controller = new AbortController()
    if (!nativeFrameReferenceUrl && !nativeFrameComparisonUrl) {
      setNativeFrameComparisonLoad({ status: 'unconfigured', referenceIr: null, comparisonIr: null, errors: [] })
      return () => controller.abort()
    }
    if (!nativeFrameReferenceUrl || !nativeFrameComparisonUrl) {
      setNativeFrameComparisonLoad({
        status: 'invalid', referenceIr: null, comparisonIr: null,
        errors: ['native Frame3D ReferenceIR and ComparisonIR URLs must be configured together'],
      })
      return () => controller.abort()
    }
    if (nativeFrameLoad.status === 'loading') {
      setNativeFrameComparisonLoad({ status: 'loading', referenceIr: null, comparisonIr: null, errors: [] })
      return () => controller.abort()
    }
    if (nativeFrameLoad.status !== 'ready' || !nativeFrameLoad.resultIr) {
      setNativeFrameComparisonLoad({
        status: 'invalid', referenceIr: null, comparisonIr: null,
        errors: ['native Frame3D comparison requires a verified ResultIR'],
      })
      return () => controller.abort()
    }
    setNativeFrameComparisonLoad({ status: 'loading', referenceIr: null, comparisonIr: null, errors: [] })
    loadNativeFrameComparison(
      nativeFrameLoad.resultIr,
      nativeFrameReferenceUrl,
      nativeFrameComparisonUrl,
      controller.signal,
    ).then(setNativeFrameComparisonLoad)
    return () => controller.abort()
  }, [nativeFrameLoad.status, nativeFrameLoad.resultIr, nativeFrameReferenceUrl, nativeFrameComparisonUrl])

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
          <>
            <AnalysisRibbon runStatus={state.runStatus} analysis={caseV2.analysis} convergenceAvailable={state.convergenceAvailable} />
            <EquationScalingPanel analysis={caseV2.analysis} />
          </>
        ) : (
          <section className="wb2-panel"><h2 className="wb2-panel__title">Analysis</h2><p className="wb2-unavailable" data-wb2-unavailable>No analysis attached.</p></section>
        )}
      </div>

      <div id="wb2-sec-run" className="wb2-section">
        <NativeFrameRunPanel
          submissionUrl={nativeFrameSubmissionUrl}
          onJobAvailable={setSubmittedNativeFrameJobUrl}
        />
        <JobServicePanel
          loadStatus={jobLoad.status}
          job={jobLoad.job}
          errors={jobLoad.errors}
          artifactStatus={jobLoad.artifactStatus}
          engineeringResultIr={jobLoad.engineeringResultIr}
        />
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
        <NativeFrameArtifactsPanel
          load={nativeFrameLoad}
          comparisonLoad={nativeFrameComparisonLoad}
          selectedMemberId={selectedNativeFrameMemberId}
          onMemberSelected={setSelectedNativeFrameMemberId}
        />
        {caseV2 ? (
          <>
            <ResultSummaryCard caseV2={caseV2} convergenceAvailable={state.convergenceAvailable} />
            <ResidualAuditPanel
              residualHistory={caseV2.residualHistory}
              sourceLabel={sourceLabel}
              residualTolerance={caseV2.analysis?.residualTolerance}
              converged={caseV2.analysis?.converged ?? { status: 'unavailable' }}
            />
          </>
        ) : (
          <section className="wb2-panel"><h2 className="wb2-panel__title">Results</h2><p className="wb2-unavailable" data-wb2-unavailable>No results attached.</p></section>
        )}
      </div>

      <div id="wb2-sec-compare" className="wb2-section">
        <ComparePanel caseV2={caseV2} rows={comparisonRows} onClear={() => setCompareIds([])} />
      </div>

      {/* Verification layer: capabilities + evidence + benchmarks */}
      <div id="wb2-sec-capabilities" className="wb2-section">
        <CapabilitySupportPanel />
      </div>
      <div id="wb2-sec-evidence" className="wb2-section">
        <EvidenceReaderPanel />
      </div>
      <div id="wb2-sec-benchmarks" className="wb2-section">
        <BenchmarkBrowser selectedCompareIds={compareIds} onToggleCompare={toggleCompare} />
      </div>

      {/* Decision: Review + Export */}
      <div id="wb2-sec-review" className="wb2-section">
        {caseV2 && !reviewDraftState ? (
          <section className="wb2-panel" aria-labelledby="wb2-verdict-title">
            <h2 id="wb2-verdict-title" className="wb2-panel__title">Review decision</h2>
            <p className="wb2-empty" role="status" data-wb2-review-loading>
              Loading reviewer draft persistence…
            </p>
          </section>
        ) : (
          <ReviewDecision
            dataMode={state.dataMode}
            draftState={reviewDraftState}
            onDraftChange={updateReviewDraft}
          />
        )}
      </div>
      <div id="wb2-sec-export" className="wb2-section">
        {caseV2 && reviewDraftState ? (
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
            reviewDraftState={reviewDraftState}
          />
        ) : caseV2 ? (
          <section className="wb2-panel" aria-labelledby="wb2-export-title">
            <h2 id="wb2-export-title" className="wb2-panel__title">Export</h2>
            <p className="wb2-empty" role="status" data-wb2-export-loading>
              Export remains unavailable until reviewer draft persistence is loaded.
            </p>
          </section>
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
