# Production viewer runtime data delivery — 2026-09-13

The remaining default-preset failure was a build omission: Vite emitted the viewer
entry and imported modules, but did not discover data scripts loaded through
runtime-created script tags. Those originals existed in the source checkout and
were absent from `dist`; a dist-only host therefore returned 404.

Source `e2f214ff6417e34e9b221b1d8ead79704c18df29` adds an explicit seven-file
runtime asset list and emits each original at its existing viewer-relative path.
It covers the embedded/preset data scripts, chart/panel-zone/optimization-history
scripts and drawing catalog manifest. The delivery verifier now rejects missing
or changed outputs and reports the asset count and byte total. The data contents,
their provenance and their existing usage/qualification boundaries are unchanged.
This local build change is not a release or new redistribution authorization.

The seven emitted files total **36,651,438 bytes** and match their sources exactly.
They remain separately requested assets; this increases build artifact size and
does not imply improved download or startup performance.

## Validation

- Eight focused Python loader/product-shell tests passed, including temporary
  build fixtures proving that missing and modified runtime data fail delivery.
- Trusted Node 24.20.0 passed TypeScript checking, production build and the updated
  delivery verifier. A targeted RC rejection browser test passed.
- A new formal browser test fetched all seven real emitted assets and compared
  original bytes, then opened the configured MIDAS preset. Its source label was
  populated, contained MIDAS and did not identify a demo. The initial attempt
  encountered a socket hang-up while fetching a large script; direct binary
  equality and response disposal replaced expensive generic buffer comparison.
  The subsequent test passed in 24.1 s. The transport failure's cause was not
  independently established and this is not a reliability benchmark.

## Actual Workbench observation

The real loopback WSGI host served the production build at 1440 px without browser
request interception. The embedded viewer source became
`canonical MIDAS33 optimized roundtrip raw model`. Its console recorded 12,728
elements and six materials, instead of the prior demo/default data. Neither
the unavailable-preset-sidecar warning nor the undefined `initLog` error appeared;
the drawing catalog manifest also loaded without its previous missing-file warning.
The RC panel remained verified, with 42 exact original HTTP responses and 14
exact original downloads. No new numerical path or policy fit ran.

The 7.813265350 s review interval includes 250 ms pacing before each download and
excludes startup, screenshots, teardown and historical numerical/training work.
It is a single desktop observation, not a speedup, mobile performance or hardware
qualification result. The successful preset load is not an independent check of
the model's physical correctness or its analysis results.

The code-check companion JSON still returns 404 in this host. Drawing comparison
still reports a null `steps` access. Software WebGL and iframe-sandbox warnings
also remain. These issues are not hidden by the successful RC and preset paths;
full viewer, code-check, GPU and product readiness remain unproved.

Read-only packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-viewer-runtime-delivery-B7MO8G`.
Six files / 242,118 bytes; inventory SHA-256
`45f40d1dfe681d0a837365f54eab144eb47aeede93c2cfd398fff87b3de37fa8`.
The [machine-readable record](viewer-runtime-delivery-20260913.summary.json)
also lists the seven emitted byte bindings. See the preceding
[preset error-path repair](viewer-preset-recovery-20260913.md).
