import type { ReactElement } from 'react'
import type { WorkbenchModel } from '../model/caseSchema'
import { StateChip, mapCheckState } from './StateChip'

export function CaseSummary({ model }: { model: WorkbenchModel }): ReactElement {
  const meta = [model.case.label, model.case.structureFamily, model.case.loadCombination].filter(
    (v): v is string => typeof v === 'string' && v.trim() !== '',
  )

  const statusRows = [
    { label: 'Solver connection', value: model.status.solverConnected, raw: String(model.status.solverConnected) },
    { label: 'P0 gate', value: model.status.p0, raw: model.status.p0 ?? '—' },
    { label: 'P1 gate', value: model.status.p1, raw: model.status.p1 ?? '—' },
    { label: 'GPU / HIP', value: model.status.gpu, raw: model.status.gpu ?? '—' },
  ]

  return (
    <section className="wb2-panel" aria-labelledby="wb2-summary-title">
      <h2 id="wb2-summary-title" className="wb2-panel__title">Case summary</h2>
      <h3 className="wb2-project-name">{model.project.name ?? 'Untitled project'}</h3>
      <p className="wb2-project-meta">{meta.length ? meta.join(' · ') : 'No case metadata'}</p>

      <ul className="wb2-status-list" aria-label="Readiness status">
        {statusRows.map((row) => (
          <li key={row.label} className="wb2-status-row">
            <span className="wb2-status-label">{row.label}</span>
            <span className="wb2-status-raw">{row.raw}</span>
            <StateChip state={mapCheckState(row.value)} srLabel={row.label} />
          </li>
        ))}
      </ul>
    </section>
  )
}
