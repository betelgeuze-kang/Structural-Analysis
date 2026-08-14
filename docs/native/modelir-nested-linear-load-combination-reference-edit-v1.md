# Nested linear-load-combination reference edit v1

This bounded C5 Workbench slice replaces one existing typed root reference in a nested linear
load combination. The installed command is:

```text
structural-workbench model-edit-nested-linear-load-combination-reference MODEL.json \
  --load-combination ID --ref-kind load_pattern|load_combination --ref-id SOURCE-ID \
  --replacement-ref-kind load_pattern|load_combination --replacement-ref-id NEW-ID \
  --output-dir DIR
```

The selected root must be source-neutral, extension-free, unreferenced by another combination and
already satisfy the acyclic nested profile: root-inclusive depth at most eight, at most 64 expanded
leaf contributions and two through 64 root terms. Source and replacement references are selected
by both kind and identity. A replacement pattern must exist and be `linear_static`; a replacement
combination must exist and be linear. The edited root must retain at least one combination term,
remain acyclic and resolve to two through 64 nonzero unique patterns within the same depth and
expansion limits.

The editor preserves the root identity, contiguous index, type, term order and count, the selected
factor, all other root terms, every descendant combination row and every unrelated model row.
Exact no-ops, duplicate typed replacements, missing or incompatible replacements, direct-root
degradation, cycles, depth or expansion overflow, downstream root references, source or extension
ownership, unsupported-feature ownership and direct round-trip ownership fail before publication.

Rust strictly parses and canonicalizes both models. Source and edited snapshots cross the single C ABI into C++ semantic, reference and cycle validation.
Output is a create-new directory containing canonical self-hashed `model-ir.json` and `edit-receipt.json`; an
existing destination is never overwritten.

The edited model carries
`structural-native:model-edit-nested-linear-load-combination-reference.v1`. Its operation is
`nested_linear_load_combination_reference_edit` and its editing profile is
`acyclic_nested_linear_static_depth_8_expanded_terms_64`. Provenance and the receipt bind source
and replacement kinds and identities, selected root and term indices, preserved factor, complete
source and edited root terms, both bounded expansion summaries and pattern terms, source input
SHA-256, all source and edited ModelIR identities, C++ snapshot status and the create-new artifact
identity.

Focused Rust tests prove deterministic publication, source immutability, kind-changing
`load_pattern` to `load_combination` replacement, descendant preservation, cycle and direct
degradation rejection, exact CPU execution, fallback 0 and byte-identical direct versus real
checkpoint resume. The installed static and shared CPU package E2E creates `COMBO_ALTERNATE` as
`0.8 LC_WEAK + 0.2 LC_STRONG`, replaces root term `LC_AXIAL` with that combination while
preserving factor `0.25`, proves exact active load `[0,-8000,2000,0,0,0]` with an empty executable
lookup path, and binds all artifacts in the append-only v52 distribution receipt.

This is not general combination editing. Factor editing, append-only root-term addition, root-term
removal and root-term reorder remain separate bounded surfaces. Arbitrary-position insertion, bulk permutation, descendant mutation, downstream-
referenced root mutation, source-format writeback, visual editing, arbitrary solver selection,
approved HIP C2, engineering acceptance and C6 remain open.
