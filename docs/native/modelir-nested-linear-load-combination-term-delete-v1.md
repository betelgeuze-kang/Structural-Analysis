# Nested linear-load-combination root-term deletion v1

This bounded C5 Workbench slice removes one typed root term from an existing nested linear load
combination. The installed command is:

```text
structural-workbench model-delete-nested-linear-load-combination-term MODEL.json \
  --load-combination ID --ref-kind load_pattern|load_combination \
  --ref-id ID --output-dir DIR
```

The selected root must be source-neutral, extension-free, unreferenced by another combination and
genuinely nested. Its source contains three through 64 ordered terms with unique typed references
and finite nonzero factors. The selected `load_pattern` or `load_combination` kind and identity must
match one existing root term exactly. The editor removes that term from any position, yielding two
through 63 root terms while preserving every retained reference, factor and relative order, every
descendant combination, the root identity, contiguous index and type, and every unrelated ModelIR
row. At least one `load_combination` term must remain, so deletion cannot silently degrade the root
to a direct combination.

Before and after deletion, deterministic resolution requires an acyclic graph with root-inclusive depth at most eight,
no more than 64 expanded leaf contributions, and two through 64 nonzero unique
`linear_static` patterns after consolidation. A missing typed term, two-term or direct source,
direct degradation, downstream reference, source or extension ownership, unsupported-feature or
round-trip ownership, duplicate typed references, malformed factors, cancellation outside the
resolved pattern bound, cycle, depth overflow and expansion overflow fail closed before
publication.

Rust strictly parses and canonicalizes source and edited models. Both snapshots cross the single C ABI into C++ semantic, reference and cycle validation.
Output uses create-new publication and
contains canonical self-hashed `model-ir.json` and `edit-receipt.json`; an existing destination is
never overwritten.

The edited model carries
`structural-native:model-delete-nested-linear-load-combination-term.v1`. Its operation is
`nested_linear_load_combination_term_delete` and its editing profile is
`acyclic_nested_linear_static_depth_8_expanded_terms_64`. Provenance and the receipt bind the typed
removed reference, factor and former index, source and edited root-term counts and arrays, both
complete bounded expansion summaries, source input SHA-256, all source and edited ModelIR
identities, C++ snapshot status and the create-new artifact identity.

Focused Rust tests prove middle-position removal, retained relative order and descendant
preservation, every closed rejection boundary, deterministic publication, source immutability,
strict C++ revalidation, exact CPU execution, fallback 0 and byte-identical direct versus real
checkpoint resume. Installed CPU static/shared distribution E2E starts with
`COMBO_NESTED = 0.5 COMBO_SERVICE + 0.25 LC_AXIAL + 0.1 LC_STRONG`, removes the middle typed term
`LC_AXIAL`, and retains `0.5 COMBO_SERVICE + 0.1 LC_STRONG`. Consolidation yields
`0.6 LC_WEAK - 0.15 LC_STRONG`; execution proves exact active load
`[0,-6000,1500,0,0,0]` with an empty executable lookup path. The append-only v56 receipt binds the
edited ModelIR, edit receipt, request receipt, analysis request, assembly receipt, checkpoint,
ResultIR, recovery and ReportIR.

This is not general nested combination editing. Root factor replacement, reference replacement,
term addition and root-term reorder are separate bounded surfaces. Bulk permutation, descendant or
downstream-referenced mutation, source-format writeback, visual editing, arbitrary solver
selection, approved HIP C2, engineering acceptance and C6 remain open.
