import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
const packed: Record<string, string> = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/rc-layout-staged.json.gz')).toString('utf8'))
export const stagedFiles: Record<string, Buffer> = Object.fromEntries(Object.entries(packed).map(([path, raw]) => [path, Buffer.from(raw, 'base64')]))
