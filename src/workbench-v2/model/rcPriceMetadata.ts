// Match FiberFrameMaterialPrices without interpreting a declaration as a quote.
// Python str.strip() and len() use these whitespace characters and code points;
// JavaScript trim() and UTF-16 length differ for some valid source declarations.
const pythonWhitespaceOnly = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u

function validPriceDate(value: unknown): boolean {
  if (typeof value !== 'string' || value.length !== 10 || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  if (year < 1 || month < 1 || month > 12 || day < 1) return false
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  return day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
}

export function validRcPriceMetadata(prices: Record<string, unknown>): boolean {
  return typeof prices.currency === 'string' && prices.currency.length === 3 && /^[A-Z]{3}$/.test(prices.currency)
    && validPriceDate(prices.as_of) && typeof prices.source === 'string'
    && prices.source.length <= 2000 && !pythonWhitespaceOnly.test(prices.source)
    && [...prices.source].length <= 1000
}
