# Experimental RC direct-control durable jobs

The original small-displacement RC control API now has a distinct single-host
durable job operation, `bounded_rc_fiber_direct_control`, with request schema
`structural-analysis-job-request.v3`. It uses the existing canonical RC model,
materials, assembler, Newton solve and whole accepted-history recovery. The
Frame3D request and solver contracts retain their existing behavior.

This connects durable execution, authenticated artifact reads and failure
accounting. RC Workbench review and M1–M4 study integration remain open. The
small local continuation tests below do not establish independent physical
verification, general cyclic capability, performance improvement or release
approval. The earlier 242-target API/CLI observation remains separate; it has
not yet been repeated through this durable service.

## Immutable request and chunk policy

The request embeds `model` as a neutral JSON object and `config` as the complete
existing `BoundedRCFiberDirectControlRequest.to_dict()` payload. The model is
loaded from canonical JSON bytes, so its original-input checksum identifies
those bytes, not an earlier file with different whitespace. `case_id`,
`source_revision`, the operation and result contract are also immutable.
The declared source revision is a caller assertion, not a signed source
attestation.

`execution_config` contains `chunk_target_count` (1–255) and
`maximum_api_invocations` (2–4096). The original cumulative target/reversal
budgets and all six Newton settings remain in `config`. Submission checks the
supported canonical model, free translational UX/UY control in metres and the
whole authored direction sequence without entering a numerical solver. A job
starts at genesis; subsequent restart bytes come from its last verified
durable checkpoint.

`execute_job_claim` dispatches the new operation to
`execute_rc_fiber_direct_control_claim`. Each lease executes one fixed chunk,
then either releases a partial checkpoint or completes the job. An optional
dispatcher target budget must equal the authored chunk size. It cannot silently
change discretization or continuation policy.

## Full replay, verification and accounting

Each chunk invokes the original API with its exact suffix and native restart
bytes. The existing API numerically replays the entire accepted prefix from
genesis before the suffix. The worker then calls
`validate_bounded_rc_fiber_direct_control_artifacts`, which repeats that complete
request and verifies original transition recovery and native restart bytes.
Both invocations must succeed before durable progress advances. An
artifact-consistent blocked path still fails the job.

The service reserves one immutable ordinal **before each API invocation**.
The generic budget fields retain their existing names, but the RC contract
explicitly labels their unit `reserved_api_invocations`. They are not counts
of completed targets, Newton iterations or linear solves. For successful chunk
endpoints `e_i`, the unchanged APIs perform `2 * sum(e_i)` core target solves,
before any retries. A single 242-target chunk would therefore require 484 core
target solves; 242 one-target chunks would require 58,806. These are accounting
implications, not measured durable performance.

Full analysis results retain prefix/suffix/total numerical work and response
reassembly counts. Fresh verification retains its own report, work and
reassembly counts. Separate wall/process nanoseconds include each API call and
artifact extraction. Database publication, transport, and observer overhead are
outside those invocation timings; no end-to-end speedup is inferred.

The service stores immutable invocation outcomes and their reservation/lease
bindings. Structured export failures retain the original available work report;
unexpected exceptions remain explicitly unknown. A crash before outcome
publication leaves a pending ordinal whose work is unknown, even after lease
takeover or explicit failed-job resume. Retries never reset the budget. The last
verified checkpoint survives failed suffixes and verification rejection.

## Publication, artifact limits and lifecycle

Checkpoints contain compact chunk receipts and terminal native restart bytes.
The final job result contains the latest cumulative API result exactly once.
Prior analysis outcomes remain separately retained for audit, so chunking still
has cumulative storage cost; it is not a constant-storage implementation.
Receipt validation binds source/request/configuration, exact target order,
native checkpoint endpoints, result hashes, work, timings and the worker's
fresh-verification report. The service also matches every receipt to its two
recorded invocation outcomes. Service validators perform structural and byte
binding checks; numerical verification belongs to the worker and is not repeated
inside the SQLite writer transaction. These remain trusted-worker observations,
not an independent numerical attestation.

RC API results retain their 512 MiB limit. RC job results and individual
invocation envelopes allow 576 MiB, accommodating the API artifact plus bounded
metadata without base64 expansion of the cumulative response history. Existing
request (16 MiB), checkpoint (128 MiB), completion evidence (16 MiB), and other
operations' result limits remain. HTTP completion admits a bounded base64
envelope and enforces the authenticated job's result limit. This is in-memory
single-host transport, not a streaming or distributed storage qualification.

Authenticated tenant reads include:

- `GET /v1/jobs/{job_id}/rc-invocations`: compact invocation metadata and pending
  ordinals, without concatenating all cumulative results.
- `GET /v1/jobs/{job_id}/rc-invocations/{ordinal}`: original individual outcome
  bytes, including retained failed analysis or verification details.
- The existing job/result/evidence routes for durable state and completed output.

A background heartbeat renews leases during long calls. Loss of a lease cannot
interrupt the running solver, but prevents publishing into a replacement lease.
Cancellation is supported between chunks; the worker does not claim immediate
in-flight numerical cancellation. An expired worker cannot attach an outcome to
another lease's reservation.

## Verification record

The development worker fixture uses the unchanged three-target elastic reversal
`(-1e-6, -2e-6, -1.5e-6)` on the existing RC L-frame. One whole chunk and three
one-target chunks across reopened services produce exact cumulative response
and material histories and identical native restart bytes. The differing suffix
requests and replay-work records are preserved. The fixture observes four
original analysis calls, four mandatory verification calls and eighteen actual
core target calls. It is a development fixture, not a frozen clean-source
benchmark or the larger yielded 242-target observation.

The first worker command failed during collection because the editable install
resolved the original checkout (zero API or core calls). Using explicit
`PYTHONPATH="$PWD/src"` selected this worktree. The first executed worker group
then passed 24 tests in 14.18 s. Its raw fixture is retained at
`/tmp/structural-rc-durable-worker-m82neh3y`; later transport-only checks reuse
those bytes without adding numerical evidence. The final worker selection passes
31 tests in 7.80 s with no additional numerical calls. The raw development bundle
is sealed at 68 files / 10,864,359 bytes; its inventory SHA-256 is
`ed989a4c210bfa495b12f16ae462ef364f933c5ece66c83c021aee8c182f6016`.
Two separate processes recheck the complete file set, lengths and hashes.
The related source copies were taken after the tests, not frozen before them.

The final combined selection passes **149 tests in 18.37 s**: 53 pure request/
artifact contracts, 65 service/HTTP contracts and 31 worker checks using copies
of the retained numerical fixture. This adds no numerical calls. Final review
found and corrected Python's `True == 1` / integer–float equality in outcome/
receipt and table/event comparisons; canonical JSON bytes now preserve exact
types. Nine mutation regressions fail before that fix and pass afterward.
Malformed HTTP lengths are rejected before body reads, and failed/unknown work
cannot be recorded as fully accounted. Initial import/monkeypatch and invalid
test-target/cancellation setup failures remain retained, without solver credit.

The existing durable/Frame3D neighborhood passes 88 tests in 212.37 s; CI
registration passes 49 tests in 0.55 s. These groups overlap other focused runs
and are not a whole-repository test pass. Ruff, formatting and diff checks pass.
Service evidence is sealed at `/tmp/structural-rc-service-hl3ehh3u` (10 files /
78,396 bytes; inventory SHA-256
`5ff2cbeca61f998dbb220ea7456b6c943b55e7709602a64a518becd359edc4af`).
The [machine summary](rc-fiber-durable-jobs-20260909.summary.json) records final
source identities, test scopes, raw references and remaining limitations.

The roadmap remains active. A clean-source large-path durable observation,
verified RC Workbench review, study integration, broader families, independent
verification and the existing owner/licensing/hardware dependencies remain.
