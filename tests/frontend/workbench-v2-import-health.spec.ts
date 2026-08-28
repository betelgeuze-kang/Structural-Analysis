import { expect, test, type Page } from '@playwright/test'
import type { CaseModel } from '../../src/workbench-v2/model/caseSchema'
import { summarizeImportHealth } from '../../src/workbench-v2/model/importHealth'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`

test.setTimeout(60000)

async function open(page: Page): Promise<void> {
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
}

function modelWithImportHealth(importHealth: unknown): CaseModel {
  return { importHealth } as unknown as CaseModel
}

function completeReceipt(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schemaVersion: 'workbench-import-health.v1',
    sourceFormat: 'MGT',
    silentLossDetected: false,
    supportedObjectCount: 3,
    partialObjectCount: 0,
    unsupportedObjectCount: 0,
    issues: [],
    ...overrides,
  }
}

test.describe('Workbench v2 — import health', () => {
  test('renders producer evidence without promoting a partial import', async ({ page }) => {
    await open(page)
    const panel = page.locator('[data-wb2-import-health]')
    await expect(panel).toBeVisible()
    await expect(panel).toHaveAttribute('data-import-health-status', 'review')
    await expect(panel).toContainText('MGT')
    await expect(panel).toContainText('demo/mgt-plant-02.mgt:184')
    await expect(panel.locator('[data-import-health-code="mgt_elastic_link_metadata_only"]')).toBeVisible()
    await expect(panel).toContainText(/does not infer a clean import/i)
  })

  test('does not infer a clean import when evidence is absent', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="unavailable"]').click()
    const panel = page.locator('[data-wb2-import-health]')
    await expect(panel).toHaveAttribute('data-import-health-status', 'unavailable')
    await expect(panel.locator('[data-wb2-import-health-unavailable]')).toContainText(
      /clean import is not inferred/i,
    )
  })

  test('malformed issue rows are preserved as blocking diagnostics', () => {
    const summary = summarizeImportHealth(modelWithImportHealth(completeReceipt({
      issues: ['invalid-row'],
    })))
    expect(summary.status).toBe('blocked')
    expect(summary.issues).toHaveLength(1)
    expect(summary.issues[0]).toMatchObject({
      code: 'invalid_import_health_issue_0',
      severity: 'error',
      blocking: true,
    })
  })

  test('malformed summary fields block instead of degrading to ready or review', () => {
    const summary = summarizeImportHealth(modelWithImportHealth({
      schemaVersion: '',
      sourceFormat: 17,
      silentLossDetected: 'false',
      supportedObjectCount: -1,
      partialObjectCount: 1.5,
      unsupportedObjectCount: '0',
      issues: [],
    }))
    expect(summary.status).toBe('blocked')
    expect(summary.issues.map((issue) => issue.code)).toEqual(expect.arrayContaining([
      'invalid_import_health_schema_version',
      'invalid_import_health_source_format',
      'invalid_import_health_silent_loss_detected',
      'invalid_import_health_supported_object_count',
      'invalid_import_health_partial_object_count',
      'invalid_import_health_unsupported_object_count',
    ]))
  })

  test('missing issue array blocks an otherwise complete receipt', () => {
    const receipt = completeReceipt()
    delete receipt.issues
    const summary = summarizeImportHealth(modelWithImportHealth(receipt))
    expect(summary.status).toBe('blocked')
    expect(summary.issues).toContainEqual(expect.objectContaining({
      code: 'invalid_import_health_issues',
      blocking: true,
    }))
  })

  test('detected silent loss blocks an otherwise complete receipt', () => {
    const summary = summarizeImportHealth(modelWithImportHealth(completeReceipt({
      silentLossDetected: true,
    })))
    expect(summary.status).toBe('blocked')
    expect(summary.silentLossStatus).toBe('detected')
  })

  test('unsupported schema identity blocks otherwise valid evidence', () => {
    const summary = summarizeImportHealth(modelWithImportHealth(completeReceipt({
      schemaVersion: 'workbench-import-health.v2',
    })))
    expect(summary.status).toBe('blocked')
    expect(summary.issues).toContainEqual(expect.objectContaining({
      code: 'invalid_import_health_schema_version',
      blocking: true,
    }))
  })

  test('unsafe integer counts and source lines fail closed', () => {
    const summary = summarizeImportHealth(modelWithImportHealth(completeReceipt({
      supportedObjectCount: Number.MAX_SAFE_INTEGER + 1,
      issues: [{
        code: 'unsafe-line',
        severity: 'warning',
        blocking: false,
        message: 'unsafe source line',
        sourceLine: Number.MAX_SAFE_INTEGER + 1,
      }],
    })))
    expect(summary.status).toBe('blocked')
    expect(summary.issues.map((issue) => issue.code)).toEqual(expect.arrayContaining([
      'invalid_import_health_supported_object_count',
      'invalid_import_health_issue_0',
    ]))
    expect(summary.supportedObjectCount).toBeUndefined()
  })

  test('ready requires complete explicit no-loss evidence and no review signal', () => {
    const summary = summarizeImportHealth(modelWithImportHealth(completeReceipt()))
    expect(summary.status).toBe('ready')
  })
})
