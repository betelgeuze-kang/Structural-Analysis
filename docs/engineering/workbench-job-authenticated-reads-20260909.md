# Workbench authenticated job transport — 2026-09-09

The durable Workbench provider previously sent cookies only, while the Python
job API requires `X-Structural-Tenant` and `Authorization: Bearer …`. An embedding
application can now supply a `jobAuthorization` callback alongside the existing
same-origin `jobStatusUrl` runtime setting. The callback receives the resolved
status URL and an abort signal and returns `{ tenantId, bearerToken }`, directly
or asynchronously. Credentials are obtained once per load and reused only for
that load's status and artifact requests. React cancellation or an authorization
callback change retires the previous load.

The callback is a host application integration point, not an implemented login
system. It must be installed before mounting Workbench. The provider does not
write credentials to storage, reports, download payloads, UI diagnostics or
build-time settings. The host remains responsible for obtaining and refreshing
credentials and protecting its own session. Without the callback, the existing
cookie integration remains available.

Before requesting credentials, the transport rejects cross-origin destinations,
URL user information, query strings and fragments. It rejects invalid header
values, redacts callback exceptions, uses GET/no-store, and refuses redirects
for both status and artifacts. A host should configure the final endpoint rather
than a redirect. Artifact paths are restricted to the existing four original
roles and RC invocation reads. This does not implement a production listener,
reverse proxy, credential issuance, deployment or permission change.

## Bounded original-byte reads

The provider now counts actual stream chunks before copying them. Missing or
false Content-Length headers cannot bypass the byte budget. An artifact's exact
reference length bounds its allocation; a view without such a reference uses
bounded chunks. Invalid media/length headers are rejected before reading the
body. Oversize, truncated, overlong and aborted reads release their readers and
cancel unread bodies. Compressed HTTP bodies use the decoded byte count for
reference identity. Original SHA-256, strict JSON, completion-evidence and
existing physical contract validators still gate display.

Existing limits remain 256 KiB for views, 64 MiB for published results and
16 MiB for completion evidence. This work does not grant RC results a larger
limit. The RC-specific worker/parser must authenticate the original v3 request
before choosing any different operation budget. Streaming the transport does
not qualify the current main-thread JSON parser or mobile memory use for the
65.7 MB retained RC result.

## Verification boundary

The transport tests cover actual chunk limits, dishonest and missing headers,
reference lengths, compressed bodies, aborts, credential destination checks,
redacted host failures and redirect refusal. Desktop and mobile viewport tests
review the preserved Python Frame3D result/evidence bytes using the new header
callback, and check that those synthetic credentials do not enter the DOM or
browser storage. Existing cookie-mode Frame3D and sparse review tests remain.

The separate real-API browser fixture mounts the built Workbench and
`DurableJobWSGIApplication` on one disposable loopback origin. It submits an
actual queued v3 RC request and checks the complete browser callback/provider/API
authentication chain, exact original-request SHA-256/length, missing credentials,
other-tenant isolation and incorrect credentials. It launches no worker; its RC
numerical entrypoint is guarded against execution. Source revision `bbbb…` in
that queued transport-only request is a synthetic caller declaration, not a
solver execution or source attestation. No result or physical RC review is
published by this fixture.

The normal hermetic frontend lane does not install Python solver dependencies.
Real-API browser integration therefore has its own explicit test selection in
an environment with the repository's Python dependencies; it is not an expected
skip or a claimed hosted integration result. RC result parsing, bounded worker
lifetime and selected-epoch/material-history review remain the next integration
work. Independent numerical validation and the full roadmap remain open.

## Recorded checks

- Initial focused transport/cookie browser selection: **32 passed (22.6 s)**.
- Initial broader selection: **425 passed, one failed (2.1 min)**. The old
  Frame3D test asserted that fetch received the caller's exact AbortSignal
  object. The provider now owns a linked signal so it can cancel sibling reads
  without aborting the caller. That assertion was updated to check one shared,
  retired request signal and an unaffected caller. Existing in-flight caller
  cancellation tests and a new pending-sibling cancellation test verify behavior.
- Final focused selection: **29 passed (17.4 s)**, including the corrected test,
  transport guards, desktop/mobile authenticated artifact review and both actual
  Python API browser cases. The actual API cases were moved to an explicit
  Python-enabled selection; normal frontend CI retains the new transport tests
  without acquiring a Python dependency.
- TypeScript, Vite build, viewer production delivery, fixture Ruff/format and
  `git diff --check` pass. No numerical study was rerun.

The final selection command uses the repository's trusted Node 24 runtime:

```sh
node scripts/verify-workbench-v2-e2e.mjs --with-job-api \
  --grep 'real durable API browser authentication|bounded job stream|job credential destination|authenticated job browser|job transport cancels|provider publishes the verified 3D|cancellation during artifact|cancelled loads' \
  --workers=2
```

The broader selection was not repeated after changing only test registration and
the obsolete assertion; it is recorded as its actual 425/426 result. Focused
source hashes and original logs are linked in the companion summary.

The preceding exact head `ec291c5bb1605492d0ee5c44c34515d023fa0d9e`
has a nonfinal hosted snapshot of 59 successes, 12 failures, five skips and one
running topology check. Both frontend lanes and frontend-contracts pass there.
This does not close the new change's hosted acceptance, the full suite's existing
preparation blockers or independent validation.
