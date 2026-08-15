# Typed ModelIR Linear Durable Job and Service C5 v1

Status: bounded CPU C5 implementation capability. The underlying typed-ModelIR assembly and
sparse-linear numerical families remain sequentially at C1 until an approved protected-runner
HIP C2 receipt exists. This slice does not promote numerical C2, authoritative C3, engineering
acceptance, or C6.

## Immutable submission envelope

`structural-model-ir-linear-durable-job-request.v1` is a language-neutral, strict JSON envelope.
It embeds one canonical `ModelIR` document and one exact
`structural-model-ir-linear-analysis-request.v1`, declares the immutable
`model_ir_linear_cpu_v1` analysis profile, and requires the request's content, semantic, and
provenance identities to match the embedded model. Duplicate keys, unknown fields, non-finite
values, unsupported profiles, identity drift, and oversized input fail before durable mutation.
The bounded limits are 64 MiB for ModelIR, 4 MiB for analysis control, and 72 MiB for the complete
canonical envelope.

## Durable runtime

The existing single-host Rust store now dispatches by the immutable analysis profile. Historical
nonlinear-NDTHA events remain byte-compatible: absence of an `analysis_profile` field means the
original profile, and the optional recovery and reaction references are omitted from those events.
ModelIR linear events explicitly preserve their profile for the entire append-only, self-hashed
chain.

A worker reparses the envelope, reconstructs ABI v1.13 C++ assembly, regenerates the canonical
CSR request, and advances the existing ABI v1.10 PCG state. An active boundary publishes the exact
outer `SAMLPC01` checkpoint and releases the lease. An expired lease can be reclaimed after reopen.
Numerical nonconvergence publishes a typed failed event while retaining the verified checkpoint;
cooperative cancellation also retains its last verified boundary.

Completion does not trust worker-provided bytes. Rust reopens the stored envelope, reassembles the
typed model, verifies the outer and inner checkpoint identities, restores the terminal state, and
regenerates sparse ResultIR, typed ModelIR result-recovery IR, constrained-reaction ResultIR,
ReportIR, and Markdown. Every byte must match the worker projection before the succeeded event is
appended. Forged recovery or reaction bytes therefore leave the running event unchanged.

## Public CLI

```text
structural-cli job submit-model-linear MODEL.json REQUEST.json \
  --store jobs --idempotency-key case-1
structural-cli job work-once --store jobs --worker-id worker-1 --step-budget 1
structural-cli job work-once --store jobs --worker-id worker-2
structural-cli job export JOB_ID --store jobs --output-dir result
```

The first command reads bounded regular non-symlink inputs before it creates a store. The same
generic poll, cancel, recover, and work-once commands support both profiles. A succeeded ModelIR
linear export contains `checkpoint.mlpcp`, `result-ir.json`, `result-recovery-ir.json`,
`reaction-result-ir.json`, `report-ir.json`, `report.md`, and a self-hashed receipt. A clean-process
E2E clears the environment, sets `PATH` to a nonexistent directory, crosses a real one-iteration
restart, and requires the six numerical/report artifacts to be byte-identical to the public direct
product path with no Python or Node lookup. Frozen succeeded events without a reaction reference
remain readable and export with an explicit legacy no-reaction claim.

## Loopback service

The bounded static-role HTTP service adds:

| Method | Route | Credential | Result |
| --- | --- | --- | --- |
| `POST` | `/v1/model-linear-jobs` | client | strict envelope submission with `Idempotency-Key` |
| `GET` | `/v1/jobs/{job_id}/result-recovery-ir` | client | verified terminal recovery bytes |
| `GET` | `/v1/jobs/{job_id}/reaction-result-ir` | client | verified constrained-reaction bytes |

The existing poll, cancel, checkpoint, ResultIR, ReportIR, document, and worker routes dispatch from
the stored profile. ModelIR checkpoints use a distinct media type. The common request-body ceiling
is 72 MiB, while the original nonlinear-NDTHA store contract retains its 16 MiB request ceiling.
Credential, loopback-only bind, exact HTTP parsing, no-store/nosniff, single-tenant, and synchronous
worker boundaries are unchanged. A socket-free service test covers strict submission, one real
iteration, resumed completion, and authenticated recovery plus constrained-reaction retrieval;
live loopback process-kill evidence remains owned by the original service profile test.

## Honest boundary

This closes a separate C5 orchestration path only for bounded linear-elastic frame3d/truss3d CPU
graphs, homogeneous constraints, and direct nodal loads already admitted by the typed ModelIR
linear product. It transports the exact bounded CPU constrained-reaction ResultIR but does not add
nonzero prescribed constraints, shell or nonlinear graphs, TLS, tenant isolation, distributed
workers, remote storage, broader Workbench profiles, PDF specialization beyond the separately
bounded Workbench path, approved protected-runner HIP C2, authoritative numerical C3, engineering
acceptance, release authority, or C6 decommission.
