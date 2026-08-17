import { expect, test, type Page } from '@playwright/test'
import {
  NEUTRAL_EDITOR_CLAIM_BOUNDARY,
  canonicalNeutralModelJson,
  seedEditableNeutralModel,
  validateEditableNeutralModel,
} from '../../src/workbench-v2/model/editableNeutralModel'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`

test.setTimeout(60_000)

async function open(page: Page): Promise<void> {
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30_000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15_000 })
  await page.locator('[data-wb2-neutral-editor]').waitFor({ state: 'visible', timeout: 15_000 })
}

test.describe('Workbench v2 — bounded neutral-model editor', () => {
  test('seed model is ready and canonical JSON is deterministic', () => {
    const model = seedEditableNeutralModel()
    const first = validateEditableNeutralModel(model)
    const second = validateEditableNeutralModel(structuredClone(model))
    expect(first.status).toBe('ready')
    expect(first.issues).toEqual([])
    expect(second.canonical).toEqual(first.canonical)
    expect(canonicalNeutralModelJson(model)).toBe(canonicalNeutralModelJson(structuredClone(model)))
    expect(first.canonical?.claimBoundary).toBe(NEUTRAL_EDITOR_CLAIM_BOUNDARY)
  })

  test('missing references and duplicate endpoint pairs fail closed', () => {
    const model = seedEditableNeutralModel()
    model.members.push({
      id: 'M2',
      nodeI: 'N2',
      nodeJ: 'N1',
      sectionId: 'SEC-1',
    })
    model.nodalLoads[0].nodeId = 'MISSING'
    const validation = validateEditableNeutralModel(model)
    expect(validation.status).toBe('blocked')
    expect(validation.canonical).toBeNull()
    expect(validation.issues.map((item) => item.code)).toEqual(expect.arrayContaining([
      'member_endpoint_pair_duplicate',
      'nodal_load_node_missing',
    ]))
    expect(canonicalNeutralModelJson(model)).toBeNull()
  })

  test('renders a ready seed with bounded export-only claim', async ({ page }) => {
    await open(page)
    const editor = page.locator('[data-wb2-neutral-editor]')
    await expect(editor).toHaveAttribute('data-neutral-editor-status', 'ready')
    await expect(editor.locator('[data-neutral-editor-chip]')).toContainText('EXPORT READY')
    await expect(editor.locator('[data-neutral-editor-json]')).toContainText('"schemaVersion": "workbench-neutral-editor.v1"')
    await expect(editor.locator('[data-neutral-editor-json]')).toContainText('"id": "N1"')
    await expect(editor.locator('[data-neutral-editor-claim]')).toContainText(/does not imply.*solver acceptance/i)
  })

  test('invalid member reference blocks preview and reset restores seed', async ({ page }) => {
    await open(page)
    const editor = page.locator('[data-wb2-neutral-editor]')
    const nodeJ = editor.locator('[data-neutral-editor-input="member-0-node-j"]')
    await nodeJ.fill('UNKNOWN')
    await expect(editor).toHaveAttribute('data-neutral-editor-status', 'blocked')
    await expect(editor.locator('[data-neutral-editor-chip]')).toContainText('BLOCKED')
    await expect(editor.locator('[data-neutral-editor-issue="member_node_j_missing"]')).toBeVisible()
    await expect(editor.locator('[data-neutral-editor-preview-blocked]')).toContainText(/unavailable.*blocked/i)
    await expect(editor.locator('[data-neutral-editor-json]')).toHaveCount(0)

    await editor.locator('[data-neutral-editor-reset]').click()
    await expect(editor).toHaveAttribute('data-neutral-editor-status', 'ready')
    await expect(editor.locator('[data-neutral-editor-issue="member_node_j_missing"]')).toHaveCount(0)
    await expect(editor.locator('[data-neutral-editor-json]')).toContainText('"nodeJ": "N2"')
  })

  test('deleting a required node remains blocked instead of inferring a usable model', async ({ page }) => {
    await open(page)
    const editor = page.locator('[data-wb2-neutral-editor]')
    await editor.getByRole('button', { name: 'Delete node 2' }).click()
    await expect(editor).toHaveAttribute('data-neutral-editor-status', 'blocked')
    await expect(editor.locator('[data-neutral-editor-issue="nodes_below_minimum"]')).toBeVisible()
    await expect(editor.locator('[data-neutral-editor-issue="member_node_j_missing"]')).toBeVisible()
    await expect(editor.locator('[data-neutral-editor-preview-blocked]')).toBeVisible()
  })
})
