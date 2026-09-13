# RC compiler and immutable section type contracts

Implementation and fresh execution source:
`14745f1be` (full revision in the adjacent summary).
This closes the 24 diagnostics recorded for the preceding eight-module check;
it does not claim repository-wide typing, full hosted CI or physical validation.

## Changes

- Compiler failure raises are annotated `NoReturn`, so references checked before
  failure calls are narrowed on the surviving path. Steel/concrete locals carry
  their union explicitly, and each member retains its own section reference.
- The axial-curvature state/response protocols expose immutable data as read-only
  properties. Concrete section entry points accept an unknown state and keep the
  existing exact state-type, section identity and parent validation. Local casts
  follow those runtime checks; they are not substituted for validation.
- History options use a two-key `TypedDict`, retaining distinct displacement and
  material-history limit types and the existing optional keyword behavior.
- Heterogeneous serialized result/report dictionaries are annotated as JSON
  containers; split ownership keys and member-row containers have explicit types.
  Requested-analysis counts count true flags. History source indexing follows
  the existing validation and an explicit non-null assertion.
- Undirected member pairs are constructed as two-element tuples without changing
  their lexicographic ordering or duplicate checks.

No solver arithmetic, tolerances, learned weights, checkpoint format or release
permissions change. A mixed-section compiler regression checks both stored member
references; three foreign-state cases verify that the widened interface still
rejects invalid objects during integration and energy recovery.

## Verification

The earlier 24 diagnostics are gone. This command passes for all nine files:

```sh
MYPYPATH=src python3 -m mypy --follow-imports=silent \
  src/structural_analysis/materials/stateful_fiber_section.py \
  src/structural_analysis/elements/axial_curvature_section.py \
  src/structural_analysis/api/nonlinear_frame.py \
  src/structural_analysis/api/nonlinear_fiber_frame.py \
  src/structural_analysis/adapters/bounded_planar_model_ir.py \
  src/structural_analysis/model_ir/validation.py \
  src/structural_analysis/ai/fiber_frame_physical_identity.py \
  src/structural_analysis/ai/fiber_frame_candidate_learning.py \
  src/structural_analysis/benchmark/fiber_frame_design.py
```

A ten-module pytest selection passes 165 tests in 45.14 seconds, covering section
and beam state, material runtime instrumentation, stable stress, public RC API,
candidate learning, quantities/design, physical identity, intermediate layers and
ModelIR. A subsequent section/API selection with the four new cases passes 29 in
9.85 seconds. There are **169 distinct passing tests**, not 194. Ruff, formatting
and diff checks pass. Frontend code is unchanged and was not rerun for this slice.

## Fresh result comparison

Two new two-step public analyses use the same authored intermediate-layer
baseline and width-change models as the preceding actual comparison. Both return
ready and pass public result validation. Every result field matches the retained
pre-type-change report, including forces, section/fiber responses, convergence,
checkpoint identity and result hashes. Serializing old and new result objects
with identical sorted-JSON options also produces exactly equal bytes, including
signed-zero representations. No old checkpoint byte equality is claimed because
the prior comparison retained checkpoint identities in its result, not separate
checkpoint bytes.

These are two repeated authored model cases, not independent physical specimens.
Their measured API times are retained as observations without a speedup claim.
The source models/report are identified through their previous sealed packet;
no external source, training fit, release gate or reference tolerance is changed.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-typed-results-m2tmbg7j`.
Inventory SHA-256:
`605e3216d7006b5fd9616fab75b5c3d41f5fe06af4c913193324e87c94a4cfa4`;
8 files / 57,691 bytes excluding the inventory. The adjacent summary retains full
source revision, result hashes, exact byte comparison hashes and timing scopes.

Whole-roadmap acceptance, independent physical validation, full hosted CI and
learned net benefit remain open.
