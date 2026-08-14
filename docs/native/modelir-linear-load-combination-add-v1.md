# ModelIR two-pattern linear load-combination addition v1

This bounded C5 Workbench slice creates one `linear` load combination from exactly two distinct
existing `linear_static` load patterns. The installed command is:

```text
structural-workbench model-add-linear-load-combination MODEL.json \
  --load-combination NEW-ID \
  --term PATTERN-A FACTOR-A --term PATTERN-B FACTOR-B \
  --output-dir ADDED-COMBINATION-MODEL
```

## Contract

Rust strictly reads a bounded regular ModelIR file. The new combination identity and both pattern
identities are UTF-8 strings containing 1-128 bytes. The combination identity must be new, both
referenced patterns must already exist and have `analysis_type: linear_static`, the pattern IDs
must differ, and both factors must be finite and nonzero.

The operation appends exactly one row with the next contiguous index, `combination_type: linear`,
two ordered `load_pattern` terms, null `source_id`, and empty entity extensions. It cannot author a
nested combination term, change an existing term, flatten factors into nodal loads, reindex rows,
or select a solver.

Both the source and edited model cross strict Rust parsing and the single C ABI into the C++ typed
ModelIR validator. The C++ reference/cycle checks therefore remain authoritative. The canonical
edited model carries `structural-native:model-add-linear-load-combination.v1`, exact upstream
content/semantic/provenance identities, and the ordered term set. Existing domain rows,
round-trip mappings, extensions, and explicit analysis blockers remain intact.

Publication is create-new and atomic. It emits `model-ir.json` plus a self-hashed
`structural-native-model-edit-receipt.v1` binding the combination identity/index/type, ordered
pattern terms and factors, source input hash, source and edited identities, C++ snapshot status,
analysis readiness, blockers, artifact hash, and claim boundary.

## Product evidence and execution boundary

Focused Rust E2E repeats the command byte-for-byte, proves source nonmutation and next-index
composition, and rejects duplicate combination IDs, missing patterns, repeated patterns,
zero/non-finite factors, invalid destinations, and invalid source semantics without partial
publication. An unrelated explicit blocker and round-trip mapping are preserved without readiness
promotion.

Installed CPU static/shared E2E v42 repeats the same creation under an empty `PATH`, validates the
edited artifact through the installed C++ boundary, renders the native topology view, and binds the
model, edit receipt, validation, view, and expected solver-preflight rejection identities into the
distribution receipt.

The current ModelIR linear reference assembly intentionally rejects every model containing load
combinations. The product test proves `model-create-linear-analysis-request` fails closed before
publication with `workbench_model_linear_request_preflight_failed`. Consequently this slice proves
native combination authoring and validation, not combination expansion or solver execution.

Nested combinations, arbitrary term counts, term editing/deletion, combination evaluation, general
solver selection, visual manipulation, engineering acceptance, approved HIP C2, React/TypeScript
removal, and C6 decommission remain open.
