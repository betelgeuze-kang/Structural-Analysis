import { expect, test, type Page } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { createRcEditorExample } from '../../src/workbench-v2/model/rcModelEditor'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'
import type { RcJobControlCommand, RcJobControlView } from '../../src/workbench-v2/model/rcJobControl'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const jobId = `job_${'1'.repeat(32)}`, otherId = `job_${'2'.repeat(32)}`
const tenant = 'control-tenant', token = 'control-private-token-never-display'
const hash = (text: string) => `sha256:${createHash('sha256').update(text).digest('hex')}`
const serialized = JSON.stringify(createRcEditorExample('a'.repeat(40)))
function initialJob(status: WorkbenchJobView['status'] = 'queued'): WorkbenchJobView {
  return { schema_version: 'structural-analysis-job-view.v1', service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: jobId, status, revision: 0, attempt: status === 'running' ? 1 : 0, progress: { completed_steps: 0, total_steps: 2 },
    created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z', lease_expires_at: status === 'running' ? '2026-10-23T00:01:00Z' : null,
    error_code: null, can_resume: false, request: { role: 'request', content_hash: hash(serialized), byte_length: Buffer.byteLength(serialized), media_type: 'application/json' },
    checkpoint: null, result: null, evidence: null, resume_contract_hash: null, solver_truth_owner: 'structural_analysis_core', result_authority: 'referenced_result_and_evidence_contracts_only', claim_boundary: 'Stub control workflow only; no solver.', terminal_event_hash: hash('created') }
}
async function workspace(page: Page, options: { status?: WorkbenchJobView['status']; initial?: boolean; unsupported?: boolean; malformed?: boolean; unknownFirst?: boolean; actionMismatch?: boolean; conflictFirst?: boolean; controlGate?: Promise<void>; postGate?: Promise<void> } = {}) {
  let job = initialJob(options.status), revision = 0, state: RcJobControlView['state'] = 'available', last: RcJobControlView['last_command'] = null
  let controlReads = 0
  const posts: Array<{ url: string; body: string }> = [], receipts = new Map<string, { hash: string; revision: number }>()
  function view(): RcJobControlView { return { schema_version: 'rc-job-control.v1', job: { job_id: job.job_id, tenant_id: tenant, request_hash: job.request.content_hash, checkpoint_hash: job.checkpoint?.content_hash ?? null, attempt: job.attempt, revision: job.revision, status: job.status, terminal_event_hash: job.terminal_event_hash }, control_revision: revision, state, last_command: last, can_pause: state === 'available', can_cancel: ['available', 'pause_pending', 'paused'].includes(state), can_resume_control: state === 'paused' } }
  function transition(command: RcJobControlCommand, raw: string): void {
    revision++; job = { ...job, revision: job.revision + 1, terminal_event_hash: hash(raw + ':requested') }
    last = { control_id: command.control_id, command_hash: hash(raw), action: command.action, control_revision: revision, requested_event_revision: job.revision, resolved_event_revision: null, disposition: 'pending', boundary: null, applied_checkpoint_hash: null, applied_progress: null }
    receipts.set(command.control_id, { hash: hash(raw), revision })
    if (job.status === 'running' && command.action !== 'resume') state = command.action === 'pause' ? 'pause_pending' : 'cancel_pending'
    else apply()
  }
  function apply(): void {
    if (!last) throw new Error('No control requested')
    const action = last.action
    job = { ...job, status: action === 'cancel' ? 'cancelled' : 'queued', lease_expires_at: null, revision: job.revision + 1, terminal_event_hash: hash(last.control_id + ':resolved') }
    state = action === 'pause' ? 'paused' : action === 'cancel' ? 'terminal' : 'available'
    last = { ...last, resolved_event_revision: job.revision, disposition: action === 'pause' ? 'paused' : action === 'cancel' ? 'cancelled' : 'resumed', boundary: 'unleased', applied_checkpoint_hash: null, applied_progress: { completed: 0, total: 2 } }
  }
  await page.addInitScript(({ tenant, token }) => {
    ;(window as any).__rcControlTenant = tenant
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs', jobAuthorization: async () => ({ tenantId: (window as any).__rcControlTenant, bearerToken: token }) }
  }, { tenant, token })
  await page.route('**/v1/jobs**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (request.method() === 'POST') {
      const raw = request.postData()!, index = posts.filter(value => value.url.endsWith('/rc-control')).length
      posts.push({ url: path, body: raw })
      if (path === '/v1/jobs') return route.fulfill({ contentType: 'application/json', body: JSON.stringify(job) })
      if (path !== `/v1/jobs/${jobId}/rc-control`) return route.fulfill({ status: 404, body: '{}' })
      if (options.postGate) await options.postGate
      if (options.unknownFirst && index === 0) {
        if (options.actionMismatch) transition({ ...JSON.parse(raw), action: 'cancel' }, raw)
        return route.fulfill({ status: 503, body: '{}' })
      }
      if (options.conflictFirst && index === 0) return route.fulfill({ status: 409, body: '{}' })
      const command = JSON.parse(raw) as RcJobControlCommand
      if (!receipts.has(command.control_id)) transition(command, raw)
      const accepted = receipts.get(command.control_id)!
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ schema_version: 'rc-job-control-command-result.v1', control_id: command.control_id, command_hash: accepted.hash, accepted_control_revision: accepted.revision, view: view() }) })
    }
    if (path === `/v1/jobs/${jobId}/rc-control`) {
      controlReads++
      if (options.controlGate) await options.controlGate
      return route.fulfill(options.unsupported ? { status: 404, body: '{}' } : { contentType: 'application/json', body: JSON.stringify(options.malformed ? job : view()) })
    }
    if (path === `/v1/jobs/${jobId}`) return route.fulfill({ contentType: 'application/json', body: JSON.stringify(job) })
    if (path === `/v1/jobs/${jobId}/request`) return route.fulfill({ contentType: 'application/json', body: serialized })
    if (path === `/v1/jobs/${otherId}`) return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ...initialJob(), job_id: otherId }) })
    if (path === `/v1/jobs/${otherId}/request`) return route.fulfill({ contentType: 'application/json', body: serialized })
    return route.fulfill({ status: 404, body: '{}' })
  })
  await page.goto(`${baseUrl}/${options.initial === false ? '' : `?rcJob=${jobId}`}#/workbench-v2`)
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
  return { posts, apply, view, reads: () => controlReads }
}
const panel = (page: Page) => page.locator('[data-rc-job-control]')

test('RC control queued pause, explicit resume and per-job cancellation never create another analysis', async ({ page }) => {
  const server = await workspace(page)
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'available')
  await panel(page).getByRole('button', { name: 'Pause job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'paused')
  await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeDisabled()
  await panel(page).getByRole('button', { name: 'Resume paused job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'available')
  await panel(page).getByRole('button', { name: 'Cancel job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'terminal')
  await expect(panel(page).getByRole('button', { name: 'Resume paused job', exact: true })).toBeDisabled()
  expect(server.posts.map(value => JSON.parse(value.body).action)).toEqual(['pause', 'resume', 'cancel'])
  expect(server.posts.every(value => value.url === `/v1/jobs/${jobId}/rc-control`)).toBe(true)
  const bodies = server.posts.map(value => JSON.parse(value.body))
  expect(bodies.map(value => value.expected_control_revision)).toEqual([0, 1, 2])
  expect(new Set(bodies.map(value => value.control_id)).size).toBe(3)
  expect(await page.locator('body').innerText()).not.toContain(token)
})

test('RC control running pause stays pending until an observed durable boundary and survives cold project reopen', async ({ page }) => {
  const server = await workspace(page, { status: 'running' })
  await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeEnabled()
  await panel(page).getByRole('button', { name: 'Pause job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'pause_pending')
  await expect(panel(page).getByRole('button', { name: 'Resume paused job', exact: true })).toBeDisabled()
  await expect(panel(page)).toContainText('current chunk may still be running')
  server.apply()
  await panel(page).getByRole('button', { name: 'Refresh job control', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'paused')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Save RC project', exact: true }).click()
  const exported = await download, path = await exported.path(), saved = await readFile(path!, 'utf8')
  expect(saved).not.toContain(token); expect(saved).not.toContain('control_id')
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  await page.reload()
  await expect(page.getByRole('button', { name: 'Open saved RC job', exact: true })).toBeVisible()
  await page.getByLabel('Open RC project file', { exact: true }).setInputFiles({ name: 'project.json', mimeType: 'application/json', buffer: Buffer.from(saved) })
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'paused')
  expect(server.posts).toHaveLength(1)
})

test('RC control uncertain POST retains exact command across same-account refresh and retries only explicitly', async ({ page }) => {
  const server = await workspace(page, { unknownFirst: true })
  await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeEnabled()
  await panel(page).getByRole('button', { name: 'Pause job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-control-unconfirmed]')).toBeVisible()
  await expect(panel(page).getByRole('button', { name: 'Cancel job', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Refresh account and job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-control-unconfirmed]')).toBeVisible()
  await expect(panel(page).getByRole('button', { name: 'Retry same control request', exact: true })).toBeEnabled()
  expect(server.posts).toHaveLength(1)
  await panel(page).getByRole('button', { name: 'Retry same control request', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'paused')
  await expect(panel(page).locator('[data-rc-control-unconfirmed]')).toHaveCount(0)
  expect(server.posts).toHaveLength(2); expect(server.posts[1]).toEqual(server.posts[0])
})

test('RC control stale CAS requires a refreshed observation and a new explicit action, never automatic POST', async ({ page }) => {
  const server = await workspace(page, { conflictFirst: true })
  await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeEnabled()
  await panel(page).getByRole('button', { name: 'Pause job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-control-message]')).toContainText('command was rejected')
  expect(server.posts).toHaveLength(1)
  await panel(page).getByRole('button', { name: 'Refresh job control', exact: true }).click()
  await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeEnabled()
  expect(server.posts).toHaveLength(1)
  await panel(page).getByRole('button', { name: 'Pause job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'paused')
  expect(server.posts).toHaveLength(2)
  expect(JSON.parse(server.posts[0].body).control_id).not.toBe(JSON.parse(server.posts[1].body).control_id)
})

for (const mode of ['unsupported', 'malformed'] as const) {
  test(`RC control ${mode} response disables controls without legacy or submission fallback`, async ({ page }) => {
    const server = await workspace(page, { [mode]: true })
    await expect(panel(page).locator('[data-rc-control-message]')).toContainText(mode === 'unsupported' ? 'unavailable on this service' : 'could not be verified')
    await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeDisabled()
    await panel(page).getByRole('button', { name: 'Refresh job control', exact: true }).click()
    expect(server.posts).toEqual([])
  })
}

test('RC control authenticated scope change while GET is pending clears private project data and stale control response', async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const server = await workspace(page, { controlGate: gate })
  await expect.poll(server.reads).toBeGreaterThan(0)
  try { await page.evaluate(() => { (window as any).__rcControlTenant = 'other-tenant' }) }
  finally { release() }
  await expect(panel(page)).toHaveCount(0)
  await expect(page.locator('[data-rc-workflow-error]')).toContainText('Authentication scope changed')
  expect(server.posts).toEqual([])
})

test('RC control can open a running captured job while its queue continues, then applied pause holds all remaining captures', async ({ page }) => {
  const server = await workspace(page, { initial: false, status: 'running' })
  await page.getByText('Submit a new RC input', { exact: true }).click()
  await page.getByLabel('Typed RC request JSON', { exact: true }).fill(serialized)
  const scenarios = page.locator('[data-rc-scenario-comparison]')
  for (const name of ['First', 'Remaining']) {
    await scenarios.getByLabel('Scenario name', { exact: true }).fill(name)
    await scenarios.getByRole('button', { name: 'Capture current design', exact: true }).click()
  }
  await scenarios.getByRole('button', { name: 'Run captured designs', exact: true }).click()
  const first = scenarios.locator('[data-scenario-id]').filter({ has: page.getByText('First', { exact: true }) })
  const remaining = scenarios.locator('[data-scenario-id]').filter({ has: page.getByText('Remaining', { exact: true }) })
  await expect(first.getByRole('button', { name: 'Open job', exact: true })).toBeEnabled()
  await first.getByRole('button', { name: 'Open job', exact: true }).click()
  await expect(scenarios.getByRole('button', { name: 'Run captured designs', exact: true })).toBeDisabled()
  await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeEnabled()
  await panel(page).getByRole('button', { name: 'Pause job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'pause_pending')
  server.apply()
  await expect(scenarios).toContainText('queue is held because this job is paused', { timeout: 10000 })
  await expect(remaining).toContainText('captured')
  await expect(remaining.getByRole('button', { name: 'Remove Remaining', exact: true })).toBeEnabled()
  expect(server.posts.filter(value => value.url === '/v1/jobs')).toHaveLength(1)
  expect(server.posts.filter(value => value.url.endsWith('/rc-control'))).toHaveLength(1)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Save RC project', exact: true }).click()
  const value = JSON.parse(await readFile((await (await download).path())!, 'utf8'))
  expect(value.scenarios[0].job.jobId).toBe(jobId)
  expect(value.scenarios[1].job).toBeNull(); expect(value.scenarios[1].attempted).toBe(false)
})

test('RC control late mutation response cannot replace a newly selected job and its original command remains recoverable', async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const server = await workspace(page, { postGate: gate })
  await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeEnabled()
  await panel(page).getByRole('button', { name: 'Pause job', exact: true }).click()
  await expect.poll(() => server.posts.length).toBe(1)
  try {
    await page.getByLabel('Saved RC job ID', { exact: true }).fill(otherId)
    await page.getByRole('button', { name: 'Open saved RC job', exact: true }).click()
    await expect(panel(page)).toContainText(otherId)
  } finally { release() }
  await expect(panel(page).locator('[data-rc-control-message]')).toContainText('unavailable on this service')
  await expect(panel(page).locator('[data-rc-control-receipt]')).toHaveCount(0)
  await expect(page.locator('[data-rc-project-link]')).toHaveAttribute('href', new RegExp(`rcJob=${otherId}`))
  await page.getByLabel('Saved RC job ID', { exact: true }).fill(jobId)
  await page.getByRole('button', { name: 'Open saved RC job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'paused')
  await expect(panel(page).locator('[data-rc-control-unconfirmed]')).toHaveCount(0)
  expect(server.posts).toHaveLength(1)
})

test('RC control GET cannot acknowledge an unknown command when the claimed action differs despite matching ID and hash', async ({ page }) => {
  const server = await workspace(page, { unknownFirst: true, actionMismatch: true })
  await expect(panel(page).getByRole('button', { name: 'Pause job', exact: true })).toBeEnabled()
  await panel(page).getByRole('button', { name: 'Pause job', exact: true }).click()
  await expect(panel(page).locator('[data-rc-control-unconfirmed]')).toBeVisible()
  await panel(page).getByRole('button', { name: 'Refresh job control', exact: true }).click()
  await expect(panel(page).locator('[data-rc-job-control-state]')).toHaveAttribute('data-rc-job-control-state', 'terminal')
  await expect(panel(page).locator('[data-rc-control-unconfirmed]')).toContainText('Unconfirmed pause command')
  await expect(panel(page).locator('[data-rc-control-receipt]')).toHaveCount(0)
  expect(server.posts).toHaveLength(1)
  expect(JSON.parse(server.posts[0].body).action).toBe('pause')
})
