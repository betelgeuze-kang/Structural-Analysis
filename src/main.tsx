import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { WorkbenchPage } from './workbench-v2/WorkbenchPage'
import './index.css'

// Lightweight entry-point routing: /workbench-v2 (path or hash) renders the
// Workbench v2 surface; everything else renders the existing App. This keeps
// route selection out of App.tsx.
function isWorkbenchV2Route(): boolean {
  const path = window.location.pathname.replace(/\/+$/, '')
  return path.endsWith('/workbench-v2') || window.location.hash.replace(/\/+$/, '') === '#/workbench-v2'
}

const Root = isWorkbenchV2Route() ? <WorkbenchPage /> : <App />

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{Root}</React.StrictMode>,
)
