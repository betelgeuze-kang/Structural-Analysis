import { useEffect, useId, useMemo, useState, type ReactElement } from 'react'
import {
  changeRcEditorRows, changeRcPortalDimensions, createRcEditorExample, createRcPortalEditorExample, rcEditorPreview, rcEditorSections, rcPortalDimensions,
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
  const width = maxX - minX, height = maxY - minY
  const fit = Math.min(width > 0 ? 380 / width : Infinity, height > 0 ? 150 / height : Infinity)
  const scale = Number.isFinite(fit) && fit > 0 ? fit : 1
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
        const color = load.phase === 'fixed' ? '#e9a23b' : '#56a8e9'
        return <g key={i} data-rc-preview-load-phase={load.phase} aria-label={`${load.phase === 'fixed' ? 'Fixed preload' : 'Reference load'} ${load.node} FX ${load.fx} kN FY ${load.fy} kN`}>
          <title>{load.phase === 'fixed' ? 'Fixed preload' : 'Reference load'}: {load.node}, FX {load.fx} kN, FY {load.fy} kN</title>
          <line x1={p.x - dx} y1={p.y - dy} x2={p.x} y2={p.y} stroke={color} strokeWidth="2" />
          <circle cx={p.x - dx} cy={p.y - dy} r="2" fill={color} />
        </g>
      })}
      <text x="10" y="240" fill="currentColor" fontSize="11">XY · coordinates in m · undeformed geometry</text>
    </svg>
    <figcaption>Draft geometry and authored supports/loads. Blue: proportional reference loads. Orange: fixed preload applied before control targets. This preview does not run or validate structural behavior.</figcaption>
  </figure>
}

/** Authoring stays local until Apply; this component has no transport or solver capability. */
export function RcModelEditor({ value, onChange, onDirtyChange, disabled = false }: RcModelEditorProps): ReactElement {
  const prefix = useId()
  const [base, setBase] = useState(value)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [dimensionInputs, setDimensionInputs] = useState<{ span: string; height: string } | null>(null)
  const [exampleRevision, setExampleRevision] = useState('')
  const [portalRevision, setPortalRevision] = useState('')
  const [message, setMessage] = useState('')
  const [dirty, setDirty] = useState(false)
  useEffect(() => { setBase(value); setEdits({}); setDimensionInputs(null); setDirty(false); setMessage('') }, [value])
  const sections = useMemo(() => base ? rcEditorSections(base) : [], [base])
  const resolution = useMemo(() => base ? resolveRcEditorDraft(base, edits) : null, [base, edits])
  const dimensions = useMemo(() => base ? rcPortalDimensions(base, edits) : null, [base, edits])
  const dimensionChange = useMemo(() => base && dimensionInputs ? changeRcPortalDimensions(base, edits, dimensionInputs.span, dimensionInputs.height) : null, [base, edits, dimensionInputs])
  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])
  useEffect(() => () => { onDirtyChange?.(false) }, [onDirtyChange])
  const preview = useMemo(() => resolution?.value ? rcEditorPreview(resolution.value) : null, [resolution])
  const rowChange = (path: string, action: 'copy' | 'remove', index: number) => {
    if (disabled || dimensionInputs || !resolution?.value) return
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
    <p>Edit a supported cantilever, pin/roller beam, fixed/guided request or one-storey, one-bay RC portal. Units are m, kN and MPa as labeled. The original profile, solver settings, execution budget and source declaration are retained. The core service performs final input admission.</p>
    <details>
      <summary>Start from the repository RC cantilever example</summary>
      <p>This explicitly selected software example copies <code>examples/public_rc_fiber_frame_explicit_layers.json</code> and the bounded two-target browser request settings. It is not a validated specimen or a source attestation. Review and replace its physical inputs before use.</p>
      <label htmlFor={`${prefix}-source`}>Caller-declared source revision for example</label>
      <input id={`${prefix}-source`} value={exampleRevision} onChange={event => setExampleRevision(event.target.value)} disabled={disabled} placeholder="40 hexadecimal characters or sha256:…" />
      <button type="button" disabled={disabled || !/^(?:[a-f0-9]{40}|sha256:[a-f0-9]{64})$/.test(exampleRevision)} onClick={() => {
        setBase(createRcEditorExample(exampleRevision)); setEdits({}); setDimensionInputs(null); setDirty(true)
        setMessage('Repository example loaded locally. Review every input, then Apply to update the submission draft.')
      }}>Load repository example locally</button>
    </details>
    <details>
      <summary>Start from the RC portal example</summary>
      <p>The shared portal example has two fixed bases, two columns and one beam. Fixed downward roof loads are applied before horizontal displacement targets. Edit the rectangle's node coordinates, sections, reinforcement and loads, then Apply. This software example carries no specimen or design qualification.</p>
      <label htmlFor={`${prefix}-portal-source`}>Caller-declared source revision for portal example</label>
      <input id={`${prefix}-portal-source`} value={portalRevision} onChange={event => setPortalRevision(event.target.value)} disabled={disabled} placeholder="40 hexadecimal characters" />
      <button type="button" disabled={disabled || !/^[a-f0-9]{40}$/.test(portalRevision)} onClick={() => {
        setBase(createRcPortalEditorExample(portalRevision)); setEdits({}); setDimensionInputs(null); setDirty(true)
        setMessage('Portal example loaded locally. Review its gravity preload, lateral targets and model, then Apply. No job has been submitted.')
      }}>Load portal example locally</button>
    </details>
    {!base && <p>Import an RC request below, or explicitly load the repository example to begin editing.</p>}
    {base && <>
      <p>Profile: <code>{String(base.schema_version)}</code> · local changes: {dirty ? 'not applied' : 'none'}</p>
      {(base.config as Record<string, unknown> | undefined)?.experimental_portal_frame === true && <>
        <p data-rc-portal-profile>RC portal: four rectangular corner nodes, two fixed bases, two columns and one beam. Gravity FY remains negative at both roof nodes; reference loads are horizontal FX.</p>
        <fieldset data-rc-portal-dimensions disabled={disabled} style={{ minWidth: 0 }}>
          <legend>Portal dimensions</legend>
          <p>Keep the left-hand X and base Y origin. Update both right-hand X coordinates and both roof Y coordinates together; member directions, supports, loads and all other fields are retained.</p>
          {dimensions ? <p data-rc-portal-current-dimensions>Current local model: span {dimensions.span} m, height {dimensions.height} m; origin ({dimensions.leftX}, {dimensions.baseY}) m.</p>
            : <p>Dimension update unavailable until the current node coordinates, members and fixed bases form a rectangle. Resolve those fields below; other edits remain in place.</p>}
          {(['span', 'height'] as const).map(name => {
            const fieldId = `${prefix}-portal-${name}`
            const related = dimensionChange?.issues.filter(issue => issue.path === `/portal_dimensions/${name}`) ?? []
            return <div key={name}>
              <label htmlFor={fieldId}>Portal {name} (m)</label>{' '}
              <input id={fieldId} inputMode="decimal" style={{ maxWidth: '100%', boxSizing: 'border-box' }}
                value={dimensionInputs?.[name] ?? (dimensions ? String(dimensions[name]) : '')}
                aria-invalid={related.length > 0} aria-describedby={related.length ? `${fieldId}-error` : undefined}
                onChange={event => {
                  setDimensionInputs(previous => ({ span: previous?.span ?? (dimensions ? String(dimensions.span) : ''), height: previous?.height ?? (dimensions ? String(dimensions.height) : ''), [name]: event.target.value }))
                  setDirty(true); setMessage('')
                }} />
              {related.length > 0 && <small id={`${fieldId}-error`}>{related.map(issue => issue.message).join(' ')}</small>}
            </div>
          })}
          <button type="button" disabled={!dimensionChange?.edits} onClick={() => {
            if (disabled || !dimensionChange?.edits) return
            setEdits(dimensionChange.edits); setDimensionInputs(null); setDirty(true)
            setMessage('Portal dimensions updated locally. Review the coordinates and preview, then Apply to update the submission draft.')
          }}>Update portal dimensions locally</button>
          {dimensionInputs && <div data-rc-portal-dimensions-pending aria-live="polite">
            <p>Dimension inputs are not yet reflected in the current local model. Update dimensions locally or Undo before Apply or saving the project.</p>
            {dimensionChange?.issues.filter(issue => issue.path === '/portal_dimensions').map(issue => <p key={issue.path}>{issue.message}</p>)}
          </div>}
        </fieldset>
      </>}
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
              <button type="button" disabled={!!dimensionInputs || !resolution?.value} onClick={() => rowChange(section.path!, 'copy', index)}>Copy {row.label}</button>{' '}
              <button type="button" disabled={!!dimensionInputs || !resolution?.value} onClick={() => rowChange(section.path!, 'remove', index)}>Remove {row.label}</button>
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
      <button type="button" disabled={disabled || !dirty || !!dimensionInputs || !resolution?.value || !!resolution.issues.length} onClick={() => {
        if (disabled || dimensionInputs || !resolution?.value || resolution.issues.length) return
        onChange(resolution.value); setDirty(false); setMessage('Applied to the submission draft. Submit is a separate explicit action.')
      }}>Apply structured model to draft</button>{' '}
      <button type="button" disabled={disabled || !dirty} onClick={() => { setBase(value); setEdits({}); setDimensionInputs(null); setDirty(false); setMessage('Local edits discarded; the imported request is restored.') }}>Undo local model changes</button>
    </>}
  </section>
}
