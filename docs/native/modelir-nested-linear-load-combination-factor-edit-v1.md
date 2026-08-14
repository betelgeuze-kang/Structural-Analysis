# Nested linear-load-combination factor edit v1

This C5 slice installs one bounded command:

```text
structural-workbench model-edit-nested-linear-load-combination-factor MODEL.json \
  --load-combination ID --ref-kind load_pattern|load_combination --ref-id ID \
  --factor NONZERO-F64 --output-dir DIR
```

The editor changes exactly one existing root-term factor selected by the typed pair
`(ref_kind, ref_id)`. The selected linear root must be source-neutral, extension-free,
unreferenced by another combination and genuinely nested. It must contain two through 64 unique
typed terms, including at least one `load_combination` reference. The edit preserves the root
identity, contiguous index, type, reference kinds and identities, declaration order, term count,
all descendant combinations and every unrelated ModelIR row.

Before and after mutation, the same bounded expansion contract requires an acyclic graph with
root-inclusive depth at most eight, no more than 64 expanded leaf contributions and two through
64 resolved nonzero unique `linear_static` patterns. Both models cross strict Rust parsing and the
single C ABI into C++ semantic, reference and cycle validation. Missing or duplicate typed terms,
direct or downstream-referenced roots, source or extension ownership, unsupported-feature or
direct round-trip ownership, malformed graphs, non-finite/zero factors, cancellation outside the
resolved-pattern bound and exact no-op edits fail closed before publication.

Output uses create-new publication and contains canonical `model-ir.json` plus a self-hashed
`edit-receipt.json`. The ModelIR provenance extension is
`structural-native:model-edit-nested-linear-load-combination-factor.v1`; its operation is
`nested_linear_load_combination_factor_edit`. It binds the typed selector, combination and term
indices, previous and edited factors, source and edited root terms, both complete expansions,
depth/expansion limits and all source/edited model identities.

Installed CPU static/shared distribution E2E v50 edits the `COMBO_SERVICE` root term from `0.5`
to `0.75`, then binds the edited ModelIR, edit/request/assembly receipts, analysis request,
checkpoint, ResultIR, recovery and ReportIR. Native CPU execution proves exact
`active_external_load` `[25000,-9000,3750,0,0,0]`, byte-identical direct/restart results, FP64
execution, fallback 0, and Python/Node lookup count 0.

This is not general combination editing. Root reference replacement, append-only root-term
addition, root-term removal and root-term reorder are separate bounded C5 surfaces. Arbitrary-position insertion and bulk permutation,
descendant mutation, downstream-referenced root editing,
source-format writeback, visual editing, arbitrary solver selection, approved HIP C2, engineering
acceptance and C6 remain open.
