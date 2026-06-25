// Typed schema + safe normalization for the Workbench v2 case model.
// Mirrors the static prototype fixture (workbench-demo.v1) but is provider-fed;
// no UI component reads raw JSON or a file path directly.

export interface WorkbenchProject {
  id: string | null
  name: string | null
}

export interface WorkbenchCase {
  id: string | null
  label: string | null
  structureFamily: string | null
  loadCombination: string | null
}

export interface WorkbenchStatus {
  solverConnected: boolean | null
  p0: string | null
  p1: string | null
  gpu: string | null
}

export interface ReferenceRow {
  quantity: string | null
  unit: string | null
  reference: number | null
  engine: number | null
}

export interface MemberRef {
  id: string
  label: string | null
}

export interface WorkbenchModel {
  schemaVersion: string | null
  dataModeRaw: string | null
  claimBoundary: string | null
  project: WorkbenchProject
  case: WorkbenchCase
  status: WorkbenchStatus
  residualHistory: number[]
  referenceComparison: ReferenceRow[]
  members: MemberRef[]
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function num(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function boolOrNull(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

export function normalizeModel(raw: unknown): WorkbenchModel {
  const r = asRecord(raw)
  const project = asRecord(r.project)
  const kase = asRecord(r.case)
  const status = asRecord(r.status)

  const residualHistory = Array.isArray(r.residual_history)
    ? r.residual_history.map((v) => num(v)).filter((v): v is number => v != null)
    : []

  const referenceComparison = Array.isArray(r.reference_comparison)
    ? r.reference_comparison.map((row) => {
        const rr = asRecord(row)
        return {
          quantity: str(rr.quantity),
          unit: str(rr.unit),
          reference: num(rr.reference),
          engine: num(rr.engine),
        }
      })
    : []

  const members = Array.isArray(r.members)
    ? r.members
        .map((m) => {
          const mr = asRecord(m)
          const id = str(mr.id)
          return id ? { id, label: str(mr.label) } : null
        })
        .filter((m): m is MemberRef => m != null)
    : []

  return {
    schemaVersion: str(r.schema_version),
    dataModeRaw: str(r.data_mode),
    claimBoundary: str(r.claim_boundary),
    project: { id: str(project.id), name: str(project.name) },
    case: {
      id: str(kase.id),
      label: str(kase.label),
      structureFamily: str(kase.structure_family),
      loadCombination: str(kase.load_combination),
    },
    status: {
      solverConnected: boolOrNull(status.solver_connected),
      p0: str(status.p0),
      p1: str(status.p1),
      gpu: str(status.gpu),
    },
    residualHistory,
    referenceComparison,
    members,
  }
}
