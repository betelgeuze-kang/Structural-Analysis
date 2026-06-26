import type { ReactElement } from 'react'
import type { WorkbenchCaseV2 } from '../model/caseSchema'
import type { DataMode, RunStatus } from '../model/workbenchState'
import { loadDraft } from '../model/reviewDraft'

interface ExportPanelProps {
  caseV2: WorkbenchCaseV2
  dataMode: DataMode
  runStatus: RunStatus
  selectedMemberId: string | null
  convergenceAvailable: boolean
}

export function ExportPanel({ caseV2, dataMode, runStatus, selectedMemberId, convergenceAvailable }: ExportPanelProps): ReactElement {
  function exportBundle(): void {
    const reviewerDraft = loadDraft(caseV2.provenance.sourceCommitSha)
    const bundle = {
      schema_version: 'workbench-v2-export.v1',
      data_mode: dataMode,
      is_demo: dataMode === 'demo',
      exported_at: new Date().toISOString(),
      run_status: runStatus,
      convergence_available: convergenceAvailable,
      // Surface the source checksum + commit at the top level so the export is
      // self-describing without digging into provenance.
      source_path: caseV2.provenance.sourcePath,
      source_sha256: caseV2.provenance.sourceSha256,
      source_commit_sha: caseV2.provenance.sourceCommitSha,
      provenance: caseV2.provenance,
      model: caseV2.model,
      analysis: caseV2.analysis ?? null,
      residual_history: caseV2.residualHistory,
      selected_member_id: selectedMemberId,
      // Human reviewer draft (not an automated verdict). Always present so the
      // export is explicit about whether a person reviewed this snapshot.
      reviewer_draft: reviewerDraft,
      claim_boundary:
        'Workbench v2 export. Values reflect the attached case only and are not a validated verdict. reviewer_draft is a human note, not an automated result.',
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
  }

  return (
    <section className="wb2-panel" aria-labelledby="wb2-export-title">
      <h2 id="wb2-export-title" className="wb2-panel__title">Export</h2>
      <div className="wb2-actions">
        <button type="button" className="wb2-btn" data-wb2-export onClick={exportBundle}>
          Export bundle (JSON)
        </button>
        <span className="wb2-action-hint">
          {dataMode === 'demo' ? 'DEMO bundle' : 'Bundle'} — includes provenance + checksum; not a validated artifact.
        </span>
      </div>
    </section>
  )
}
