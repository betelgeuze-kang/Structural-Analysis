import type { ReactElement } from 'react'

export function Unavailable({ message }: { message?: string }): ReactElement {
  return (
    <div className="ec-unavailable" data-ec-unavailable>
      {message ?? 'Evidence unavailable'}
    </div>
  )
}

export function UnavailablePill({ label = 'unavailable' }: { label?: string }): ReactElement {
  return <span className="ec-pill ec-pill--unavailable">{label}</span>
}
