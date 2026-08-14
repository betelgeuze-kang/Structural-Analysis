# Direct linear-load-combination term deletion v1

This bounded C5 surface removes one existing pattern term from a direct linear load combination:

```text
structural-workbench model-delete-linear-load-combination-term MODEL.json \
  --load-combination COMBO_SERVICE --load-pattern LC_STRONG --output-dir EDITED
```

The source combination must be neutral, extension-free, unreferenced and linear. It must contain
three through 64 ordered, unique terms that reference existing `linear_static` load patterns with
finite nonzero factors. The selected pattern must occur exactly once. The operation removes only
that term, permits any source position, retains the relative order and exact factors of every
remaining term, and yields two through 63 terms without changing the combination identity, index,
type or unrelated ModelIR rows.

Missing terms, two-term sources, nested or downstream-referenced combinations, source-owned or
extended combinations, malformed factors or references, unsupported-feature ownership and direct
round-trip ownership fail closed before publication. Source and edited bytes pass the strict Rust
ModelIR parser and the single C ABI into C++ semantic, reference and cycle validation. Publication
is create-new and atomic.

The edited model records
`structural-native:model-delete-direct-linear-load-combination-term.v1`. The extension and
self-hashed edit receipt use operation `direct_linear_load_combination_term_delete` and profile
`unique_direct_linear_static_patterns_2_to_63`. They bind the selected combination and pattern,
removed index and factor, source and edited term counts, complete source and edited term arrays,
source input/content/semantic/provenance identities, edited content/semantic/provenance identities,
C++ snapshot status and the bounded claim boundary.

Focused Rust library, CLI and product E2E tests prove middle-position removal, stable remaining
order, deterministic repeated output, immutable input, strict failure for missing and minimum-term
cases, exact CPU active load `[25000,-12000,0,0,0,0]`, fallback 0, and byte-identical direct and
checkpoint/restart results. Installed CPU static/shared distribution E2E extends the receipt with
append-only v54 hashes for the edited ModelIR, edit receipt, request receipt, analysis request,
assembly receipt, checkpoint, ResultIR, recovery and ReportIR.

This is not general combination editing. Factor/reference editing and append-only direct term
addition are separate bounded surfaces. Reordering, nested term insertion or removal,
downstream-referenced editing, source-owned writeback, general solver selection, visual editing,
approved HIP C2, engineering acceptance and C6 remain open.
