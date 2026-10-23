import { useId, useState, type KeyboardEvent, type ReactElement } from 'react'
import type { RcResultGeometry } from '../model/rcResultVisualization'

export interface RcDeformedShapeProps {
  geometry: RcResultGeometry
  displacements: Array<{ nodeId: string; ux: number; uy: number }>
  selectedMember: string
  onSelectMember: (id: string) => void
  scale?: string
  onScaleChange?: (value: string) => void
}
const finite = (value: number) => Number.isFinite(value)
const tick = (value: number) => value === 0 ? '0' : value.toPrecision(5)
const activate = (event: KeyboardEvent<SVGElement>, action: () => void) => {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); action() }
}

/** Draw verified nodal translations only. The straight chords are not an
 * interpolation of curvature, end rotations or internal member response.
 */
export function RcDeformedShape({ geometry, displacements, selectedMember, onSelectMember, scale: controlledScale, onScaleChange }: RcDeformedShapeProps): ReactElement {
  const id = useId(), [localScale, setLocalScale] = useState('1')
  const scale = controlledScale ?? localScale
  const factor = scale.trim() ? Number(scale) : NaN
  const translations = new Map(displacements.map(row => [row.nodeId, row]))
  const nodes = geometry.nodes.map(node => {
    const movement = translations.get(node.id)
    return { ...node, dx: movement ? node.x + movement.ux * factor : NaN, dy: movement ? node.y + movement.uy * factor : NaN }
  })
  const lookup = new Map(nodes.map(node => [node.id, node]))
  let valid = finite(factor) && factor >= 0 && nodes.length > 0 && nodes.length <= 16
    && geometry.members.length > 0 && geometry.members.length <= 256
    && translations.size === displacements.length && translations.size === nodes.length
    && nodes.every(row => [row.x, row.y, row.dx, row.dy].every(finite))
    && geometry.members.every(row => lookup.has(row.nodeI) && lookup.has(row.nodeJ))
  const xs = nodes.flatMap(row => [row.x, row.dx]), ys = nodes.flatMap(row => [row.y, row.dy])
  const magnitude = Math.max(...xs.map(Math.abs), ...ys.map(Math.abs)) || 1
  const minX = Math.min(...xs.map(value => value / magnitude)), maxX = Math.max(...xs.map(value => value / magnitude))
  const minY = Math.min(...ys.map(value => value / magnitude)), maxY = Math.max(...ys.map(value => value / magnitude))
  const spanX = maxX - minX, spanY = maxY - minY
  const fit = Math.min(spanX > 0 ? 540 / spanX : Infinity, spanY > 0 ? 220 / spanY : Infinity)
  valid = valid && finite(magnitude) && finite(fit) && fit > 0
  const point = (x: number, y: number) => ({ x: 320 + (x / magnitude - (minX + maxX) / 2) * fit, y: 150 - (y / magnitude - (minY + maxY) / 2) * fit })
  return <figure data-rc-deformed-shape style={{ minWidth: 0, maxWidth: '100%', margin: '1rem 0' }}>
    <label htmlFor={`${id}-scale`}>Deformation scale</label>{' '}
    <input id={`${id}-scale`} value={scale} inputMode="decimal" aria-invalid={!valid} style={{ width: '8rem' }}
      onChange={event => { setLocalScale(event.target.value); onScaleChange?.(event.target.value) }} />{' '}
    <label htmlFor={`${id}-member`}>Result member</label>{' '}
    <select id={`${id}-member`} data-rc-member-selection value={selectedMember} style={{ maxWidth: '100%' }} onChange={event => onSelectMember(event.target.value)}>
      <option value="">All members</option>
      {geometry.members.map(member => <option key={member.id} value={member.id}>{member.id}</option>)}
    </select>
    {valid ? <svg viewBox="0 0 640 320" role="group" aria-label="Verified undeformed and deformed RC chords in global XY" style={{ width: '100%', maxHeight: 390 }}>
      <text x="16" y="20" fill="currentColor" fontSize="12">Global XY (m) · equal axis scale · deformation ×{scale}</text>
      {geometry.members.map(member => {
        const a = lookup.get(member.nodeI)!, b = lookup.get(member.nodeJ)!
        const originalA = point(a.x, a.y), originalB = point(b.x, b.y), deformedA = point(a.dx, a.dy), deformedB = point(b.dx, b.dy)
        const selected = member.id === selectedMember
        return <g key={member.id} role="button" tabIndex={0} aria-label={`Select member ${member.id}`} aria-pressed={selected}
          data-rc-member={member.id} data-rc-x1={a.x} data-rc-y1={a.y} data-rc-x2={b.x} data-rc-y2={b.y}
          data-rc-deformed-x1={a.dx} data-rc-deformed-y1={a.dy} data-rc-deformed-x2={b.dx} data-rc-deformed-y2={b.dy}
          onClick={() => onSelectMember(member.id)} onKeyDown={event => activate(event, () => onSelectMember(member.id))}>
          <title>{`${member.id}: ${member.nodeI} (${a.x}, ${a.y}) → ${member.nodeJ} (${b.x}, ${b.y}) m. Scaled translations: (${a.dx}, ${a.dy}) → (${b.dx}, ${b.dy}) m.`}</title>
          <line x1={originalA.x} y1={originalA.y} x2={originalB.x} y2={originalB.y} stroke="currentColor" opacity="0.45" strokeWidth="2" strokeDasharray="5 4" />
          <line x1={deformedA.x} y1={deformedA.y} x2={deformedB.x} y2={deformedB.y} stroke={selected ? '#e9a23b' : '#56a8e9'} strokeWidth={selected ? 5 : 3} />
          <line x1={deformedA.x} y1={deformedA.y} x2={deformedB.x} y2={deformedB.y} stroke="transparent" strokeWidth="16" />
          <text x={(deformedA.x + deformedB.x) / 2} y={(deformedA.y + deformedB.y) / 2 - 12} fill="currentColor" textAnchor="middle" fontSize="12">{member.id}</text>
        </g>
      })}
      {nodes.map(node => {
        const at = point(node.dx, node.dy)
        return <g key={node.id}><circle cx={at.x} cy={at.y} r="3" fill="currentColor" /><text x={at.x + 7} y={at.y + 18} fill="currentColor" fontSize="11">{node.id}</text></g>
      })}
    </svg> : <p role="status" data-rc-shape-unavailable>Shape unavailable. Use a finite nonnegative scale and verified nodal coordinates and translations.</p>}
    <figcaption>Dashed: original geometry. Solid: nodal translations with the chosen scale. Straight chords preserve equal X/Y scale; member curvature and rotations are not interpolated. Select a member or use the member list.</figcaption>
  </figure>
}

export interface RcHistoryPlotProps {
  label: string
  xLabel: string
  yLabel: string
  points: Array<{ state: number; x: number; y: number }>
  selectedState?: number
  onSelectState?: (state: number) => void
}
/** Preserve the supplied stored order, including repeated values and reversals. */
export function RcHistoryPlot({ label, xLabel, yLabel, points, selectedState, onSelectState }: RcHistoryPlotProps): ReactElement {
  const id = useId()
  const valid = points.length > 0 && points.length <= 50 && new Set(points.map(row => row.state)).size === points.length
    && points.every(row => Number.isSafeInteger(row.state) && row.state >= 0 && finite(row.x) && finite(row.y))
  if (!valid) return <figure data-rc-history-plot={label}><figcaption>{label}</figcaption><p role="status">This bounded history page has no plottable verified values.</p></figure>
  const xs = points.map(row => row.x), ys = points.map(row => row.y)
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys)
  const xMagnitude = Math.max(Math.abs(x0), Math.abs(x1)) || 1, yMagnitude = Math.max(Math.abs(y0), Math.abs(y1)) || 1
  const x = (value: number) => x0 === x1 ? 325 : 70 + (value / xMagnitude - x0 / xMagnitude) / (x1 / xMagnitude - x0 / xMagnitude) * 500
  const y = (value: number) => y0 === y1 ? 135 : 235 - (value / yMagnitude - y0 / yMagnitude) / (y1 / yMagnitude - y0 / yMagnitude) * 200
  return <figure data-rc-history-plot={label} style={{ minWidth: 0, maxWidth: '100%', margin: '1rem 0' }}>
    <figcaption>{label}</figcaption>
    <svg viewBox="0 0 640 310" role="group" aria-label={label} style={{ width: '100%', maxHeight: 360 }}>
      <path d="M70 25 V235 H590" fill="none" stroke="currentColor" />
      <text x="70" y="18" fill="currentColor" fontSize="12">{yLabel}: {tick(y0)} to {tick(y1)}</text>
      <text x="70" y="257" fill="currentColor" fontSize="11">{tick(x0)}</text><text x="490" y="257" fill="currentColor" fontSize="11">{tick(x1)}</text>
      <text x="320" y="282" textAnchor="middle" fill="currentColor" fontSize="12">{xLabel}</text>
      <polyline data-rc-history-line fill="none" stroke="#56a8e9" strokeWidth="2" points={points.map(row => `${x(row.x)},${y(row.y)}`).join(' ')} />
      {points.map(row => <circle key={row.state} cx={x(row.x)} cy={y(row.y)} r={row.state === selectedState ? 6 : 4}
        data-rc-history-point={row.state} data-rc-x={row.x} data-rc-y={row.y}
        fill={row.state === selectedState ? '#e9a23b' : '#56a8e9'} role={onSelectState ? 'button' : undefined} tabIndex={onSelectState ? 0 : undefined}
        aria-label={`Inspect stored state ${row.state}`} aria-pressed={onSelectState ? row.state === selectedState : undefined}
        onClick={() => onSelectState?.(row.state)} onKeyDown={event => activate(event, () => onSelectState?.(row.state))}>
        <title>{`State ${row.state}: ${xLabel} = ${String(row.x)}, ${yLabel} = ${String(row.y)}`}</title>
      </circle>)}
    </svg>
    {onSelectState && <><label htmlFor={`${id}-state`}>{label} stored state</label>{' '}
      <select id={`${id}-state`} style={{ maxWidth: '100%' }} value={points.some(row => row.state === selectedState) ? selectedState : ''} onChange={event => { if (event.target.value !== '') onSelectState(Number(event.target.value)) }}>
        <option value="" disabled>Select stored state</option>
        {points.map(row => <option key={row.state} value={row.state}>State {row.state}: {String(row.x)}, {String(row.y)}</option>)}
      </select></>}
    <details><summary>{label} values</summary><div style={{ overflowX: 'auto' }}><table className="wb2-table">
      <caption>Exact displayed values · stored state indices start at zero</caption>
      <thead><tr><th>State</th><th>{xLabel}</th><th>{yLabel}</th></tr></thead>
      <tbody>{points.map(row => <tr key={row.state}><th scope="row">{row.state}</th><td>{String(row.x)}</td><td>{String(row.y)}</td></tr>)}</tbody>
    </table></div></details>
    <p>Stored order is retained. Lines connect recorded values as visual guides; no fitting, interpolation or zero shift is applied.</p>
  </figure>
}
