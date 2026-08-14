# ModelIR typed node-identity cascade v2

Status: C5 product slice. This does not authorize C6.

`structural-workbench model-edit-node-identity-cascade MODEL.json --node SOURCE-ID
--new-node NEW-ID --output-dir DIR` replaces one referenced node identity and publishes a new
canonical `model-ir.json` plus a self-hashed `edit-receipt.json`. The original input and an existing
destination are never overwritten.

## Closed mutation boundary

Rust requires distinct source and replacement IDs that satisfy the ModelIR stable-ID grammar. The
source node must exist, the replacement node must not exist, and the source must have at least one
typed element, constraint, or nodal-load reference. The operation changes only:

- the selected `nodes[].id`;
- matching `elements[].node_ids` entries;
- matching `constraints[].node_id` entries;
- matching `load_patterns[].nodal_loads[].node_id` entries; and
- direct node `roundtrip_map[].model_ir_entity_id` entries.

An exact or canonicalized direct mapping is conservatively degraded to `approximated`; an already
approximated or unsupported status is retained. The selected node's contiguous index, finite SI
coordinates, source identity and extensions are retained exactly. Unrelated domain rows and
round-trip rows remain byte-canonically unchanged before the editor binds provenance under
`structural-native:model-edit-node-identity-cascade.v2` with operation
`node_identity_cascade_edit`.

The operation rejects missing, colliding, malformed, no-op, or unreferenced IDs; index or retained-
field drift; unsupported-feature ownership of the source or replacement ID; malformed or wrong-kind
direct mappings; and invalid source or edited semantics. It does not scan or rewrite untyped
extension payloads. Orphan identities remain the responsibility of `model-edit-node-identity`.

## Validation and execution authority

Both source and edited bytes pass strict Rust parsing and the single C ABI into C++ semantic and
reference validation. Publication occurs only after the C++ canonical snapshot succeeds. The
receipt binds input, semantic, provenance and edited hashes, all four typed-reference counts, the
retained node fields, the edited artifact and the claim boundary.

Focused E2E replaces `N2` with `N2_LINKED`, including one element reference, four nodal-load
references and one direct node mapping, then creates a model-bound `LC_WEAK` CPU request. It proves
active DOFs `[6,7,8,9,10,11]`, active load `[0,-10000,0,0,0,0]`, frame recovery type `[1]`, offsets
`[0,12]`, fallback 0, and byte-identical initialized-checkpoint restart.

Installed static/shared distribution E2E repeats the same bounded surface from verified packages
on the v75 model, retains root model identity and `COMBO_RENAMED`, proves combined active load
`[25000,-12000,5000,0,0,0]`, and emits an append-only v76 receipt binding the edited ModelIR,
edit/request/assembly receipts, analysis request, checkpoint, ResultIR, recovery and ReportIR.
Python and Node executable lookup remain zero on that path.

This slice does not claim untyped-extension cascade, unsupported-feature cascade, arbitrary
reference families, coordinate/topology/property/load-content editing, engineering acceptance,
approved HIP C2, or complete native Workbench replacement. It cannot authorize C6.
