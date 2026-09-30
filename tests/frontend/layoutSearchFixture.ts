import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
const packed = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/rc-layout-search.json.gz')).toString('utf8'))
export const layoutFiles: Record<string, Buffer> = Object.fromEntries(Object.entries(packed.files).map(([path, encoded]) => [path, Buffer.from(encoded as string, 'base64')]))
export const layoutRead = async (path: string): Promise<Uint8Array> => {
  if (!Object.hasOwn(layoutFiles, path)) throw new Error('unknown layout fixture path')
  return new Uint8Array(layoutFiles[path])
}
