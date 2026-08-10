import type { ReactElement } from 'react'
import type { EvidenceValue, EngineeringValue } from '../model/caseSchema'

interface EngineeringValueTextProps {
  value: EngineeringValue
  integer?: boolean
}

function formatNumber(value: number, integer: boolean): string {
  if (integer) return value.toLocaleString()
  if (value !== 0 && (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e6)) return value.toExponential(3)
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

/** Renders every engineering number with its explicit contract state. */
export function EngineeringValueText({ value, integer = false }: EngineeringValueTextProps): ReactElement {
  if (value.status === 'available') {
    return (
      <span className="wb2-engineering-value" data-engineering-value-state="available">
        {formatNumber(value.value, integer)}
      </span>
    )
  }

  return (
    <span
      className={`wb2-engineering-value wb2-engineering-value--${value.status}`}
      data-engineering-value-state={value.status}
      title={value.status === 'unavailable' ? 'Evidence is unavailable' : value.reason}
    >
      {value.status.toUpperCase()}
    </span>
  )
}

/** Renders non-numeric evidence with the same four-state vocabulary. */
export function EvidenceValueText<T>({
  value,
  format,
}: {
  value: EvidenceValue<T>
  format: (available: T) => string
}): ReactElement {
  if (value.status === 'available') {
    return (
      <span className="wb2-engineering-value" data-engineering-value-state="available">
        {format(value.value)}
      </span>
    )
  }
  return (
    <span
      className={`wb2-engineering-value wb2-engineering-value--${value.status}`}
      data-engineering-value-state={value.status}
      title={value.status === 'unavailable' ? 'Evidence is unavailable' : value.reason}
    >
      {value.status.toUpperCase()}
    </span>
  )
}

export function BooleanEvidenceValueText({ value }: { value: EvidenceValue<boolean> }): ReactElement {
  return <EvidenceValueText value={value} format={(available) => String(available)} />
}
