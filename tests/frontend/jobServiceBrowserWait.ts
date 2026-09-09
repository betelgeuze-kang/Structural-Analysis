import { expect, test, type Locator, type Page } from '@playwright/test'
import type { JobLoadStatus } from '../../src/workbench-v2/model/jobProvider'

type SettledJobStatus = Exclude<JobLoadStatus, 'loading' | 'unconfigured'>

/** Observe the first completed artifact validation before asserting its outcome. */
export async function waitForJobService(page: Page, expected: SettledJobStatus = 'ready'): Promise<Locator> {
  return test.step(`Durable job finishes loading as ${expected}`, async () => {
    const panel = page.locator('[data-job-service]')
    // Original result/evidence bytes must finish loading and strict validation.
    // Only this asynchronous boundary gets a larger budget; numerical, integrity,
    // download and rendering assertions retain their existing limits.
    await expect(panel).toHaveAttribute('data-job-service', /^(?!loading$|unconfigured$).+$/, { timeout: 60000 })
    const status = await panel.getAttribute('data-job-service')
    const diagnostic = (await panel.innerText()).slice(0, 1000)
    expect(status, `Durable job terminal state ${status}: ${diagnostic}`).toBe(expected)
    await expect(panel).toBeVisible()
    return panel
  })
}
