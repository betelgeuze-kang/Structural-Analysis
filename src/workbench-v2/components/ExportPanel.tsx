import type { ReactElement } from 'react'
import type { WorkbenchCaseV2 } from '../model/caseSchema'
import type { DataMode, RunStatus } from '../model/workbenchState'

interface ExportPanelProps {
  caseV2: WorkbenchCaseV2
  dataMode: DataMode
  runStatus: RunStatus
  selectedMemberId: string | null
}

export function ExportPanel({ caseV2, dataMode, runStatus, selectedMemberId }: ExportPanelProps): ReactElement {
  function exportBundle(): void {
    const bundle = {
      schema_version: 'workbench-v2-export.v1',
      data_mode: dataMode,
      is_demo: dataMode === 'demo',
      exported_at: new Date().toISOString(),
      run_status: runStatus,
      provenance: caseV2.provenance,
      model: caseV2.model,
      analysis: caseV2.analysis ?? null,
      selected_member_id: selectedMemberId,
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
