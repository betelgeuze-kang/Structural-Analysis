# Typed ModelIR Linear-Buckling Durable Job and Service C5 v1

Status: bounded CPU C5 implementation capability. The reference-static and dense spectral
numerical families remain at their separately evidenced C1 authority. This integration does not
promote HIP C2, numerical validation C3, engineering acceptance, or release authority.

## Immutable request and execution profile

`structural-model-ir-linear-buckling-durable-job-request.v1` embeds one canonical `ModelIR` and
one exact `structural-model-ir-linear-buckling-analysis-request.v1`. Its immutable profile is
`model_ir_linear_buckling_cpu_v1`. The request must bind the embedded model's content, semantic,
and provenance identities. Duplicate keys, unknown fields, unsupported profiles, identity drift,
and inputs outside the 64 MiB model, 4 MiB control, or 72 MiB envelope bounds fail before store
mutation.

The common append-only store preserves this profile through every self-hashed event. A claimed
worker reparses the envelope and runs the existing deterministic reference-static plus Frame3D
geometric-stiffness and dense generalized-eigen product. A process exit releases the local store
lock; lease expiry requeues the job, and a replacement worker can claim the same immutable request.
Queued jobs cancel without execution. Cancellation observed after computation retains the verified
aggregate `checkpoint.mbcp` boundary and never publishes a successful artifact set.

## Verified completion and artifact custody

Success publishes the exact lexical eighteen-file product inventory as named content-addressed
references in one terminal event. Before that event is appended, Rust requires:

- the fixed file names, order, media types, bounded sizes, and canonical JSON bytes;
- byte-identical embedded model and analysis request;
- a valid aggregate checkpoint bound to the exact model identity triple and request hash;
- exact equality between the aggregate checkpoint's inner PCG/spectral boundaries and the three
  separately published checkpoint files; and
- a regenerated dense ResultIR, ReportIR, and Markdown projection equal to the supplied bytes.

The common checkpoint, ResultIR, ReportIR, and report-document references point to the same
content hashes as their named product entries. Reference-static recovery and reaction files remain
named evidence; they are not mislabeled as the buckling result's recovery or reaction slots. Blob
hash or length drift fails closed during retrieval/export.

## CLI and loopback HTTP

```text
structural-cli job submit-model-buckling MODEL.json BUCKLING-REQUEST.json \
  --store jobs --idempotency-key buckling-1
structural-cli job work-once --store jobs --worker-id worker-1
structural-cli job poll JOB_ID --store jobs
structural-cli job export JOB_ID --store jobs --output-dir result
```

Export creates a new directory containing the same eighteen files as the direct
`analysis model-buckling-run` product plus a self-hashed `job-receipt.json`. It never overwrites an
existing destination.

The bounded loopback service adds strict envelope submission at
`POST /v1/model-buckling-jobs`. Every named product artifact is retrievable with a client token at
`GET /v1/jobs/{job_id}/artifacts/{file_name}`. Existing poll, cancel, worker, and common artifact
routes dispatch from the stored profile. Static-role credentials, single-host/single-tenant scope,
synchronous worker execution, no-store responses, and the 72 MiB body ceiling are unchanged.

## Focused evidence and boundary

Focused tests cover canonical-envelope round trip and duplicate/unknown/identity rejection;
idempotent clean-process submit/work/export; byte equality with the direct eighteen-file product;
expired-lease recovery on a replacement attempt; queued cancellation; immutable blob tamper
rejection; and authenticated HTTP submit, worker, inventory, and named ResultIR retrieval.

This is not distributed orchestration, object storage, remote worker consensus, TLS, tenant
isolation, general sparse/subspace buckling, shell buckling, imperfections, follower/distributed
prestress, nonlinear/path-following buckling, Workbench job monitoring, protected-runner HIP C2,
engineering validation, release authority, or C6 decommission.
