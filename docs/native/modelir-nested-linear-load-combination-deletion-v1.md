# ModelIR bounded nested linear load-combination deletion v1

This C5 slice extends the installed linear-load-combination deletion command to one bounded nested
root without changing the frozen ABI v1.13 function table:

```text
structural-workbench model-delete-linear-load-combination MODEL.json \
  --load-combination COMBO_NESTED \
  --output-dir DELETED-NESTED-COMBINATION-MODEL
```

The requested candidate must be the last contiguous load-combination row, have null `source_id`,
empty entity extensions and `combination_type: linear`, and be unreferenced by another combination.
Its root contains two through 64 ordered, uniquely typed `load_pattern` or `load_combination` terms,
at least one of which is a combination reference. Every factor is finite and nonzero and every
reference already exists.

Deletion reuses the product's deterministic bounded expansion contract. The
root-inclusive combination depth is at most eight, at most 64 pattern-leaf contributions are
traversed, and the resolved case
contains two through 64 nonzero unique `linear_static` patterns. Missing or duplicate typed
references, cycles, excessive depth or expansion, non-finite propagation, cancellation below two
patterns, source/extension/feature/round-trip ownership, a referenced root, and nonterminal rows
fail closed before mutation. No row is cascaded or reindexed.

Rust preserves the source, publishes create-new canonical ModelIR, reparses it strictly and sends it
through the single C ABI for C++ reference and cycle validation. The extension
`structural-native:model-delete-nested-linear-load-combination.v3` records operation
`nested_linear_load_combination_delete` and deletion profile
`acyclic_nested_linear_static_depth_8_expanded_terms_64`. Its self-hashed receipt binds the exact
ordered root terms, expanded pattern terms, root depth, expanded term and pattern counts, maximum
bounds, source/edited content, semantic and provenance identities, and the C++ snapshot.

Compatibility is append-only. Exact-two direct deletion retains the frozen v1 extension and byte
set; three-through-64 direct deletion retains v2. Only a bounded root containing an explicit
`load_combination` term uses v3.

Focused Rust tests cover deterministic v3 deletion and retention of the referenced child
combination. Installed CPU static/shared distribution E2E v48 repeats deletion of `COMBO_NESTED`,
proves source nonmutation and identical output artifacts, retains `COMBO_SERVICE`, executes that
child through the native product with exact active external load `[0,-12000,5000,0,0,0]`, binds
edit/request/assembly/checkpoint/ResultIR/recovery/ReportIR identities, proves byte-identical direct
and resumed output, and requires fallback 0 with Python/Node lookup 0.

This slice does not claim deletion of a nested nonterminal or referenced row, cascading or
reindexing, general direct or nested term/reference editing beyond the separate bounded factor
editors, arbitrary graph rewriting, depth beyond eight, more than 64 leaf contributions,
self-weight, time functions, construction stages, shell/nonlinear combination execution,
engineering acceptance, approved HIP C2, or C6 decommission.
