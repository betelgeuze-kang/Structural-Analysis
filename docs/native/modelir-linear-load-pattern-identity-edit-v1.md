# ModelIR linear-load-pattern identity edit v1

`structural-workbench model-edit-linear-load-pattern-identity` is a bounded native edit surface
that replaces the stable identity of one existing, unreferenced ModelIR v2 `linear_static` load
pattern. It changes no structural property and publishes a new artifact directory without
modifying its source.

```text
structural-workbench model-edit-linear-load-pattern-identity MODEL.json \
  --load-pattern SOURCE-ID --new-load-pattern NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement
must satisfy the ModelIR stable-ID grammar, differ from the source, and be unique in the
load-pattern namespace. The command changes only `load_patterns[].id`. It preserves the contiguous
pattern index, `linear_static` analysis type, complete self-weight vector, complete ordered nodal
loads, the optional complete ordered member-distributed-load rows and all of their fields,
`source_id`, extensions, and every unrelated structural row.

## Reference closure, validation, and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. A missing source, duplicate or malformed replacement, no-op, noncontiguous pattern
or nested-load index, non-`linear_static` type, malformed retained field, or source/replacement
identity referenced by a load-combination term, construction stage, unsupported-feature row, or
round-trip mapping fails closed. This v1 surface does not infer or cascade reference changes. The
edited canonical bytes are strictly reparsed and cross the same C++ validator before create-new
publication.

The root extension `structural-native:model-edit-linear-load-pattern-identity.v1` and the
self-hashed `structural-native-model-edit-receipt.v1` bind operation
`linear_load_pattern_identity_edit`, both pattern identities, the retained index, analysis type,
self-weight, complete nodal- and member-distributed-load rows, source identity and extensions, all source and edited hashes,
C++ verification, readiness, blockers, and the model artifact hash. Unrelated explicit blockers
remain visible and no round-trip or solver authority is promoted.

Installed CPU static/shared distribution E2E consumes the v67 nodal-load-identity-edited model and
replaces `LC_WEAK` with `LC_WEAK_RENAMED` without changing structural meaning. The append-only v68
receipt binds the model, edit receipt, request receipt, request, assembly receipt, checkpoint,
ResultIR, recovery, and ReportIR. Typed recovery proves active DOFs `[12,13,14,15,16,17]`, exact
active external load `[0,-1000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and
fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only stable-identity replacement for one unreferenced existing `linear_static` load
pattern. It does not cascade load-combination, construction-stage, unsupported-feature, or
round-trip references; edit nonlinear patterns or other entity identities beyond the separate
bounded linear-material surface; change self-weight,
loads, nodes, combinations, constraints, or topology; create or delete patterns; select a solver;
provide general visual editing or engineering acceptance; remove React/TypeScript;
prove approved HIP C2; or authorize C6.
