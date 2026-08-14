# ModelIR bounded direct linear load combinations v1

This C5 slice extends the native linear-load-combination path from the frozen exact-two profile to
two through 64 ordered terms. Every term must reference a unique existing `linear_static` load
pattern and must carry a finite, nonzero signed factor. References to another combination, repeated
patterns, one term, more than 64 terms, self-weight and non-linear patterns fail closed.

## Compatibility boundary

The exact-two path remains byte-contract compatible with the earlier slice:

- the edited model keeps `structural-native:model-add-linear-load-combination.v1`;
- the edit receipt keeps operation `linear_load_combination_add`;
- the request receipt keeps
  `structural-native-model-linear-combination-request-create-receipt.v1`; and
- the frozen request field remains `load_pattern_id`, interpreted only as an unambiguous load-case
  selector.

Three through 64 terms use the explicit
`structural-native:model-add-direct-linear-load-combination.v2` provenance extension and the
`structural-native-model-linear-direct-combination-request-create-receipt.v2` request receipt.
Both record the bounded direct-pattern profile and exact term count. No slot or structure was added
to the frozen ABI v1.13 function table.

## Native execution authority

Rust strictly parses, authors, canonicalizes and self-hashes the ModelIR and receipts. The model is
then revalidated through the single C ABI by C++, which checks the selected combination and
deterministically accumulates every direct pattern into the canonical CPU assembly. ResultIR,
typed recovery, ReportIR and checkpoint/restart all consume that same assembly.

The focused three-pattern fixture uses:

```text
0.25 * LC_AXIAL + 1.2 * LC_WEAK - 0.5 * LC_STRONG
```

Its active external-load vector is exactly `[25000,-12000,5000,0,0,0]` and native CPU execution
reports fallback 0. Direct and resumed terminal artifacts are byte-identical.

Installed CPU static/shared distribution E2E v45 repeats the authoring, v2 request preflight,
assembly, initialized checkpoint, resume and terminal report path under an empty `PATH`. The
append-only receipt binds the edited ModelIR, edit receipt, request receipt, analysis request,
assembly receipt, checkpoint, ResultIR, recovery and ReportIR hashes. Frozen v1 through v44
distribution receipts retain their narrower authority.

One existing direct factor can be changed only through the separately bounded v49 surface in
`docs/native/modelir-direct-linear-load-combination-factor-edit-v1.md`. One existing direct pattern
reference can be replaced, with its factor/order/count preserved, only through the separately
bounded v51 surface in
`docs/native/modelir-direct-linear-load-combination-reference-edit-v1.md`. One unique new direct
pattern term can be appended only through the separately bounded v53 surface in
`docs/native/modelir-direct-linear-load-combination-term-add-v1.md`. Term removal and reorder are
separate bounded surfaces; general
arbitrary-position or nested insertion, nested reference replacement, self-weight, time functions,
construction stages, shell/nonlinear combination execution, nested/general deletion,
approved-device HIP C2, engineering acceptance and C6 remain open.
