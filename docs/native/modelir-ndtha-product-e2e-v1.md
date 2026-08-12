# Bounded ModelIR NDTHA Product E2E v1

## Closed profile

This slice closes C4 and C5 only for `fixed_guided_frame3d_x_v1`, the exact one-element profile
defined by [Bounded ModelIR to NDTHA Adapter v1](modelir-ndtha-adapter-v1.md). The structural
model remains authoritative: Rust strictly parses and hashes ModelIR v2, C++ validates and derives
the scalar problem through ABI v1.6, and the existing ABI v1.5 CPU kernel advances or resumes it.

The separate `structural-model-ir-ndtha-analysis-request.v1` document carries only explicit
execution data and stable selectors. It repeats the expected ModelIR content, semantic and
provenance hashes, so a request cannot silently target different source bytes. Duplicate keys,
unknown fields, non-finite values, bad stable IDs, identity drift and unsupported profile values
fail before execution.

## Commands and artifacts

~~~bash
structural-cli analysis model-run model.json model-request.json --output-dir run
structural-cli analysis model-run model.json model-request.json \
  --output-dir partial --step-budget 2
structural-cli analysis model-resume model.json model-request.json \
  partial/checkpoint.ndcp --output-dir resumed
~~~

Every advancement publishes a new directory atomically and refuses an existing destination.
Inputs are size-bounded regular files and symlinks are rejected. A terminal directory contains:

- `model-ir.json`: canonical exact ModelIR bytes;
- `model-analysis-request.json`: canonical explicit adapter request;
- `generated-request.json`: canonical scalar native request produced from the C++ derivation;
- `checkpoint.ndcp`: ModelIR-bound outer checkpoint envelope;
- `native-run-receipt.json`: receipt from the inner bounded NDTHA product;
- `result-ir.json`, `report-ir.json` and `report.md`: terminal native product artifacts;
- `run-receipt.json`: self-hashed inventory and derivation receipt.

A partial run omits the terminal result/report files and reports `checkpointed`. Completion and
physical collapse retain the inner native status instead of being coalesced.

## Checkpoint binding

The canonical little-endian `SAMNCP01` envelope contains and hashes:

- ModelIR content, semantic and provenance SHA-256 identities;
- canonical adapter-request and generated-request identities;
- the embedded ABI v1.5 checkpoint identity and exact byte length.

The aggregate hash uses a domain separator. Decode rejects truncation, trailing bytes, oversized
artifacts, malformed lowercase digests, inner-state corruption and any binding mismatch. A model
that happens to derive the same mass and stiffness as another model therefore cannot reuse its
checkpoint.

## Evidence and authority boundary

The tracked test invokes the absolute Rust CLI after clearing its environment, so neither Python
nor Node can be resolved. Direct execution and partial-plus-resume produce the same nine terminal
artifacts byte for byte. Their lengths and SHA-256 values are frozen. Focused tests also mutate
every checkpoint byte, change one analysis field, forge a ModelIR identity and pass a symlinked
model; each case fails without publishing an output directory. The derivation receipt records CPU
backend selection and `fallback_count: 0`.

Result authority remains `bounded_candidate`. This capability does not claim arbitrary ModelIR
topology reduction, general frame/truss/shell assembly, inferred nonlinear material state,
P-delta derivation, HIP C2 parity, native Workbench composition or C6 Python decommission.
