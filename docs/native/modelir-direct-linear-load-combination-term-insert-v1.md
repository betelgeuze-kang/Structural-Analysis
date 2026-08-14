# Direct linear-load-combination term insertion v1

This bounded C5 Workbench slice inserts one new pattern term at an explicit final index in an
existing direct linear load combination. The installed command is:

```text
structural-workbench model-insert-linear-load-combination-term MODEL.json \
  --load-combination ID --load-pattern NEW-PATTERN-ID --factor NONZERO-F64 \
  --at-index 0..63 --output-dir DIR
```

The selected combination must be source-neutral, extension-free, unreferenced and linear. It must
contain two through 63 ordered unique terms that reference existing `linear_static` load patterns
with finite nonzero factors. The new pattern must exist, be `linear_static`, and not already occur
in the combination. The requested zero-based final index may be any position from zero through the
source term count, inclusive. The editor preserves every existing reference, factor and relative
order, the combination identity, contiguous index and type, and every unrelated ModelIR row.

An index above the source term count, a missing, nonlinear or duplicate new pattern, a 64-term
source, nested or downstream-referenced combinations, source or extension ownership,
unsupported-feature or round-trip ownership, duplicate source references and malformed factors
fail closed before publication. Rust strictly parses and canonicalizes source and edited models.
Both snapshots cross the single C ABI into C++ semantic, reference and cycle validation. Output
uses create-new atomic publication; an existing destination is never overwritten.

The edited model carries
`structural-native:model-insert-direct-linear-load-combination-term.v1`. Its operation is
`direct_linear_load_combination_term_insert` and its editing profile is
`unique_direct_linear_static_patterns_3_to_64`. Provenance and the self-hashed receipt bind the new
pattern, factor, requested final index, source and edited term counts, complete source and edited
term arrays, source input SHA-256, all source and edited ModelIR identities, C++ snapshot status and
the create-new artifact identity.

Focused Rust library, CLI and product E2E tests prove explicit middle insertion, closed factor,
range, missing-pattern, duplicate and ownership boundaries, deterministic repeated publication,
source immutability, strict C++ revalidation, exact CPU execution, fallback 0 and byte-identical
direct versus real checkpoint resume. Installed CPU static/shared distribution E2E starts with
`COMBO_SERVICE = 1.2 LC_WEAK - 0.5 LC_STRONG` and inserts `0.25 LC_AXIAL` at index one. Execution
produces exact active load `[25000,-12000,5000,0,0,0]` with an empty executable lookup path. The
append-only v59 receipt binds the edited ModelIR, edit receipt, request receipt, analysis request,
assembly receipt, checkpoint, ResultIR, recovery and ReportIR.

This is not arbitrary combination rewriting. Append-only addition, factor/reference replacement,
term deletion and existing-term reorder remain separate bounded surfaces. Bulk insertion,
permutation, nested or downstream-referenced mutation, source-format writeback, visual editing,
arbitrary solver selection, approved HIP C2, engineering acceptance and C6 remain open.
