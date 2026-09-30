# Cohort Workbench through the artifact HTTP application — 2026-09-13

Source `8165b9799c0d492f7ef482712d32f385e961d89e` extends the disposable transport observation
server and tests. Product frontend source is unchanged from
`87d6b8074b30e5953768d3816c359c18afb53173`; its already-built assets are used.

## Integration and failure correction

The existing loopback WSGI harness now accepts either the controlled cohort fixture
or an original cohort directory with an explicitly supplied report hash. It uses
`RcStrategyCohortBundle.from_reader` and the same tenant-authorized immutable
`RcSearchArtifactWSGIApplication` as standalone studies. Original data are read
only; numerical execution and training entry points remain forbidden in this
transport observer.

The new cohort contract/browser specs were missing from the explicit Workbench E2E
list. They are now included in the default list, with the actual HTTP cohort spec
included under `--with-job-api`, alongside the existing actual HTTP search tests.
This registration is code, not proof that hosted execution has completed.

The first original HTTP observation found a page script error even though the
cohort rendered. Diagnosis identified a missing optional
`src/structure-viewer/index.midas33.data.js` request receiving SPA HTML from the
harness. Missing file requests now return plain-text 404; extensionless application
navigation retains the index fallback. The regression checks missing-script status
and browser page errors. Two diagnostic reruns preceded the corrected observation;
failed server receipts and available diagnostic drivers/logs are preserved. No
physical solve or fit was repeated for these failures.

## Direct verification

Eight real HTTP browser tests passed after the correction: four new cohort tests
and four existing search tests. They cover desktop/mobile review, original physical
and runtime/cohort downloads, invalid credentials, tenant isolation, rejected writes,
unknown artifact paths and missing static scripts. Successful API response lengths
and hashes are checked against original fixture bytes on shutdown. These controlled
fixtures establish transport behavior, not scientific generalization.

TypeScript, focused Ruff and diff checks passed. The formal E2E command
`node scripts/verify-workbench-v2-e2e.mjs --with-job-api --grep cohort --workers=1`
stopped at `trusted_node_identity_mismatch` before building/testing. Its pinned Node
version/hash checks were not weakened. Direct Playwright execution passed; it is
not equivalent to passing that formal toolchain entrypoint.

## Original-data observation

The source portable packet inventory was verified against
`390442ef9599a5bcbe29d727ae0ec1dbb2b9633130968405c94c63d1f357c740` and its 577-file
snapshot was mounted with the original cohort report hash. Browser requests were
served by the actual loopback HTTP application, without Playwright interception.

Both 1440- and 390-pixel views retained 4 pairs and 8 executions, opened selected
candidate `w047`, and downloaded byte-exact cohort/runtime records (4 downloads
total). There were 1,234 successful HTTP responses, all checked against the original
inventory, plus 4 direct byte reads for download comparison. Both views had zero
page errors, stayed within the viewport boundary, and the server exited with code 0.
The two incomparable selections remain included and the aggregate cost ratio stays
unavailable.

The observer measured 7470.047 ms after browser launch through both
views, downloads, teardown and response-byte checks. It excludes interpreter startup,
server snapshot loading and browser launch. The server separately recorded snapshot
loading 67.165 ms and its own overlapping lifecycle wall
interval 7301.662 ms. These intervals must not be summed or presented
as a complete campaign time. No new fit or nonlinear solve was executed. No speedup,
independent physical validation or release qualification follows from this result.

## Records and remaining work

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cohort-real-http-e85xm9_e` contains 19 files / 2,510,435 bytes. Its
sibling inventory SHA-256 is `460ed4a646024d0a038a630bfd7410f7d78b1ed1146596cd13e20a22fcc403ce`. It includes exact source
delta from the previous committed source, test logs, observation drivers, failed and
successful server receipts, screenshots and measurement scopes. Earlier sealed
packets remain unchanged.

This closes the previously unexecuted local actual-HTTP cohort browser path. Full
hosted CI, the pinned local frontend entrypoint, end-to-end campaign cost accounting,
independent cases and physical/model qualification remain open, together with the
existing licensing, owner/administrator and hardware dependencies.
