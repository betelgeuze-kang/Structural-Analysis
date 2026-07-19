// Fail-closed browser persistence and local operations state boundary.
import {
  VIEWER_RUNTIME_INGEST_PAYLOAD_SESSION_KEY,
  createRuntimeIngestPayloadStorage,
} from './viewer-runtime-ingest-payload-storage.js';

export * from './viewer-contracts.js';
export * from './viewer-runtime-ingest-payload-storage.js';
export * from './viewer-local-ops-state.js';

export function createBrowserRuntimeIngestPayloadStorage(browserWindow) {
  if (!browserWindow || typeof browserWindow !== 'object') {
    throw new TypeError('browserWindow is required');
  }
  return createRuntimeIngestPayloadStorage({
    storageKey: VIEWER_RUNTIME_INGEST_PAYLOAD_SESSION_KEY,
    // Access sessionStorage inside each callback. Its getter may throw under a
    // browser security policy; the leaf storage adapter converts that failure
    // into an explicit fail-closed receipt while retaining in-memory payloads.
    storageGet: key => browserWindow.sessionStorage.getItem(key),
    storageSet: (key, text) => browserWindow.sessionStorage.setItem(key, text),
    storageRemove: key => browserWindow.sessionStorage.removeItem(key),
  });
}
