# ModelIR fixed-constraint DOF deletion v1

`structural-workbench model-delete-fixed-constraint-dof` is a bounded native edit surface that
removes one named restrained DOF from one existing ModelIR v2 `fixed_dofs` constraint. It preserves
the constraint identity and publishes a new artifact directory without modifying its source.

```text
structural-workbench model-delete-fixed-constraint-dof MODEL.json \
  --constraint CONSTRAINT-ID --dof UX|UY|UZ|RX|RY|RZ \
  --output-dir EDITED-DIR
```

The option order is fixed and the constraint identity contains 1 through 128 UTF-8 bytes. The
command removes only the requested entry from `dofs` and, when present, the matching entry from
`prescribed_values_si`. It retains at least one restrained DOF and preserves the remaining order
and values, constraint identity/index/type/target node, `source_id`, extensions, and unrelated rows.

## Validation and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. An invalid or unrestrained DOF, missing constraint, noncontiguous index,
non-`fixed_dofs` type, malformed retained fields, or deletion of the final restrained DOF fails
closed. The edited canonical bytes are strictly reparsed and cross the same C++ validator before
create-new publication.

The root extension `structural-native:model-delete-fixed-constraint-dof.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `fixed_constraint_dof_delete`, the
constraint identity/index/type/target, removed DOF, whether its prescribed value was explicit, its
effective SI value, all retained DOFs and prescribed values, source identity and extensions, all
source and edited hashes, C++ verification, readiness, blockers, and the model artifact hash. A
matching constraint round-trip row is conservatively degraded to `approximated`; no round-trip or
solver authority is promoted.

Installed CPU static/shared distribution E2E consumes the v62 constraint-target-edited model,
removes `BC_N3/RZ`, and creates an exact model-bound CPU request. The append-only v63 receipt binds
the model, edit receipt, request receipt, request, assembly receipt, checkpoint, ResultIR, recovery
and ReportIR. Typed recovery proves active DOFs `[11,12,13,14,15,16,17]`, exact active external load
`[0,0,-1000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and fallback 0 with Python and
Node lookup counts both zero.

## Claim boundary

This closes only one-DOF deletion from one existing `fixed_dofs` constraint. DOF addition or
reordering, value-only editing, identity editing, constraint creation/deletion, MPC/contact/support
sets, general topology, solver or visual editing, engineering acceptance, React/TypeScript removal,
approved HIP C2, and C6 remain open.
