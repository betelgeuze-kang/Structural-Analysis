# ModelIR two-pattern linear load-combination addition v1

This bounded C5 Workbench slice creates one `linear` load combination from exactly two distinct
existing `linear_static` load patterns. The installed command is:

```text
structural-workbench model-add-linear-load-combination MODEL.json \
  --load-combination NEW-ID \
  --term PATTERN-A FACTOR-A --term PATTERN-B FACTOR-B \
  --output-dir ADDED-COMBINATION-MODEL
```

## Contract

Rust strictly reads a bounded regular ModelIR file. The new combination identity and both pattern
identities are UTF-8 strings containing 1-128 bytes. The combination identity must be new, both
referenced patterns must already exist and have `analysis_type: linear_static`, the pattern IDs
must differ, and both factors must be finite and nonzero.

The operation appends exactly one row with the next contiguous index, `combination_type: linear`,
two ordered `load_pattern` terms, null `source_id`, and empty entity extensions. It cannot author a
nested combination term, change an existing term, flatten factors into nodal loads, reindex rows,
or select a solver.

Both the source and edited model cross strict Rust parsing and the single C ABI into the C++ typed
ModelIR validator. The C++ reference/cycle checks therefore remain authoritative. The canonical
edited model carries `structural-native:model-add-linear-load-combination.v1`, exact upstream
content/semantic/provenance identities, and the ordered term set. Existing domain rows,
round-trip mappings, extensions, and explicit analysis blockers remain intact.

Publication is create-new and atomic. It emits `model-ir.json` plus a self-hashed
`structural-native-model-edit-receipt.v1` binding the combination identity/index/type, ordered
pattern terms and factors, source input hash, source and edited identities, C++ snapshot status,
analysis readiness, blockers, artifact hash, and claim boundary.

## Product execution

The same installed Workbench creates a bounded combination request with:

```text
structural-workbench model-create-linear-analysis-request MODEL.json \
  --case CASE-ID \
  --load-combination COMBINATION-ID \
  --max-iterations 100 \
  --absolute-residual-tolerance 1e-11 \
  --relative-residual-tolerance 1e-13 \
  --maximum-increment 0 \
  --output-dir REQUEST
```

The analysis request remains `structural-model-ir-linear-analysis-request.v1`. Its frozen selector
field is named `load_pattern_id`; for this bounded path it carries the unambiguous combination ID.
The separate self-hashed
`structural-native-model-linear-combination-request-create-receipt.v1` records
`load_selector_kind: load_combination`, the exact two ordered terms, and
`frozen_request_selector_field: load_pattern_id`. A pattern and combination with the same ID fail
closed.

C++ projects the validated combination alongside the load patterns, resolves the selector, and
accumulates each nodal component in declared term order using its signed FP64 factor. Exactly two
distinct direct `linear_static` pattern references with finite nonzero factors are accepted.
Nested terms, other term counts, duplicate references, missing selectors, nonzero self-weight,
scaling/accumulation overflow, time functions, stages, and unsupported features fail closed. The
existing stiffness, mass, internal force, JVP and recovery kernels remain shared with direct-pattern
execution; only the external load is linearly combined.

## Product evidence and execution boundary

Focused Rust E2E repeats the command byte-for-byte, proves source nonmutation and next-index
composition, and rejects duplicate combination IDs, missing patterns, repeated patterns,
zero/non-finite factors, invalid destinations, and invalid source semantics without partial
publication. An unrelated explicit blocker and round-trip mapping are preserved without readiness
promotion.

Installed CPU static/shared E2E v44 repeats the same creation under an empty `PATH`, validates the
edited artifact through the installed C++ boundary, renders the native topology view, creates the
combination-bound request, and executes `1.2 * LC_WEAK - 0.5 * LC_STRONG`. It proves the exact
active external load `[0, -12000, 5000, 0, 0, 0]`, typed frame recovery, CPU FP64, fallback 0, and
byte-identical direct/checkpoint/restart output. The append-only receipt binds the combination model
and edit receipt inherited from v42 plus the v44 request receipt, analysis request, assembly receipt,
checkpoint, ResultIR, recovery, and ReportIR identities. A missing combination selector still
fails without publication.

Nested combinations, arbitrary term counts, term editing, general solver selection, self-weight,
time functions, stages, shell/nonlinear combination execution, visual manipulation, engineering
acceptance, approved HIP C2, React/TypeScript removal, and C6 decommission remain open.
