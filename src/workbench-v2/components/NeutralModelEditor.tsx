import { useMemo, useState, type ReactElement } from 'react'
import {
  NEUTRAL_EDITOR_CLAIM_BOUNDARY,
  canonicalNeutralModelJson,
  seedEditableNeutralModel,
  validateEditableNeutralModel,
  type EditableMemberRow,
  type EditableNeutralModel,
  type EditableNodalLoadRow,
  type EditableNodeRow,
} from '../model/editableNeutralModel'
import './neutralModelEditor.css'

const DOFS = ['ux', 'uy', 'uz', 'rx', 'ry', 'rz'] as const
const LOAD_FIELDS = ['fx', 'fy', 'fz', 'mx', 'my', 'mz'] as const
type SupportDof = (typeof DOFS)[number]

function nextId(prefix: string, existing: string[]): string {
  const ids = new Set(existing.map((value) => value.trim()))
  let index = ids.size + 1
  while (ids.has(`${prefix}${index}`)) index += 1
  return `${prefix}${index}`
}

export function NeutralModelEditor(): ReactElement {
  const [model, setModel] = useState<EditableNeutralModel>(() => seedEditableNeutralModel())
  const validation = useMemo(() => validateEditableNeutralModel(model), [model])
  const canonicalJson = useMemo(() => canonicalNeutralModelJson(model), [model])

  function updateNode(index: number, field: keyof EditableNodeRow, value: string): void {
    setModel((current) => ({
      ...current,
      nodes: current.nodes.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row),
    }))
  }

  function updateMember(index: number, field: keyof EditableMemberRow, value: string): void {
    setModel((current) => ({
      ...current,
      members: current.members.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row),
    }))
  }

  function updateSupportNode(index: number, value: string): void {
    setModel((current) => ({
      ...current,
      supports: current.supports.map((row, rowIndex) => rowIndex === index ? { ...row, nodeId: value } : row),
    }))
  }

  function updateSupportDof(index: number, dof: SupportDof, value: boolean): void {
    setModel((current) => ({
      ...current,
      supports: current.supports.map((row, rowIndex) => rowIndex === index ? { ...row, [dof]: value } : row),
    }))
  }

  function updateLoad(index: number, field: keyof EditableNodalLoadRow, value: string): void {
    setModel((current) => ({
      ...current,
      nodalLoads: current.nodalLoads.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row),
    }))
  }

  function addNode(): void {
    setModel((current) => ({
      ...current,
      nodes: [
        ...current.nodes,
        {
          id: nextId('N', current.nodes.map((row) => row.id)),
          x: '0',
          y: '0',
          z: '0',
        },
      ],
    }))
  }

  function addMember(): void {
    setModel((current) => ({
      ...current,
      members: [
        ...current.members,
        {
          id: nextId('M', current.members.map((row) => row.id)),
          nodeI: current.nodes[0]?.id ?? '',
          nodeJ: current.nodes[1]?.id ?? '',
          sectionId: 'SEC-1',
        },
      ],
    }))
  }

  function addSupport(): void {
    setModel((current) => ({
      ...current,
      supports: [
        ...current.supports,
        {
          nodeId: current.nodes[0]?.id ?? '',
          ux: true,
          uy: true,
          uz: true,
          rx: true,
          ry: true,
          rz: true,
        },
      ],
    }))
  }

  function addLoad(): void {
    setModel((current) => ({
      ...current,
      nodalLoads: [
        ...current.nodalLoads,
        {
          id: nextId('L', current.nodalLoads.map((row) => row.id)),
          nodeId: current.nodes.at(-1)?.id ?? '',
          fx: '0',
          fy: '-1',
          fz: '0',
          mx: '0',
          my: '0',
          mz: '0',
        },
      ],
    }))
  }

  return (
    <section
      className="wb2-panel wb2-neutral-editor"
      data-wb2-neutral-editor
      data-neutral-editor-status={validation.status}
      aria-labelledby="wb2-neutral-editor-title"
    >
      <div className="wb2-neutral-editor__header">
        <div>
          <h2 id="wb2-neutral-editor-title" className="wb2-panel__title">Neutral model table editor</h2>
          <p className="wb2-note">
            Local bounded authoring only. The editor does not submit a solver job or infer analysis readiness.
          </p>
        </div>
        <div className="wb2-actions">
          <span
            className={`wb2-chip ${validation.status === 'ready' ? 'wb2-chip--live' : 'wb2-chip--blocked'}`}
            data-neutral-editor-chip
          >
            {validation.status === 'ready' ? 'EXPORT READY' : 'BLOCKED'}
          </span>
          <button
            type="button"
            className="wb2-btn"
            onClick={() => setModel(seedEditableNeutralModel())}
            data-neutral-editor-reset
          >
            Reset seed
          </button>
        </div>
      </div>

      <EditorSection title="Nodes" addLabel="Add node" onAdd={addNode}>
        <div className="wb2-table-scroll">
          <table className="wb2-table wb2-editor-table" data-neutral-editor-nodes>
            <thead><tr><th>ID</th><th>X (m)</th><th>Y (m)</th><th>Z (m)</th><th>Action</th></tr></thead>
            <tbody>
              {model.nodes.map((row, index) => (
                <tr key={`node-${index}`}>
                  <EditorTextCell label={`Node ${index + 1} id`} value={row.id} onChange={(value) => updateNode(index, 'id', value)} testId={`node-${index}-id`} />
                  <EditorTextCell label={`Node ${index + 1} x`} value={row.x} onChange={(value) => updateNode(index, 'x', value)} inputMode="decimal" testId={`node-${index}-x`} />
                  <EditorTextCell label={`Node ${index + 1} y`} value={row.y} onChange={(value) => updateNode(index, 'y', value)} inputMode="decimal" testId={`node-${index}-y`} />
                  <EditorTextCell label={`Node ${index + 1} z`} value={row.z} onChange={(value) => updateNode(index, 'z', value)} inputMode="decimal" testId={`node-${index}-z`} />
                  <DeleteCell label={`Delete node ${index + 1}`} onDelete={() => setModel((current) => ({ ...current, nodes: current.nodes.filter((_, rowIndex) => rowIndex !== index) }))} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </EditorSection>

      <EditorSection title="Members" addLabel="Add member" onAdd={addMember}>
        <div className="wb2-table-scroll">
          <table className="wb2-table wb2-editor-table" data-neutral-editor-members>
            <thead><tr><th>ID</th><th>Node i</th><th>Node j</th><th>Section ID</th><th>Action</th></tr></thead>
            <tbody>
              {model.members.map((row, index) => (
                <tr key={`member-${index}`}>
                  <EditorTextCell label={`Member ${index + 1} id`} value={row.id} onChange={(value) => updateMember(index, 'id', value)} testId={`member-${index}-id`} />
                  <EditorTextCell label={`Member ${index + 1} node i`} value={row.nodeI} onChange={(value) => updateMember(index, 'nodeI', value)} testId={`member-${index}-node-i`} />
                  <EditorTextCell label={`Member ${index + 1} node j`} value={row.nodeJ} onChange={(value) => updateMember(index, 'nodeJ', value)} testId={`member-${index}-node-j`} />
                  <EditorTextCell label={`Member ${index + 1} section id`} value={row.sectionId} onChange={(value) => updateMember(index, 'sectionId', value)} testId={`member-${index}-section`} />
                  <DeleteCell label={`Delete member ${index + 1}`} onDelete={() => setModel((current) => ({ ...current, members: current.members.filter((_, rowIndex) => rowIndex !== index) }))} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </EditorSection>

      <EditorSection title="Supports" addLabel="Add support" onAdd={addSupport}>
        <div className="wb2-table-scroll">
          <table className="wb2-table wb2-editor-table" data-neutral-editor-supports>
            <thead><tr><th>Node</th>{DOFS.map((dof) => <th key={dof}>{dof}</th>)}<th>Action</th></tr></thead>
            <tbody>
              {model.supports.map((row, index) => (
                <tr key={`support-${index}`}>
                  <EditorTextCell label={`Support ${index + 1} node`} value={row.nodeId} onChange={(value) => updateSupportNode(index, value)} testId={`support-${index}-node`} />
                  {DOFS.map((dof) => (
                    <td key={dof}>
                      <input
                        type="checkbox"
                        checked={row[dof]}
                        aria-label={`Support ${index + 1} ${dof}`}
                        onChange={(event) => updateSupportDof(index, dof, event.currentTarget.checked)}
                        data-neutral-editor-input={`support-${index}-${dof}`}
                      />
                    </td>
                  ))}
                  <DeleteCell label={`Delete support ${index + 1}`} onDelete={() => setModel((current) => ({ ...current, supports: current.supports.filter((_, rowIndex) => rowIndex !== index) }))} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </EditorSection>

      <EditorSection title="Nodal loads" addLabel="Add nodal load" onAdd={addLoad}>
        <div className="wb2-table-scroll">
          <table className="wb2-table wb2-editor-table wb2-editor-table--loads" data-neutral-editor-loads>
            <thead><tr><th>ID</th><th>Node</th>{LOAD_FIELDS.map((field) => <th key={field}>{field}</th>)}<th>Action</th></tr></thead>
            <tbody>
              {model.nodalLoads.map((row, index) => (
                <tr key={`load-${index}`}>
                  <EditorTextCell label={`Load ${index + 1} id`} value={row.id} onChange={(value) => updateLoad(index, 'id', value)} testId={`load-${index}-id`} />
                  <EditorTextCell label={`Load ${index + 1} node`} value={row.nodeId} onChange={(value) => updateLoad(index, 'nodeId', value)} testId={`load-${index}-node`} />
                  {LOAD_FIELDS.map((field) => (
                    <EditorTextCell
                      key={field}
                      label={`Load ${index + 1} ${field}`}
                      value={row[field]}
                      onChange={(value) => updateLoad(index, field, value)}
                      inputMode="decimal"
                      testId={`load-${index}-${field}`}
                    />
                  ))}
                  <DeleteCell label={`Delete load ${index + 1}`} onDelete={() => setModel((current) => ({ ...current, nodalLoads: current.nodalLoads.filter((_, rowIndex) => rowIndex !== index) }))} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </EditorSection>

      <div className="wb2-neutral-editor__result-grid">
        <section className="wb2-neutral-editor__issues" aria-labelledby="wb2-neutral-editor-issues-title">
          <h3 id="wb2-neutral-editor-issues-title">Validation</h3>
          {validation.issues.length ? (
            <ul data-neutral-editor-issues>
              {validation.issues.map((item, index) => (
                <li key={`${item.code}-${item.rowIndex ?? 'model'}-${index}`} data-neutral-editor-issue={item.code}>
                  <strong>{item.code}</strong>: {item.message}
                </li>
              ))}
            </ul>
          ) : (
            <p className="wb2-note" data-neutral-editor-valid>No bounded table consistency issue detected.</p>
          )}
        </section>
        <section className="wb2-neutral-editor__preview" aria-labelledby="wb2-neutral-editor-preview-title">
          <h3 id="wb2-neutral-editor-preview-title">Canonical JSON preview</h3>
          {canonicalJson == null ? (
            <p className="wb2-unavailable" data-neutral-editor-preview-blocked>
              JSON export is unavailable while validation is blocked.
            </p>
          ) : (
            <pre data-neutral-editor-json>{canonicalJson}</pre>
          )}
        </section>
      </div>

      <p className="wb2-claim" data-neutral-editor-claim>{NEUTRAL_EDITOR_CLAIM_BOUNDARY}</p>
    </section>
  )
}

interface EditorSectionProps {
  title: string
  addLabel: string
  onAdd: () => void
  children: ReactElement
}

function EditorSection({ title, addLabel, onAdd, children }: EditorSectionProps): ReactElement {
  return (
    <section className="wb2-neutral-editor__section">
      <div className="wb2-neutral-editor__section-header">
        <h3>{title}</h3>
        <button type="button" className="wb2-member-btn" onClick={onAdd}>{addLabel}</button>
      </div>
      {children}
    </section>
  )
}

interface EditorTextCellProps {
  label: string
  value: string
  onChange: (value: string) => void
  inputMode?: 'text' | 'decimal'
  testId: string
}

function EditorTextCell({ label, value, onChange, inputMode = 'text', testId }: EditorTextCellProps): ReactElement {
  return (
    <td>
      <input
        className="wb2-editor-input"
        value={value}
        aria-label={label}
        inputMode={inputMode}
        onChange={(event) => onChange(event.currentTarget.value)}
        data-neutral-editor-input={testId}
      />
    </td>
  )
}

interface DeleteCellProps {
  label: string
  onDelete: () => void
}

function DeleteCell({ label, onDelete }: DeleteCellProps): ReactElement {
  return (
    <td>
      <button type="button" className="wb2-editor-delete" onClick={onDelete} aria-label={label}>Delete</button>
    </td>
  )
}
