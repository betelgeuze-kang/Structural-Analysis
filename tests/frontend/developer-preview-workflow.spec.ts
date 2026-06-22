import { expect, test } from '@playwright/test'

const baseUrl = process.env.DEVELOPER_PREVIEW_BASE_URL ?? 'http://127.0.0.1:4173'

const workflowSteps = [
  { id: 'import', label: 'Import' },
  { id: 'model_health', label: 'Model Health' },
  { id: 'analysis_setup', label: 'Analysis Setup' },
  { id: 'run_monitor', label: 'Run & Monitor' },
  { id: 'compare_report', label: 'Compare & Report' },
]

test('Developer Preview workflow shell exposes five task steps without readiness promotion', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      errors.push(message.text())
    }
  })

  await page.goto(baseUrl, { waitUntil: 'networkidle' })

  const workflowShell = page.locator('[data-phase5-gui-workflow-shell="true"]')
  await expect(workflowShell).toBeVisible()
  await expect(workflowShell).toHaveAttribute('data-phase5-feature-module', 'DeveloperPreviewWorkflowPanel')
  await expect(workflowShell).toContainText('Import → Model Health → Analysis Setup → Run & Monitor → Compare & Report')
  await expect(workflowShell).toContainText('workflow blocked')
  await expect(workflowShell).toContainText('GUI shell')
  await expect(workflowShell).toContainText('5/5')
  await expect(workflowShell).toContainText('Execution pass')
  await expect(workflowShell).toContainText('0/5')
  await expect(workflowShell).toContainText('UX observation')
  await expect(workflowShell).toContainText('blocked')
  const vocabulary = workflowShell.locator('[data-phase5-status-vocabulary="ready blocked missing error"]')
  await expect(vocabulary).toContainText('ready')
  await expect(vocabulary).toContainText('blocked')
  await expect(vocabulary).toContainText('missing')
  await expect(vocabulary).toContainText('error')
  const valueKindLegend = workflowShell.locator(
    '[data-phase5-value-kind-legend="exact_value derived_proxy reference_value"]',
  )
  await expect(valueKindLegend).toContainText('exact value')
  await expect(valueKindLegend).toContainText('derived proxy')
  await expect(valueKindLegend).toContainText('reference value')
  await expect(workflowShell.locator('[data-phase5-value-kind="exact_value"]')).toHaveCount(7)
  await expect(workflowShell.locator('[data-phase5-value-kind="derived_proxy"]')).toHaveCount(5)
  await expect(workflowShell.locator('[data-phase5-value-kind="reference_value"]')).toHaveCount(3)
  const provenanceDisclosure = workflowShell.locator('[data-phase5-provenance-disclosure="collapsed"]')
  await expect(provenanceDisclosure).not.toHaveAttribute('open', '')
  await expect(provenanceDisclosure.locator('[data-phase5-provenance-summary="advanced provenance"]')).toContainText(
    'Advanced provenance',
  )
  await provenanceDisclosure.locator('summary').click()
  await expect(provenanceDisclosure.locator('[data-phase5-provenance-details="true"]')).toContainText('Claim boundary')
  const selectionState = workflowShell.locator('[data-phase5-selection-state="unified"]')
  await expect(selectionState).toContainText('single selection state')
  await expect(selectionState).toContainText('3D/table/chart/comparison row')
  await expect(selectionState.locator('[data-phase5-selection-channel="3d"]')).toContainText('3d')
  await expect(selectionState.locator('[data-phase5-selection-channel="table"]')).toContainText('table')
  await expect(selectionState.locator('[data-phase5-selection-channel="chart"]')).toContainText('chart')
  await expect(selectionState.locator('[data-phase5-selection-channel="comparison_row"]')).toContainText(
    'comparison row',
  )
  const workerBoundary = workflowShell.locator('[data-phase5-worker-boundary="web_worker"]')
  await expect(workerBoundary).toBeVisible()
  await expect(workerBoundary).toContainText('Web Worker boundary')
  await expect(workerBoundary).toContainText('off the UI thread')
  await expect(workerBoundary).toContainText('does not prove execution')
  await expect(workerBoundary.locator('[data-phase5-worker-task="ifc_parse"]')).toContainText('ifc parse')
  await expect(workerBoundary.locator('[data-phase5-worker-task="result_processing"]')).toContainText(
    'result processing',
  )
  const evidenceConsoleAbsorption = workflowShell.locator(
    '[data-phase5-evidence-console-absorption="compare_report"]',
  )
  await expect(evidenceConsoleAbsorption).toBeVisible()
  await expect(evidenceConsoleAbsorption).toContainText('Evidence Console absorption')
  await expect(evidenceConsoleAbsorption).toContainText('Compare & Report')
  await expect(evidenceConsoleAbsorption).toContainText('does not prove launch readiness')
  await expect(evidenceConsoleAbsorption.locator('[data-phase5-evidence-console-feature="case_list"]')).toContainText(
    'case list',
  )
  await expect(
    evidenceConsoleAbsorption.locator('[data-phase5-evidence-console-feature="reference_vs_engine_comparison"]'),
  ).toContainText('reference vs engine comparison')
  await expect(
    evidenceConsoleAbsorption.locator('[data-phase5-evidence-console-feature="reproduce_bundle_export"]'),
  ).toContainText('reproduce bundle export')
  const routeState = workflowShell.locator('[data-phase5-route-state="true"]')
  await expect(routeState).toBeVisible()
  await expect(routeState).toHaveAttribute('data-phase5-route-id', 'developer-preview-local-workflow')
  await expect(routeState).toHaveAttribute('data-phase5-case-id', 'open-benchmark-seed-corpus')
  await expect(routeState).toHaveAttribute('data-phase5-run-id', 'execution-receipt-pending')
  await expect(routeState).toHaveAttribute('data-phase5-route-status', 'blocked')
  await expect(routeState).toContainText('route/case/run blocked')
  await expect(routeState).toContainText('route/case/run-centered workflow state')

  for (const step of workflowSteps) {
    const stepCard = workflowShell.locator(`[data-phase5-workflow-step="${step.id}"]`)
    await expect(stepCard).toBeVisible()
    await expect(stepCard).toHaveAttribute('data-phase5-workflow-status', 'blocked')
    await expect(stepCard).toContainText(`Phase5 workflow step: ${step.label}`)
    await expect(stepCard.locator('h3')).toHaveText(step.label)
  }

  await expect(workflowShell.locator('[data-phase5-workflow-step="import"]')).toContainText(
    'file and license/provenance review',
  )
  await expect(workflowShell.locator('[data-phase5-workflow-step="model_health"]')).toContainText(
    'disconnected component checks',
  )
  await expect(workflowShell.locator('[data-phase5-workflow-step="analysis_setup"]')).toContainText(
    'solver tolerance controls',
  )
  await expect(workflowShell.locator('[data-phase5-workflow-step="run_monitor"]')).toContainText(
    'residual and increment trace',
  )
  await expect(workflowShell.locator('[data-phase5-workflow-step="compare_report"]')).toContainText(
    'reproduction bundle export',
  )
  await expect(workflowShell.locator('[data-phase5-workflow-step="compare_report"]')).toContainText(
    'Evidence Console absorption',
  )

  expect(errors).toEqual([])
})
