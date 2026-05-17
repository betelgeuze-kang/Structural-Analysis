const DEFAULT_SELECTOR = '#viewport canvas';

export async function waitForCanvasNonBlank(page, {
  selector = DEFAULT_SELECTOR,
  timeout = 45000,
  variedPixelThreshold = 32,
} = {}) {
  await page.waitForFunction(
    ({ selector: canvasSelector, variedPixelThreshold: threshold }) => {
      const metrics = window.__measureStructureViewerCanvasFrame?.(canvasSelector);
      return Boolean(metrics && metrics.nonBlank && metrics.significantPixelCount > threshold);
    },
    { selector, variedPixelThreshold },
    { timeout },
  );
}

export async function installCanvasFrameProbe(page) {
  await page.addInitScript(() => {
    window.__measureStructureViewerCanvasFrame = (selector = '#viewport canvas') => {
      const canvas = document.querySelector(selector);
      if (!(canvas instanceof HTMLCanvasElement) || canvas.width < 10 || canvas.height < 10) {
        return {
          nonBlank: false,
          reason: 'canvas_missing_or_too_small',
          canvasWidth: canvas?.width || 0,
          canvasHeight: canvas?.height || 0,
        };
      }
      const probe = document.createElement('canvas');
      const width = Math.min(180, Math.max(1, canvas.width));
      const height = Math.min(120, Math.max(1, canvas.height));
      probe.width = width;
      probe.height = height;
      const context = probe.getContext('2d');
      if (!context) {
        return { nonBlank: false, reason: 'no_2d_context', canvasWidth: canvas.width, canvasHeight: canvas.height };
      }
      context.drawImage(canvas, 0, 0, width, height);
      const pixels = context.getImageData(0, 0, width, height).data;
      let significantPixelCount = 0;
      let minX = width;
      let minY = height;
      let maxX = -1;
      let maxY = -1;
      for (let index = 0; index < pixels.length; index += 4) {
        const red = pixels[index];
        const green = pixels[index + 1];
        const blue = pixels[index + 2];
        const alpha = pixels[index + 3];
        const maxChannel = Math.max(red, green, blue);
        const luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722;
        const isModelPixel = alpha > 0 && (maxChannel >= 44 || luminance >= 40);
        if (!isModelPixel) continue;
        const pixelIndex = index / 4;
        const x = pixelIndex % width;
        const y = Math.floor(pixelIndex / width);
        significantPixelCount += 1;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
      if (significantPixelCount <= 0) {
        return {
          nonBlank: false,
          reason: 'no_significant_pixels',
          canvasWidth: canvas.width,
          canvasHeight: canvas.height,
          sampleWidth: width,
          sampleHeight: height,
          significantPixelCount,
        };
      }
      const bboxWidth = maxX - minX + 1;
      const bboxHeight = maxY - minY + 1;
      const centerX = (minX + maxX + 1) / 2 / width;
      const centerY = (minY + maxY + 1) / 2 / height;
      return {
        nonBlank: true,
        canvasWidth: canvas.width,
        canvasHeight: canvas.height,
        sampleWidth: width,
        sampleHeight: height,
        significantPixelCount,
        significantPixelRatio: significantPixelCount / (width * height),
        bbox: { minX, minY, maxX, maxY, width: bboxWidth, height: bboxHeight },
        coverageWidth: bboxWidth / width,
        coverageHeight: bboxHeight / height,
        bboxAspectRatio: bboxWidth / Math.max(1, bboxHeight),
        centerX,
        centerY,
      };
    };
  });
}

export async function readCanvasFrameMetrics(page, { selector = DEFAULT_SELECTOR } = {}) {
  return page.evaluate((canvasSelector) => window.__measureStructureViewerCanvasFrame?.(canvasSelector), selector);
}

export async function assertCanvasWellFramed(page, {
  selector = DEFAULT_SELECTOR,
  label = 'structure viewer canvas',
  minPixelRatio = 0.0015,
  minCoverageWidth = 0.1,
  minCoverageHeight = 0.14,
  maxCoverageWidth = 1,
  maxCoverageHeight = 1,
  minAspectRatio = 0.08,
  maxAspectRatio = 6.5,
  minCenter = 0.08,
  maxCenter = 0.92,
} = {}) {
  const metrics = await readCanvasFrameMetrics(page, { selector });
  const failures = [];
  if (!metrics?.nonBlank) failures.push(metrics?.reason || 'blank canvas');
  if ((metrics?.significantPixelRatio || 0) < minPixelRatio) failures.push('too few significant pixels');
  if ((metrics?.coverageWidth || 0) < minCoverageWidth) failures.push('model bbox too narrow');
  if ((metrics?.coverageHeight || 0) < minCoverageHeight) failures.push('model bbox too short');
  if ((metrics?.coverageWidth || 0) > maxCoverageWidth) failures.push('model bbox fills too much width');
  if ((metrics?.coverageHeight || 0) > maxCoverageHeight) failures.push('model bbox fills too much height');
  if ((metrics?.bboxAspectRatio || 0) < minAspectRatio) failures.push('model bbox is excessively vertical');
  if ((metrics?.bboxAspectRatio || Infinity) > maxAspectRatio) failures.push('model bbox is excessively horizontal');
  if ((metrics?.centerX || 0) < minCenter || (metrics?.centerX || 1) > maxCenter) failures.push('model bbox off-center horizontally');
  if ((metrics?.centerY || 0) < minCenter || (metrics?.centerY || 1) > maxCenter) failures.push('model bbox off-center vertically');
  if (failures.length > 0) {
    throw new Error(`${label} framing failed: ${failures.join(', ')} | metrics=${JSON.stringify(metrics)}`);
  }
  return metrics;
}
