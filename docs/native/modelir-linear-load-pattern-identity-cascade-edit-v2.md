# ModelIR typed linear-load-pattern identity cascade v2

Status: C5 product slice. This does not authorize C6.

`structural-workbench model-edit-linear-load-pattern-identity-cascade MODEL.json --load-pattern
SOURCE-ID --new-load-pattern NEW-ID --output-dir DIR` replaces one referenced `linear_static`
load-pattern identity and publishes a new canonical `model-ir.json` plus a self-hashed
`edit-receipt.json`. The original input and an existing destination are never overwritten.

## Closed mutation boundary

Rust requires distinct source and replacement IDs that satisfy the ModelIR stable-ID grammar. The
source pattern must exist, have a contiguous index, use `analysis_type=linear_static`, retain a
complete finite self-weight vector, ordered nodal loads and optional ordered member-distributed
loads, and have at least one typed load-combination or construction-stage reference. The
replacement pattern must not exist. The operation
changes only:

- the selected `load_patterns[].id`;
- matching `load_combinations[].terms[]` entries with `ref_kind=load_pattern`;
- matching `construction_stages[].load_pattern_ids[]` entries; and
- direct load-pattern `roundtrip_map[].model_ir_entity_id` entries.

An exact or canonicalized direct mapping is conservatively degraded to `approximated`; an already
approximated or unsupported status is retained. The selected pattern's index, analysis type,
self-weight, complete nodal and member-distributed loads, source identity and extensions remain exact. Unrelated domain and
round-trip rows remain byte-canonically unchanged before provenance is bound under
`structural-native:model-edit-linear-load-pattern-identity-cascade.v2` with operation
`linear_load_pattern_identity_cascade_edit`.

The operation rejects missing, colliding, malformed, no-op or unreferenced IDs; index or retained-
field drift; unsupported-feature ownership of the source or replacement ID; malformed, replacement-
owned or wrong-kind typed references; non-linear patterns; and invalid source or edited semantics.
It does not scan or rewrite untyped extension payloads. Unreferenced pattern identities remain the
responsibility of `model-edit-linear-load-pattern-identity`.

## Validation and execution authority

Both source and edited bytes pass strict Rust parsing and the single C ABI into C++ semantic and
reference validation. Publication occurs only after the C++ canonical snapshot succeeds. The
receipt binds input, semantic, provenance and edited hashes, load-combination, construction-stage
and round-trip reference counts, retained pattern fields, the edited artifact and claim boundary.

Focused E2E replaces `LC_WEAK` with `LC_WEAK_LINKED` in a direct combination and mapping, then
proves active DOFs `[6,7,8,9,10,11]`, combined active load `[25000,-10000,0,0,0,0]`, native CPU
FP64, fallback 0 and byte-identical initialized-checkpoint restart. A separate stage-bearing fixture
proves the construction-stage cascade and C++ semantic round-trip; the linear reference runtime
intentionally does not execute models that retain construction stages.

Installed static/shared distribution E2E starts from the v79 edited model and replaces `LC_WEAK`
with `LC_WEAK_LINKED` through retained `COMBO_RENAMED`. It retains the root model
identity, `N2_LINKED`, `S1_LINKED`, `M1_LINKED` and `T1_LINKED`, proves frame-plus-truss recovery
types `[1,2]`, offsets `[0,12,15]`, active DOFs `[6,7,8,9,10,11]`, combined active load
`[25000,-12000,5000,0,0,0]`, and emits an append-only v80 receipt binding the edited ModelIR,
edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
Python and Node executable lookup remain zero on that path.

This slice does not claim untyped-extension cascade, unsupported-feature cascade, nonlinear pattern
editing, pattern content editing, general solver selection, visual manipulation, engineering
acceptance, approved HIP C2, or complete native Workbench replacement. It cannot authorize C6.
