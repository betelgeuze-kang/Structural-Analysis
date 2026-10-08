import path from 'node:path'
import { realpathSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { assertControlDirectory } from './rc-observer-controls-artifacts.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const native = process.env.PLAYWRIGHT_JSON_OUTPUT_FILE
if (typeof native !== 'string' || !path.isAbsolute(native)
  || path.basename(native) !== 'positive-raw-native.json' || realpathSync(root) !== root) throw new Error('rc_control_config_output')
const directory = path.dirname(native)
assertControlDirectory(directory)

// Dedicated lane only. Original native 30000ms/5000ms defaults are not overridden.
export default {
  testDir: path.join(root, 'tests', 'frontend'),
  testMatch: ['**/rc-observer-browser.spec.ts'],
  workers: 1,
  retries: 0,
  outputDir: path.join(directory, 'positive-test-results'),
  reporter: [['line'], ['json', { outputFile: native }]],
  use: { browserName: 'chromium', headless: true },
}
