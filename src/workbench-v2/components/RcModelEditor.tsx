import { useEffect, useId, useMemo, useState, type ReactElement } from 'react'
import {
  changeRcEditorRows, createRcEditorExample, rcEditorPreview, rcEditorSections,
  resolveRcEditorDraft, type RcEditorPreview,
} from '../model/rcModelEditor'

export interface RcModelEditorProps {
  value: Record<string, unknown> | null
  onChange: (value: Record<string, unknown>) => void
  onDirtyChange?: (dirty: boolean) => void
  disabled?: boolean
}

function ModelPreview({ model }: { model: RcEditorPreview }): ReactElement {
  const xs = model.nodes.map(n => n.x), ys = model.nodes.map(n => n.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const span = Math.max(maxX - minX, maxY - minY)
  const scale = span > 0 && Number.isFinite(span) ? 380 / span : 1
  const point = (id: string) => {
    const n = model.nodes.find(row => row.id === id)!
    return { x: 250 + (n.x - minX - (maxX - minX) / 2) * scale,
      y: 125 - (n.y - minY - (maxY - minY) / 2) * scale }
  }
  return <figure>
    <svg viewBox="0 0 500 250" role="img" aria-label="Authored RC model XY preview" style={{ maxHeight: 300, width: '100%', border: '1px solid currentColor' }}>
      <title>Authored RC model XY preview</title>
      {model.members.map((member, i) => {
        const a = point(member.from), b = point(member.to)
        return <g key={i} data-rc-preview-member={member.id}>
          <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="currentColor" strokeWidth="3" />
          <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 12} textAnchor="middle" fill="currentColor" fontSize="12">{member.id}</text>
        </g>
      })}
      {model.nodes.map(n => {
        const p = point(n.id)
        return <g key={n.id} data-rc-preview-node={n.id}>
          <circle cx={p.x} cy={p.y} r="4" fill="currentColor" />
          <text x={p.x} y={p.y - 20} textAnchor="middle" fill="currentColor" fontSize="12">{n.id}</text>
          {n.support.length > 0 && <>
            <path d={`M${p.x},${p.y + 6} l-9,15 h18 Z`} fill="none" stroke="currentColor" />
            <text x={p.x} y={p.y + 38} textAnchor="middle" fill="currentColor" fontSize="10">{n.support.join('/')}</text>
          </>}
        </g>
      })}
      {model.loads.filter(l => l.fx !== 0 || l.fy !== 0).map((load, i) => {
        const p = point(load.node), length = Math.hypot(load.fx, load.fy)
        const dx = load.fx / length * 30, dy = -load.fy / length * 30
        return <g key={i} aria-label={`${load.node} FX ${load.fx} kN FY ${load.fy} kN`}>
          <line x1={p.x - dx} y1={p.y - dy} x2={p.x} y2={p.y} stroke="currentColor" strokeWidth="2" />
          <circle cx={p.x - dx} cy={p.y - dy} r="2" fill="currentColor" />
        </g>
      })}
      <text x="10" y="240" fill="currentColor" fontSize="11">XY · coordinates in m · undeformed geometry</text>
    </svg>
    <figcaption>Draft geometry and authored supports/loads. This preview does not run or validate structural behavior.</figcaption>
  </figure>
}

/** Authoring stays local until Apply; this component has no transport or solver capability. */
export function RcModelEditor({ value, onChange, onDirtyChange, disabled = false }: RcModelEditorProps): ReactElement {
  const prefix = useId()
  const [base, setBase] = useState(value)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [exampleRevision, setExampleRevision] = useState('')
  const [message, setMessage] = useState('')
  const [dirty, setDirty] = useState(false)
  useEffect(() => { setBase(value); setEdits({}); setDirty(false); setMessage('') }, [value])
  const sections = useMemo(() => base ? rcEditorSections(base) : [], [base])
  const resolution = useMemo(() => base ? resolveRcEditorDraft(base, edits) : null, [base, edits])
  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])
  useEffect(() => () => { onDirtyChange?.(false) }, [onDirtyChange])
  const preview = useMemo(() => resolution?.value ? rcEditorPreview(resolution.value) : null, [resolution])
  const rowChange = (path: string, action: 'copy' | 'remove', index: number) => {
    if (disabled || !resolution?.value) return
    try {
      setBase(changeRcEditorRows(resolution.value, path, action, index))
      setEdits({}); setDirty(true); setMessage('Row changed locally. References are retained; resolve admission errors before Apply.')
    } catch (error) {
      setMessage(error instanceof Error && error.message === 'rc_editor_indexed_control_would_move'
        ? 'Removing this node would change the node selected by the indexed control DOF. Explicitly choose a control node that remains before removing it, or edit the complete request JSON.'
        : 'The row cannot be changed within this editor’s bounds.')
    }
  }
  return <section data-rc-model-editor aria-label="Structured RC model editor">
    <h3>Structured RC model editor</h3>
    <p>Edit a bounded serial cantilever, pin/roller beam or fixed/guided request. Units are m, kN and MPa as labeled. The original profile, solver settings, execution budget and source declaration are retained. The core service performs final input admission.</p>
    <details>
      <summary>Start from the repository RC cantilever example</summary>
      <p>This explicitly selected software example copies <code>examples/public_rc_fiber_frame_explicit_layers.json</code> and the bounded two-target browser request settings. It is not a validated specimen or a source attestation. Review and replace its physical inputs before use.</p>
      <label htmlFor={`${prefix}-source`}>Caller-declared source revision for example</label>
      <input id={`${prefix}-source`} value={exampleRevision} onChange={event => setExampleRevision(event.target.value)} disabled={disabled} placeholder="40 hexadecimal characters or sha256:…" />
      <button type="button" disabled={disabled || !/^(?:[a-f0-9]{40}|sha256:[a-f0-9]{64})$/.test(exampleRevision)} onClick={() => {
        setBase(createRcEditorExample(exampleRevision)); setEdits({}); setDirty(true)
        setMessage('Repository example loaded locally. Review every input, then Apply to update the submission draft.')
      }}>Load repository example locally</button>
    </details>
    {!base && <p>Import an RC request below, or explicitly load the repository example to begin editing.</p>}
    {base && <>
      <p>Profile: <code>{String(base.schema_version)}</code> · local changes: {dirty ? 'not applied' : 'none'}</p>
      {resolution?.value && Number.isInteger(resolution.value.config?.control_global_dof) && <p>Indexed control currently selects{' '}
        <strong>{String(resolution.value.model?.nodes?.[Math.floor(resolution.value.config.control_global_dof / 3)]?.id ?? 'unavailable')}</strong>{' '}
        {['UX', 'UY', 'RZ'][resolution.value.config.control_global_dof % 3] ?? 'unavailable'}. Copied nodes are appended so existing indexed controls retain their node.</p>}
      <fieldset disabled={disabled} style={{ minWidth: 0 }}>
        <legend>Authored model fields</legend>
        {sections.map((section, sectionIndex) => <details key={`${section.label}:${sectionIndex}`} open={section.label === 'Request' || section.label === 'Nodes'}>
          <summary>{section.label} ({section.rows.length})</summary>
          {section.rows.map((row, index) => <fieldset key={row.path || 'request'} style={{ minWidth: 0 }}>
            <legend>{row.label}</legend>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
              {row.fields.map((field, fieldIndex) => {
                const fieldId = `${prefix}-${sectionIndex}-${index}-${fieldIndex}`
                const related = resolution?.issues.filter(issue => issue.path === field.path || (issue.path !== '/' && field.path.startsWith(`${issue.path}/`))) ?? []
                return <label key={field.path} htmlFor={fieldId}>{field.label}
                  <input id={fieldId} data-rc-editor-field={field.path} value={edits[field.path] ?? field.value}
                    inputMode={field.kind === 'number' ? 'decimal' : undefined} aria-invalid={related.length > 0}
                    aria-describedby={related.length ? `${fieldId}-error` : undefined}
                    onChange={event => { setEdits(previous => ({ ...previous, [field.path]: event.target.value })); setDirty(true); setMessage('') }} />
                  {related.length > 0 && <small id={`${fieldId}-error`}>{related.map(issue => issue.message).join(' ')}</small>}
                </label>
              })}
            </div>
            {section.path && <p>
              <button type="button" disabled={!resolution?.value} onClick={() => rowChange(section.path!, 'copy', index)}>Copy {row.label}</button>{' '}
              <button type="button" disabled={!resolution?.value} onClick={() => rowChange(section.path!, 'remove', index)}>Remove {row.label}</button>
            </p>}
          </fieldset>)}
          {section.rows.length === 0 && <p>No rows remain. Undo the local changes to restore the imported rows.</p>}
        </details>)}
      </fieldset>
      {preview ? <ModelPreview model={preview} /> : <p data-rc-preview-unavailable>Preview unavailable until the current draft has finite, uniquely identified nodes.</p>}
      <div aria-live="polite">
        {resolution?.issues.length ? <><p>Resolve {resolution.issues.length} admission issue(s) before Apply:</p>
          <ul>{resolution.issues.map((issue, index) => <li key={`${issue.path}:${index}`}><code>{issue.path}</code>: {issue.message}</li>)}</ul></>
          : <p>Local profile and reference checks pass. No calculation has run.</p>}
        {message && <p role="status">{message}</p>}
      </div>
      <button type="button" disabled={disabled || !dirty || !resolution?.value || !!resolution.issues.length} onClick={() => {
        if (disabled || !resolution?.value || resolution.issues.length) return
        onChange(resolution.value); setDirty(false); setMessage('Applied to the submission draft. Submit is a separate explicit action.')
      }}>Apply structured model to draft</button>{' '}
      <button type="button" disabled={disabled || !dirty} onClick={() => { setBase(value); setEdits({}); setDirty(false); setMessage('Local edits discarded; the imported request is restored.') }}>Undo local model changes</button>
    </>}
  </section>
}
