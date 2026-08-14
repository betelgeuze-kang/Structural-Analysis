# Direct linear-load-combination term reorder v1

This bounded C5 Workbench slice moves one existing pattern term to a distinct final index in an
existing direct linear load combination. The installed command is:

```text
structural-workbench model-reorder-linear-load-combination-term MODEL.json \
  --load-combination ID --load-pattern PATTERN-ID \
  --to-index 0..63 --output-dir DIR
```

The selected combination must be source-neutral, extension-free, unreferenced and linear. It must
contain two through 64 ordered unique terms that reference existing `linear_static` load patterns
with finite nonzero factors. The selected pattern must occur exactly once, and the requested
zero-based final index must be inside the combination and differ from the source index. The editor
preserves term count, every reference and factor, the combination identity, contiguous index and
type, and every unrelated ModelIR row. Only declaration order changes.

Missing terms, no-op or out-of-range moves, nested or downstream-referenced combinations, source
or extension ownership, unsupported-feature or round-trip ownership, duplicate references and
malformed factors fail closed before publication. Rust strictly parses and canonicalizes source
and edited models. Both snapshots cross the single C ABI into C++ semantic, reference and cycle validation.
Output uses create-new atomic publication; an existing destination is never
overwritten.

The edited model carries
`structural-native:model-reorder-direct-linear-load-combination-term.v1`. Its operation is
`direct_linear_load_combination_term_reorder` and its editing profile is
`unique_direct_linear_static_patterns_2_to_64`. Provenance and the self-hashed receipt bind the
selected pattern, preserved factor, source and target indices, term count, complete source and
edited term arrays, source input SHA-256, all source and edited ModelIR identities, C++ snapshot
status and the create-new artifact identity.

Focused Rust library, CLI and product E2E tests prove identity selection, order-only mutation,
closed no-op/range/missing-pattern boundaries, deterministic repeated publication, source
immutability, strict C++ revalidation, exact CPU execution, fallback 0 and byte-identical direct
versus real checkpoint resume. Installed CPU static/shared distribution E2E starts with
`COMBO_SERVICE = 1.2 LC_WEAK + 0.25 LC_AXIAL` and moves `LC_AXIAL` from index one to index zero.
Execution retains exact active load `[25000,-12000,0,0,0,0]` with an empty executable lookup path.
The append-only v58 receipt binds the edited ModelIR, edit receipt, request receipt, analysis
request, assembly receipt, checkpoint, ResultIR, recovery and ReportIR.

This is not arbitrary combination rewriting. Factor/reference replacement and term addition or
deletion remain separate bounded surfaces. Bulk permutation, nested or downstream-referenced
mutation, source-format writeback, visual editing, arbitrary solver selection, approved HIP C2,
engineering acceptance and C6 remain open.
