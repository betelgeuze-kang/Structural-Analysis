import type { CaseModel } from './caseSchema'

export type ImportHealthSeverity = 'info' | 'warning' | 'error'
export type ImportHealthStatus = 'ready' | 'review' | 'blocked' | 'unavailable'
export type SilentLossStatus = 'clear' | 'detected' | 'unavailable'

export interface ImportHealthIssue {
  code: string
  severity: ImportHealthSeverity
  blocking: boolean
  message: string
  sourcePath?: string
  sourceLine?: number
  entityId?: string
  remediation?: string
}

export interface ImportHealthSummary {
  status: ImportHealthStatus
  schemaVersion?: string
  sourceFormat?: string
  supportedObjectCount?: number
  partialObjectCount?: number
  unsupportedObjectCount?: number
  silentLossStatus: SilentLossStatus
  issues: ImportHealthIssue[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function optionalCount(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
    ? value
    : undefined
}

function invalidIssue(index: number, message: string): ImportHealthIssue {
  return {
    code: `invalid_import_health_issue_${index}`,
    severity: 'error',
    blocking: true,
    message,
    remediation: 'Regenerate the import-health receipt with the documented v1 fields.',
  }
}

function normalizeIssue(value: unknown, index: number): ImportHealthIssue {
  if (!isRecord(value)) {
    return invalidIssue(index, 'Import-health issue row is not an object.')
  }

  const code = optionalString(value.code)
  const message = optionalString(value.message)
  const severity = value.severity
  if (!code || !message || !['info', 'warning', 'error'].includes(String(severity))) {
    return invalidIssue(index, 'Import-health issue row has an invalid code, message, or severity.')
  }
  if (value.blocking != null && typeof value.blocking !== 'boolean') {
    return invalidIssue(index, 'Import-health issue row has a non-boolean blocking value.')
  }
  if (
    value.sourceLine != null
    && (
      typeof value.sourceLine !== 'number'
      || !Number.isInteger(value.sourceLine)
      || value.sourceLine <= 0
    )
  ) {
    return invalidIssue(index, 'Import-health issue row has an invalid source line.')
  }

  const blocking = typeof value.blocking === 'boolean'
    ? value.blocking
    : severity === 'error'
  const sourceLine = typeof value.sourceLine === 'number'
    ? value.sourceLine
    : undefined

  return {
    code,
    message,
    severity: severity as ImportHealthSeverity,
    blocking,
    sourcePath: optionalString(value.sourcePath),
    sourceLine,
    entityId: optionalString(value.entityId),
    remediation: optionalString(value.remediation),
  }
}

export function summarizeImportHealth(model: CaseModel): ImportHealthSummary {
  const raw = model.importHealth
  if (raw == null) {
    return {
      status: 'unavailable',
      silentLossStatus: 'unavailable',
      issues: [],
    }
  }
  if (!isRecord(raw)) {
    return {
      status: 'blocked',
      silentLossStatus: 'unavailable',
      issues: [invalidIssue(0, 'model.importHealth is not an object.')],
    }
  }

  const issuesRaw = Array.isArray(raw.issues) ? raw.issues : []
  const issues = issuesRaw.map(normalizeIssue)
  if (raw.issues != null && !Array.isArray(raw.issues)) {
    issues.push(invalidIssue(issues.length, 'model.importHealth.issues is not an array.'))
  }

  const silentLossStatus: SilentLossStatus = raw.silentLossDetected === true
    ? 'detected'
    : raw.silentLossDetected === false
      ? 'clear'
      : 'unavailable'
  const supportedObjectCount = optionalCount(raw.supportedObjectCount)
  const partialObjectCount = optionalCount(raw.partialObjectCount)
  const unsupportedObjectCount = optionalCount(raw.unsupportedObjectCount)
  const hasBlockingIssue = issues.some((issue) => issue.blocking || issue.severity === 'error')
  const needsReview = issues.some((issue) => issue.severity === 'warning')
    || (partialObjectCount ?? 0) > 0
    || (unsupportedObjectCount ?? 0) > 0
    || silentLossStatus === 'unavailable'

  const status: ImportHealthStatus = silentLossStatus === 'detected' || hasBlockingIssue
    ? 'blocked'
    : needsReview
      ? 'review'
      : 'ready'

  return {
    status,
    schemaVersion: optionalString(raw.schemaVersion),
    sourceFormat: optionalString(raw.sourceFormat),
    supportedObjectCount,
    partialObjectCount,
    unsupportedObjectCount,
    silentLossStatus,
    issues,
  }
}
