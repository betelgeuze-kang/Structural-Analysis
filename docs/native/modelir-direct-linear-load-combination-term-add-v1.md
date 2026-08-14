# Direct linear-load-combination term addition v1

This bounded C5 Workbench slice appends one new load-pattern term to an existing direct linear
load combination. The installed command is:

```text
structural-workbench model-add-linear-load-combination-term MODEL.json \
  --load-combination ID --load-pattern NEW-PATTERN-ID \
  --factor NONZERO-F64 --output-dir DIR
```

The selected combination must be source-neutral, extension-free and unreferenced by another
combination. Its source contains two through 63 ordered `load_pattern` terms with unique existing
`linear_static` pattern identities and finite nonzero factors. The new pattern must exist, be
`linear_static` and not already occur in the combination. The editor appends it at the final term
index, yielding three through 64 terms while preserving the combination identity, contiguous
index, type, every existing reference, factor and order, and every unrelated model row.

Missing or nonlinear new patterns, duplicate references, a 64-term source, nested terms,
downstream combination references, source or extension ownership, malformed factors,
unsupported-feature ownership and direct round-trip ownership fail before publication. Rust
strictly parses and canonicalizes both models. The source and edited snapshots cross the single C ABI into C++ semantic, reference and cycle validation. Output is a create-new directory containing
canonical self-hashed `model-ir.json` and `edit-receipt.json`; an existing destination is never
overwritten.

The edited model carries
`structural-native:model-add-direct-linear-load-combination-term.v1`. Its operation is
`direct_linear_load_combination_term_add` and its editing profile is
`unique_direct_linear_static_patterns_3_to_64`. Provenance and the edit receipt bind the
combination and append indices, source and edited term counts, new pattern identity and factor,
complete source and edited term arrays, source input SHA-256, all source and edited ModelIR
identities, C++ snapshot status and the create-new artifact identity.

Focused Rust tests prove append-only order preservation, all closed rejection boundaries,
deterministic publication, source immutability, strict C++ revalidation, exact CPU execution,
fallback 0 and byte-identical direct versus real-checkpoint resume. The installed static and
shared CPU package E2E starts with `COMBO_SERVICE = 1.2 LC_WEAK - 0.5 LC_STRONG`, appends
`0.25 LC_AXIAL`, proves exact active load `[25000,-12000,5000,0,0,0]` with an empty executable
lookup path, and binds the edited ModelIR, edit receipt, request receipt, analysis request,
assembly receipt, checkpoint, ResultIR, recovery and ReportIR in the append-only v53 distribution
receipt.

This is not general combination editing. Existing factor, reference and single-term removal remain
separate surfaces. Reorder, insertion at arbitrary positions, nested term insertion,
descendant or downstream-referenced mutation, source-format writeback, visual editing, arbitrary
solver selection, approved HIP C2, engineering acceptance and C6 remain open.
