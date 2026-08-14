# Nested linear-load-combination root-term reorder v1

This bounded C5 Workbench slice moves one existing typed root term to a distinct final index in an
existing nested linear load combination. The installed command is:

```text
structural-workbench model-reorder-nested-linear-load-combination-term MODEL.json \
  --load-combination ID --ref-kind load_pattern|load_combination \
  --ref-id ID --to-index 0..63 --output-dir DIR
```

The selected root must be source-neutral, extension-free, unreferenced by another combination and
genuinely nested. Its source contains two through 64 ordered terms with unique typed references and
finite nonzero factors, including at least one `load_combination` reference. The selected kind and
identity must match exactly one root term, and the requested zero-based final index must be inside
that root and differ from the source index. The editor preserves the term count, every reference
and factor, the root identity, contiguous index and type, every descendant combination and every
unrelated ModelIR row. Only declaration order changes.

Before and after the move, deterministic resolution requires an acyclic graph with root-inclusive depth at most eight,
no more than 64 expanded leaf contributions, and two through 64 nonzero unique
`linear_static` patterns after repeated-path consolidation. Missing typed terms, no-op or
out-of-range moves, direct or downstream-referenced roots, source or extension ownership,
unsupported-feature or round-trip ownership, duplicate typed references, malformed factors,
cancellation outside the resolved-pattern bound, cycles, depth overflow and expansion overflow
fail closed before publication.

Rust strictly parses and canonicalizes source and edited models. Both snapshots cross the single C ABI into C++ semantic, reference and cycle validation.
Output uses create-new publication and
contains canonical self-hashed `model-ir.json` and `edit-receipt.json`; an existing destination is
never overwritten.

The edited model carries
`structural-native:model-reorder-nested-linear-load-combination-term.v1`. Its operation is
`nested_linear_load_combination_term_reorder` and its editing profile is
`acyclic_nested_linear_static_depth_8_expanded_terms_64`. Provenance and the receipt bind the typed
reference, preserved factor, source and target indices, term count, complete source and edited
root arrays and expansion summaries, source input SHA-256, all source and edited ModelIR
identities, C++ snapshot status and the create-new artifact identity.

Focused Rust tests prove typed selection, order-only mutation, descendant preservation, closed
no-op/range/missing-reference boundaries, deterministic publication, source immutability, strict
C++ revalidation, exact CPU execution, fallback 0 and byte-identical direct versus real checkpoint
resume. Installed CPU static/shared distribution E2E starts with
`COMBO_NESTED = 0.5 COMBO_SERVICE + 0.1 LC_STRONG` and moves `LC_STRONG` from index one to index
zero. The consolidated declaration order changes from `0.6 LC_WEAK - 0.15 LC_STRONG` to
`-0.15 LC_STRONG + 0.6 LC_WEAK`, while execution retains exact active load
`[0,-6000,1500,0,0,0]` with an empty executable lookup path. The append-only v57 receipt binds the
edited ModelIR, edit receipt, request receipt, analysis request, assembly receipt, checkpoint,
ResultIR, recovery and ReportIR.

This is not arbitrary combination rewriting. Factor/reference replacement and term addition or
deletion remain separate bounded surfaces. Bulk permutation, descendant or downstream-referenced
mutation, source-format writeback, visual editing, arbitrary solver selection, approved HIP C2,
engineering acceptance and C6 remain open.
