import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

const rootHtml = fileURLToPath(new URL('./index.html', import.meta.url))
const viewerHtml = fileURLToPath(new URL('./src/structure-viewer/index.html', import.meta.url))

// `base` lets the app (and its evidence bundle under /evidence/) work when
// served from a GitHub Pages subpath. Set VITE_BASE_PATH=/Repo-Name/ in the
// deploy workflow; defaults to '/' for local dev.
export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? '/',
  plugins: [react()],
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
