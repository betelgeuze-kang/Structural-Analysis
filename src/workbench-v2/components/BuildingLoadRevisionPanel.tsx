import { useEffect, useRef, useState, type ReactElement } from 'react'
import {
  BUILDING_LOAD_REVISION_MAX_BYTES,
  prepareBuildingLoadRevision,
  openBuildingLoadRevisionDraft,
  serializeBuildingLoadRevisionDraft,
  getBuildingLoadRevisionEditorView,
  compileBuildingLoadRevision,
  createBuildingRevisionNodalLoad,
  type BuildingLoadRevisionDraft,
} from '../model/buildingLoadRevision'
import { registerUnsavedProjectGuard } from '../model/unsavedProjectGuard'

interface BuildingLoadRevisionPanelProps {
  modelBytes?: Uint8Array
  resultBytes?: Uint8Array
  mappingBytes?: Uint8Array
  sourceFingerprint?: string
}
type EditorView = Awaited<ReturnType<typeof getBuildingLoadRevisionEditorView>>
type Compilation = Awaited<ReturnType<typeof compileBuildingLoadRevision>>
type Components = 'FX' | 'FY' | 'FZ' | 'MX' | 'MY' | 'MZ'
const COMPONENTS: Components[] = ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ']
const unit = (name: Components): string => name.startsWith('F') ? 'N' : 'N·m'
type EditableLoad = Omit<EditorView['patterns'][number]['nodal_loads'][number], 'components_si'> & {
  components_si: Record<Components, string>
}
interface PatternEditor { id: string; selfWeight: [string, string, string]; loads: EditableLoad[] }
interface Session { draft: BuildingLoadRevisionDraft; view: EditorView; sourceFingerprint: string }

function formPatterns(draft: BuildingLoadRevisionDraft, view: EditorView): PatternEditor[] {
  return view.patterns.map(pattern => {
    const patch = draft.patches.find(row => row.pattern_id === pattern.id)
    return { id: pattern.id,
      selfWeight: (patch?.self_weight ?? pattern.self_weight).map(String) as [string, string, string],
      loads: (patch?.nodal_loads ?? pattern.nodal_loads).map(load => ({ ...structuredClone(load),
        components_si: Object.fromEntries(COMPONENTS.map(name => [name, String(load.components_si[name])])) as Record<Components, string>,
      })),
    }
  })
}
function fingerprint(draft: BuildingLoadRevisionDraft): string {
  return [draft.parent.model_ir.sha256, draft.parent.result_ir.sha256, draft.parent.mapping.sha256].join(':')
}
function finite(value: string, label: string): number {
  if (!value.trim() || !Number.isFinite(Number(value))) throw new Error(`${label} must be a finite, explicitly entered number.`)
  return Number(value)
}

/** Local authoring only: the saved source result is never a result of this revision. */
export function BuildingLoadRevisionPanel(props: BuildingLoadRevisionPanelProps): ReactElement {
  const [session, setSession] = useState<Session | null>(null)
  const [patterns, setPatterns] = useState<PatternEditor[]>([]), [patternId, setPatternId] = useState('')
  const [revisionId, setRevisionId] = useState('building.load.revision')
  const [newLoadId, setNewLoadId] = useState(''), [newNodeId, setNewNodeId] = useState('')
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [dirty, setDirty] = useState(false)
  const [compiled, setCompiled] = useState<Compilation | null>(null)
  const pending = useRef(false), generation = useRef(0), dirtyRef = useRef(false), urls = useRef(new Set<string>())
  const pendingNewLoad = Boolean(newLoadId || newNodeId)
  dirtyRef.current = dirty || pendingNewLoad
  useEffect(() => registerUnsavedProjectGuard(() => dirtyRef.current), [])
  useEffect(() => () => {
    generation.current++
    for (const url of urls.current) URL.revokeObjectURL(url)
    urls.current.clear()
  }, [])
  const canPrepare = Boolean(props.modelBytes && props.resultBytes && props.mappingBytes)
  const changedSource = session !== null && Boolean(props.sourceFingerprint) && session.sourceFingerprint !== props.sourceFingerprint
  function changed(): void { generation.current++; setCompiled(null); setDirty(true); setMessage('Load revision draft changed. Validate this exact draft before exporting a target model or revision record.') }
  function download(body: BlobPart, name: string): void {
    const url = URL.createObjectURL(new Blob([body], { type: 'application/json' }))
    urls.current.add(url)
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = name
    document.body.append(anchor); anchor.click(); anchor.remove()
    window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url) }, 0)
  }
  function mayReplace(): boolean {
    return !dirtyRef.current || window.confirm('This load revision has changes since its last draft download. Discard this local revision and replace it?')
  }
  function install(draft: BuildingLoadRevisionDraft, view: EditorView, prepared: boolean): void {
    setSession({ draft, view, sourceFingerprint: fingerprint(draft) }); setPatterns(formPatterns(draft, view))
    setPatternId(view.patterns[0]?.id ?? ''); setRevisionId(draft.revision_id)
    setNewNodeId(''); setNewLoadId(''); setCompiled(null); setDirty(prepared)
  }
  async function prepare(): Promise<void> {
    if (pending.current) return
    const { modelBytes, resultBytes, mappingBytes } = props
    if (!modelBytes || !resultBytes || !mappingBytes) {
      setMessage('Open a matching stored model, result and declared member mapping first, or import a self-contained saved revision draft.')
      return
    }
    // Capture the admitted triple before any await; later source selection cannot retarget it.
    const captured = { model: new Uint8Array(modelBytes), result: new Uint8Array(resultBytes), mapping: new Uint8Array(mappingBytes) }
    const own = ++generation.current; pending.current = true; setBusy(true); setMessage('')
    try {
      const draft = await prepareBuildingLoadRevision(captured.model, captured.result, captured.mapping, revisionId)
      const view = await getBuildingLoadRevisionEditorView(draft)
      if (own !== generation.current || !mayReplace()) return
      install(draft, view, true)
      setMessage('Prepared a load revision from the frozen admitted source. No calculation was run. Download the draft to preserve it.')
    } catch (error) { if (own === generation.current) setMessage(`${error instanceof Error ? error.message : 'Revision preparation failed.'} The previous revision is retained.`) }
    finally { if (own === generation.current) { pending.current = false; setBusy(false) } }
  }
  async function importDraft(file?: File): Promise<void> {
    if (!file || pending.current) return
    const own = ++generation.current; pending.current = true; setBusy(true); setMessage('')
    try {
      if (!file.size || file.size > BUILDING_LOAD_REVISION_MAX_BYTES) throw new Error(`Choose a non-empty revision draft of at most ${BUILDING_LOAD_REVISION_MAX_BYTES / 1024 / 1024} MiB.`)
      const bytes = new Uint8Array(await file.arrayBuffer())
      const draft = await openBuildingLoadRevisionDraft(bytes)
      const view = await getBuildingLoadRevisionEditorView(draft)
      if (own !== generation.current || !mayReplace()) return
      install(draft, view, false)
      setMessage('Opened the saved revision draft and its embedded parent files. Validate it to generate target downloads; opening a draft does not run or save a model.')
    } catch (error) { if (own === generation.current) setMessage(`${error instanceof Error ? error.message : 'The revision draft could not be opened.'} The previous revision and target downloads are retained.`) }
    finally { if (own === generation.current) { pending.current = false; setBusy(false) } }
  }
  function candidate(): BuildingLoadRevisionDraft {
    if (!session) throw new Error('Prepare or import a load revision first.')
    if (pendingNewLoad) throw new Error('Add the pending nodal load row or clear its entry fields before saving or validating. Pending fields are not a load definition.')
    const draft = structuredClone(session.draft)
    draft.revision_id = revisionId
    draft.patches = patterns.flatMap(pattern => {
      const self_weight = pattern.selfWeight.map((value, index) => finite(value, `${pattern.id} self-weight ${['X', 'Y', 'Z'][index]}`)) as [number, number, number]
      const nodal_loads = pattern.loads.map(load => ({ ...structuredClone(load), components_si:
        Object.fromEntries(COMPONENTS.map(name => [name, finite(load.components_si[name], `${load.id} ${name}`)])) as Record<Components, number>,
      }))
      const original = session.view.patterns.find(row => row.id === pattern.id)!
      return JSON.stringify({ self_weight, nodal_loads }) === JSON.stringify({ self_weight: original.self_weight, nodal_loads: original.nodal_loads })
        ? [] : [{ pattern_id: pattern.id, self_weight, nodal_loads }]
    })
    return draft
  }
  async function validate(): Promise<void> {
    if (pending.current) return
    const own = ++generation.current; pending.current = true; setBusy(true); setMessage('')
    try {
      const draft = candidate(), outcome = await compileBuildingLoadRevision(draft)
      if (own !== generation.current) return
      setSession(previous => previous && ({ ...previous, draft })); setCompiled(outcome)
      setMessage('Validated this exact load revision and generated target downloads. Target analysis is NOT_RUN and every design review remains NOT_REVIEWED. Validation does not save your draft.')
    } catch (error) { if (own === generation.current) { setCompiled(null); setMessage(`${error instanceof Error ? error.message : 'Revision validation failed.'} No target result was generated; the draft is retained.`) } }
    finally { if (own === generation.current) { pending.current = false; setBusy(false) } }
  }
  function saveDraft(): void {
    try {
      const draft = candidate(), bytes = serializeBuildingLoadRevisionDraft(draft)
      download(bytes as BlobPart, 'building-load-revision.draft.json')
      setSession(previous => previous && ({ ...previous, draft })); setDirty(false)
      setMessage('Downloaded the current load revision draft with its frozen parent files. This saves authoring work; it does not run analysis, apply a mass source or perform a design check.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'The draft could not be saved. Your edits are retained.') }
  }
  const selected = patterns.find(pattern => pattern.id === patternId)
  function updatePattern(change: (pattern: PatternEditor) => void): void {
    setPatterns(previous => previous.map(pattern => { if (pattern.id !== patternId) return pattern; const next = structuredClone(pattern); change(next); return next }))
    changed()
  }
  function addLoad(): void {
    if (!session || !selected) return
    const id = newLoadId.trim()
    if (!/^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(id) || !session.view.nodes.some(node => node.id === newNodeId)) { setMessage('Enter a stable load ID and explicitly select an existing model node.'); return }
    if (selected.loads.some(load => load.id === id)) { setMessage('That load ID is already used in this pattern.'); return }
    const original = session.view.patterns.find(pattern => pattern.id === patternId)!
    const used = new Set([...selected.loads, ...original.nodal_loads].map(load => load.index)); let index = 0
    while (used.has(index)) index++
    const load = createBuildingRevisionNodalLoad(revisionId, id, index, newNodeId, { FX: 0, FY: 0, FZ: 0, MX: 0, MY: 0, MZ: 0 })
    updatePattern(pattern => pattern.loads.push({ ...load,
      components_si: { FX: '0', FY: '0', FZ: '0', MX: '0', MY: '0', MZ: '0' },
    }))
    setNewLoadId(''); setNewNodeId(''); setMessage('Added an explicit zero-valued nodal load row. Enter its global components; no tributary area or automatic load distribution was applied.')
  }

  return <section className="wb2-rc-job wb2-building-load-revision" aria-label="Building static load revision" data-building-load-revision>
    <h2>5. Revise static loads while retaining physical member IDs</h2>
    <p>Create a local authoring revision from the admitted model, result and member mapping. Edit existing linear-static patterns; geometry, physical member IDs, other load definitions and combinations are preserved. Nothing is submitted or calculated here.</p>
    <p>This model format has no supported building mass-source setup. This editor does not convert weight to mass, distribute floor loads, apply KDS rules or run analysis.</p>
    <label>Load revision ID <input aria-label="Load revision ID" value={revisionId} maxLength={128} disabled={busy || Boolean(session)} onChange={event => { setRevisionId(event.target.value) }} /></label>{' '}
    <button type="button" className="wb2-btn" disabled={busy || !canPrepare} onClick={() => void prepare()}>Prepare load revision from admitted files</button>
    {!canPrepare ? <p data-building-load-source-needed>To prepare a new revision, first open a matching stored model, result and declared member mapping above. A saved revision draft already contains its parent files and can be imported directly below.</p> : null}
    <label className="wb2-portable-file">Import saved load revision draft{' '}<input type="file" aria-label="Import saved load revision draft" accept="application/json,.json" disabled={busy}
      onChange={event => { void importDraft(event.target.files?.[0]); event.target.value = '' }} /></label>
    {session ? <>
      {changedSource ? <p data-building-load-source-changed role="status">The displayed parent review has changed. This load revision still uses its own frozen parent files below. Prepare a replacement explicitly to use the newly admitted files; your draft has not been retargeted.</p> : null}
      <dl className="wb2-kv" data-building-load-parent>
        <dt>Frozen parent model</dt><dd>{session.view.parentIdentity.model_id}</dd>
        <dt>Frozen parent result</dt><dd>{session.view.parentIdentity.result_id}</dd>
        <dt>Source role</dt><dd>Original stored result is parent context only; it is not a result of the revised model or selected pattern.</dd>
      </dl>
      <details><summary>Frozen parent identities</summary><pre style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{JSON.stringify(session.view.parentIdentity, null, 2)}</pre></details>
      <fieldset disabled={busy}>
        <legend>Existing linear-static load pattern</legend>
        <label>Edit load pattern <select aria-label="Edit load pattern" value={patternId} onChange={event => setPatternId(event.target.value)}>
          {patterns.map(pattern => <option key={pattern.id}>{pattern.id}</option>)}
        </select></label>
        {selected ? <>
          <h3>Global self-weight multipliers</h3>
          <p>Dimensionless X/Y/Z multipliers of standard gravity 9.80665 m/s². These are not accelerations or a mass source.</p>
          {(['X', 'Y', 'Z'] as const).map((axis, index) => <label key={axis}>Self-weight {axis} multiplier{' '}<input type="number" step="any" aria-label={`Self-weight ${axis} multiplier`} value={selected.selfWeight[index]}
            onChange={event => { const value = event.target.value; updatePattern(pattern => { pattern.selfWeight[index] = value }) }} /></label>)}
          <h3>Explicit global nodal loads</h3>
          <p>Forces in N and moments in N·m use global axes. Existing load IDs, indices and source metadata are retained. Several distinct rows may intentionally act on the same node. Removing a row does not renumber surviving rows.</p>
          <div className="wb2-table-wrap"><table className="wb2-table" data-building-load-rows><caption>Nodal load rows in selected pattern {selected.id}; no automatic distribution</caption>
            <thead><tr><th>Load / index</th><th>Model node</th>{COMPONENTS.map(name => <th key={name}>{name} ({unit(name)})</th>)}<th>Action</th></tr></thead>
            <tbody>{selected.loads.map((load, rowIndex) => <tr key={`${load.id}:${load.index}`} data-building-nodal-load={load.id}>
              <th scope="row">{load.id} / {load.index}</th>
              <td><select aria-label={`Load ${load.id} node`} value={load.node_id} onChange={event => { const value = event.target.value; updatePattern(pattern => { pattern.loads[rowIndex].node_id = value }) }}>
                {session.view.nodes.map(node => <option key={node.id}>{node.id}</option>)}
              </select></td>
              {COMPONENTS.map(name => <td key={name}><input type="number" step="any" aria-label={`Load ${load.id} ${name} (${unit(name)})`} value={load.components_si[name]}
                onChange={event => { const value = event.target.value; updatePattern(pattern => { pattern.loads[rowIndex].components_si[name] = value }) }} /></td>)}
              <td><button type="button" className="wb2-btn" aria-label={`Remove load ${load.id}`} onClick={() => updatePattern(pattern => { pattern.loads.splice(rowIndex, 1) })}>Remove</button></td>
            </tr>)}</tbody>
          </table></div>
          {!selected.loads.length ? <p>No explicit nodal loads in this pattern. Preserved member loads and self-weight are separate definitions.</p> : null}
          <label>New nodal load ID <input aria-label="New nodal load ID" value={newLoadId} maxLength={128} onChange={event => { setNewLoadId(event.target.value); changed() }} /></label>{' '}
          <label>New load model node <select aria-label="New load model node" value={newNodeId} onChange={event => { setNewNodeId(event.target.value); changed() }}><option value="">Choose an existing node</option>{session.view.nodes.map(node => <option key={node.id}>{node.id}</option>)}</select></label>{' '}
          <button type="button" className="wb2-btn" onClick={addLoad}>Add explicit nodal load row</button>
          {pendingNewLoad ? <><button type="button" className="wb2-btn" onClick={() => { setNewLoadId(''); setNewNodeId(''); changed() }}>Clear pending nodal load entry</button>
            <p data-building-load-pending-entry>Add this row or clear its entry fields before saving or validating. These pending fields are not part of the revision draft.</p></> : null}
          <p>New rows start with six visible zeros for you to edit. A mapping orientation does not change global loads or transform member-local distributed loads.</p>
        </> : <p>No editable existing linear-static pattern is available.</p>}
      </fieldset>
      <p>Uniform member loads remain in their original initial-member-local frame, and combinations retain their original signed factors. This editor does not merge, envelope or reinterpret those definitions.</p>
      <p data-building-load-draft-status>{dirty ? 'Unsaved load revision draft. Validation and target downloads do not save this draft.' : 'The load revision draft matches its imported or downloaded file.'}</p>
      <div className="wb2-actions"><button type="button" className="wb2-btn" disabled={busy || pendingNewLoad} onClick={saveDraft}>Download load revision draft</button>
        <button type="button" className="wb2-btn" disabled={busy || pendingNewLoad} onClick={() => void validate()}>Validate load revision</button></div>
      {compiled ? <section aria-label="Validated load revision target" data-building-load-target>
        <h3>Target model: NOT_RUN / NOT_REVIEWED</h3>
        <p>No result is attached to this target. Stored force tables describe their separately admitted source, never this target. This revision’s own frozen parent identity is shown here.</p>
        <details><summary>Target model identities</summary><pre style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{JSON.stringify(compiled.targetIdentity, null, 2)}</pre></details>
        <div className="wb2-actions"><button type="button" className="wb2-btn" disabled={busy} onClick={() => download(compiled.modelBytes as BlobPart, 'building-load-revision.model-ir.json')}>Export revised ModelIR</button>
          <button type="button" className="wb2-btn" disabled={busy} onClick={() => download(JSON.stringify(compiled.revisionRecord, null, 2), 'building-load-revision.record.json')}>Export load revision record</button>
          <button type="button" className="wb2-btn" disabled={busy} onClick={() => download(compiled.recipeBytes as BlobPart, 'building-load-revision.recipe.json')}>Export load edit recipe</button></div>
        <p>Keep the revision draft to reopen these edits. A future, explicit analysis must produce a new result bound to this target before target member forces can be reviewed. File validation does not establish solver acceptance, design compliance or physical validity.</p>
      </section> : <p data-building-load-target-unavailable>Target downloads are unavailable until this exact draft is validated. No target result exists.</p>}
    </> : null}
    {busy ? <p role="status">Checking the local load revision…</p> : null}
    {message ? <p role="status" data-building-load-status>{message}</p> : null}
  </section>
}
