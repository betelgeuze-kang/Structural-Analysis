# ModelIR bounded direct linear load-combination deletion v1

This C5 slice extends terminal neutral linear-load-combination deletion from the frozen exact-two
profile to two through 64 direct `linear_static` pattern terms. The installed command remains:

```text
structural-workbench model-delete-linear-load-combination MODEL.json \
  --load-combination ID \
  --output-dir DELETED-COMBINATION-MODEL
```

The candidate must be the last contiguous load-combination row, have null `source_id`, empty entity
extensions and `combination_type: linear`. It must contain two through 64 ordered terms referencing
unique existing `linear_static` patterns with finite nonzero factors. Missing, nonterminal,
source-owned, extended, referenced, unsupported-feature-owned, round-trip-owned, malformed,
duplicate-pattern and nested candidates fail before mutation. No row is reindexed or cascaded.

## Compatibility and provenance

Exact-two deletion keeps the original
`structural-native:model-delete-linear-load-combination.v1` extension and receipt fields byte
compatible. Three through 64 terms use
`structural-native:model-delete-direct-linear-load-combination.v2`, operation
`direct_linear_load_combination_delete`, deletion profile
`unique_direct_linear_static_patterns_2_to_64`, and an explicit term count. Both paths bind the
exact removed ordered terms, source and edited ModelIR identities and C++ semantic snapshot in the
self-hashed edit receipt.

Rust preserves the source, publishes a create-new canonical model, reparses it strictly and sends
it through the single C ABI for C++ reference/cycle validation. The command leaves all unrelated
rows, blockers, round-trip mappings and prior authoring provenance unchanged.

Focused Rust tests cover a three-pattern deletion and the unchanged exact-two v1 field set.
Installed CPU static/shared distribution E2E v47 repeatedly deletes `COMBO_DIRECT`, proves source
nonmutation and identical artifacts, then creates and executes a direct `LC_WEAK` request. It binds
the deleted ModelIR, edit receipt, request, assembly receipt, checkpoint, ResultIR, recovery and
ReportIR identities; verifies exact active load `[0,-10000,0,0,0,0]`; proves byte-identical direct
and resumed output; and requires fallback 0 with Python/Node lookup 0.

Nested deletion, direct or nested term editing, nonterminal/general deletion, self-weight, time
functions, stages, shell/nonlinear execution, visual manipulation, engineering acceptance,
approved HIP C2 and C6 remain open.
