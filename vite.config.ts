import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `base` lets the app (and its evidence bundle under /evidence/) work when
// served from a GitHub Pages subpath. Set VITE_BASE_PATH=/Repo-Name/ in the
// deploy workflow; defaults to '/' for local dev.
export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? '/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
