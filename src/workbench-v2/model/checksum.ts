// In-browser SHA-256 over a canonical string. Returns a `sha256:<hex>` digest,
// or null when Web Crypto is unavailable (so callers can mark it honestly as
// unavailable rather than fabricating a value).

export async function sha256Hex(text: string): Promise<string | null> {
  try {
    const subtle = typeof crypto !== 'undefined' ? crypto.subtle : undefined
    if (!subtle) return null
    const bytes = new TextEncoder().encode(text)
    const digest = await subtle.digest('SHA-256', bytes)
    const hex = Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('')
    return `sha256:${hex}`
  } catch {
    return null
  }
}

/** Stable JSON: object keys sorted recursively, so the digest is deterministic. */
export function canonicalJson(value: unknown): string {
  return JSON.stringify(sortKeys(value))
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys)
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>
    return Object.keys(obj)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = sortKeys(obj[key])
        return acc
      }, {})
  }
  return value
}
