import { createReadStream, existsSync, mkdirSync, statSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const outputArgIndex = process.argv.indexOf('--out')
const outputRelativePath =
  outputArgIndex >= 0 ? process.argv[outputArgIndex + 1] || '' : 'docs/assets/commercialization-status-card.png'
const outputPath = path.resolve(rootDir, outputRelativePath)
const viewerPath = '/src/structure-viewer/index.html?preset=midas33_optimized'
const viewport = { width: 1600, height: 900 }
const captureViewPreset = process.env.README_CAPTURE_VIEW_PRESET ?? 'review'
const cameraFactors = {
  x: Number(process.env.README_CAPTURE_CAMERA_X ?? '-0.55'),
  y: Number(process.env.README_CAPTURE_CAMERA_Y ?? '0.85'),
  z: Number(process.env.README_CAPTURE_CAMERA_Z ?? '0.35'),
}

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml; charset=utf-8',
  '.ts': 'text/plain; charset=utf-8',
}

function sendText(response, status, text) {
  const body = Buffer.from(text)
  response.writeHead(status, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Content-Length': String(body.length),
  })
  response.end(body)
}

function createStaticServer() {
  return http.createServer((request, response) => {
    const requestUrl = new URL(request.url || '/', 'http://127.0.0.1')
    const decodedPath = decodeURIComponent(requestUrl.pathname === '/' ? '/index.html' : requestUrl.pathname)
    const target = path.resolve(rootDir, `.${decodedPath}`)
    if (!target.startsWith(rootDir)) {
      sendText(response, 403, 'Forbidden')
      return
    }
    if (!existsSync(target) || !statSync(target).isFile()) {
      sendText(response, 404, 'Not found')
      return
    }
    response.writeHead(200, {
      'Content-Type': mimeTypes[path.extname(target)] || 'application/octet-stream',
    })
    createReadStream(target).pipe(response)
  })
}

async function waitForCanvasNonBlank(page) {
  await page.waitForFunction(
    () => {
      const canvas = document.querySelector('#viewport canvas')
      if (!(canvas instanceof HTMLCanvasElement) || canvas.width < 10 || canvas.height < 10) {
        return false
      }
      const probe = document.createElement('canvas')
      const width = Math.min(128, canvas.width)
      const height = Math.min(128, canvas.height)
      probe.width = width
      probe.height = height
      const context = probe.getContext('2d')
      if (!context) {
        return false
      }
      context.drawImage(canvas, 0, 0, width, height)
      const pixels = context.getImageData(0, 0, width, height).data
      let variedPixels = 0
      for (let index = 0; index < pixels.length; index += 4) {
        const red = pixels[index]
        const green = pixels[index + 1]
        const blue = pixels[index + 2]
        const alpha = pixels[index + 3]
        if (alpha > 0 && (red > 8 || green > 8 || blue > 8)) {
          variedPixels += 1
        }
        if (variedPixels > 32) {
          return true
        }
      }
      return false
    },
    undefined,
    { timeout: 45000 },
  )
}

async function applyMidas33ReadmeCameraPose(page) {
  const result = await page.evaluate(({ preset, factors }) => {
    if (typeof window.setMidas33ViewPreset === 'function') {
      return {
        applied: window.setMidas33ViewPreset(preset),
        mode: 'midas33-view-preset',
        preset,
      }
    }
    const bounds = typeof window.getViewerModelBounds === 'function' ? window.getViewerModelBounds() : null
    if (!bounds || typeof window.setViewerCameraPose !== 'function') {
      return {
        applied: false,
        mode: 'fallback-camera-factors',
        hasBoundsApi: typeof window.getViewerModelBounds === 'function',
        hasPoseApi: typeof window.setViewerCameraPose === 'function',
        bounds,
      }
    }
    const target = bounds.center
    const radius = Number(bounds.radius) || 1
    const applied = window.setViewerCameraPose({
      target,
      position: {
        x: target.x + radius * factors.x,
        y: target.y + radius * factors.y,
        z: target.z + radius * factors.z,
      },
      up: { x: 0, y: 0, z: 1 },
    })
    return { applied, hasBoundsApi: true, hasPoseApi: true, bounds }
  }, { preset: captureViewPreset, factors: cameraFactors })
  if (!result.applied) {
    throw new Error(`Failed to apply the MIDAS33 README camera pose in the structure viewer: ${JSON.stringify(result)}`)
  }
}

async function capture(port) {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      errors.push(message.text())
    }
  })

  try {
    await page.goto(`http://127.0.0.1:${port}${viewerPath}`, { timeout: 90000, waitUntil: 'commit' })
    await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: 30000 })
    await page.locator('#stage-panel').waitFor({ state: 'visible', timeout: 30000 })
    await page.waitForFunction(() => {
      const label = document.querySelector('#provenance-source-label')
      return Boolean(label && label.textContent && label.textContent.trim() !== '--')
    })
    await waitForCanvasNonBlank(page)
    await page.locator('#btn-solid').click({ timeout: 10000 }).catch(() => {})
    await page.getByRole('button', { name: 'Fit All' }).click({ timeout: 10000 }).catch(() => {})
    await applyMidas33ReadmeCameraPose(page)
    await page.waitForTimeout(1000)
    if (errors.length > 0) {
      throw new Error(`Viewer console/page errors while capturing README image:\n${errors.join('\n')}`)
    }
    mkdirSync(path.dirname(outputPath), { recursive: true })
    await page.screenshot({ path: outputPath, fullPage: false })
  } finally {
    await browser.close()
  }
}

async function main() {
  const server = createStaticServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const { port } = server.address()
  try {
    await capture(port)
    console.log(`Captured ${path.relative(rootDir, outputPath)}`)
  } finally {
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
