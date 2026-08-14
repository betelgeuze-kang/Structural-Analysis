# Direct linear-load-combination reference edit v1

This bounded C5 Workbench slice replaces one existing load-pattern reference in a direct linear
load combination. The installed command is:

```text
structural-workbench model-edit-linear-load-combination-reference MODEL.json \
  --load-combination ID --load-pattern SOURCE-PATTERN-ID \
  --replacement-load-pattern NEW-PATTERN-ID --output-dir DIR
```

The selected combination must be source-neutral, extension-free and unreferenced by another
combination. It contains two through 64 ordered `load_pattern` terms with unique existing
`linear_static` pattern identities and finite nonzero factors. The source term must exist and the
replacement pattern must exist, be `linear_static`, and not occur in another term. The editor
preserves the combination identity, contiguous index, type, term order and count, every factor,
and every unrelated term and model row. Exact no-ops, duplicate or missing replacements, nested
terms, source or extension ownership, unsupported-feature ownership and direct round-trip
ownership fail before publication.

Rust strictly parses and canonicalizes both models. The source and edited snapshots cross the
single C ABI into C++ semantic, reference and cycle validation. Output is a create-new directory
containing canonical self-hashed `model-ir.json` and `edit-receipt.json`; an existing destination
is never overwritten.

The edited model carries
`structural-native:model-edit-direct-linear-load-combination-reference.v1`. Its operation is
`direct_linear_load_combination_reference_edit` and its editing profile is
`unique_direct_linear_static_patterns_2_to_64`. Provenance and the edit receipt bind the
combination and term indices, source and replacement pattern identities, preserved factor,
complete source and edited term arrays, source input SHA-256, all source and edited ModelIR
identities, C++ snapshot status and the create-new artifact identity.

Focused Rust tests prove deterministic publication, source immutability, factor/order/count
preservation, strict C++ revalidation, exact active-load change, fallback 0, and byte-identical
direct versus real-checkpoint resume. The installed static and shared CPU package E2E repeats the
same flow by replacing `LC_WEAK` with `LC_AXIAL` in `COMBO_SERVICE`, proves exact active load
`[120000,0,5000,0,0,0]` with an empty executable lookup path, and binds its artifacts in the
append-only v51 distribution receipt.

This is not general combination editing. Factor editing, bounded append-only direct term addition,
single-term removal, direct term reorder and nested typed-reference replacement remain separate
surfaces. Bulk permutation,
explicit-position insertion is a separate bounded surface; nested insertion, descendant or
downstream-referenced mutation,
source-format writeback, visual editing, arbitrary solver selection, approved HIP C2,
engineering acceptance and C6 remain open.
