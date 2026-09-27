import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'

// Original producer bytes from the source-bound three-design portal study.
const packed: Record<string, string> = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/rc-portal-design-artifacts.json.gz')).toString('utf8'))

export function portalDesignBytes(path: string): Uint8Array {
  const value = packed[path]
  if (typeof value !== 'string') throw new Error(`missing original portal study artifact: ${path}`)
  return Uint8Array.from(Buffer.from(value, 'base64'))
}

export const portalDesignRead = async (path: string): Promise<Uint8Array> => portalDesignBytes(path)
