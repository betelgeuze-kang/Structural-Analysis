# ModelIR bounded linear load-combination execution v1

This C5 slice executes one validated `linear` load combination formed from exactly two distinct
direct `linear_static` load patterns. It extends the existing CPU ModelIR product without changing
the C ABI v1.13 table or any structure size.

## Frozen ABI compatibility

The ABI field `sa_model_ir_linear_assembly_config_v1.load_pattern_id` and the corresponding result
field `load_pattern_index` are frozen. For this bounded extension they are documented as legacy
wire aliases for an unambiguous load-case selector and selector index. C++ resolves the ID against
both typed load-pattern and load-combination families. A missing ID or an ID present in both
families fails with `SA_ERR_INVALID_ARGUMENT`; no caller-owned output is published.

`Model::project_linear_reference_graph` now carries pointer-free combination identities, stable
indices, reference kinds, IDs, and factors. A selected combination is accepted only when it has
exactly two terms, both are direct pattern references, the referenced patterns are distinct, and
both factors are finite and nonzero. Existing projection limits still require zero-self-weight
linear-static patterns, supported frame3d/truss3d elements, homogeneous constraints, no time
functions or construction stages, and no unsupported-feature rows.

External nodal loads are scaled and accumulated in declared term order. Every multiplication and
addition is checked for finite FP64 output and reports `SA_ERR_RESIDUAL_LIMIT` on overflow. Tangent,
mass, internal force, JVP, equilibrium residual, and result recovery continue to use the same C++
element and deterministic assembly sources as direct-pattern execution. The backend is CPU FP64
and the fallback count is exactly zero.

## Rust and Workbench surface

The safe Rust FFI wrapper copies both pattern and combination selector indices before constructing
the immutable native handle and independently verifies the index returned by C++. The existing
strict v1 analysis request remains byte compatible. Workbench creates the combination request with:

```text
structural-workbench model-create-linear-analysis-request MODEL.json \
  --case CASE-ID --load-combination COMBINATION-ID \
  --max-iterations N \
  --absolute-residual-tolerance VALUE \
  --relative-residual-tolerance VALUE \
  --maximum-increment VALUE \
  --output-dir REQUEST
```

The request's frozen `load_pattern_id` field carries the combination ID. Its companion
`structural-native-model-linear-combination-request-create-receipt.v1` explicitly records the
selector kind, combination ID, exact ordered terms, frozen field alias, C++ semantic snapshot and
assembly preflight, generated sparse request hash, and create-new artifact identity. Pattern-mode
request bytes and receipts remain unchanged.

## Evidence and boundary

C++ unit and ABI tests prove deterministic signed-factor accumulation, direct-pattern invariance in
the presence of combinations, immutable repeatability, selector ambiguity rejection, exact-term
count and distinct-pattern enforcement, zero-factor rejection, and overflow taxonomy. Rust product
tests prove strict JSON -> C ABI -> C++ -> canonical CSR -> PCG -> ResultIR/recovery execution and
byte-identical initialized checkpoint/restart output.

Installed CPU static/shared distribution E2E v44 repeats the Workbench creation and execution with
an empty `PATH`. The self-hashed append-only receipt binds the request receipt, analysis request,
assembly receipt, final checkpoint, ResultIR, recovery, and ReportIR. It proves the active load for
`1.2 * LC_WEAK - 0.5 * LC_STRONG` is exactly `[0, -12000, 5000, 0, 0, 0]`, direct/restart bytes are
identical, and fallback is zero.

This does not claim nested or arbitrary-term combinations, self-weight, time-dependent or staged
combinations, shell or nonlinear combination execution, HIP parity, engineering acceptance, or C6
decommission.
