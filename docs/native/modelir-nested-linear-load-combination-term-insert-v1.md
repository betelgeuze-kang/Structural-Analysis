# Nested linear-load-combination root-term insertion v1

This bounded C5 Workbench slice inserts one new explicitly typed root term at an explicit final
index in an existing nested linear load combination. The installed command is:

```text
structural-workbench model-insert-nested-linear-load-combination-term MODEL.json \
  --load-combination ID --ref-kind load_pattern|load_combination --ref-id NEW-ID \
  --factor NONZERO-F64 --at-index 0..63 --output-dir DIR
```

The selected root must be source-neutral, extension-free, unreferenced, acyclic, nested and
linear. It must contain two through 63 ordered unique typed terms with finite nonzero factors and
at least one load-combination reference. The new typed reference must resolve to an existing
`linear_static` pattern or linear combination and must not already occur in the root. The requested
zero-based final index may be any position from zero through the source root-term count, inclusive.
Every existing reference, factor and relative order, each descendant combination, the root
identity/index/type and every unrelated ModelIR row are preserved.

Both source and edited graphs must resolve with root-inclusive depth at most eight, no more than 64
expanded leaf contributions, and two through 64 nonzero unique `linear_static` patterns after
repeated-path consolidation. An out-of-range index, missing or incompatible reference, duplicate
typed reference, direct root, cycle, 64-term source, downstream reference, source or extension
ownership, unsupported-feature ownership, round-trip ownership or malformed factor fails closed.
Rust strictly parses and canonicalizes both snapshots, which cross the
single C ABI into C++ semantic, reference and cycle validation. Output uses create-new atomic
publication.

The edited model carries
`structural-native:model-insert-nested-linear-load-combination-term.v1`. Its operation is
`nested_linear_load_combination_term_insert` and its profile remains
`acyclic_nested_linear_static_depth_8_expanded_terms_64`. Provenance and the self-hashed receipt
bind the typed reference, factor, requested final index, source and edited root terms, complete
source and edited expansions, all ModelIR identities and the create-new artifact identity.

Focused Rust library, CLI and product E2E tests prove typed middle insertion, descendant and source
preservation, deterministic repeated publication, closed range/duplicate/missing/cycle/ownership
boundaries, strict C++ revalidation, exact CPU execution, fallback 0 and byte-identical direct
versus checkpoint resume. Installed CPU static/shared E2E inserts `0.1 LC_STRONG` at index one in
the root `[COMBO_SERVICE,LC_AXIAL]`, producing `[COMBO_SERVICE,LC_STRONG,LC_AXIAL]` and exact active
load `[25000,-6000,1500,0,0,0]` with an empty executable lookup path. The append-only v60 receipt
binds the edited ModelIR, edit receipt, request receipt, analysis request, assembly receipt,
checkpoint, ResultIR, recovery and ReportIR.

This is not arbitrary graph rewriting. Append-only addition, factor/reference replacement, term
deletion and existing-term reorder remain separate bounded surfaces. Bulk insertion or
permutation, descendant or downstream-referenced mutation, source-format writeback, visual
editing, arbitrary solver selection, approved HIP C2, engineering acceptance and C6 remain open.
