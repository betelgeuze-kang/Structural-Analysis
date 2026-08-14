# ModelIR fixed-constraint DOF addition v1

`structural-workbench model-add-fixed-constraint-dof` is a bounded native edit surface that
appends one named restrained DOF and an explicit finite prescribed SI value to one existing
ModelIR v2 `fixed_dofs` constraint. It preserves the constraint identity and publishes a new
artifact directory without modifying its source.

```text
structural-workbench model-add-fixed-constraint-dof MODEL.json \
  --constraint CONSTRAINT-ID --dof UX|UY|UZ|RX|RY|RZ \
  --value SI-VALUE --output-dir EDITED-DIR
```

The option order is fixed and the constraint identity contains 1 through 128 UTF-8 bytes. The
command appends only the requested entry to `dofs` and inserts its explicit value in
`prescribed_values_si`. It preserves every existing DOF and prescribed value, their order,
constraint identity/index/type/target node, `source_id`, extensions, and unrelated rows.

## Validation and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. An invalid or already restrained DOF, non-finite value, missing constraint,
noncontiguous index, non-`fixed_dofs` type, malformed retained field, or same-node restrained-DOF
overlap fails closed. The edited canonical bytes are strictly reparsed and cross the same C++
validator before create-new publication.

The root extension `structural-native:model-add-fixed-constraint-dof.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `fixed_constraint_dof_add`, the constraint
identity/index/type/target, added DOF/value/unit, complete source and edited masks and prescribed
values, source identity and extensions, all source and edited hashes, C++ verification, readiness,
blockers, and the model artifact hash. A matching constraint round-trip row is conservatively
degraded to `approximated`; no round-trip or solver authority is promoted.

Installed CPU static/shared distribution E2E consumes the v63 constraint-DOF-deleted model,
restores `BC_N3/RZ=0`, and creates an exact model-bound CPU request. The append-only v64 receipt
binds the model, edit receipt, request receipt, request, assembly receipt, checkpoint, ResultIR,
recovery and ReportIR. Typed recovery proves active DOFs `[12,13,14,15,16,17]`, exact active
external load `[0,-1000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and fallback 0
with Python and Node lookup counts both zero.

## Claim boundary

This closes only one-DOF append to one existing `fixed_dofs` constraint. DOF deletion or
reordering, value-only editing, identity editing, constraint creation/deletion,
MPC/contact/support sets, general topology, solver or visual editing, engineering acceptance,
React/TypeScript removal, approved HIP C2, and C6 remain open.
