# RC-fiber candidate review transport observation — 2026-09-09

Four candidate-review `net::ERR_ABORTED` diagnostics were reproduced while the
native response bodies reached EOF and the verified review remained usable.
This retained-data observation identifies the recorded consumption state; it
does not establish the Chromium internal cause or explain earlier uninstrumented
diagnostics. A separate provider correction keeps unsolicited `AbortError`
failures visible instead of treating them as caller cancellation.

The numerical source and first-feasible search results remain those documented in
[the candidate stop runtime observation](rc-fiber-candidate-stop-runtime-20260909.md).
This work made zero numerical requests and zero training calls.

## Source and evidence boundaries

- Observation root: `/tmp/structural-candidate-transport-probe.5k6_rzjr`.
- Pre-change revision: `ff512f450ed3406a94cc2d6be794fd38b6174068`.
- The instrumented probe used the existing UI build from
  `f0acd24f130db4fe909a0faf9685d4db7e33437f`; the relevant UI source was unchanged.
  Observing that supplied build is not an independent build attestation.
- The later classification correction is committed as
  `ea9d1d5e1f5c20bc7261775764f99fe702c9798d`.
- `observed/receipt.json`, `transport-analysis.json` and `independent-audit.txt`
  preserve the pre-change trace and its saved-data analysis.
- `execution-summary.json` and `validation/receipt.json` bind the separate
  post-change source, built files and focused verification.

The served portable bundle was the original `review-bundle` under
`/tmp/structural-candidate-stop-observation.5rnmmzev`.
No original sealed artifact was rewritten or regenerated.
The probe recorded 240 source, build and dependency inputs unchanged.

## Instrumented transport and subsequent review

The receipt passed 521 explicitly counted comparisons with no listed failures.
Additional Playwright assertions are not included in that counter.
The portable bundle contains 72 files, 93,060,419 bytes and 54 original artifact
links. Desktop and mobile each fetched all 72 files once: 93,060,419 body bytes
per viewport, with HTTP 200, 72 EOF results and 72 reader releases.
Including the initial Node provider verification, the server retained 216
candidate-review GET requests, all returning HTTP 200.

Each viewport subsequently visited all 12 original slots and downloaded 18
byte-exact artifacts: 16 selected M2 manifest/report files, the suite and the
root review manifest. Slot selection did not fetch the review again.
The recorded candidate diagnostics occurred during navigation, before the
verified UI and those slot/download checks; context closure occurred later.

All four diagnostic paths below are relative to `/candidate-review/`.
For each, native EOF byte count, HTTP `Content-Length`, original manifest length
and the sum of CDP `dataLength` agree.

| Viewport | Path | Agreed body bytes |
| --- | --- | ---: |
| Desktop | `artifacts/requests/00011-learned.json` | 2,873 |
| Desktop | `artifacts/workers/00010-deterministic/search.json` | 5,090,716 |
| Mobile | `artifacts/workers/00001-deterministic/search.json` | 3,939,614 |
| Mobile | `artifacts/workers/00008-deterministic/search.json` | 3,939,613 |

CDP reports `loadingFailed`, `net::ERR_ABORTED` and `canceled: true` for these
four requests, with no `loadingFinished` event for them. Native fetch/read did
not reject. Every recorded signal remained un-aborted; neither viewport trace
contains a signal-abort event or a `reader.cancel` call.
CDP `encodedDataLength` is retained separately and is not a consumed-body or
truncation counter. Trace chunks were counted, not independently SHA-hashed;
identity rests on provider/manifest validation and exact download-byte checks.

Both page-error arrays are empty, but other diagnostics remain: one viewer
data-script `ERR_ABORTED`, five 404 console errors and the `initLog` viewer
fallback error per viewport. This is not a whole-application error-free result.

## What the observer can establish

The hook forwards native fetch once, returns the original Response and forwards
the original reader methods. It adds no retry, replacement body, clone or extra
read. Its logging, promises, listeners and retained references can still affect
timing and garbage collection. No performance comparison is derived from it.

Host event-arrival timestamps, CDP timestamps and page performance timestamps
are different clocks. Their proximity does not establish an engine-internal
causal order. Absence of recorded caller abort or reader cancellation also does
not cover every possible internal cancellation path.

The original five diagnostics in the earlier sealed observation lacked these
hooks. The new four cannot retrospectively determine the earlier five causes
or body-consumption states. Chromium's internal triggering mechanism remains
unidentified; this observation neither removes diagnostics nor proves an
engine fix, general transport reliability or physical verification.

## Separate cancellation-classification correction

`candidateProcessProvider.ts` now requires `signal?.aborted` as well as an
`AbortError` name before returning the quiet `unconfigured` cancellation result.
An unsolicited fetch/body `AbortError`, with no signal or an active signal,
returns `invalid` with its diagnostic and no partial bundle. Caller cancellation
continues to suppress stale delivery and prevents the next request.
This one-line condition does not reinterpret the four successful-body CDP
diagnostics or claim to eliminate their browser-internal source.

Seven regressions were added to the existing candidate process contract spec:
four unsolicited fetch/body failures across absent/active signals, two caller
cancellations during fetch/body consumption, and one already-cancelled request.
The pre-fix run retained four expected failures in `red-tests.log`.
The post-fix candidate process/history/stop contract group passed 131 tests in
57.2 seconds, including those seven; `green-tests.log` preserves that run.
These groups overlap and are not added as independent coverage totals.

TypeScript `--noEmit` exited 0. The new build and viewer-delivery check exited 0.
The focused browser run passed three tests in 18.6 seconds: two new desktop/mobile
synthetic unsolicited-error displays, plus the existing leave/return lifecycle
test against delayed prior-source delivery. They are post-change UI regressions,
separate from the pre-change 521-comparison original-bundle probe.
The validation receipt records server closure and source/build byte rechecking.

## Retention and claim limits

The new root is sealed: 103 inventoried files, 199,164,255 bytes, excluding the
17,248-byte `artifact-inventory.json` itself. Its SHA-256 is
`23685bc4b4b5aa61c9df056b364d2223c715572aa9ca6000b89728e7e308d890`.
The separate read-only seal verification passed; this is a retained file-set
and byte-integrity check, not an atomic snapshot or source attestation.
The old sealed root also passed complete file-set/hash rechecking: 790 files,
385,977,598 bytes, with `mutation_performed: false` in
`original-seal-verification.json`.

The saved-data reviewer performed no browser, build, test, fit, numerical solve
or physical recovery. The probe and focused browser tests did run browser/UI
work, and their observer overhead remains in their own elapsed measurements.
No speedup, currency saving, external acceptance or release authority follows
from either the transport observation or the classification correction.
