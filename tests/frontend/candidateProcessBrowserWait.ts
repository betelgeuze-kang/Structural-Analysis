import { expect, test, type Locator, type Page } from '@playwright/test'
import type { CandidateProcessStatus } from '../../src/workbench-v2/model/candidateProcessProvider'

type SettledCandidateStatus = Exclude<CandidateProcessStatus, 'loading' | 'unconfigured'>

/** Wait for transport and strict validation before checking the requested outcome. */
export async function waitForCandidateProcess(page: Page, expected: SettledCandidateStatus = 'verified'): Promise<Locator> {
  return test.step(`Candidate review finishes loading as ${expected}`, async () => {
    const panel = page.locator('[data-candidate-process]')
    // The retained fixture loads 72 files / 16.8 MB and can legitimately exceed
    // the default five-second UI assertion on a slower runner. Only this load
    // boundary gets a 60-second budget; all artifact and UI assertions keep theirs.
    await expect(panel).toHaveAttribute('data-candidate-process', /^(?!loading$|unconfigured$).+$/, { timeout: 60000 })
    const status = await panel.getAttribute('data-candidate-process')
    const diagnostic = (await panel.innerText()).slice(0, 1000)
    // Check the first terminal outcome immediately. An invalid/error result must
    // expose its diagnostic instead of waiting for a later verified state.
    expect(status, `Candidate review terminal state ${status}: ${diagnostic}`).toBe(expected)
    await expect(panel).toBeVisible()
    return panel
  })
}
