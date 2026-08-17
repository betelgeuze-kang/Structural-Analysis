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

function invalidFieldIssue(field: string, message: string): ImportHealthIssue {
  return {
    code: `invalid_import_health_${field}`,
    severity: 'error',
    blocking: true,
    message,
    remediation: 'Regenerate the import-health receipt with an explicit valid field value.',
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

  const issues = Array.isArray(raw.issues)
    ? raw.issues.map(normalizeIssue)
    : [invalidFieldIssue('issues', 'model.importHealth.issues must be an explicit array.')]

  const schemaVersion = optionalString(raw.schemaVersion)
  if (!schemaVersion) {
    issues.push(invalidFieldIssue('schema_version', 'Import-health schemaVersion is missing or invalid.'))
  }
  const sourceFormat = optionalString(raw.sourceFormat)
  if (!sourceFormat) {
    issues.push(invalidFieldIssue('source_format', 'Import-health sourceFormat is missing or invalid.'))
  }

  const silentLossStatus: SilentLossStatus = raw.silentLossDetected === true
    ? 'detected'
    : raw.silentLossDetected === false
      ? 'clear'
      : 'unavailable'
  if (typeof raw.silentLossDetected !== 'boolean') {
    issues.push(invalidFieldIssue(
      'silent_loss_detected',
      'Import-health silentLossDetected must be an explicit boolean.',
    ))
  }

  const supportedObjectCount = optionalCount(raw.supportedObjectCount)
  if (supportedObjectCount == null) {
    issues.push(invalidFieldIssue(
      'supported_object_count',
      'Import-health supportedObjectCount must be a non-negative integer.',
    ))
  }
  const partialObjectCount = optionalCount(raw.partialObjectCount)
  if (partialObjectCount == null) {
    issues.push(invalidFieldIssue(
      'partial_object_count',
      'Import-health partialObjectCount must be a non-negative integer.',
    ))
  }
  const unsupportedObjectCount = optionalCount(raw.unsupportedObjectCount)
  if (unsupportedObjectCount == null) {
    issues.push(invalidFieldIssue(
      'unsupported_object_count',
      'Import-health unsupportedObjectCount must be a non-negative integer.',
    ))
  }

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
    schemaVersion,
    sourceFormat,
    supportedObjectCount,
    partialObjectCount,
    unsupportedObjectCount,
    silentLossStatus,
    issues,
  }
}
