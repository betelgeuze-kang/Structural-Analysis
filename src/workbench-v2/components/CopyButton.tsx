import { useState, type ReactElement } from 'react'

interface CopyButtonProps {
  value: string
  label?: string
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through to legacy path */
  }
  try {
    if (typeof document === 'undefined') return false
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'absolute'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  } catch {
    return false
  }
}

/** Small copy-to-clipboard button with transient confirmation. */
export function CopyButton({ value, label = 'Copy' }: CopyButtonProps): ReactElement {
  const [copied, setCopied] = useState(false)

  async function onClick(): Promise<void> {
    const ok = await copyText(value)
    if (ok) {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    }
  }

  return (
    <button
      type="button"
      className="wb2-copy-btn"
      data-wb2-copy
      aria-label={`${label} command`}
      onClick={() => {
        void onClick()
      }}
    >
      {copied ? 'Copied ✓' : label}
    </button>
  )
}
