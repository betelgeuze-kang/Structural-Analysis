import { useEffect, useRef, useState, type ReactElement } from 'react'
import { BUILDING_MEMBER_RESULT_MAX_BYTES } from '../model/buildingMemberReview'
import { serializeBuildingLoadRevisionDraft, type BuildingLoadRevisionDraft } from '../model/buildingLoadRevision'
import {
  BUILDING_REVISION_RESULT_MAX_BYTES,
  attachBuildingRevisionResult,
  openBuildingRevisionResultAttachment,
  type BuildingRevisionLoadSource,
  type BuildingRevisionResultSession,
} from '../model/buildingRevisionResult'
import { BuildingMemberForceReview } from './BuildingMemberForceReview'

export interface BuildingRevisionResultPanelProps {
  draft?: BuildingLoadRevisionDraft
  draftFingerprint?: string
  loadSources?: BuildingRevisionLoadSource[]
}
interface FrozenSession { value: BuildingRevisionResultSession; contextFingerprint: string | null }

/** Explicit local file attachment only. It never starts analysis or changes a draft's NOT_RUN state. */
export function BuildingRevisionResultPanel({ draft, draftFingerprint, loadSources = [] }: BuildingRevisionResultPanelProps): ReactElement {
  const [resultFile, setResultFile] = useState<File | null>(null)
  const [selectedSource, setSelectedSource] = useState('')
  const [session, setSession] = useState<FrozenSession | null>(null)
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('')
  const generation = useRef(0), pending = useRef(false), urls = useRef(new Set<string>())
  useEffect(() => {
    // An in-flight attachment may not be installed as a result of a newer edit.
    generation.current++; pending.current = false; setBusy(false); setSelectedSource('')
  }, [draft, draftFingerprint])
  useEffect(() => () => {
    generation.current++
    for (const url of urls.current) URL.revokeObjectURL(url)
    urls.current.clear()
  }, [])
  const currentFingerprint = draft ? (draftFingerprint ?? null) : null
  const contextChanged = Boolean(session && session.contextFingerprint !== currentFingerprint)
  const current = session?.value
  const expectedSource = loadSources.find(source => `${source.kind}:${source.id}` === selectedSource)

  async function read(file: File, limit: number, label: string): Promise<Uint8Array> {
    // Reject oversized files before asking the browser to allocate their body.
    if (!file.size || file.size > limit) throw new Error(`Choose a non-empty ${label} file of at most ${limit / 1024 / 1024} MiB.`)
    return new Uint8Array(await file.arrayBuffer())
  }
  async function attach(): Promise<void> {
    if (pending.current || !draft || !draftFingerprint || !resultFile || !expectedSource) return
    // Freeze both the exact validated revision and the selected file before awaiting.
    const own = ++generation.current, capturedFingerprint = currentFingerprint, capturedFile = resultFile
    const capturedSource = { ...expectedSource }
    pending.current = true; setBusy(true); setMessage('')
    try {
      const draftBytes = serializeBuildingLoadRevisionDraft(draft)
      const resultBytes = await read(capturedFile, BUILDING_MEMBER_RESULT_MAX_BYTES, 'stored target ResultIR')
      if (own !== generation.current) return
      const value = await attachBuildingRevisionResult(draftBytes, resultBytes, capturedSource)
      if (own !== generation.current) return
      setSession({ value, contextFingerprint: capturedFingerprint })
      setMessage('Attached the stored result to this frozen revision target. File bindings are consistent; execution origin is UNVERIFIED and every design review is NOT_REVIEWED. No analysis was run.')
    } catch (error) {
      if (own === generation.current) setMessage(`${error instanceof Error ? error.message : 'The stored result could not be attached.'} Any previously verified attached result is retained.`)
    } finally { if (own === generation.current) { pending.current = false; setBusy(false) } }
  }
  async function reopen(file?: File): Promise<void> {
    if (!file || pending.current) return
    const own = ++generation.current
    pending.current = true; setBusy(true); setMessage('')
    try {
      const body = await read(file, BUILDING_REVISION_RESULT_MAX_BYTES, 'linked revision result')
      if (own !== generation.current) return
      const value = await openBuildingRevisionResultAttachment(body)
      if (own !== generation.current) return
      setSession({ value, contextFingerprint: null })
      setMessage('Opened the self-contained linked revision result and recomputed its target, mapping and review from embedded files. File bindings are consistent; execution origin is UNVERIFIED. No analysis was run.')
    } catch (error) {
      if (own === generation.current) setMessage(`${error instanceof Error ? error.message : 'The linked revision result could not be opened.'} Any previously verified attached result is retained.`)
    } finally { if (own === generation.current) { pending.current = false; setBusy(false) } }
  }
  function download(body: Uint8Array, name: string): void {
    const url = URL.createObjectURL(new Blob([body as BlobPart], { type: 'application/json' }))
    urls.current.add(url)
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = name
    document.body.append(anchor); anchor.click(); anchor.remove()
    window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url) }, 0)
  }

  return <section className="wb2-rc-job wb2-building-revision-result" aria-label="Stored revision result attachment" data-building-revision-result>
    <h2>6. Open a stored result for a revised model</h2>
    <p>Attach an existing native ResultIR to the exact validated load revision above, or reopen one linked-result file on its own. This reads local files; it does not submit, calculate, authenticate an execution or perform a design check.</p>
    <p>The authoring revision remains NOT_RUN. A separate attached review records only stored-result file consistency, with execution origin UNVERIFIED and every member NOT_REVIEWED.</p>
    <label>Expected target result load source <select aria-label="Expected target result load source" value={selectedSource} disabled={busy || !draft || !draftFingerprint} onChange={event => {
      generation.current++; setSelectedSource(event.target.value); setMessage('Expected load source changed. Attach a matching file explicitly; any displayed review still uses its own frozen result and source.')
    }}><option value="">Choose the intended pattern or combination</option>{loadSources.map(source => <option key={`${source.kind}:${source.id}`} value={`${source.kind}:${source.id}`}>{source.kind === 'load_pattern' ? 'Pattern' : 'Combination'}: {source.id}</option>)}</select></label>
    <label className="wb2-portable-file">Stored target ResultIR file{' '}<input type="file" aria-label="Stored target ResultIR file" accept="application/json,.json" disabled={busy}
      onChange={event => { setResultFile(event.target.files?.[0] ?? null); setMessage('Selected target result changed. Any displayed attached review still uses its own frozen files.') }} /></label>
    <button type="button" className="wb2-btn" disabled={busy || !draft || !draftFingerprint || !resultFile || !expectedSource} onClick={() => void attach()}>Attach stored result to validated revision</button>
    <p>Select the intended load source explicitly. A ResultIR bound to another pattern or combination is rejected, even if that source exists in the same revised model.</p>
    {!draft || !draftFingerprint ? <p data-building-revision-result-target-needed>Validate the exact current load revision to attach a separate target ResultIR. You can reopen a self-contained linked revision result below without preparing or importing any parent files.</p> : null}
    <label className="wb2-portable-file">Import linked revision result{' '}<input type="file" aria-label="Import linked revision result" accept="application/json,.json" disabled={busy}
      onChange={event => { void reopen(event.target.files?.[0]); event.target.value = '' }} /></label>
    <p>Target ResultIR limit: 2 MiB. Self-contained linked revision result limit: 16 MiB. These are file admission limits, not model-size qualification.</p>
    {contextChanged ? <p role="status" data-building-revision-result-context-changed>The authoring draft context has changed or is no longer validated. The attached review retains its own frozen revision and result below; its forces have not been retargeted to the current edits. Validate and attach a matching result explicitly to replace it.</p> : null}
    {busy ? <p role="status">Checking local revision result files…</p> : null}
    {message ? <p role="status" data-building-revision-result-status>{message}</p> : null}
    {current ? <>
      <dl className="wb2-kv" data-building-revision-result-identity>
        <dt>Frozen revision ID</dt><dd>{current.draft.revision_id}</dd>
        <dt>Historical parent result ID</dt><dd>{current.lineage.parent.result_id}</dd>
        <dt>Historical parent load source</dt><dd>{current.lineage.parent_load_source.kind}: {current.lineage.parent_load_source.id}</dd>
        <dt>Attached result ID</dt><dd>{current.review.source.result_id}</dd>
        <dt>Attached result hash</dt><dd style={{ overflowWrap: 'anywhere' }}>{current.review.source.result_hash}</dd>
        <dt>Attached pattern</dt><dd>{current.review.source.load_pattern_id ?? 'None — result selects a combination'}</dd>
        <dt>Attached combination</dt><dd>{current.review.source.load_combination_id ?? 'None — result selects a pattern'}</dd>
        <dt>Consistency / execution origin / design review</dt><dd>STORED_RESULT_FILE_CONSISTENT / UNVERIFIED / NOT_REVIEWED</dd>
      </dl>
      <p>Parent stored result is historical context only. The attached file may select a different preserved pattern or combination; load-source labels are retained, and no like-for-like comparison or envelope is inferred.</p>
      <details><summary>Frozen revision, parent, target and load-source lineage</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }} data-building-revision-result-lineage>{JSON.stringify(current.lineage, null, 2)}</pre></details>
      <BuildingMemberForceReview key={`${current.review.source.result_hash}:${current.review.mapping_hash}`} review={current.review} heading="Attached revision member forces" headingLevel={3} />
      <h3>Save this separate linked result</h3>
      <p>The linked-result file embeds the frozen revision draft, its parent files and this exact target ResultIR. Reopening recomputes the target and declared mapping. It does not prove who ran a solver, reproduce a calculation or change the saved authoring record.</p>
      <div className="wb2-actions">
        <button type="button" className="wb2-btn" disabled={busy} onClick={() => download(current.attachmentBytes, 'building-revision-result.linked.json')}>Export linked revision result</button>
        <button type="button" className="wb2-btn" disabled={busy} onClick={() => download(current.mappingBytes, 'building-revision-result.mapping.json')}>Export linked result member mapping</button>
        <button type="button" className="wb2-btn" disabled={busy} onClick={() => download(current.reviewBytes, 'building-revision-result.review.json')}>Export linked result member review</button>
        <button type="button" className="wb2-btn" disabled={busy} onClick={() => download(current.lineageBytes, 'building-revision-result.lineage.json')}>Export linked result lineage</button>
        <button type="button" className="wb2-btn" disabled={busy} onClick={() => download(current.targetModelBytes, 'building-revision-result.model-ir.json')}>Export linked result target ModelIR</button>
        <button type="button" className="wb2-btn" disabled={busy} onClick={() => download(current.resultBytes, 'building-revision-result.result-ir.json')}>Export exact linked ResultIR</button>
      </div>
    </> : null}
  </section>
}
