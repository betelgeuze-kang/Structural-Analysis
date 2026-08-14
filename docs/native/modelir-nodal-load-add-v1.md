# ModelIR linear nodal-load addition v1

`structural-workbench model-add-nodal-load` is a bounded native load-authoring surface. It appends
exactly one nonzero nodal load to one existing `linear_static` load pattern and targets one existing
node in a strict ModelIR v2 document. The source file is never modified.

```text
structural-workbench model-add-nodal-load MODEL.json \
  --load-pattern EXISTING-PATTERN-ID --load NEW-LOAD-ID \
  --node EXISTING-NODE-ID --components FX FY FZ MX MY MZ \
  --output-dir ADDED-LOAD-DIR
```

The option order and vocabulary are fixed. All six force/moment components are finite SI values and
at least one must be nonzero. The new load receives the next contiguous index within its pattern,
has neutral `source_id: null`, and cannot create or retarget a pattern or node. Its identity must be
unique across every load pattern.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before mutation. It rejects
missing patterns or nodes, duplicate load identities, non-`linear_static` patterns, all-zero or
non-finite components, and invalid source semantics. It records
`structural-native:model-add-nodal-load.v1`, retains complete upstream provenance, marks only a
matching exact/canonicalized load-pattern round-trip row as `approximated`, and rewrites direct
provenance to `structural-native-model-editor`.

The edited bytes are strictly reparsed and cross the C++ semantic validator again. Contiguous
indices, dangling references, duplicate IDs, invalid load domains, explicit blockers, and all other
ModelIR semantics therefore fail closed before create-new publication. A semantically valid source
with an explicit unsupported-feature blocker remains authorable, but the blocker and
`analysis_ready: false` remain visible.

The product composition test first creates one connected frame3d node/member, then adds an FY load
to its new node, creates an ABI v1.13 C++-assembly-preflighted request, and completes native CPU
linear execution. Typed recovery proves that the new global N3-UY active DOF carries the exact
`-1000 N` external load, changes the displacement field, and retains fallback 0.

Repeated additions from the same source and arguments produce byte-identical artifacts. CPU static
and shared installed-package E2E v24 repeats the complete composition under an empty `PATH`, proves
source nonmutation, C++ validation, exact active external load, request creation, native linear
execution, and binds the edited model, edit receipt, request, ResultIR, and recovery identities.
Earlier distribution receipts retain their narrower authority.

## Claim boundary

This closes one linear-static nodal-load addition to existing identities. Target-node replacement
is a separate bounded C5 surface. It does not create load patterns, nodes, members, properties,
constraints, combinations or stages; it does not delete or merge existing loads, select arbitrary analysis types/backends/solvers, provide visual
manipulation, infer engineering acceptance, prove protected HIP C2, replace React/TypeScript, or
authorize C6.
