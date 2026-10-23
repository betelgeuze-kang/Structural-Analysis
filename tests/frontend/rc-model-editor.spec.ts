import { expect, test } from '@playwright/test'
import {
  changeRcEditorRows, createRcEditorExample, rcEditorPreview, rcEditorSections,
  resolveRcEditorDraft, validateRcEditorRequest,
} from '../../src/workbench-v2/model/rcModelEditor'

const revision = 'a'.repeat(40)
const request = () => createRcEditorExample(revision)

test('explicit repository example requires an authored source declaration and retains bounded settings', () => {
  const invalid = createRcEditorExample('')
  expect(validateRcEditorRequest(invalid).some(issue => issue.path === '/')).toBe(true)
  const value = request()
  expect(validateRcEditorRequest(value)).toEqual([])
  expect(value.source_revision).toBe(revision)
  expect(value.config.targets_m).toEqual([-1e-6, -2e-6])
  expect(value.execution_config).toEqual({ chunk_target_count: 1, maximum_api_invocations: 8 })
})

test('geometric and material edits preserve the complete imported profile and do not mutate its source', () => {
  const original = request(), snapshot = JSON.stringify(original)
  const edited = resolveRcEditorDraft(original, {
    '/model/nodes/1/coordinates/0': '4.5',
    '/model/materials/0/yield_stress_mpa': '300',
    '/model/sections/0/steel_layers/0/bar_area_m2': '0.00021',
  })
  expect(edited.issues).toEqual([])
  expect(edited.value!.model.nodes[1].coordinates[0]).toBe(4.5)
  expect(edited.value!.model.materials[0].yield_stress_mpa).toBe(300)
  for (const key of ['config', 'execution_config', 'source_revision', 'operation', 'schema_version', 'result_contract']) expect(edited.value![key]).toEqual(original[key])
  expect(JSON.stringify(original)).toBe(snapshot)
  expect(rcEditorPreview(edited.value!)!.nodes[1].x).toBe(4.5)
})

for (const raw of ['', ' ', '-', 'NaN', 'Infinity', '1e999', '0x10', '3 trailing']) {
  test(`invalid numeric draft ${JSON.stringify(raw)} is never coerced to zero or an earlier geometry`, () => {
    const edits = { '/model/nodes/1/coordinates/0': raw }
    const resolved = resolveRcEditorDraft(request(), edits)
    expect(resolved.value).toBeNull()
    expect(resolved.issues[0].path).toBe('/model/nodes/1/coordinates/0')
    expect(edits['/model/nodes/1/coordinates/0']).toBe(raw)
  })
}

test('renaming a node exposes every dangling reference instead of silently rewriting connectivity or loads', () => {
  const result = resolveRcEditorDraft(request(), { '/model/nodes/1/id': 'NEW_NODE' })
  expect(result.value!.model.elements[0].nodes).toEqual(['N1', 'N2'])
  expect(result.value!.model.loads[0].node).toBe('N2')
  expect(result.issues.map(i => i.path)).toEqual(expect.arrayContaining(['/model/elements/0/nodes', '/model/loads/0/node']))
})

test('unsupported topology, wrong material kind and bar geometry are refused before Apply', () => {
  const result = resolveRcEditorDraft(request(), {
    '/model/elements/0/nodes/1': 'N1',
    '/model/sections/0/concrete_material': 'steel',
    '/model/sections/0/steel_layers/0/y_m': '0.4',
  })
  expect(result.issues.map(i => i.path)).toEqual(expect.arrayContaining([
    '/model/elements/0/nodes', '/model/elements', '/model/sections/0/concrete_material', '/model/sections/0',
  ]))
})

test('control targets and authored reversal limits retain their transport admission checks', () => {
  expect(resolveRcEditorDraft(request(), { '/config/targets_m': '-0.000001, -0.000003' }).issues).toEqual([])
  for (const raw of ['0.1,', '1, Infinity', '-0.000001, -0.000001', '-0.000001, 0.000001']) {
    expect(resolveRcEditorDraft(request(), { '/config/targets_m': raw }).issues.length).toBeGreaterThan(0)
  }
  expect(resolveRcEditorDraft(request(), { '/config/control_global_dof': '2' }).issues.length).toBeGreaterThan(0)
})

test('copy and removal are explicit, preserve original references and expose invalid intermediate drafts', () => {
  const original = request()
  const copied = changeRcEditorRows(original, '/model/nodes', 'copy', 1)
  expect(copied.model.nodes).toHaveLength(3)
  expect(copied.model.nodes[2]).toEqual({ ...original.model.nodes[1], id: '' })
  expect(validateRcEditorRequest(copied).length).toBeGreaterThan(0)
  expect(() => changeRcEditorRows(original, '/model/nodes', 'remove', 1)).toThrow('rc_editor_indexed_control_would_move')
  const explicit = request()
  delete explicit.config.control_global_dof
  explicit.config.control_node_id = 'N2'
  const removed = changeRcEditorRows(explicit, '/model/nodes', 'remove', 1)
  expect(removed.model.elements[0].nodes).toEqual(['N1', 'N2'])
  expect(validateRcEditorRequest(removed).some(i => i.path === '/model/elements/0/nodes')).toBe(true)
  expect(original.model.nodes).toHaveLength(2)
  const copyFirst = changeRcEditorRows(original, '/model/nodes', 'copy', 0)
  expect(copyFirst.model.nodes[1].id).toBe('N2')
  expect(copyFirst.config.control_global_dof).toBe(4)
  expect(() => changeRcEditorRows(original, '/config/targets_m', 'remove', 0)).toThrow('rc_editor_row_path_invalid')
})

test('pin/roller and fixed/guided imports keep their explicit opt-ins and support contracts', () => {
  const pin = request()
  pin.schema_version = 'structural-analysis-job-request.v4'
  pin.config.schema_version = 'bounded-rc-fiber-direct-control-request.v4'
  pin.config.experimental_pin_roller_beam = true
  pin.model.nodes = [{ id: 'N1', coordinates: [0, 0, 0] }, { id: 'N2', coordinates: [1, 0, 0] }, { id: 'N3', coordinates: [2, 0, 0] }]
  pin.model.elements.push({ ...pin.model.elements[0], id: 'M2', nodes: ['N2', 'N3'] })
  pin.model.supports = [{ node: 'N1', dofs: ['UX', 'UY'] }, { node: 'N3', dofs: ['UY'] }]
  expect(resolveRcEditorDraft(pin, { '/model/sections/0/width_m': '0.5' }).issues).toEqual([])
  const guide = request()
  guide.schema_version = 'structural-analysis-job-request.v5'
  guide.config.schema_version = 'bounded-rc-fiber-direct-control-request.v5'
  guide.config.experimental_fixed_guided_axial = true
  guide.config.control_global_dof = 3
  guide.model.supports.push({ node: 'N2', dofs: ['UY', 'RZ'] })
  guide.model.loads[0].components = { FX: 1, FY: 0, FZ: 0, MX: 0, MY: 0, MZ: 0 }
  const resolved = resolveRcEditorDraft(guide, { '/model/nodes/1/coordinates/0': '4' })
  expect(resolved.issues).toEqual([])
  expect(resolved.value!.config.experimental_fixed_guided_axial).toBe(true)
})

test('preview excludes dangling members and refuses duplicate IDs and overflowing extents', () => {
  const value = request()
  expect(rcEditorPreview(value)!.members).toEqual([{ id: 'M1', from: 'N1', to: 'N2' }])
  value.model.elements[0].nodes[1] = 'missing'
  expect(rcEditorPreview(value)!.members).toEqual([])
  value.model.nodes[1].id = 'N1'
  expect(rcEditorPreview(value)).toBeNull()
  value.model.nodes[1].id = 'N2'
  value.model.nodes[0].coordinates[0] = -1e308
  value.model.nodes[1].coordinates[0] = 1e308
  expect(rcEditorPreview(value)).toBeNull()
  expect(validateRcEditorRequest(value).some(issue => issue.path === '/model/nodes')).toBe(true)
})

test('untrusted material keys never become editable object paths, and oversized lists stay bounded', () => {
  const value = request()
  value.model.materials[0]['nested/path'] = 123
  expect(rcEditorSections(value).flatMap(s => s.rows.flatMap(r => r.fields)).some(f => f.path.includes('nested/path'))).toBe(false)
  expect(resolveRcEditorDraft(value, { '/model/materials/0/nested/path': '5' }).value).toBeNull()
  value.model.nodes = Array.from({ length: 1000 }, (_, i) => ({ id: `N${i}`, coordinates: [i, 0, 0] }))
  expect(rcEditorSections(value).find(s => s.label === 'Nodes')!.rows.length).toBeLessThanOrEqual(48)
  expect(validateRcEditorRequest(value).some(i => i.path === '/model/nodes')).toBe(true)
})

test('browser keeps invalid text local, updates preview from parsed draft and applies without submitting a job', async ({ page }) => {
  const posts: string[] = []
  page.on('request', outgoing => { if (outgoing.method() === 'POST') posts.push(outgoing.url()) })
  await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs' } })
  await page.goto(`${process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'}/#/workbench-v2`)
  await page.getByText('Submit a new RC input', { exact: true }).click()
  await page.getByText('Start from the repository RC cantilever example', { exact: true }).click()
  await page.getByLabel('Caller-declared source revision for example').fill(revision)
  await page.getByRole('button', { name: 'Load repository example locally' }).click()
  const coordinate = page.locator('[data-rc-editor-field="/model/nodes/1/coordinates/0"]')
  const apply = page.getByRole('button', { name: 'Apply structured model to draft' })
  const submit = page.getByRole('button', { name: 'Submit RC analysis', exact: true })
  await coordinate.fill('')
  await expect(coordinate).toHaveValue('')
  await expect(apply).toBeDisabled()
  await expect(submit).toBeDisabled()
  await expect(page.locator('[data-rc-preview-unavailable]')).toBeVisible()
  await coordinate.fill('4.5')
  await expect(page.getByRole('img', { name: 'Authored RC model XY preview' })).toBeVisible()
  await expect(apply).toBeEnabled()
  await expect(submit).toBeDisabled()
  await apply.click()
  const raw = await page.getByRole('textbox', { name: 'Typed RC request JSON', exact: true }).inputValue()
  const parsed = JSON.parse(raw)
  expect(parsed.model.nodes[1].coordinates[0]).toBe(4.5)
  expect(parsed.source_revision).toBe(revision)
  expect(parsed.config).toEqual(request().config)
  await expect(submit).toBeEnabled()
  await coordinate.fill('-')
  await expect(coordinate).toHaveValue('-')
  await expect(submit).toBeDisabled()
  await page.getByRole('button', { name: 'Undo local model changes' }).click()
  await expect(coordinate).toHaveValue('4.5')
  await expect(submit).toBeEnabled()
  expect(posts).toEqual([])
})
