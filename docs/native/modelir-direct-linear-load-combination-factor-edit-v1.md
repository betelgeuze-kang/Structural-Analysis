# Direct linear-load-combination factor edit v1

This C5 slice installs one bounded command:

```text
structural-workbench model-edit-linear-load-combination-factor MODEL.json \
  --load-combination ID --load-pattern PATTERN-ID --factor NONZERO-F64 \
  --output-dir DIR
```

The editor changes exactly one existing `load_pattern` term factor. The selected linear
combination must be source-neutral, extension-free and unreferenced by another combination. It
must contain two through 64 ordered, unique, existing `linear_static` pattern terms with finite
nonzero factors. The edit preserves the combination identity, contiguous index, type, term
reference kinds, reference identities, declaration order and term count.

Both the source and edited ModelIR cross strict Rust parsing and the single C ABI into C++
semantic/reference validation. Nested or referenced combinations, missing patterns, source or
extension ownership, unsupported-feature or direct round-trip ownership, malformed terms,
non-finite/zero factors and exact no-op edits fail closed. Output uses create-new publication and
contains canonical `model-ir.json` plus a self-hashed `edit-receipt.json`.

The ModelIR provenance extension is
`structural-native:model-edit-direct-linear-load-combination-factor.v1`; its operation is
`direct_linear_load_combination_factor_edit`. It binds the selected combination and pattern,
combination/term indices, previous and edited factors, the complete edited term array and all
source/edited model identities.

Installed CPU static/shared distribution E2E v49 edits `LC_WEAK` from `1.2` to `1.35`, then binds
the edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR,
recovery and ReportIR. Native CPU execution proves exact `active_external_load`
`[25000,-13500,5000,0,0,0]`, byte-identical direct/restart results, FP64 execution, fallback 0,
and Python/Node lookup count 0.

This is not general combination editing. Direct pattern-reference replacement is a separate
bounded surface documented in
`docs/native/modelir-direct-linear-load-combination-reference-edit-v1.md`. Append-only direct term
addition and single-term removal are other bounded surfaces; reorder, arbitrary-position or nested
insertion,
downstream-referenced editing and nested edits beyond the separate bounded typed-root-factor
surface, source-format writeback, visual editing, arbitrary solver selection, approved HIP C2,
engineering acceptance and C6 remain open.
