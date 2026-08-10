import { readFile } from 'node:fs/promises'

/**
 * Node-side Playwright tests import TypeScript source directly. Vite handles JSON
 * modules in the browser build, but Node ESM requires an import attribute. This
 * test-only loader converts local JSON modules to JavaScript default exports so
 * the E2E runner consumes the exact generated file without copying its values.
 */
export async function load(url, context, nextLoad) {
  if (url.startsWith('file:') && url.endsWith('.json')) {
    const text = await readFile(new URL(url), 'utf8')
    JSON.parse(text)
    return {
      format: 'module',
      shortCircuit: true,
      source: `export default ${text.trim()}\n`,
    }
  }
  return nextLoad(url, context)
}
