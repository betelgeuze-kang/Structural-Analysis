import type { ReactElement } from 'react'
import type { DataMode } from '../model/workbenchState'
import { StateChip } from './StateChip'

/**
 * Review decision panel. There is intentionally no automated verdict: a
 * demo/live-without-evidence dataset shows UNAVAILABLE, never an inferred PASS.
 */
export function ReviewDecision({ dataMode }: { dataMode: DataMode }): ReactElement {
  const note =
    dataMode === 'demo'
      ? 'Demo data with no solver evidence — a PASS/REVIEW/FAIL result is never inferred here.'
      : 'No verdict is shown unless it is present in attached evidence; it is never defaulted to PASS.'

  return (
    <section className="wb2-panel" aria-labelledby="wb2-verdict-title">
      <h2 id="wb2-verdict-title" className="wb2-panel__title">Review decision</h2>
      <StateChip state="UNAVAILABLE" srLabel="Automated verdict" />
      <p className="wb2-note">{note}</p>
    </section>
  )
}
