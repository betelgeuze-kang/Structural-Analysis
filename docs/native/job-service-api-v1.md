# Bounded Native Job Service API v1

## Closed profile

This slice closes C5 only for a loopback, single-host, single-tenant HTTP facade over the bounded
CPU nonlinear-NDTHA durable-job runtime. Rust owns the HTTP parser, role authentication, routing,
job composition and response serialization. C++ remains the numerical owner through ABI v1.5.
No Python, Node, web framework or external process is used by the service.

A separately tracked C5 route admits the bounded typed-ModelIR frame3d/truss3d CPU linear durable
profile and retrieves its recovery artifact. It composes ABI v1.13 assembly with ABI v1.10 PCG and
does not promote either underlying numerical family beyond C1. See
`docs/native/modelir-linear-durable-job-v1.md`.

The server accepts exact HTTP/1.1 requests over one request per TCP connection. It rejects:

- non-loopback bind addresses;
- duplicate headers, `Transfer-Encoding`, `Expect`, pipelining and ambiguous or encoded paths;
- missing or non-decimal `Content-Length`, headers over 16 KiB and bodies over 72 MiB;
- wrong content types, unknown JSON fields, duplicate JSON keys and invalid worker bounds; and
- missing, malformed or role-confused bearer credentials.

Every response declares its exact API profile and sends `Cache-Control: no-store`,
`X-Content-Type-Options: nosniff`, an exact `Content-Length`, and `Connection: close`. Stable error
bodies do not contain tokens, filesystem paths, platform errors or solver internals.

## Credential and bind boundary

The service requires distinct client and worker bearer tokens. Tokens are loaded from separate
regular non-symlink files, hashed immediately with a domain-separated SHA-256 identity and never
retained in the service configuration. On Unix, the files must grant no group or other
permissions; mode `0600` is the intended setting. The final path is opened without following a
symlink, and the opened device/inode, length and permissions are checked against the inspected
file.

This is static role authentication, not user identity issuance or tenant authorization. The v1
server refuses any non-loopback address. TLS termination and non-loopback deployment are outside
this capability and must not be inferred from the presence of bearer checks.

## Routes

| Method | Route | Credential | Result |
| --- | --- | --- | --- |
| `GET` | `/v1/health` | none | bounded readiness metadata only |
| `POST` | `/v1/jobs` | client | idempotent strict request submission; requires `Idempotency-Key` |
| `POST` | `/v1/model-linear-jobs` | client | strict ModelIR linear envelope submission; requires `Idempotency-Key` |
| `GET` | `/v1/jobs/{job_id}` | client | fully verified durable job projection |
| `POST` | `/v1/jobs/{job_id}/cancel` | client | queued/checkpointed cancellation or conflict for terminal jobs |
| `GET` | `/v1/jobs/{job_id}/checkpoint` | client | verified immutable checkpoint bytes |
| `GET` | `/v1/jobs/{job_id}/result-ir` | client | verified terminal ResultIR bytes |
| `GET` | `/v1/jobs/{job_id}/report-ir` | client | verified terminal ReportIR bytes |
| `GET` | `/v1/jobs/{job_id}/report-document` | client | verified terminal Markdown bytes |
| `GET` | `/v1/jobs/{job_id}/result-recovery-ir` | client | verified terminal ModelIR recovery bytes |
| `POST` | `/v1/worker/run-once` | worker | claim and advance at most one bounded job |

The worker command is strict JSON:

~~~json
{"schema_version":"structural-native-job-worker-command.v1","worker_id":"worker-1","lease_millis":3600000,"step_budget":2}
~~~

The server is intentionally single-threaded in this slice. `run-once` executes synchronously, so
the network facade does not claim concurrent cancellation while a solve is in flight. The durable
store itself retains its process-wide lock, lease and expired-worker recovery contract.

## Startup

~~~bash
chmod 600 client.token worker.token
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  service serve \
  --listen 127.0.0.1:8080 \
  --store native-jobs \
  --client-token-file client.token \
  --worker-token-file worker.token
~~~

`--ready-file <NEW-FILE>` publishes credential-free startup metadata with create-new semantics.
`--max-requests <N>` is an explicit drain/test bound; omitting it serves until the process is
stopped. Startup and drain receipts expose only the loopback address, request count, recovered-job
count, API profile and claim boundary.

## Restart evidence

The clean-environment E2E removes the entire child environment, including `PATH`, starts the
native server on an operating-system-selected loopback port, submits a request, and advances it to
step 2. It then kills the service process, starts a fresh process over the same store, observes the
checkpointed state, resumes to success and retrieves checkpoint, ResultIR, ReportIR and Markdown
over HTTP. All four response bodies are byte-identical to an uninterrupted direct native run.
The test also proves client credentials cannot invoke the worker route, unauthenticated submission
fails, terminal cancellation conflicts, queued cancellation succeeds, security headers are
present and neither role token appears in process output.

The underlying runtime tests separately prove expired in-flight lease recovery, stale-token
rejection, corrupt-chain/blob failure and one-winner local claims. This HTTP slice inherits those
store semantics but does not relabel them as distributed service evidence.

## Authority boundary

This slice does not provide TLS, non-loopback exposure, multiple tenants, tenant isolation,
per-user authorization, identity issuance, remote worker leases, distributed consensus, concurrent
request execution, rate limiting, quotas, retention, backups, supervision, metrics, audit export or
release authority. Only the tracked CPU nonlinear-NDTHA and bounded typed-ModelIR linear profiles
are executable. Broader ModelIR-to-analysis adaptation, broader solver families, HIP C2, native
Workbench integration and final C6 decommission remain open.
