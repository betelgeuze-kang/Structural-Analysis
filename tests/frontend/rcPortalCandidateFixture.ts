import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'

// Byte-exact, graph-referenced originals from the two-fixed-portal candidate run.
const packed: Record<string, string> = JSON.parse(
  gunzipSync(readFileSync('tests/frontend/fixtures/rc-portal-candidate-search-artifacts.json.gz')).toString('utf8'),
)

export function portalCandidateBytes(path: string): Uint8Array {
  const value = packed[path]
  if (typeof value !== 'string') throw new Error(`missing original portal candidate artifact: ${path}`)
  return Uint8Array.from(Buffer.from(value, 'base64'))
}

export const portalCandidateRead = async (path: string): Promise<Uint8Array> => portalCandidateBytes(path)
