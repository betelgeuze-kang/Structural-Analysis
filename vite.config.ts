import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { readFileSync } from 'node:fs'

const rootHtml = fileURLToPath(new URL('./index.html', import.meta.url))
const viewerHtml = fileURLToPath(new URL('./src/structure-viewer/index.html', import.meta.url))
const viewerRuntimeAssets: string[] = JSON.parse(readFileSync(new URL('./src/structure-viewer/viewer-runtime-assets.json', import.meta.url), 'utf8'))

// `base` lets the app (and its evidence bundle under /evidence/) work when
// served from a GitHub Pages subpath. Set VITE_BASE_PATH=/Repo-Name/ in the
// deploy workflow; defaults to '/' for local dev.
export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? '/',
  plugins: [react(), {
    name: 'viewer-original-runtime-assets',
    generateBundle() {
      for (const relative of viewerRuntimeAssets) {
        if (!/^[a-zA-Z0-9_./-]+$/.test(relative) || relative.split('/').some(part => !part || part === '.' || part === '..')) throw new Error('Invalid viewer runtime asset path')
        this.emitFile({ type: 'asset', fileName: `src/structure-viewer/${relative}`, source: readFileSync(new URL(`./src/structure-viewer/${relative}`, import.meta.url)) })
      }
    },
  }],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        workbench: rootHtml,
        structureViewer: viewerHtml,
      },
    },
  },
})
