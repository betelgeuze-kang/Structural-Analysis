# ModelIR bounded nested linear load combinations v1

This C5 slice moves bounded acyclic nested linear-load-combination authoring and CPU execution into
the native product. It does not change the frozen ABI v1.13 function table. The installed authoring
command is:

```text
structural-workbench model-add-nested-linear-load-combination MODEL.json \
  --load-combination COMBO_NESTED \
  --combination-term COMBO_BASE 0.5 \
  --pattern-term LC_AXIAL 0.25 \
  --output-dir EDITED
```

The root contains two through 64 ordered, finite, nonzero terms and at least one explicit
`load_combination` reference. Every referenced combination and pattern already exists; patterns are
`linear_static`. New identity, typed-reference duplication, missing references, self-reference,
invalid factors and source semantic failures fail before publication. Rust publishes create-new
canonical ModelIR and a self-hashed edit receipt, never mutating the source.

Flattening is deterministic and bounded:

- root-inclusive combination depth is at most eight;
- every visited combination contains two through 64 terms;
- at most 64 pattern-leaf contributions are traversed;
- patterns retain first declaration encounter order;
- repeated paths accumulate factors in traversal order;
- exact zero factors after accumulation are removed; and
- the resolved case contains two through 64 nonzero unique patterns.

Depth nine, a sixty-fifth leaf contribution, non-finite propagation or accumulation, a cycle, and
cancellation below two patterns fail closed. The strict ModelIR validator already rejects dangling
references and cycles; both Rust preflight and C++ assembly nevertheless enforce the product bounds.

The authoring provenance extension is
`structural-native:model-add-nested-linear-load-combination.v3`. It binds root terms, resolved
pattern terms, depth, expanded leaf count, source content/semantic/provenance identities and the
claim boundary. Request creation emits
`structural-native-model-linear-nested-combination-request-create-receipt.v3`, while the frozen
request field `load_pattern_id` remains the explicit combination selector alias. Existing exact-two
v1 and direct v2 authoring/request receipts remain unchanged.

C++ uses the same frame/truss constitutive, assembly, JVP and recovery sources as direct patterns.
`SA_MODEL_IR_LINEAR_MAX_NESTED_COMBINATION_DEPTH` is eight and
`SA_MODEL_IR_LINEAR_MAX_EXPANDED_COMBINATION_TERMS` is 64. The caller-owned ABI outputs, immutable
handle contract, CPU execution backend and fallback counter are unchanged.

Focused C++ unit/ABI tests cover deterministic flattening, repeated-pattern consolidation, depth
and expansion rejection. Rust tests cover authoring, v3 receipt binding, cancellation, request
preflight, CLI execution and checkpoint/restart. The independent NumPy C1 oracle covers the nested
external load and equilibrium residual.

Installed CPU static/shared distribution E2E v46 authors `COMBO_BASE`, then
`0.5*COMBO_BASE + 0.25*LC_AXIAL`, verifies the exact active external load
`[25000,-6000,2500,0,0,0]`, binds edit/request/assembly/checkpoint/ResultIR/recovery/ReportIR hashes,
proves byte-identical direct and resumed output, and requires fallback 0 with Python/Node lookup 0.

This slice does not claim nested deletion or term editing, depth beyond eight, more than 64 leaf
contributions, self-weight, time functions, construction stages, shell/nonlinear combination
execution, general solver selection, visual manipulation, engineering acceptance, approved HIP C2,
or C6 decommission.
