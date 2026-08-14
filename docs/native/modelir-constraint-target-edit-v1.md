# ModelIR fixed-constraint target edit v1

`structural-workbench model-edit-constraint-target` is a bounded native edit surface that moves one
existing ModelIR v2 `fixed_dofs` constraint from its current node to a distinct existing node. It
preserves the constraint identity and publishes a new artifact directory without modifying its
source.

```text
structural-workbench model-edit-constraint-target MODEL.json \
  --constraint CONSTRAINT-ID --node NEW-TARGET-NODE-ID \
  --output-dir EDITED-DIR
```

The option order is fixed and each identity contains 1 through 128 UTF-8 bytes. The command changes
only the selected constraint's `node_id`. Its index, type, restrained DOF mask, finite prescribed SI
values, `source_id`, extensions, and unrelated ModelIR rows are retained exactly.

## Validation and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. Missing constraint or replacement-node identities, a same-node no-op,
noncontiguous indices, a non-`fixed_dofs` type, malformed retained fields, or any restrained-DOF
overlap at the replacement node fail closed. The edited canonical bytes are strictly reparsed and
cross the same C++ validator, which closes all remaining duplicate-constraint and reference cases,
before create-new publication.

The root extension `structural-native:model-edit-constraint-target.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `constraint_target`, both node identities,
the constraint identity and index, retained type, DOFs, prescribed values, source identity and
extensions, all source and edited hashes, C++ verification, readiness, blockers, and the model
artifact hash. A matching constraint round-trip row is conservatively degraded to `approximated`;
no round-trip or solver authority is promoted.

Installed CPU static/shared distribution E2E composes a connected N3 frame member, an N3 nodal
load, and a homogeneous N3 fixed constraint, then retargets that constraint to N2 and creates an
exact model-bound CPU request. The append-only v62 receipt binds the model, edit receipt, request
receipt, request, assembly receipt, checkpoint, ResultIR, recovery and ReportIR. Typed recovery
proves active DOFs `[12,13,14,15,16,17]`, exact active external load
`[0,-1000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and fallback 0 with Python and
Node lookup counts both zero.

## Claim boundary

This closes only target-node replacement for one existing `fixed_dofs` constraint. Prescribed-value
editing and homogeneous constraint creation/deletion are separate bounded C5 surfaces. DOF-mask or
identity editing, MPC/contact/support sets, general topology, solver or visual editing, engineering
acceptance, React/TypeScript removal, approved HIP C2, and C6 remain open.
