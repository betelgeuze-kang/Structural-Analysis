export const NEUTRAL_EDITOR_SCHEMA_VERSION = 'workbench-neutral-editor.v1' as const
export const NEUTRAL_EDITOR_CLAIM_BOUNDARY = 'Editor validation checks bounded table consistency only. JSON export does not imply import completeness, solver acceptance, analysis readiness, numerical correctness, design authority, public support, or release authority.' as const

export interface EditableNodeRow {
  id: string
  x: string
  y: string
  z: string
}

export interface EditableMemberRow {
  id: string
  nodeI: string
  nodeJ: string
  sectionId: string
}

export interface EditableSupportRow {
  nodeId: string
  ux: boolean
  uy: boolean
  uz: boolean
  rx: boolean
  ry: boolean
  rz: boolean
}

export interface EditableNodalLoadRow {
  id: string
  nodeId: string
  fx: string
  fy: string
  fz: string
  mx: string
  my: string
  mz: string
}

export interface EditableNeutralModel {
  schemaVersion: typeof NEUTRAL_EDITOR_SCHEMA_VERSION
  unitSystem: 'SI-kN-m'
  nodes: EditableNodeRow[]
  members: EditableMemberRow[]
  supports: EditableSupportRow[]
  nodalLoads: EditableNodalLoadRow[]
}

export type NeutralEditorEntity = 'model' | 'node' | 'member' | 'support' | 'nodalLoad'

export interface NeutralEditorIssue {
  code: string
  message: string
  entity: NeutralEditorEntity
  rowIndex?: number
  entityId?: string
  field?: string
}

export interface CanonicalNeutralModel {
  schemaVersion: typeof NEUTRAL_EDITOR_SCHEMA_VERSION
  unitSystem: 'SI-kN-m'
  nodes: Array<{ id: string; x: number; y: number; z: number }>
  members: Array<{ id: string; nodeI: string; nodeJ: string; sectionId: string }>
  supports: Array<{
    nodeId: string
    restrainedDofs: Array<'ux' | 'uy' | 'uz' | 'rx' | 'ry' | 'rz'>
  }>
  nodalLoads: Array<{
    id: string
    nodeId: string
    fx: number
    fy: number
    fz: number
    mx: number
    my: number
    mz: number
  }>
  claimBoundary: typeof NEUTRAL_EDITOR_CLAIM_BOUNDARY
}

export interface NeutralEditorValidation {
  status: 'ready' | 'blocked'
  issues: NeutralEditorIssue[]
  canonical: CanonicalNeutralModel | null
}

const LIMITS = {
  nodes: 100,
  members: 200,
  supports: 100,
  nodalLoads: 200,
} as const

function trimmed(value: string): string {
  return value.trim()
}

function parsedFinite(value: string): number | null {
  if (!value.trim()) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function issue(
  code: string,
  message: string,
  entity: NeutralEditorEntity,
  rowIndex?: number,
  entityId?: string,
  field?: string,
): NeutralEditorIssue {
  return { code, message, entity, rowIndex, entityId, field }
}

function validateUniqueIds<T>(
  rows: T[],
  entity: Exclude<NeutralEditorEntity, 'model' | 'support'>,
  readId: (row: T) => string,
  issues: NeutralEditorIssue[],
): Set<string> {
  const ids = new Set<string>()
  rows.forEach((row, rowIndex) => {
    const id = trimmed(readId(row))
    if (!id) {
      issues.push(issue(`${entity}_id_missing`, `${entity} id is required.`, entity, rowIndex, undefined, 'id'))
      return
    }
    if (ids.has(id)) {
      issues.push(issue(`${entity}_id_duplicate`, `${entity} id '${id}' is duplicated.`, entity, rowIndex, id, 'id'))
      return
    }
    ids.add(id)
  })
  return ids
}

function validateCount(
  count: number,
  minimum: number,
  maximum: number,
  field: keyof typeof LIMITS,
  issues: NeutralEditorIssue[],
): void {
  if (count < minimum) {
    issues.push(issue(`${field}_below_minimum`, `${field} requires at least ${minimum} row(s).`, 'model'))
  }
  if (count > maximum) {
    issues.push(issue(`${field}_above_limit`, `${field} exceeds the bounded editor limit of ${maximum}.`, 'model'))
  }
}

export function seedEditableNeutralModel(): EditableNeutralModel {
  return {
    schemaVersion: NEUTRAL_EDITOR_SCHEMA_VERSION,
    unitSystem: 'SI-kN-m',
    nodes: [
      { id: 'N1', x: '0', y: '0', z: '0' },
      { id: 'N2', x: '2', y: '0', z: '0' },
    ],
    members: [
      { id: 'M1', nodeI: 'N1', nodeJ: 'N2', sectionId: 'SEC-1' },
    ],
    supports: [
      { nodeId: 'N1', ux: true, uy: true, uz: true, rx: true, ry: true, rz: true },
    ],
    nodalLoads: [
      { id: 'L1', nodeId: 'N2', fx: '0', fy: '-10', fz: '0', mx: '0', my: '0', mz: '0' },
    ],
  }
}

export function validateEditableNeutralModel(model: EditableNeutralModel): NeutralEditorValidation {
  const issues: NeutralEditorIssue[] = []
  if (model.schemaVersion !== NEUTRAL_EDITOR_SCHEMA_VERSION) {
    issues.push(issue('schema_version_invalid', 'Editor schema version is not supported.', 'model'))
  }
  if (model.unitSystem !== 'SI-kN-m') {
    issues.push(issue('unit_system_invalid', 'Only the explicit SI-kN-m editor unit system is supported.', 'model'))
  }

  validateCount(model.nodes.length, 2, LIMITS.nodes, 'nodes', issues)
  validateCount(model.members.length, 1, LIMITS.members, 'members', issues)
  validateCount(model.supports.length, 1, LIMITS.supports, 'supports', issues)
  validateCount(model.nodalLoads.length, 0, LIMITS.nodalLoads, 'nodalLoads', issues)

  const nodeIds = validateUniqueIds(model.nodes, 'node', (row) => row.id, issues)
  validateUniqueIds(model.members, 'member', (row) => row.id, issues)
  validateUniqueIds(model.nodalLoads, 'nodalLoad', (row) => row.id, issues)

  const canonicalNodes: CanonicalNeutralModel['nodes'] = []
  model.nodes.forEach((row, rowIndex) => {
    const id = trimmed(row.id)
    const numeric = [row.x, row.y, row.z].map(parsedFinite)
    const fields = ['x', 'y', 'z'] as const
    numeric.forEach((value, fieldIndex) => {
      if (value == null) {
        issues.push(issue(
          'node_coordinate_invalid',
          `Node '${id || rowIndex + 1}' ${fields[fieldIndex]} must be a finite number.`,
          'node',
          rowIndex,
          id || undefined,
          fields[fieldIndex],
        ))
      }
    })
    if (id && numeric.every((value): value is number => value != null)) {
      canonicalNodes.push({ id, x: numeric[0], y: numeric[1], z: numeric[2] })
    }
  })

  const canonicalMembers: CanonicalNeutralModel['members'] = []
  const endpointPairs = new Set<string>()
  model.members.forEach((row, rowIndex) => {
    const id = trimmed(row.id)
    const nodeI = trimmed(row.nodeI)
    const nodeJ = trimmed(row.nodeJ)
    const sectionId = trimmed(row.sectionId)
    if (!nodeIds.has(nodeI)) {
      issues.push(issue('member_node_i_missing', `Member '${id || rowIndex + 1}' references missing node i '${nodeI}'.`, 'member', rowIndex, id || undefined, 'nodeI'))
    }
    if (!nodeIds.has(nodeJ)) {
      issues.push(issue('member_node_j_missing', `Member '${id || rowIndex + 1}' references missing node j '${nodeJ}'.`, 'member', rowIndex, id || undefined, 'nodeJ'))
    }
    if (nodeI && nodeI === nodeJ) {
      issues.push(issue('member_zero_topology', `Member '${id || rowIndex + 1}' endpoints must differ.`, 'member', rowIndex, id || undefined))
    }
    if (!sectionId) {
      issues.push(issue('member_section_missing', `Member '${id || rowIndex + 1}' requires a section id.`, 'member', rowIndex, id || undefined, 'sectionId'))
    }
    if (nodeI && nodeJ && nodeI !== nodeJ) {
      const pair = [nodeI, nodeJ].sort().join('\u0000')
      if (endpointPairs.has(pair)) {
        issues.push(issue('member_endpoint_pair_duplicate', `Member '${id || rowIndex + 1}' duplicates an existing unordered endpoint pair.`, 'member', rowIndex, id || undefined))
      }
      endpointPairs.add(pair)
    }
    if (id && nodeIds.has(nodeI) && nodeIds.has(nodeJ) && nodeI !== nodeJ && sectionId) {
      canonicalMembers.push({ id, nodeI, nodeJ, sectionId })
    }
  })

  const canonicalSupports: CanonicalNeutralModel['supports'] = []
  const supportedNodes = new Set<string>()
  model.supports.forEach((row, rowIndex) => {
    const nodeId = trimmed(row.nodeId)
    if (!nodeIds.has(nodeId)) {
      issues.push(issue('support_node_missing', `Support row references missing node '${nodeId}'.`, 'support', rowIndex, nodeId || undefined, 'nodeId'))
    }
    if (supportedNodes.has(nodeId) && nodeId) {
      issues.push(issue('support_node_duplicate', `Node '${nodeId}' has more than one support row.`, 'support', rowIndex, nodeId, 'nodeId'))
    }
    supportedNodes.add(nodeId)
    const restrainedDofs = (['ux', 'uy', 'uz', 'rx', 'ry', 'rz'] as const).filter((dof) => row[dof])
    if (!restrainedDofs.length) {
      issues.push(issue('support_empty', `Support at '${nodeId || rowIndex + 1}' restrains no DOF.`, 'support', rowIndex, nodeId || undefined))
    }
    if (nodeIds.has(nodeId) && restrainedDofs.length) {
      canonicalSupports.push({ nodeId, restrainedDofs })
    }
  })

  const canonicalLoads: CanonicalNeutralModel['nodalLoads'] = []
  model.nodalLoads.forEach((row, rowIndex) => {
    const id = trimmed(row.id)
    const nodeId = trimmed(row.nodeId)
    if (!nodeIds.has(nodeId)) {
      issues.push(issue('nodal_load_node_missing', `Nodal load '${id || rowIndex + 1}' references missing node '${nodeId}'.`, 'nodalLoad', rowIndex, id || undefined, 'nodeId'))
    }
    const fields = ['fx', 'fy', 'fz', 'mx', 'my', 'mz'] as const
    const components = fields.map((field) => parsedFinite(row[field]))
    components.forEach((value, fieldIndex) => {
      if (value == null) {
        issues.push(issue('nodal_load_component_invalid', `Nodal load '${id || rowIndex + 1}' ${fields[fieldIndex]} must be a finite number.`, 'nodalLoad', rowIndex, id || undefined, fields[fieldIndex]))
      }
    })
    if (components.every((value) => value === 0)) {
      issues.push(issue('nodal_load_zero', `Nodal load '${id || rowIndex + 1}' has no non-zero component.`, 'nodalLoad', rowIndex, id || undefined))
    }
    if (id && nodeIds.has(nodeId) && components.every((value): value is number => value != null) && components.some((value) => value !== 0)) {
      canonicalLoads.push({
        id,
        nodeId,
        fx: components[0],
        fy: components[1],
        fz: components[2],
        mx: components[3],
        my: components[4],
        mz: components[5],
      })
    }
  })

  if (issues.length) {
    return { status: 'blocked', issues, canonical: null }
  }

  return {
    status: 'ready',
    issues: [],
    canonical: {
      schemaVersion: NEUTRAL_EDITOR_SCHEMA_VERSION,
      unitSystem: 'SI-kN-m',
      nodes: canonicalNodes.sort((left, right) => left.id.localeCompare(right.id)),
      members: canonicalMembers.sort((left, right) => left.id.localeCompare(right.id)),
      supports: canonicalSupports.sort((left, right) => left.nodeId.localeCompare(right.nodeId)),
      nodalLoads: canonicalLoads.sort((left, right) => left.id.localeCompare(right.id)),
      claimBoundary: NEUTRAL_EDITOR_CLAIM_BOUNDARY,
    },
  }
}

export function canonicalNeutralModelJson(model: EditableNeutralModel): string | null {
  const validation = validateEditableNeutralModel(model)
  return validation.canonical == null
    ? null
    : `${JSON.stringify(validation.canonical, null, 2)}\n`
}
