# Structure Viewer module boundaries

Workbench v2 is the application product shell. Static Viewer is an embedded, directly openable 3D/drawing/evidence subsystem. Its runtime entry point composes stable responsibility facades instead of importing leaf implementation files directly.

| Module | Owns | Must not own |
| --- | --- | --- |
| `viewer-contracts` | payload validation, resource limits, persistence policies | DOM rendering, project workflow |
| `viewer-ingest` | loading, file reads, normalization, ingest validation | browser persistence, rendering |
| `viewer-state` | URL/workspace, selection, comparison, timeline state | storage adapters, DOM rendering |
| `viewer-storage` | fail-closed session/local persistence and local operations state | engineering verdicts, renderer state |
| `viewer-report` | evidence interpretation, reviewer records, viewer-local report/export | application-wide workflow authority |
| `viewer-renderer` | Three.js scene, meshes, picking, contour, deformation, HUD | payload persistence, review decisions |
| `viewer-shell` | Viewer-local panels and UI composition | Workbench project/run/result orchestration |
| `release-viewer-bundler` (`implementation.phase1.release_viewer_bundler`) | recursive ESM inlining for offline single-file artifacts | runtime behavior or evidence interpretation |

`src/structure-viewer/index.html` may import only the six runtime composition facades (`viewer-ingest`, `viewer-state`, `viewer-storage`, `viewer-report`, `viewer-renderer`, and `viewer-shell`). `viewer-contracts` is reached through ingest/storage, while worker leaf URLs remain explicit because the worker bootstrap needs concrete module URLs.

The application production build is multi-entry: `vite.config.ts` emits Workbench at `dist/index.html` and Static Viewer at `dist/src/structure-viewer/index.html`. This preserved nested path is part of the Workbench/Viewer delivery contract, not a development-server convenience. `scripts/verify-workbench-viewer-delivery.mjs` checks both entries, every emitted local asset reference, the Viewer shell marker, and the Workbench bundle's Viewer target; browser E2E additionally proves the iframe did not resolve to the Workbench SPA fallback.

The Python `implementation.phase1.release_viewer_bundler` follows this module graph recursively and replaces every reachable local Viewer import with a deterministic data URL. The runtime modules never depend on the release bundler.

This boundary is an incremental migration seam: leaf files remain separately testable and can be moved behind their owning facade without changing the HTML entry point or release artifact contract.
