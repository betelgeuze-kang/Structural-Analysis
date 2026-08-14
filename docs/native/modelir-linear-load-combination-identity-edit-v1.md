# ModelIR linear load-combination identity edit v1

`structural-workbench model-edit-linear-load-combination-identity` is a bounded native edit surface
that replaces the stable identity of one existing, unreferenced ModelIR v2 linear load combination.
It changes no term, factor, reference, or order and publishes a new artifact directory without
modifying its source.

```text
structural-workbench model-edit-linear-load-combination-identity MODEL.json \
  --load-combination SOURCE-ID --new-load-combination NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement must
satisfy the ModelIR stable-ID grammar, differ from the source, be unique in the load-combination
namespace, and not name a load pattern. The command changes only `load_combinations[].id`. It
preserves the contiguous index and exact remaining row, including `combination_type`, ordered typed
terms, factors, `source_id`, and extensions.

## Profile, reference closure, validation, and provenance

The accepted direct profile contains two through 64 unique `linear_static` load-pattern terms. The
accepted nested profile is acyclic, has at most eight combination levels, and expands to at most 64
pattern terms. The bounded expansion before and after the edit must be identical.

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. A missing source, duplicate or malformed replacement, no-op, load-pattern
ambiguity, noncontiguous index, malformed or out-of-profile row, or source/replacement identity
referenced by another load combination, an unsupported-feature `source_entity_id`, or a direct
round-trip `model_ir_entity_id` fails closed. This v1 surface does not infer or cascade reference
changes. The edited canonical bytes are strictly reparsed and cross the same C++ validator before
create-new publication.

The root extension
`structural-native:model-edit-linear-load-combination-identity.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation
`linear_load_combination_identity_edit`, both identities, retained index and exact row without its
identity, direct/nested profile, root and expanded term counts, expanded pattern terms, all source
and edited hashes, C++ verification, readiness, blockers, and the model artifact hash.

Installed CPU static/shared distribution E2E replaces `COMBO_DIRECT` with `COMBO_RENAMED` and
creates a model-bound request selecting the replacement identity. The append-only v74 receipt binds
the model, edit receipt, request receipt, request, assembly receipt, checkpoint, ResultIR, recovery,
and ReportIR. Typed recovery proves frame element type `[1]`, offsets `[0,12]`, active DOFs
`[6,7,8,9,10,11]`, exact combined active external load `[25000,-12000,5000,0,0,0]`, byte-identical
initialized-checkpoint restart, and fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only stable-identity replacement for one unreferenced existing bounded direct or nested
linear load combination. It does not cascade downstream combination, unsupported-feature, or
round-trip references; edit terms, factors, references, order, or count; create or delete
combinations; select a general solver; provide visual editing or engineering acceptance; remove
React/TypeScript; prove approved HIP C2; or authorize C6.
