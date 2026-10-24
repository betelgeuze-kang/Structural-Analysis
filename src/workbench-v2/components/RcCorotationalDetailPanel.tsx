import { useEffect, useId, useRef, useState, type ReactElement } from 'react'
import type { RcCorotationalReportReview } from '../model/rcCorotationalReportReview'
import type { RcCorotationalDetailSummary, RcCorotationalDetailMemberView, RcCorotationalDetailSectionView,
  RcCorotationalDetailFiber, RcCorotationalSectionHistory, RcCorotationalFiberHistory } from '../model/rcCorotationalDetailReport'
import { RcHistoryPlot } from './RcResultVisualization'

const PAGE_SIZE = 20
export function RcCorotationalDetailPanel({ review, index, selectedMember, onSelectMember, onSelectState }: {
  review: RcCorotationalReportReview; index: number; selectedMember: string
  onSelectMember: (member: string) => void; onSelectState: (state: number) => void
}): ReactElement {
  const fieldId = useId()
  const [summary, setSummary] = useState<RcCorotationalDetailSummary | null>(null)
  const [opening, setOpening] = useState(false), [message, setMessage] = useState('')
  const [memberValue, setMember] = useState<{ key: string; value: RcCorotationalDetailMemberView } | null>(null)
  const [point, setPoint] = useState(0), [fiberText, setFiberText] = useState('0')
  const [sectionValue, setSection] = useState<{ key: string; value: RcCorotationalDetailSectionView } | null>(null)
  const [fiberValue, setFiber] = useState<{ key: string; value: RcCorotationalDetailFiber } | null>(null)
  const [sectionPageValue, setSectionPage] = useState<{ key: string; value: RcCorotationalSectionHistory[] } | null>(null)
  const [fiberPageValue, setFiberPage] = useState<{ key: string; value: RcCorotationalFiberHistory[] } | null>(null)
  const generation = useRef(0), urls = useRef(new Set<string>())
  const historyStart = Math.floor(index / PAGE_SIZE) * PAGE_SIZE
  const fiberIndex = /^(?:0|[1-9]\d*)$/.test(fiberText) ? Number(fiberText) : NaN
  const memberKey = JSON.stringify([index, selectedMember]), sectionKey = JSON.stringify([index, selectedMember, point])
  const fiberKey = JSON.stringify([index, selectedMember, point, fiberIndex])
  const sectionPageKey = JSON.stringify([historyStart, selectedMember, point]), fiberPageKey = JSON.stringify([historyStart, selectedMember, point, fiberIndex])
  const member = memberValue?.key === memberKey ? memberValue.value : null
  const section = sectionValue?.key === sectionKey ? sectionValue.value : null
  const fiber = fiberValue?.key === fiberKey ? fiberValue.value : null
  const sectionPage = sectionPageValue?.key === sectionPageKey ? sectionPageValue.value : null
  const fiberPage = fiberPageValue?.key === fiberPageKey ? fiberPageValue.value : null
  const validFiber = !!section && Number.isSafeInteger(fiberIndex) && fiberIndex < section.fiberCount
  useEffect(() => {
    generation.current++; setSummary(null); setOpening(false); setMessage(''); setMember(null); setSection(null); setFiber(null)
    return () => { generation.current++; for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear() }
  }, [review])
  useEffect(() => { setPoint(0); setFiberText('0') }, [selectedMember])
  useEffect(() => { setFiberText('0') }, [point])
  useEffect(() => {
    let active = true; setMember(null); setMessage('')
    if (summary && selectedMember && review.detailMember) review.detailMember(index, selectedMember)
      .then(value => { if (active) setMember({ key: memberKey, value }) })
      .catch(() => { if (active) setMessage('Stored member details are unavailable. The verified nodal report remains available.') })
    return () => { active = false }
  }, [review, summary, index, selectedMember])
  useEffect(() => {
    let active = true; setSection(null)
    if (summary && member && review.detailSection) review.detailSection(index, selectedMember, point)
      .then(value => { if (active) setSection({ key: sectionKey, value }) })
      .catch(() => { if (active) setMessage('The selected stored section is unavailable.') })
    return () => { active = false }
  }, [review, summary, member, index, selectedMember, point])
  useEffect(() => {
    let active = true; setFiber(null)
    if (summary && validFiber && review.detailFiber) review.detailFiber(index, selectedMember, point, fiberIndex)
      .then(value => { if (active) setFiber({ key: fiberKey, value }) })
      .catch(() => { if (active) setMessage('The selected stored fiber is unavailable.') })
    return () => { active = false }
  }, [review, summary, validFiber, index, selectedMember, point, fiberIndex])
  useEffect(() => {
    let active = true; setSectionPage(null)
    if (summary && selectedMember && review.detailSectionPage) review.detailSectionPage(selectedMember, point, historyStart, PAGE_SIZE)
      .then(rows => { if (active) setSectionPage({ key: sectionPageKey, value: rows }) })
      .catch(() => { if (active) setMessage('The stored section history page is unavailable.') })
    return () => { active = false }
  }, [review, summary, selectedMember, point, historyStart])
  useEffect(() => {
    let active = true; setFiberPage(null)
    if (summary && validFiber && review.detailFiberPage) review.detailFiberPage(selectedMember, point, fiberIndex, historyStart, PAGE_SIZE)
      .then(rows => { if (active) setFiberPage({ key: fiberPageKey, value: rows }) })
      .catch(() => { if (active) setMessage('The stored fiber history page is unavailable.') })
    return () => { active = false }
  }, [review, summary, validFiber, selectedMember, point, fiberIndex, historyStart])
  async function open(): Promise<void> {
    if (opening || !review.openDetails) return
    const own = generation.current; setOpening(true); setMessage('')
    try {
      const value = await review.openDetails()
      if (own !== generation.current) return
      setSummary(value)
      if (!value.members.some(row => row.member_id === selectedMember)) onSelectMember(value.members[0]?.member_id ?? '')
    } catch { if (own === generation.current) setMessage('Stored member, section and fiber details are unavailable or could not be verified. The verified nodal report remains available.') }
    finally { if (own === generation.current) setOpening(false) }
  }
  async function download(): Promise<void> {
    if (!summary || !review.detailDownload) return
    const own = generation.current
    try {
      const blob = await review.detailDownload()
      if (own !== generation.current) return
      const url = URL.createObjectURL(blob), anchor = document.createElement('a')
      urls.current.add(url); anchor.href = url; anchor.download = `${summary.reportId}-corotational-detail-report.json`
      document.body.append(anchor); anchor.click(); anchor.remove()
      setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url) }, 0)
    } catch { if (own === generation.current) setMessage('The exact stored detail report could not be downloaded.') }
  }
  return <section data-rc-corotational-details={summary ? 'verified' : opening ? 'loading' : 'closed'} aria-label="Stored member, section and fiber details" style={{ minWidth: 0, maxWidth: '100%' }}>
    <h4>Stored member, section and fiber details</h4>
    {!summary ? <>
      <p data-rc-corotational-member-unavailable>Member end forces, section moment–curvature and fiber stress–strain are unavailable in this saved nodal report. Open the separate stored detail report to inspect them when available.</p>
      <button type="button" disabled={opening || !review.openDetails} onClick={() => void open()}>Open stored RC details</button>
    </> : <>
      <p>Read from the saved accepted responses, including gravity preload and subdivisions. No analysis is run. Member endpoints and integration points keep their authored order.</p>
      <p data-rc-corotational-detail-report-id style={{ overflowWrap: 'anywhere' }}>{summary.reportId}</p>
      <label htmlFor={`${fieldId}-member`}>Detail member</label>{' '}
      <select id={`${fieldId}-member`} value={selectedMember} style={{ maxWidth: '100%' }} onChange={event => onSelectMember(event.target.value)}>
        <option value="">Choose a member</option>{summary.members.map(row => <option key={row.member_id} value={row.member_id}>{row.member_id}: {row.node_i} → {row.node_j}</option>)}
      </select>
      {!selectedMember ? <p>Select a member to inspect its stored response.</p> : !member ? <p role="status">Loading stored member response…</p> : <>
        <p data-rc-detail-member>Accepted state {index} · {member.member_id}: {member.node_i} → {member.node_j}. Initial length {member.initial_length_m} m; current length {member.current_length_m} m.</p>
        <div role="region" aria-label="Stored member endpoint forces" tabIndex={0} style={{ overflowX: 'auto', maxWidth: '100%' }}>
          <table className="wb2-table" data-rc-detail-force-table><caption>Stored member endpoint forces · accepted state {index}</caption>
            <thead><tr><th scope="col">Frame</th><th scope="col">End</th><th scope="col">FX (kN)</th><th scope="col">FY (kN)</th><th scope="col">MZ (kN*m)</th></tr></thead>
            <tbody>{(['global', 'local'] as const).flatMap(frame => [0, 3].map(offset => <tr key={`${frame}:${offset}`} data-rc-detail-force={`${frame}:${offset ? 'j' : 'i'}`}>
              <th scope="row">{frame === 'global' ? 'Global XY' : 'Current local xy'}</th><td>{offset ? `j: ${member.node_j}` : `i: ${member.node_i}`}</td>
              {member[frame === 'global' ? 'end_force_global_kn_knm' : 'end_force_local_kn_knm'].slice(offset, offset + 3).map((value, component) => <td key={component}>{String(value)}</td>)}
            </tr>))}</tbody>
          </table>
        </div>
        <p>Local x follows the current chord i→j; local y is its counterclockwise normal. Current direction: ({member.current_direction.map(String).join(', ')}). Local forces rotate the stored global endpoint forces; MZ is unchanged. Endpoint signs are work-conjugate nodal signs, not a continuous internal-force diagram.</p>
        <label htmlFor={`${fieldId}-point`}>Detail integration point</label>{' '}
        <select id={`${fieldId}-point`} value={point} style={{ maxWidth: '100%' }} onChange={event => setPoint(Number(event.target.value))}>
          {member.sections.map(row => <option key={row.integration_point_index} value={row.integration_point_index}>Point {row.integration_point_index} · xi {row.xi} · {row.section_id}</option>)}
        </select>
        <p>xi runs from −1 to +1 along the initial member i→j. Section signs: epsilon_f = epsilon_0 − kappa_z*y_f; N = sum(sigma_f*A_f), MZ = −sum(sigma_f*A_f*y_f). Positive N is tension.</p>
        {section ? <>
          <div role="region" aria-label="Stored section response" tabIndex={0} style={{ overflowX: 'auto', maxWidth: '100%' }}>
            <table className="wb2-table" data-rc-detail-section-table><caption>Stored section response · accepted state {index} · integration point {point}</caption>
              <thead><tr><th scope="col">Axial strain (1)</th><th scope="col">Curvature z (1/m)</th><th scope="col">N (kN)</th><th scope="col">MZ (kN*m)</th></tr></thead>
              <tbody><tr>{[section.axial_strain, section.curvature_z_per_m, section.axial_force_kn, section.moment_z_kn_m].map((value, column) => <td key={column}>{String(value)}</td>)}</tr></tbody>
            </table>
          </div>
          <label htmlFor={`${fieldId}-fiber`}>Detail fiber index</label>{' '}
          <input id={`${fieldId}-fiber`} value={fiberText} inputMode="numeric" aria-invalid={!validFiber} style={{ width: '6rem' }} onChange={event => setFiberText(event.target.value)} />{' '}
          <button type="button" disabled={!validFiber || fiberIndex === 0} onClick={() => setFiberText(String(fiberIndex - 1))}>Previous stored fiber</button>{' '}
          <button type="button" disabled={!validFiber || fiberIndex + 1 >= section.fiberCount} onClick={() => setFiberText(String(fiberIndex + 1))}>Next stored fiber</button>
          <p>Stored fiber indices: 0–{section.fiberCount - 1}. Indices follow the source order; a steel fiber may represent an aggregate bar layer.</p>
          {!validFiber ? <p role="status">Choose an integer fiber index within this section.</p> : fiber ? <div role="region" aria-label="Stored fiber response" tabIndex={0} style={{ overflowX: 'auto', maxWidth: '100%' }}>
            <table className="wb2-table" data-rc-detail-fiber-table><caption>Stored fiber response · accepted state {index}</caption>
              <thead><tr><th scope="col">Fiber index</th><th scope="col">Material</th><th scope="col">Strain (1)</th><th scope="col">Stress (MPa)</th></tr></thead>
              <tbody><tr><td>{fiber.fiber_index}</td><td>{fiber.material_kind}</td><td>{String(fiber.strain)}</td><td>{String(fiber.stress_mpa)}</td></tr></tbody>
            </table>
          </div> : <p role="status">Loading stored fiber response…</p>}
        </> : <p role="status">Loading stored section response…</p>}
        <p>History page: accepted states {historyStart}–{Math.min(summary.stateCount - 1, historyStart + PAGE_SIZE - 1)}. Stored order and reversals are retained; page boundaries are not joined or fitted. Select a point to inspect its accepted state.</p>
        {sectionPage && <RcHistoryPlot label="Section moment–curvature history" xLabel="Curvature z (1/m)" yLabel="Moment z (kN*m)" points={sectionPage.map(row => ({ state: row.state_index, x: row.curvature_z_per_m, y: row.moment_z_kn_m }))} selectedState={index} onSelectState={onSelectState} />}
        {fiberPage && validFiber && <RcHistoryPlot label="Fiber stress–strain history" xLabel="Strain (dimensionless)" yLabel="Stress (MPa)" points={fiberPage.map(row => ({ state: row.state_index, x: row.strain, y: row.stress_mpa }))} selectedState={index} onSelectState={onSelectState} />}
      </>}
      <button type="button" disabled={!review.detailDownload} onClick={() => void download()}>Download corotational detail report</button>
    </>}
    {message && <p role="status" data-rc-detail-message>{message}</p>}
  </section>
}
