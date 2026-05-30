#!/usr/bin/env node
import http from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const port = Number(process.env.STRUCTURE_VIEWER_PORT || 8765);
const host = process.env.STRUCTURE_VIEWER_HOST || '127.0.0.1';
const viewerEntry = '/src/structure-viewer/index.html';
const defaultQuery = 'project=midas33_release&drawing=midas33_optimized&variant=optimized';

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
};

function sendText(response, status, text) {
  const body = Buffer.from(text);
  response.writeHead(status, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Content-Length': String(body.length),
  });
  response.end(body);
}

const server = http.createServer((request, response) => {
  const requestUrl = new URL(request.url || '/', `http://${host}:${port}`);
  if (requestUrl.pathname === '/' || requestUrl.pathname === '/index.html') {
    const target = `${viewerEntry}?${defaultQuery}`;
    response.writeHead(302, { Location: target });
    response.end();
    return;
  }
  const decodedPath = decodeURIComponent(requestUrl.pathname);
  const target = path.resolve(rootDir, `.${decodedPath}`);
  if (!target.startsWith(rootDir)) {
    sendText(response, 403, 'Forbidden');
    return;
  }
  if (!existsSync(target) || !statSync(target).isFile()) {
    sendText(response, 404, `Not found: ${decodedPath}`);
    return;
  }
  response.writeHead(200, {
    'Content-Type': mimeTypes[path.extname(target)] || 'application/octet-stream',
    'Cache-Control': 'no-store',
  });
  createReadStream(target).pipe(response);
});

server.listen(port, host, () => {
  const url = `http://${host}:${port}${viewerEntry}?${defaultQuery}`;
  console.log(`Structure viewer: ${url}`);
  console.log('Serve root:', rootDir);
});
