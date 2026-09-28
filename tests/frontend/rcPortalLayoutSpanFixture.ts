import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'

export type PortalSpanRun = 'staged' | 'full'

// Byte-exact originals from two separate, source-bound portal layout runs.
const packed: Record<string, string> = JSON.parse(
  gunzipSync(readFileSync('tests/frontend/fixtures/rc-portal-layout-span-artifacts.json.gz')).toString('utf8'),
)

export function portalSpanBytes(run: PortalSpanRun, path: string): Uint8Array {
  const value = packed[`${run}/${path}`]
  if (typeof value !== 'string') throw new Error(`missing original portal span artifact: ${run}/${path}`)
  return Uint8Array.from(Buffer.from(value, 'base64'))
}

export const portalSpanRead = (run: PortalSpanRun) => async (path: string): Promise<Uint8Array> =>
  portalSpanBytes(run, path)
