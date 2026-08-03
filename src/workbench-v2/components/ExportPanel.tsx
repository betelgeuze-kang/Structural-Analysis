import { useState, type ReactElement } from 'react'
import { isAvailableValue, type WorkbenchCaseV2 } from '../model/caseSchema'
import type { DataMode, RunStatus } from '../model/workbenchState'
import {
  reviewDraftPersistenceMetadata,
  type ReviewDraftState,
} from '../model/reviewDraft'
import { canonicalJson, sha256Hex } from '../model/checksum'
import { evidenceManifestUrl, type EvidenceManifest } from '../model/evidence/evidenceSources'
import { BooleanEvidenceValueText, EvidenceValueText } from './EngineeringValueText'

export interface ComparisonRow {
  id: string
  title: string
  truthClass: string
  comparable: boolean
  referenceSolver: string | null
  referenceResultsAvailable: boolean
  referenceResultsPath: string | null
  runnerId: string | null
}

interface ExportPanelProps {
  caseV2: WorkbenchCaseV2
  dataMode: DataMode
  runStatus: RunStatus
  selectedMemberId: string | null
  convergenceAvailable: boolean
  /** Blockers currently displayed in the UI (validation warnings, etc.). */
  blockers: string[]
  /** Benchmark rows the reviewer selected for comparison. */
  comparisonRows: ComparisonRow[]
  /** Deep link into the viewer for the current selection. */
  viewerDeepLink: string
  /** Base URL used to locate the published evidence manifest. */
  baseUrl: string
  /** Exact in-memory reviewer draft and its fail-closed persistence receipt. */
  reviewDraftState: ReviewDraftState
}

interface EvidenceManifestRef {
  status: 'attached' | 'unavailable'
  source_commit_sha: string | null
  artifact_count: number | null
  manifest_sha256: string | null
  detail?: string
}

async function loadEvidenceManifestRef(baseUrl: string): Promise<EvidenceManifestRef> {
  try {
    const res = await fetch(evidenceManifestUrl(baseUrl), { cache: 'no-store' })
    if (!res.ok) return { status: 'unavailable', source_commit_sha: null, artifact_count: null, manifest_sha256: null, detail: `HTTP ${res.status}` }
    const manifest = (await res.json()) as EvidenceManifest
    const digest = await sha256Hex(canonicalJson(manifest))
    return {
      status: 'attached',
      source_commit_sha: manifest.source_commit_sha ?? null,
      artifact_count: Array.isArray(manifest.artifacts) ? manifest.artifacts.length : null,
      manifest_sha256: digest,
    }
  } catch (error) {
    return { status: 'unavailable', source_commit_sha: null, artifact_count: null, manifest_sha256: null, detail: String((error as Error)?.message ?? error) }
  }
}

function productProvenanceIssues(caseV2: WorkbenchCaseV2, dataMode: DataMode): string[] {
  if (dataMode === 'demo') return []
  const issues: string[] = []
  if (!/^[0-9a-f]{40}$/.test(caseV2.provenance.sourceCommitSha)) {
    issues.push('source commit SHA is missing or not exact')
  }
  if (!caseV2.provenance.engineVersion || caseV2.provenance.engineVersion === 'unknown') {
    issues.push('engine build identity is unavailable')
  }
  const generatedAt = Date.parse(caseV2.provenance.generatedAt)
  if (!Number.isFinite(generatedAt) || caseV2.provenance.generatedAt === 'unknown') {
    issues.push('generated timestamp is unavailable or invalid')
  }
  if (!isAvailableValue(caseV2.productProfile.id)
      || !isAvailableValue(caseV2.productProfile.public)
      || !isAvailableValue(caseV2.productProfile.releaseEligible)) {
    issues.push('product profile authority is unavailable')
  }
  return issues
}

export function ExportPanel({
  caseV2,
  dataMode,
  runStatus,
  selectedMemberId,
  convergenceAvailable,
  blockers,
  comparisonRows,
  viewerDeepLink,
  baseUrl,
  reviewDraftState,
}: ExportPanelProps): ReactElement {
  const [busy, setBusy] = useState(false)
  const provenanceIssues = productProvenanceIssues(caseV2, dataMode)
  const exportAllowed = provenanceIssues.length === 0

  async function exportBundle(): Promise<void> {
    if (!exportAllowed) return
    setBusy(true)
    try {
      const evidenceManifest = await loadEvidenceManifestRef(baseUrl)
      const immutableAnalysisCore = {
        schema_version: 'workbench-v2-immutable-analysis-core.v1',
        source_path: caseV2.provenance.sourcePath,
        source_sha256: caseV2.provenance.sourceSha256,
        source_commit_sha: caseV2.provenance.sourceCommitSha,
        engine_version: caseV2.provenance.engineVersion,
        generated_at: caseV2.provenance.generatedAt,
        provenance: caseV2.provenance,
        model: caseV2.model,
        analysis: caseV2.analysis ?? null,
        residual_history: caseV2.residualHistory,
        product_profile: caseV2.productProfile,
      }
      const immutableAnalysisCoreSha256 = await sha256Hex(
        canonicalJson(immutableAnalysisCore),
      )
      const reviewEnvelope = {
        schema_version: 'workbench-v2-review-envelope.v1',
        data_mode: dataMode,
        is_demo: dataMode === 'demo',
        run_status: runStatus,
        convergence_available: convergenceAvailable,
        selected_member_id: selectedMemberId,
        viewer_deep_link: viewerDeepLink,
        displayed_blockers: blockers,
        selected_comparison_rows: comparisonRows,
        evidence_manifest: evidenceManifest,
        reviewer_draft: reviewDraftState.draft,
        reviewer_draft_persistence: reviewDraftPersistenceMetadata(reviewDraftState.receipt),
      }
      const reviewEnvelopeSha256 = await sha256Hex(canonicalJson(reviewEnvelope))
      const bundle = {
        schema_version: 'workbench-v2-export.v3',
        exported_at: new Date().toISOString(),
        immutable_analysis_core: immutableAnalysisCore,
        immutable_analysis_core_sha256: immutableAnalysisCoreSha256,
        review_envelope: reviewEnvelope,
        review_envelope_sha256: reviewEnvelopeSha256,
        // Compatibility fields remain explicit while consumers migrate to the
        // separately hashed immutable core and human review envelope.
        data_mode: dataMode,
        is_demo: dataMode === 'demo',
        run_status: runStatus,
        convergence_available: convergenceAvailable,
        source_path: caseV2.provenance.sourcePath,
        source_sha256: caseV2.provenance.sourceSha256,
        source_commit_sha: caseV2.provenance.sourceCommitSha,
        analysis_result_sha256: immutableAnalysisCoreSha256,
        provenance: caseV2.provenance,
        model: caseV2.model,
        analysis: caseV2.analysis ?? null,
        residual_history: caseV2.residualHistory,
        product_profile: caseV2.productProfile,
        selected_member_id: selectedMemberId,
        viewer_deep_link: viewerDeepLink,
        displayed_blockers: blockers,
        selected_comparison_rows: comparisonRows,
        evidence_manifest: evidenceManifest,
        reviewer_draft: reviewDraftState.draft,
        reviewer_draft_persistence: reviewDraftPersistenceMetadata(reviewDraftState.receipt),
        provenance_contract: {
          status: 'available',
          issues: [],
        },
        claim_boundary:
          'Workbench v2 export. immutable_analysis_core is the solver-produced evidence projection; review_envelope is the human review context. Their checksums are integrity references, not a validated verdict or signature. reviewer_draft remains a human note and reviewer_draft_persistence states whether that exact in-memory note was saved.',
      }
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'workbench_v2_bundle.json'
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="wb2-panel" aria-labelledby="wb2-export-title">
      <h2 id="wb2-export-title" className="wb2-panel__title">Export</h2>
      <dl className="wb2-kv" data-export-truth-state>
        <dt>Product profile</dt><dd>
          <EvidenceValueText value={caseV2.productProfile.id} format={(value) => value} />
        </dd>
        <dt>Public profile</dt><dd><BooleanEvidenceValueText value={caseV2.productProfile.public} /></dd>
        <dt>Release eligible</dt><dd>
          <BooleanEvidenceValueText value={caseV2.productProfile.releaseEligible} />
        </dd>
        <dt>Analysis status</dt><dd>{caseV2.analysis?.status ?? 'not_run'}</dd>
        <dt>Converged</dt><dd>
          <BooleanEvidenceValueText value={caseV2.analysis?.converged ?? { status: 'unavailable' }} />
        </dd>
      </dl>
      {provenanceIssues.length > 0 ? (
        <div className="wb2-callout wb2-callout--warning" data-export-provenance-blocked>
          Product export blocked: {provenanceIssues.join('; ')}.
        </div>
      ) : null}
      <ul className="wb2-export-contents" aria-label="Export contents">
        <li>separately hashed immutable analysis core + human review envelope</li>
        <li>provenance + source checksum + exact source commit</li>
        <li>displayed blockers ({blockers.length})</li>
        <li>selected comparison rows ({comparisonRows.length})</li>
        <li>viewer deep link + reviewer draft + persistence receipt</li>
        <li>evidence manifest reference (checksum + commit, if published)</li>
      </ul>
      <div className="wb2-actions">
        <button type="button" className="wb2-btn" data-wb2-export disabled={busy || !exportAllowed} onClick={() => void exportBundle()}>
          {busy ? 'Preparing…' : 'Export bundle (JSON)'}
        </button>
        <span className="wb2-action-hint">
          {dataMode === 'demo' ? 'DEMO bundle' : 'Bundle'} — references + checksums for integrity; not a validated artifact.
        </span>
      </div>
    </section>
  )
}
