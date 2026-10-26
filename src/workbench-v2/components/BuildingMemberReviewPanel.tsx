import { useEffect, useRef, useState, type ReactElement } from 'react'
import {
  BUILDING_MEMBER_MODEL_MAX_BYTES,
  BUILDING_MEMBER_RESULT_MAX_BYTES,
  BUILDING_MEMBER_MAPPING_MAX_BYTES,
  createBuildingMemberMappingTemplate,
  openBuildingMemberReview,
  type BuildingMemberMapping,
  type BuildingMemberReview,
} from '../model/buildingMemberReview'
import { parseNativeJsonStrict } from '../model/nativeFrameProvider'
import { registerUnsavedProjectGuard } from '../model/unsavedProjectGuard'
import { BuildingLoadRevisionPanel } from './BuildingLoadRevisionPanel'
import { BuildingMemberForceReview } from './BuildingMemberForceReview'
import '../workbenchV2.css'

const jsonBytes = (value: unknown): Uint8Array => new TextEncoder().encode(JSON.stringify(value, null, 2))

/** A file-only workspace: this component neither requests a service nor starts analysis. */
export function BuildingMemberReviewPanel(): ReactElement {
  const [model, setModel] = useState<File | null>(null), [result, setResult] = useState<File | null>(null)
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(false), [message, setMessage] = useState('')
  const [savedDraft, setSavedDraft] = useState('')
  const [admitted, setAdmitted] = useState<{ review: BuildingMemberReview; mapping: Uint8Array; modelBytes: Uint8Array; resultBytes: Uint8Array; viewId: number } | null>(null)
  const [storeyId, setStoreyId] = useState(''), [storeyLabel, setStoreyLabel] = useState(''), [elevation, setElevation] = useState('')
  const [memberId, setMemberId] = useState(''), [memberLabel, setMemberLabel] = useState(''), [memberStorey, setMemberStorey] = useState('')
  const [elementId, setElementId] = useState(''), [orientation, setOrientation] = useState<'i_to_j' | 'j_to_i'>('i_to_j')
  const [segmentId, setSegmentId] = useState(''), [segmentMember, setSegmentMember] = useState('')
  const [stationStart, setStationStart] = useState('0'), [stationEnd, setStationEnd] = useState('1')
  const generation = useRef(0), pending = useRef(false), urls = useRef(new Set<string>()), unsaved = useRef(false)
  unsaved.current = draft !== savedDraft
  const workbenchUrl = new URL(window.location.href)
  workbenchUrl.pathname = workbenchUrl.pathname.replace(/\/building-review\/*$/, '/')
  workbenchUrl.hash = '/workbench-v2'
  useEffect(() => () => {
    generation.current++
    for (const url of urls.current) URL.revokeObjectURL(url)
    urls.current.clear()
  }, [])
  useEffect(() => registerUnsavedProjectGuard(() => unsaved.current), [])
  function invalidatePending(): void {
    generation.current++; pending.current = false; setBusy(false)
  }

  async function bytes(file: File | null, limit: number, label: string): Promise<Uint8Array> {
    if (!file || !file.size || file.size > limit) throw new Error(`Choose a non-empty ${label} file of at most ${limit / 1024 / 1024} MiB.`)
    return new Uint8Array(await file.arrayBuffer())
  }
  function save(body: BlobPart, name: string): void {
    const url = URL.createObjectURL(new Blob([body], { type: 'application/json' }))
    urls.current.add(url)
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = name
    document.body.append(anchor); anchor.click(); anchor.remove()
    window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url) }, 0)
  }
  async function open(prepare: boolean): Promise<void> {
    if (pending.current) return
    const own = ++generation.current
    pending.current = true; setBusy(true); setMessage('')
    try {
      const [modelBytes, resultBytes] = await Promise.all([
        bytes(model, BUILDING_MEMBER_MODEL_MAX_BYTES, 'stored ModelIR'),
        bytes(result, BUILDING_MEMBER_RESULT_MAX_BYTES, 'stored ResultIR'),
      ])
      if (own !== generation.current) return
      const mapping = prepare ? jsonBytes(await createBuildingMemberMappingTemplate(modelBytes, resultBytes)) : new TextEncoder().encode(draft)
      if (own !== generation.current) return
      if (!mapping.byteLength || mapping.byteLength > BUILDING_MEMBER_MAPPING_MAX_BYTES) throw new Error('The mapping must be non-empty and at most 1 MiB.')
      const review = await openBuildingMemberReview(modelBytes, resultBytes, mapping)
      if (own !== generation.current) return
      if (prepare) setDraft(new TextDecoder().decode(mapping))
      setAdmitted({ review, mapping, modelBytes, resultBytes, viewId: own })
      setElementId(review.rows[0]?.element_id ?? '')
      setMessage(prepare
        ? 'Stored model and result admitted. The new mapping is empty: all analysis elements remain UNMAPPED. Add your own storeys and physical members, then open the mapping.'
        : 'Opened the stored result with your declared mapping. Every member remains NOT_REVIEWED. No analysis or design check was run.')
    } catch (error) {
      if (own === generation.current) setMessage(`${error instanceof Error ? error.message : 'These files could not be admitted.'} Any previously opened review is retained.`)
    } finally { if (own === generation.current) { pending.current = false; setBusy(false) } }
  }
  async function importMapping(file?: File): Promise<void> {
    if (!file || pending.current) return
    const own = ++generation.current
    pending.current = true; setBusy(true); setMessage('')
    try {
      const body = await bytes(file, BUILDING_MEMBER_MAPPING_MAX_BYTES, 'operator-declared mapping')
      if (body[0] === 0xef && body[1] === 0xbb && body[2] === 0xbf) throw new Error('Mapping UTF-8 BOM is not supported.')
      const text = new TextDecoder('utf-8', { fatal: true }).decode(body)
      if (own === generation.current) { setDraft(text); setSavedDraft(text); setMessage('Mapping loaded into the editor. Choose “Open declared mapping” to validate it against the selected stored model and result.') }
    } catch (error) {
      if (own === generation.current) setMessage(`${error instanceof Error ? error.message : 'The mapping file could not be read.'} The previous draft and opened review are retained.`)
    } finally { if (own === generation.current) { pending.current = false; setBusy(false) } }
  }
  function editMapping(change: (mapping: BuildingMemberMapping) => void): void {
    try {
      const mapping = parseNativeJsonStrict(draft) as BuildingMemberMapping
      if (!Array.isArray(mapping.storeys) || !Array.isArray(mapping.members)) throw new Error('Prepare or import a mapping before adding rows.')
      change(mapping)
      const body = JSON.stringify(mapping, null, 2)
      if (new TextEncoder().encode(body).byteLength > BUILDING_MEMBER_MAPPING_MAX_BYTES) throw new Error('The edited mapping exceeds 1 MiB.')
      invalidatePending(); setDraft(body); setMessage('Mapping draft changed. Open the declared mapping to check and apply it. The displayed review still uses its previously admitted mapping.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'The mapping draft could not be edited.') }
  }
  const review = admitted?.review
  const elements = review ? [...new Set(review.rows.map(row => row.element_id))] : []


  return <main className="wb2-portable-workspace" data-building-member-workspace>
    <nav aria-label="Building workspace"><a href={workbenchUrl.href}>Return to Workbench</a></nav>
    <h1>Review stored building member forces</h1>
    <p>Connect your physical member and storey IDs to an existing native Frame3D model and one stored result. Files stay in this browser session; this workspace does not connect to a job service.</p>
    <p>Mapping is your declaration. This view does not establish structural suitability, design compliance or physical validation, and does not run an analysis.</p>
    <section aria-label="Stored building files" className="wb2-rc-job">
      <h2>1. Open a stored model and result</h2>
      <label className="wb2-portable-file">Stored native ModelIR file{' '}<input type="file" aria-label="Stored native ModelIR file" accept="application/json,.json" disabled={busy}
        onChange={event => { invalidatePending(); setModel(event.target.files?.[0] ?? null); setMessage('Selected files changed. The displayed review still uses its previously admitted files.') }} /></label>
      <label className="wb2-portable-file">Stored native ResultIR file{' '}<input type="file" aria-label="Stored native ResultIR file" accept="application/json,.json" disabled={busy}
        onChange={event => { invalidatePending(); setResult(event.target.files?.[0] ?? null); setMessage('Selected files changed. The displayed review still uses its previously admitted files.') }} /></label>
      <p>Use a matching ModelIR v2 and bounded native linear Frame3D ResultIR v1. Each file is limited to 2 MiB. No example is loaded as your project.</p>
      <button type="button" className="wb2-btn" disabled={busy || !model || !result} onClick={() => void open(true)}>Prepare empty member mapping</button>
    </section>
    <section aria-label="Operator-declared member mapping" className="wb2-rc-job">
      <h2>2. Declare storeys, physical members and review locations</h2>
      <p>Prepare an empty mapping from the selected files, or import one. No storey, physical member or end orientation is inferred from element names or coordinates.</p>
      <label className="wb2-portable-file">Import operator-declared mapping{' '}<input type="file" aria-label="Import operator-declared mapping" accept="application/json,.json" disabled={busy}
        onChange={event => { void importMapping(event.target.files?.[0]); event.target.value = '' }} /></label>
      <details open={Boolean(draft)}><summary>Mapping editor and simple member form</summary>
        <fieldset disabled={busy || !draft}>
          <legend>Add a storey</legend>
          <label>Storey ID <input aria-label="Storey ID" value={storeyId} onChange={event => setStoreyId(event.target.value)} /></label>{' '}
          <label>Storey label <input aria-label="Storey label" value={storeyLabel} onChange={event => setStoreyLabel(event.target.value)} /></label>{' '}
          <label>Declared elevation (m) <input aria-label="Declared elevation (m)" type="number" step="any" value={elevation} onChange={event => setElevation(event.target.value)} /></label>{' '}
          <button type="button" className="wb2-btn" onClick={() => {
            if (!storeyId.trim() || !storeyLabel.trim() || elevation.trim() === '' || !Number.isFinite(Number(elevation))) { setMessage('Enter a storey ID, label and finite elevation.'); return }
            editMapping(mapping => { mapping.storeys.push({ storey_id: storeyId.trim(), label: storeyLabel.trim(), elevation_m: Number(elevation) }) })
          }}>Add storey to draft</button>
        </fieldset>
        <fieldset disabled={busy || !draft || !review}>
          <legend>Add a physical member</legend>
          <label>Physical member ID <input aria-label="Physical member ID" value={memberId} onChange={event => setMemberId(event.target.value)} /></label>{' '}
          <label>Physical member label <input aria-label="Physical member label" value={memberLabel} onChange={event => setMemberLabel(event.target.value)} /></label>{' '}
          <label>Declared storey ID <input aria-label="Declared storey ID" value={memberStorey} onChange={event => setMemberStorey(event.target.value)} /></label>{' '}
          <button type="button" className="wb2-btn" onClick={() => {
            if (!memberId.trim() || !memberLabel.trim() || !memberStorey.trim()) { setMessage('Enter a physical member ID, label and declared storey ID.'); return }
            editMapping(mapping => { mapping.members.push({ member_id: memberId.trim(), label: memberLabel.trim(), storey_id: memberStorey.trim(), segments: [], review_locations: [] }) })
            setSegmentMember(memberId.trim())
          }}>Add physical member to draft</button>
        </fieldset>
        <fieldset disabled={busy || !draft || !review}>
          <legend>Add an analysis segment and its two review locations</legend>
          <label>Segment physical member ID <input aria-label="Segment physical member ID" value={segmentMember} onChange={event => setSegmentMember(event.target.value)} /></label>{' '}
          <label>Segment ID (at most 119 characters) <input aria-label="Segment ID" maxLength={119} value={segmentId} onChange={event => setSegmentId(event.target.value)} /></label>{' '}
          <label>Analysis element <select aria-label="Analysis element" value={elementId} onChange={event => setElementId(event.target.value)}>{elements.map(id => <option key={id}>{id}</option>)}</select></label>{' '}
          <label>Physical start station <input aria-label="Physical start station" type="number" min="0" max="1" step="any" value={stationStart} onChange={event => setStationStart(event.target.value)} /></label>{' '}
          <label>Physical end station <input aria-label="Physical end station" type="number" min="0" max="1" step="any" value={stationEnd} onChange={event => setStationEnd(event.target.value)} /></label>{' '}
          <label>Physical start to end <select aria-label="Physical start to end" value={orientation} onChange={event => setOrientation(event.target.value as 'i_to_j' | 'j_to_i')}>
            <option value="i_to_j">Native i → j</option><option value="j_to_i">Native j → i</option>
          </select></label>{' '}
          <button type="button" className="wb2-btn" onClick={() => {
            const start = Number(stationStart), end = Number(stationEnd)
            if (!segmentMember.trim() || !segmentId.trim() || segmentId.trim().length > 119 || !elementId || stationStart.trim() === '' || stationEnd.trim() === '' || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > 1 || start >= end) {
              setMessage('Enter a declared physical member ID, segment ID, element and increasing stations within 0–1.'); return
            }
            editMapping(mapping => {
              const member = mapping.members.find(row => row.member_id === segmentMember.trim())
              if (!member) throw new Error('The segment physical member ID is not declared in this draft.')
              member.segments.push({ segment_id: segmentId.trim(), element_id: elementId, member_start: start, member_end: end, orientation })
              member.review_locations.push({ location_id: `${segmentId.trim()}:native-i`, element_id: elementId, end: 'i' }, { location_id: `${segmentId.trim()}:native-j`, element_id: elementId, end: 'j' })
            })
          }}>Add segment and native end locations to draft</button>
          <p>Add each segment explicitly. Stations 0–1 describe your physical member; they do not interpolate new forces. The form appends “:native-i” and “:native-j” to the segment ID for the two end location IDs. The JSON editor below also permits selected locations and members without elements.</p>
        </fieldset>
        <label className="wb2-review-field">Operator-declared mapping JSON<textarea aria-label="Operator-declared mapping JSON" rows={18} maxLength={BUILDING_MEMBER_MAPPING_MAX_BYTES} spellCheck={false} value={draft} disabled={busy}
          onChange={event => { invalidatePending(); setDraft(event.target.value); setMessage('Mapping draft changed. Open the declared mapping to apply it; the displayed review is unchanged.') }} style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'monospace' }} /></label>
      </details>
      <button type="button" className="wb2-btn" disabled={busy || !model || !result || !draft} onClick={() => void open(false)}>Open declared mapping</button>
      <p data-building-draft-status>{draft !== savedDraft ? 'Unsaved mapping draft. Opening it does not save your changes.' : 'The mapping draft matches its imported or downloaded file.'}</p>
      <button type="button" className="wb2-btn" disabled={busy || !draft} onClick={() => {
        save(draft, 'building-member-mapping-unvalidated.draft.json'); setSavedDraft(draft)
        setMessage('Downloaded the current mapping draft as unvalidated text. This does not admit the mapping or update the displayed review. Keep this file to continue editing in another session.')
      }}>Download unvalidated mapping draft</button>
    </section>
    {busy ? <p role="status">Checking stored files and declared member mapping…</p> : null}
    {message ? <p role="status" data-building-member-status>{message}</p> : null}
    {review ? <section className="wb2-rc-job" aria-label="Stored physical member force review" data-building-member-review="admitted">
      <BuildingMemberForceReview key={admitted!.viewId} review={review} />
      <h3>4. Save the admitted mapping and complete review</h3>
      <p>These downloads use the displayed admitted review, including unmapped endpoints and NOT_REVIEWED members. Unsaved editor changes are not applied. Keep the original model and result files for another session.</p>
      <div className="wb2-actions"><button type="button" className="wb2-btn" onClick={() => {
        save(admitted!.mapping as BlobPart, 'building-member-mapping.json')
        const saved = new TextDecoder().decode(admitted!.mapping)
        if (draft === saved) setSavedDraft(saved)
      }}>Export admitted member mapping</button>
        <button type="button" className="wb2-btn" onClick={() => save(JSON.stringify(review, null, 2), 'building-member-review.json')}>Export complete member review</button></div>
    </section> : null}
    <BuildingLoadRevisionPanel
      modelBytes={admitted?.modelBytes}
      resultBytes={admitted?.resultBytes}
      mappingBytes={admitted?.mapping}
      sourceFingerprint={admitted ? `${admitted.review.source.model_file_hash}:${admitted.review.source.result_file_hash}:${admitted.review.source.mapping_file_hash}` : undefined}
    />
  </main>
}
