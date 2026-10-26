import { useState, type ReactElement } from 'react'
import type { BuildingMemberReview } from '../model/buildingMemberReview'

interface BuildingMemberForceReviewProps {
  review: BuildingMemberReview
  heading?: string
  headingLevel?: 2 | 3
}
const PAGE_SIZE = 50

/** Pure stored-result presentation: no file admission, authoring, execution or service access. */
export function BuildingMemberForceReview({ review, heading = '3. Inspect signed stored forces', headingLevel = 2 }: BuildingMemberForceReviewProps): ReactElement {
  const [filter, setFilter] = useState('all'), [page, setPage] = useState(0)
  const visibleRows = review.rows.filter(row => filter === 'all' || (filter === 'unmapped' ? row.mapping_status === 'UNMAPPED' : `member:${row.physical_member_id}` === filter))
  const pages = Math.max(1, Math.ceil(visibleRows.length / PAGE_SIZE)), displayedPage = Math.min(page, pages - 1)
  const rows = visibleRows.slice(displayedPage * PAGE_SIZE, (displayedPage + 1) * PAGE_SIZE)
  const Heading = headingLevel === 2 ? 'h2' : 'h3'
  const Subheading = headingLevel === 2 ? 'h3' : 'h4'
  return <div data-building-force-review>
      <Heading>{heading}</Heading>
      <p data-building-member-authority>Operator-declared mapping. All physical members are NOT_REVIEWED.</p>
      <p>File and model/result bindings checked. Origin is not authenticated. Numeric availability is not a design check or an acceptance decision.</p>
      <dl className="wb2-kv">
        <dt>Model</dt><dd>{review.source.model_id}</dd>
        <dt>Stored result</dt><dd>{review.source.result_id}</dd>
        <dt>Load pattern</dt><dd data-building-load-pattern>{review.source.load_pattern_id ?? 'Not selected — this result uses a combination'}</dd>
        <dt>Load combination</dt><dd data-building-load-combination>{review.source.load_combination_id ?? 'Not selected — this result uses a pattern'}</dd>
        <dt>Declared storeys / physical members</dt><dd>{review.counts.storeys} / {review.counts.physical_members}</dd>
        <dt>Mapped / unmapped analysis elements</dt><dd data-building-mapping-counts>{review.counts.mapped_elements} / {review.counts.unmapped_elements}</dd>
        <dt>Declared review locations / all native endpoint rows</dt><dd>{review.counts.review_locations} / {review.counts.endpoint_rows}</dd>
      </dl>
      <details><summary>Source identities and mapping record</summary><dl className="wb2-kv" style={{ overflowWrap: 'anywhere' }}>
        {Object.entries(review.source).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value === null ? 'null' : String(value)}</dd></div>)}
        <dt>mapping_id</dt><dd>{review.mapping_id}</dd><dt>mapping_hash</dt><dd>{review.mapping_hash}</dd>
      </dl></details>
      <Subheading>Declared physical members</Subheading>
      <div className="wb2-table-wrap"><table className="wb2-table" data-building-physical-members><caption>Author-declared physical members, including members without mapped elements</caption><thead><tr><th>Physical member</th><th>Label</th><th>Storey</th><th>Segments</th><th>Mapping / coverage</th><th>Unmapped station intervals</th><th>Review</th></tr></thead>
        <tbody>{review.physical_members.map(member => <tr key={member.member_id}><th scope="row">{member.member_id}</th><td>{member.label}</td><td>{member.storey_id}</td><td>{member.segments.length}</td><td>{member.mapping_status} / {member.coverage_status}</td><td>{member.coverage_gaps.map(gap => `${gap.start}–${gap.end}`).join(', ') || 'No gaps in declared coverage'}</td><td>{member.review_status}</td></tr>)}</tbody></table></div>
      {!review.physical_members.length ? <p>No physical members are declared. All analysis elements remain visible below as UNMAPPED.</p> : null}
      <p>Native member-local components FX, FY, FZ, MX, MY, MZ are preserved with their original signs and i/j ends. Reversing the declared physical orientation only changes the physical station label; it does not rotate axes or transform signs. Released ends and offsets retain the native result convention.</p>
      <label>Member rows <select aria-label="Member rows" value={filter} onChange={event => { setFilter(event.target.value); setPage(0) }}>
        <option value="all">All native endpoint rows</option><option value="unmapped">Unmapped analysis elements</option>
        {review.physical_members.map(member => <option key={member.member_id} value={`member:${member.member_id}`}>{member.member_id} · {member.label}</option>)}
      </select></label>
      <p data-building-row-count>Rows {visibleRows.length ? displayedPage * PAGE_SIZE + 1 : 0}–{Math.min(visibleRows.length, (displayedPage + 1) * PAGE_SIZE)} of {visibleRows.length}. Export retains all {review.rows.length} native endpoint rows.</p>
      <div className="wb2-table-wrap"><table className="wb2-table" data-building-force-rows><caption>Signed native end forces — force in N, moment in N·m; coordinate frame member_local</caption><thead><tr>
        <th>Physical member / storey</th><th>Element / index</th><th>Native end / node</th><th>Physical station / orientation</th><th>Review location</th><th>Mapping / review</th>
        {['FX (N)', 'FY (N)', 'FZ (N)', 'MX (N·m)', 'MY (N·m)', 'MZ (N·m)'].map(label => <th key={label}>{label}</th>)}
      </tr></thead><tbody>{rows.map(row => <tr key={`${row.element_id}:${row.end}`} data-building-element={row.element_id} data-building-end={row.end}>
        <td>{row.physical_member_id ?? 'UNMAPPED'} / {row.storey_id ?? 'UNMAPPED'}</td><th scope="row">{row.element_id} / {row.member_index}</th><td>{row.end} / {row.node_id}</td>
        <td>{row.member_station === null ? 'UNMAPPED' : row.member_station} / {row.orientation ?? 'UNMAPPED'}</td><td>{row.review_location_id ?? 'Not declared'}</td>
        <td>{row.mapping_status} / {row.review_status}</td>{row.force_n_nm.map((value, index) => <td key={index} className="wb2-num" data-building-component={row.component_names[index]}>{String(value)}</td>)}
      </tr>)}</tbody></table></div>
      <div className="wb2-actions"><button type="button" className="wb2-btn" disabled={!displayedPage} onClick={() => setPage(displayedPage - 1)}>Previous member rows</button>
        <button type="button" className="wb2-btn" disabled={displayedPage >= pages - 1} onClick={() => setPage(displayedPage + 1)}>Next member rows</button></div>
  </div>
}
