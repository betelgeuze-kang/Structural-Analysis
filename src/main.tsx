import React, { lazy, Suspense, useEffect, useState, type ReactElement } from 'react'
import ReactDOM from 'react-dom/client'
import { WorkbenchPage } from './workbench-v2/WorkbenchPage'
import './index.css'

const LegacyApp = lazy(() => import('./App'))

export type ProductSurface = 'workbench-v2' | 'legacy-app'

export function resolveProductSurface(location: Pick<Location, 'pathname' | 'hash'>): ProductSurface {
  const path = location.pathname.replace(/\/+$/, '')
  const hash = location.hash.replace(/\/+$/, '')
  const legacyRoute = path.endsWith('/legacy') || hash === '#/legacy'
  return legacyRoute ? 'legacy-app' : 'workbench-v2'
}

export function resolveSameOriginJobUrl(value: string | undefined, origin: string): string | undefined {
  const candidate = value?.trim()
  if (!candidate) return undefined
  try {
    const resolved = new URL(candidate, origin)
    return resolved.origin === origin ? resolved.toString() : undefined
  } catch {
    return undefined
  }
}

function LegacyAppSurface(): ReactElement {
  return (
    <div className="legacy-surface-route" data-legacy-surface>
      <aside className="legacy-surface-route__notice" role="note">
        <strong>Legacy evidence desk.</strong> This surface is retained for compatibility and historical
        evidence browsing. <a href="#/workbench-v2">Return to Workbench v2</a> for the product shell.
      </aside>
      <Suspense
        fallback={(
          <p className="legacy-surface-route__loading" role="status" data-legacy-loading>
            Loading legacy evidence desk…
          </p>
        )}
      >
        <LegacyApp />
      </Suspense>
    </div>
  )
}

function RootRouter(): ReactElement {
  const [surface, setSurface] = useState<ProductSurface>(() => resolveProductSurface(window.location))

  useEffect(() => {
    const updateSurface = () => setSurface(resolveProductSurface(window.location))
    window.addEventListener('hashchange', updateSurface)
    window.addEventListener('popstate', updateSurface)
    return () => {
      window.removeEventListener('hashchange', updateSurface)
      window.removeEventListener('popstate', updateSurface)
    }
  }, [])

  const jobStatusUrl = resolveSameOriginJobUrl(
    import.meta.env.VITE_JOB_STATUS_URL
      || window.__STRUCTURAL_WORKBENCH_CONFIG__?.jobStatusUrl,
    window.location.origin,
  )
  const nativeFrameResultUrl = resolveSameOriginJobUrl(
    import.meta.env.VITE_NATIVE_FRAME_RESULT_URL
      || window.__STRUCTURAL_WORKBENCH_CONFIG__?.nativeFrameResultUrl,
    window.location.origin,
  )
  const nativeFrameReportUrl = resolveSameOriginJobUrl(
    import.meta.env.VITE_NATIVE_FRAME_REPORT_URL
      || window.__STRUCTURAL_WORKBENCH_CONFIG__?.nativeFrameReportUrl,
    window.location.origin,
  )

  return surface === 'legacy-app' ? (
    <LegacyAppSurface />
  ) : (
    <WorkbenchPage
      jobStatusUrl={jobStatusUrl}
      nativeFrameResultUrl={nativeFrameResultUrl}
      nativeFrameReportUrl={nativeFrameReportUrl}
    />
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RootRouter />
  </React.StrictMode>,
)
