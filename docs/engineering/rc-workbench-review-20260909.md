# Stored RC Workbench review — 2026-09-09

Workbench now recognizes the experimental RC durable result media type and
fetches the original request, saved job checkpoint when present, result and
completion evidence through the authenticated transport. It transfers those
buffers to a dedicated worker. The worker checks byte lengths/SHA-256, strict
JSON, request/model/control identities, wrapper/API/receipt logical hashes,
completion report bindings, reservation counts, the saved checkpoint prefix and
native terminal restart, and the complete accepted response history before
returning a small review summary. Numeric-token-preserving slices verify the
producer's compact JSON hashes without reserializing Python floats as JavaScript
numbers. This does not recompute the solver's binary state hashes or execute
constitutive laws, equilibrium or fresh numerical verification.

The worker retains original bytes and accepted history; React receives one
selected epoch and one selected material point's stored history. The result cap
remains 64 MiB, with 128 MiB for an attached durable checkpoint and 16 MiB for
request/evidence. A media type does not grant a larger memory budget. Whole JSON
parsing and transient hashing allocations still occur inside the worker; this
is not a constant-memory parser or mobile hardware qualification. Navigation,
caller cancellation, worker errors and RPC timeout terminate the worker and
retire pending calls. A worker failure removes physical tables and downloads.

The review exposes each authored target's node displacement, support reaction,
member end force, section response and fiber strain/stress. Selecting a steel or
concrete material point exposes its stored internal state at every accepted
epoch. Material history is paginated in groups of 20, initially at the final
page; all epochs remain available. Original request, saved job checkpoint,
result, evidence and terminal restart downloads retain their exact bytes
regardless of the selected epoch.

Reserved API invocations and successful-receipt subtotals remain distinct.
An unconfirmed reservation is unknown work, never zero-cost work. Source revision
is a caller declaration. Fresh replay remains a stored trusted-worker
attestation, not browser execution or independent source authentication. Public
J1–J5 authority, independent physical validation, design and release approval
remain false.

## Local verification

The portable fixture contains the original hash-checked bytes from the retained
three-target split/restart development observation. It has six successful API
invocations, twelve core calls and twenty-four Newton iterations in its retained
receipts. Those counts concern the selected split job, not the separate whole
fixture's aggregate full-plus-split work. No new numerical calls were executed.

Contract tests exercise original-byte tampering in all four roles, changed
physical data behind refreshed outer hashes, rehashed authority promotion,
duplicate keys and unknown reservation work. Browser tests cover desktop/mobile
step selection, steel and concrete history, all five exact downloads, corrupt
input, worker disposal on navigation and fail-closed worker errors. An initial
13-test run had eleven passes and two failures: selecting the already selected
material point cleared its history without triggering a reload. The selection
handler was fixed; existing selections now retain their data.

The final focused selection passes **27 tests in 33.4 seconds** and includes the new RC checks and the existing
Frame3D, sparse and authenticated job browser regressions. TypeScript, Vite build
and viewer delivery are included in the command:

```sh
node scripts/verify-workbench-v2-e2e.mjs \
  --grep 'RC review|stored RC browser|persisted Frame3D review|extended sparse job browser|authenticated job browser|job transport cancels' \
  --workers=2
```

The separate large-file observation uses the unchanged 65,680,274-byte resumed
result from the frozen `962c302` 242-target durable observation. Original request,
checkpoint, result and evidence references are checked before serving them from
a disposable authenticated loopback read server. Local Chromium inspects steps
1, 122 and 242, compares original node displacements and checkpoint identities,
counts 84 fiber rows, and navigates the first/last pages of all 242 stored
material steps at 1440×1000 and 390×844 viewports. Screenshots and exact receipts
are retained in the companion summary's raw directory. Loading elapsed times
and a progressing timer are observations, not a comparative benchmark or a
responsiveness guarantee.

The first two large-file observation attempts reached the correct RC values but
failed their page-error check: the disposable server returned the app's HTML for
missing optional viewer assets, including `index.midas33.data.js`. The harness
now returns 404 for missing assets, preserving their unavailable state. Those
failures and missing asset paths remain recorded. No protected evidence or
optional viewer dataset was generated to conceal that absence.

## Remaining work

Hosted acceptance of this change, actual authenticated completed-RC service
mount qualification, broader physical families, constrained-device memory
measurements, study/candidate integration and independent validation remain
open. The large observation serves retained files, whereas the preceding
authentication observation used the real Python API for a queued RC job; neither
is relabeled as a completed RC job served end-to-end by a production mount.
This implementation does not complete the M1–M5/P1–P3 roadmap or authorize merge,
deployment or release.
