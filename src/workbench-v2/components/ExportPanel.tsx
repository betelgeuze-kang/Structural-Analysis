import { useState, type ReactElement } from 'react'
import type { WorkbenchCaseV2 } from '../model/caseSchema'
import type { DataMode, RunStatus } from '../model/workbenchState'
import { loadDraft } from '../model/reviewDraft'
import { canonicalJson, sha256Hex } from '../model/checksum'
import { evidenceManifestUrl, type EvidenceManifest } from '../model/evidence/evidenceSources'

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
}: ExportPanelProps): ReactElement {
  const [busy, setBusy] = useState(false)

  async function exportBundle(): Promise<void> {
    setBusy(true)
    try {
      const reviewerDraft = loadDraft(caseV2.provenance.sourceCommitSha)
      // Checksum computed in-browser over the canonical analysis payload so the
      // export can be integrity-checked; null when Web Crypto is unavailable.
      const analysisResultSha256 = await sha256Hex(
        canonicalJson({ analysis: caseV2.analysis ?? null, residualHistory: caseV2.residualHistory }),
      )
      const evidenceManifest = await loadEvidenceManifestRef(baseUrl)

      const bundle = {
        schema_version: 'workbench-v2-export.v2',
        data_mode: dataMode,
        is_demo: dataMode === 'demo',
        exported_at: new Date().toISOString(),
        run_status: runStatus,
        convergence_available: convergenceAvailable,
        source_path: caseV2.provenance.sourcePath,
        source_sha256: caseV2.provenance.sourceSha256,
        source_commit_sha: caseV2.provenance.sourceCommitSha,
        analysis_result_sha256: analysisResultSha256,
        provenance: caseV2.provenance,
        model: caseV2.model,
        analysis: caseV2.analysis ?? null,
        residual_history: caseV2.residualHistory,
        selected_member_id: selectedMemberId,
        viewer_deep_link: viewerDeepLink,
        // Blockers exactly as displayed — never silently dropped.
        displayed_blockers: blockers,
        // Reviewer-selected comparison rows (may be empty).
        selected_comparison_rows: comparisonRows,
        // Reference to the published evidence manifest, by checksum + commit.
        evidence_manifest: evidenceManifest,
        // Human reviewer draft (not an automated verdict).
        reviewer_draft: reviewerDraft,
        claim_boundary:
          'Workbench v2 export. Values reflect the attached case only and are not a validated verdict. evidence_manifest and checksums are references for integrity, not a pass/fail result; reviewer_draft is a human note.',
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
      <ul className="wb2-export-contents" aria-label="Export contents">
        <li>provenance + source checksum + analysis result checksum</li>
        <li>displayed blockers ({blockers.length})</li>
        <li>selected comparison rows ({comparisonRows.length})</li>
        <li>viewer deep link + reviewer draft</li>
        <li>evidence manifest reference (checksum + commit, if published)</li>
      </ul>
      <div className="wb2-actions">
        <button type="button" className="wb2-btn" data-wb2-export disabled={busy} onClick={() => void exportBundle()}>
          {busy ? 'Preparing…' : 'Export bundle (JSON)'}
        </button>
        <span className="wb2-action-hint">
          {dataMode === 'demo' ? 'DEMO bundle' : 'Bundle'} — references + checksums for integrity; not a validated artifact.
        </span>
      </div>
    </section>
  )
}
