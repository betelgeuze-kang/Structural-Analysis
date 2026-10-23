import { parseNativeJsonStrict } from './nativeFrameProvider'
import { rcRequestChanges } from './rcJobDiagnostics'
import { validateRcRequestProfile, type RcObject } from './rcJobSchema'
import { rcScenarioCompatibilityFields } from './rcScenarioComparison'

export const RC_INPUT_COMPARISON_BYTES = 1024 * 1024
const VALUE_LIMIT = 20000, DEPTH_LIMIT = 48, CELL_LIMIT = 240, ROW_LIMIT = 200
interface RawValue { start: number; end: number; number?: string }
interface Input { text: string; value: RcObject; spans: Map<string, RawValue>; fields: ReturnType<typeof rcScenarioCompatibilityFields> }
export interface RcScenarioInputChange {
  path: string; before: string; after: string; beforeClipped: boolean; afterClipped: boolean
  kind: 'value' | 'numeric_token'
}
export interface RcScenarioInputComparison {
  status: 'available' | 'missing' | 'invalid' | 'limited'
  rawIdentical: boolean | null
  message: string
  changes: RcScenarioInputChange[]
  truncated: boolean
  compatibility: 'compatible' | 'incompatible' | 'unavailable'
  reasons: Array<{ key: string; label: string }>
  precisionLimited: boolean
}
const pointer = (key: string) => key.replace(/~/g, '~0').replace(/\//g, '~1')

/** Index original value spans without converting number tokens. Strict admission
 * still uses the shared parser below. Bounds apply before recursive JSON.parse.
 */
function rawValues(text: string): Map<string, RawValue> {
  const spans = new Map<string, RawValue>()
  let position = 0, count = 0
  const fail = (): never => { throw new Error('rc_input_json_invalid') }
  const whitespace = () => { while (/[\t\r\n ]/.test(text[position] ?? '\u0000')) position++ }
  const string = (): string => {
    const pattern = /"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[\da-fA-F]{4}))*"/y
    pattern.lastIndex = position
    const match = pattern.exec(text)
    if (!match) return fail()
    position = pattern.lastIndex
    return JSON.parse(match[0]) as string
  }
  function read(path: string, depth: number): void {
    if (++count > VALUE_LIMIT || depth > DEPTH_LIMIT) throw new Error('rc_input_limit')
    whitespace()
    const start = position, opening = text[position]
    let number: string | undefined
    if (opening === '{' || opening === '[') {
      const object = opening === '{', close = object ? '}' : ']'
      position++; whitespace()
      let index = 0
      if (text[position] !== close) while (true) {
        let key: string
        if (object) { key = string(); whitespace(); if (text[position++] !== ':') fail() }
        else key = String(index++)
        read(`${path}/${pointer(key!)}`, depth + 1)
        whitespace()
        if (text[position] === close) break
        if (text[position++] !== ',') fail()
        whitespace()
      }
      position++
    } else if (opening === '"') string()
    else {
      const pattern = /(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/y
      pattern.lastIndex = position
      const match = pattern.exec(text)
      if (!match) fail()
      position = pattern.lastIndex
      if (/[-\d]/.test(opening)) {
        number = match![0]
        if (number.length > 256) throw new Error('rc_input_limit')
      }
    }
    spans.set(path, { start, end: position, number })
  }
  read('', 0); whitespace()
  if (position !== text.length) fail()
  return spans
}

// The legacy diff reads properties by name. Remove inherited properties so an
// authored __proto__/constructor key cannot turn absence into a prototype value.
function ownValues(value: any): any {
  if (Array.isArray(value)) return value.map(ownValues)
  if (value && typeof value === 'object') return Object.assign(Object.create(null), Object.fromEntries(Object.entries(value).map(([key, item]) => [key, ownValues(item)])))
  return value
}

function input(text: string): Input {
  if (text.length > RC_INPUT_COMPARISON_BYTES || new TextEncoder().encode(text).byteLength > RC_INPUT_COMPARISON_BYTES) throw new Error('rc_input_limit')
  const spans = rawValues(text), value = parseNativeJsonStrict(text)
  validateRcRequestProfile(value)
  return { text, spans, value: value as RcObject, fields: rcScenarioCompatibilityFields(value as RcObject) }
}

/** Exact finite decimal normalization only for detecting Number collisions.
 * It does not round, evaluate a solver input, or replace stored request bytes.
 */
function decimal(token: string): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(token)!
  let digits = `${match[2]}${match[3] ?? ''}`.replace(/^0+/, '')
  if (!digits) return '0'
  const trailing = /0*$/.exec(digits)![0].length
  digits = digits.slice(0, digits.length - trailing)
  return `${match[1]}${digits}e${BigInt(match[4] ?? '0') - BigInt((match[3]?.length ?? 0) - trailing)}`
}
function risky(token: string): boolean {
  const number = Number(token)
  return !Number.isFinite(number) || (Number.isInteger(number) && !Number.isSafeInteger(number)) || (number === 0 && decimal(token) !== '0')
}

/** Read-only comparison of captured original strings. No current draft, job
 * result, submission key, transport, or solver participates in this function.
 */
export function compareRcScenarioInputs(before: string | null | undefined, after: string | null | undefined, maximum = ROW_LIMIT): RcScenarioInputComparison {
  const base: RcScenarioInputComparison = {
    status: 'missing', rawIdentical: typeof before === 'string' && typeof after === 'string' ? before === after : null,
    message: 'Select two captured inputs. A missing input is unavailable, not an empty request.', changes: [], truncated: false,
    compatibility: 'unavailable', reasons: [], precisionLimited: false,
  }
  if (typeof before !== 'string' || typeof after !== 'string') return base
  if (!Number.isSafeInteger(maximum) || maximum < 1 || maximum > ROW_LIMIT) throw new Error('rc_input_row_limit_invalid')
  let left: Input, right: Input
  for (const [side, text] of [['Baseline', before], ['Compared', after]] as const) {
    try { const parsed = input(text); if (side === 'Baseline') left = parsed; else right = parsed }
    catch (error) {
      const limited = error instanceof Error && error.message === 'rc_input_limit'
      return { ...base, status: limited ? 'limited' : 'invalid', truncated: limited,
        message: limited ? `${side} input exceeds the comparison bound (1 MiB, 20,000 values, depth 48 or numeric token length 256). Original captured input is retained; comparison is unavailable.`
          : `${side} input is invalid JSON or cannot be projected into the supported RC input comparison. Comparison is unavailable.` }
    }
  }
  const parsed = rcRequestChanges(ownValues(left!.value), ownValues(right!.value), maximum)
  const paths = new Set(parsed.changes.map(change => change.path))
  let precisionLimited = false
  for (const path of new Set([...left!.spans.keys(), ...right!.spans.keys()])) {
    const a = left!.spans.get(path)?.number, b = right!.spans.get(path)?.number
    if ((a !== undefined && risky(a)) || (b !== undefined && risky(b))) precisionLimited = true
    if (a !== undefined && b !== undefined && a !== b) {
      paths.add(path || '/')
      if (Number(a) === Number(b) && decimal(a) !== decimal(b)) precisionLimited = true
    }
  }
  const show = (source: Input, path: string): { value: string; clipped: boolean } => {
    const found = source.spans.get(path)
    if (!found) return { value: '(absent)', clipped: false }
    const clipped = found.end - found.start > CELL_LIMIT
    return { value: source.text.slice(found.start, Math.min(found.end, found.start + CELL_LIMIT)), clipped }
  }
  const changes = [...paths].sort().slice(0, maximum).map(path => {
    // Shared diff uses '/' for a root replacement; valid RC inputs are objects,
    // so a literal top-level empty key is kept distinct when it is present.
    const sourcePath = path === '/' && !left!.spans.has('/') && !right!.spans.has('/') ? '' : path
    const a = show(left!, sourcePath), b = show(right!, sourcePath)
    const numeric = left!.spans.get(sourcePath)?.number !== undefined && right!.spans.get(sourcePath)?.number !== undefined
    return { path, before: a.value, after: b.value, beforeClipped: a.clipped, afterClipped: b.clipped, kind: numeric ? 'numeric_token' as const : 'value' as const }
  })
  const fields = left!.fields, compared = new Map(right!.fields.map(field => [field.key, field.signature]))
  const reasons = fields.filter(field => field.signature !== compared.get(field.key)).map(({ key, label }) => ({ key, label }))
  return { ...base, status: 'available', changes, truncated: parsed.truncated || paths.size > maximum, precisionLimited,
    compatibility: reasons.length ? 'incompatible' : precisionLimited ? 'unavailable' : 'compatible', reasons,
    message: before === after ? 'Captured original request text is exactly identical.'
      : changes.length ? 'Captured original request text differs. Values below come from the original strings; numeric tokens are not rounded for display.'
        : 'Captured original request text differs, but no value or numeric-token difference was found within the completed comparison. Whitespace, key order or string escaping may differ.' }
}
