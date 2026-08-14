# ModelIR typed linear-material identity cascade v2

Status: C5 product slice. This does not authorize C6.

`structural-workbench model-edit-linear-material-identity-cascade MODEL.json --material SOURCE-ID
--new-material NEW-ID --output-dir DIR` replaces one referenced v1 `linear_elastic_isotropic`
material identity and publishes a new canonical `model-ir.json` plus a self-hashed
`edit-receipt.json`. The original input and an existing destination are never overwritten.

## Closed mutation boundary

Rust requires distinct source and replacement IDs that satisfy the ModelIR stable-ID grammar. The
source material must exist, use `law_id=linear_elastic_isotropic` and
`parameter_set_version=1`, retain the exact three finite physical SI parameters and stateless v1
trial/commit/rollback schema, and have at least one typed element reference. The replacement
material must not exist. The operation changes only:

- the selected `materials[].id`;
- matching `elements[].material_id` entries; and
- direct material `roundtrip_map[].model_ir_entity_id` entries.

An exact or canonicalized direct mapping is conservatively degraded to `approximated`; an already
approximated or unsupported status is retained. The selected material's contiguous index, law,
version, parameter object, state schema, source identity and extensions are retained exactly.
Unrelated domain and round-trip rows remain byte-canonically unchanged before the editor binds
provenance under `structural-native:model-edit-linear-material-identity-cascade.v2` with operation
`linear_material_identity_cascade_edit`.

The operation rejects missing, colliding, malformed, no-op, or unreferenced IDs; index or retained-
field drift; `steel_material_id` or `concrete_material_id` section ownership; unsupported-feature
ownership of the source or replacement ID; malformed or wrong-kind direct mappings; unsupported
material laws; and invalid source or edited semantics. It does not scan or rewrite untyped
extension payloads. Unreferenced linear-material identities remain the responsibility of
`model-edit-linear-material-identity`.

## Validation and execution authority

Both source and edited bytes pass strict Rust parsing and the single C ABI into C++ semantic and
reference validation. Publication occurs only after the C++ canonical snapshot succeeds. The
receipt binds input, semantic, provenance and edited hashes, the element and round-trip reference
counts, retained material fields, edited artifact and claim boundary.

Focused E2E replaces `M1` with `M1_LINKED`, including one element reference and one direct material
mapping, then creates a model-bound `LC_WEAK` CPU request. It proves active DOFs
`[6,7,8,9,10,11]`, active load `[0,-10000,0,0,0,0]`, frame recovery type `[1]`, offsets `[0,12]`,
fallback 0, and byte-identical initialized-checkpoint restart.

Installed static/shared distribution E2E repeats the same bounded surface from verified packages
on the v77 model, retains root model identity, `N2_LINKED`, `S1_LINKED` and `COMBO_RENAMED`, proves
combined active load `[25000,-12000,5000,0,0,0]`, and emits an append-only v78 receipt binding the
edited ModelIR, edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery
and ReportIR. Python and Node executable lookup remain zero on that path.

This slice does not claim nonlinear section-material reference cascade, untyped-extension cascade,
unsupported-feature cascade, non-linear-elastic material laws, parameter/law/state editing,
material creation/deletion, general property retargeting, engineering acceptance, approved HIP C2,
or complete native Workbench replacement. It cannot authorize C6.
