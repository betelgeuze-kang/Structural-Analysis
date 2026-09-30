# RC search artifacts: authenticated real HTTP integration

The combined Workbench review now loads a pinned search artifact graph from a
real local HTTP application. Source `577b3246ff51c63903b3850744ae6d7ba7fd4dd9`
implements the mount and passes the actual browser/API observation; subsequent
`614a2c458e56befd965b806b5802f10748f1a1b5` adds a no-oracle publication test
without changing execution code. This extends the previous
[intercepted-route browser verification](rc-control-search-workbench-20260910.md).

## Application integration

`RcSearchArtifactBundle.from_directory` imports a completed, host-owned output
with an explicitly pinned logical report hash. `from_reader` supports a host's
bounded storage adapter. Registration walks only the report's named graph,
checks metadata hashes and model/result/checkpoint/verification byte references,
and freezes the selected bytes. It never includes an arbitrary directory listing,
producer logs, fixture provenance or unreferenced files.

`RcSearchArtifactWSGIApplication` serves registered `(tenant, study)` pairs at
`/v1/rc-search/{study}/{artifact}`. The host supplies its authorization callback;
there are no default credentials or secret-loading behavior. Every request uses
the existing `X-Structural-Tenant` and bearer convention. Only authenticated GET
requests to exact registered paths return bytes. The mount rejects other methods,
bodies, queries, traversal, unregistered files and cross-tenant access. Responses
carry explicit lengths, `no-store` and `nosniff` headers.

The host can mount the application alongside the built Workbench and configure
`rcControlSearchUrl` with the same-origin result endpoint, using the existing
`jobAuthorization` callback. For example, a host-controlled composition uses:

```python
bundle = RcSearchArtifactBundle.from_directory(
    completed_output_directory, expected_report_hash=approved_report_hash
)
application = RcSearchArtifactWSGIApplication(
    {(tenant_id, "design-study"): bundle}, authorize=host_authorize_tenant
)
```

The matching Workbench endpoint is
`/v1/rc-search/design-study/result.json`. The host retains listener/TLS,
authentication-backend and deployment configuration responsibility. This change
implements and tests the service component; it does not deploy a public service.

A snapshot is immutable for its application lifetime. HTTP requests never read
mutable filesystem paths or launch numerical work. Filesystem import rejects
links and changed files, and requires a completed directory without concurrent
writers during publication. Byte budgets are bounded per file and to 1 GiB for
the snapshot and all mounts combined, with at most 32 registered mounts.
A later source-file change cannot replace an already registered response.

The service provides integrity and access control, not engineering acceptance.
The existing Workbench validator still verifies the complete result/model,
performance, quantity, price and coverage bindings before displaying them.
The server neither recalibrates the model nor certifies learned predictions.

## Real browser and API observation

The official pinned frontend harness runs with `--with-job-api` and a focused
selection of new RC search and existing durable API authentication tests. The
new disposable server mounts the actual WSGI component and serves the actual
built frontend over loopback HTTP. There are **no Playwright response routes or
request fulfilment mocks** in this observation. Credentials are synthetic and
kept in the test process.

Both 1440 px and 390 px browsers load all three strategy records, preserve the
three-alternative denominator, select the verified learned-arm `cheap` design
and download exact original model/result/checkpoint/verification files plus the
search report. The captures are visually reviewed. Separate actual HTTP requests
exercise missing/wrong credentials, cross-tenant isolation, unregistered files
and forbidden mutation methods. A credential rejection hides the browser's
candidate selection. Existing durable job API authentication still passes.

All **six browser tests pass** on the first run: four new RC search tests and
two existing durable API tests. Type checking, production build and the existing
viewer-delivery contract pass in the same official harness. Node v24.20.0 matches
executable SHA-256
`89af8424dd53e560b1933f87ba650d8bf57c83ca5a04600eefb31f416aabbae7`.
The 25.3 s test interval is not a solver or service throughput benchmark.

The RC server registers **75 artifacts / 3,064,643 bytes** and records 165 API
requests. All **159 successful responses / 6,881,668 bytes** match the original
fixture bytes and SHA-256 values, covering all 75 registered paths. Three
requests return 401, two return 404 and one returns 405. No credential value is
written into that receipt. Ten user downloads across the two viewports match
original bytes; search-report downloads use the already verified worker copy.

Snapshot loading takes 0.017974 s. The server lifetime is 6.558453 s with
0.099176 s process CPU and 114340 KiB peak RSS on the observed Linux host. These
figures include test interaction and are not isolated hardware qualification.
Numerical and fit entry points are patched to raise in the transport server;
**no new solver call or fit** occurs. Existing numerical costs remain attached
to the earlier authored fixture generation and are not recounted as new work.

## Python checks and preserved evidence

The first 29 Python tests pass. After a no-oracle graph case is added, all
**30 tests pass in 1.66 s**. They cover original bytes, authorization errors,
callback failure, exact paths, read-only framing, bounded reads, pin mismatch,
changed files, link rejection and immutable snapshots. The no-oracle bundle
registers 42 actual references and exposes no exhaustive-oracle route. Ruff and
scoped mypy pass; an unused test import was removed during preparation.

A separate original-record audit checks 221 source/fixture files against Git,
all successful HTTP responses against originals, status counts and terminal
server state. It takes 0.803465 s and executes no fit or structural solve.
The server and original harness are terminal with exit zero. The packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-search-http-_d0rcmm4` is sealed after exactly rereading **231 files / 6,727,016 bytes**;
inventory SHA-256 is
`72a5bb434f8c2bcf16ec25cb50fa6a1d6b8d7fc099fd2b2940482f09567d885a`.
The [machine summary](rc-search-http-integration-20260910.summary.json) retains
source identities, every API response receipt, costs, tests and seal.

The local actual HTTP artifact-mount gap for this search format is now covered.
Production identity/deployment, broader independent-family repetitions, learned
net benefit and independent structural validation remain open. This observation
adds transport evidence, not a new experiment, external training admission or
full-roadmap completion.
