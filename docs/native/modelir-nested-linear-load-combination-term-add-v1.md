# Nested linear-load-combination root-term addition v1

This bounded C5 Workbench slice appends one typed term to an existing nested linear load
combination. The installed command is:

```text
structural-workbench model-add-nested-linear-load-combination-term MODEL.json \
  --load-combination ID --ref-kind load_pattern|load_combination \
  --ref-id NEW-ID --factor NONZERO-F64 --output-dir DIR
```

The selected root must be source-neutral, extension-free, unreferenced by another combination and
genuinely nested. Its source contains two through 63 ordered terms with unique typed references,
finite nonzero factors and at least one `load_combination` reference. The new typed reference must
exist, be compatible (`linear_static` for a pattern and `linear` for a combination), and not already
occur in the root. The editor appends it at the final root index, yielding three through 64 terms
while preserving root identity, contiguous index and type, every existing root reference, factor
and order, every descendant combination, and every unrelated ModelIR row.

Before and after the append, deterministic resolution requires an acyclic graph with
root-inclusive depth at most eight, no more than 64 expanded leaf contributions, and two through
64 nonzero unique `linear_static` patterns after consolidation. Duplicate, missing or incompatible
new references,
direct or downstream-referenced roots, source or extension ownership, unsupported-feature or
round-trip ownership, cycles, depth or expansion overflow, cancellation outside the resolved
pattern bound, malformed factors and a 64-term source fail closed before publication.

Rust strictly parses and canonicalizes source and edited models. Both snapshots cross the single C ABI into C++ semantic, reference and cycle validation. Output uses create-new publication and
contains canonical self-hashed `model-ir.json` and `edit-receipt.json`; an existing destination is
never overwritten.

The edited model carries
`structural-native:model-add-nested-linear-load-combination-term.v1`. Its operation is
`nested_linear_load_combination_term_add` and its editing profile is
`acyclic_nested_linear_static_depth_8_expanded_terms_64`. Provenance and the receipt bind the typed
new reference, factor and append index, source and edited root-term counts and arrays, both complete
bounded expansion summaries, source input SHA-256, all source and edited ModelIR identities, C++
snapshot status and the create-new artifact identity.

Focused Rust tests prove append-only order and descendant preservation, every closed rejection
boundary, deterministic publication, source immutability, strict C++ revalidation, exact CPU
execution, fallback 0 and byte-identical direct versus real-checkpoint resume. Installed CPU
static/shared distribution E2E starts with
`COMBO_NESTED = 0.5 COMBO_SERVICE + 0.25 LC_AXIAL`; its resolved terms are
`0.6 LC_WEAK - 0.25 LC_STRONG + 0.25 LC_AXIAL`. The E2E appends explicit `0.1 LC_STRONG`.
Consolidation yields `-0.15 LC_STRONG`; execution proves exact active load
`[25000,-6000,1500,0,0,0]` with an empty executable lookup path. The append-only v55 receipt binds
the edited ModelIR, edit receipt, request receipt, analysis request, assembly receipt, checkpoint,
ResultIR, recovery and ReportIR.

This is not general nested combination editing. Root factor and reference replacement, bounded
explicit-position root-term insertion, root-term removal and root-term reorder are separate
surfaces. Bulk insertion or permutation, descendant or downstream-referenced mutation,
source-format writeback, visual editing, arbitrary solver selection, approved HIP C2, engineering
acceptance and C6 remain open.
