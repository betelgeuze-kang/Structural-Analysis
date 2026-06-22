Goal: Diagnose the failing mobile Playwright smoke in `npm run verify:frontend-browser-smoke`.

Scope:
- Focus only on `tests/frontend/structure-viewer-smoke.spec.ts`, `src/structure-viewer/index.html`, and CSS under `src/structure-viewer/` that affects `#viewport`, `.stage-frame`, and canvas sizing.
- Do not edit files.
- Identify why the two mobile tests time out in `openViewer()` waiting for `#viewport canvas` to have width/height > 10.

Candidate evidence:
- Last observed failures:
  - `structure viewer keeps the mobile real drawing workflow usable`
  - `structure viewer keeps the mobile MIDAS33 optimized workflow usable`
  - both fail at `tests/frontend/structure-viewer-smoke.spec.ts:31` in `page.waitForFunction`, after `#viewport canvas` is visible and provenance is loaded.

Verification criteria:
- Report the most likely root cause with file/line references.
- Suggest the smallest aligned fix.
- Report any command run and its result.
- Keep output concise: changed files should be `none`, tests run, findings, recommended fix, blockers.
