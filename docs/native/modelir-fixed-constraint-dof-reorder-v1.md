# ModelIR fixed-constraint DOF reorder v1

`structural-workbench model-reorder-fixed-constraint-dof` is a bounded native edit surface that
moves one named restrained DOF to a distinct final position inside one existing ModelIR v2
`fixed_dofs` constraint. It preserves the complete restraint membership and publishes a new
artifact directory without modifying its source.

```text
structural-workbench model-reorder-fixed-constraint-dof MODEL.json \
  --constraint CONSTRAINT-ID --dof UX|UY|UZ|RX|RY|RZ \
  --to-index 0..5 --output-dir EDITED-DIR
```

The option order is fixed and the constraint identity contains 1 through 128 UTF-8 bytes. The
requested index must be inside both the closed six-DOF domain and the source constraint's actual
mask. The command moves only the requested `dofs` entry; it preserves constraint identity,
contiguous index, type, target node, complete DOF membership, every explicit prescribed SI value
and implicit-zero meaning, `source_id`, extensions, and unrelated rows.

## Validation and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. An invalid or unrestrained DOF, missing constraint, noncontiguous index,
non-`fixed_dofs` type, malformed retained field, target index outside the source mask, or no-op move
fails closed. The edited canonical bytes are strictly reparsed and cross the same C++ validator
before create-new publication.

The root extension `structural-native:model-reorder-fixed-constraint-dof.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `fixed_constraint_dof_reorder`, the
constraint identity/index/type/target, moved DOF/value/unit and explicitness, source and target
indices, complete source and edited order, retained prescribed values, source identity and
extensions, all source and edited hashes, C++ verification, readiness, blockers, and the model
artifact hash. A matching constraint round-trip row is conservatively degraded to `approximated`;
no round-trip or solver authority is promoted.

Installed CPU static/shared distribution E2E consumes the v64 constraint-DOF-added model and moves
`BC_N3/RZ` from index 5 to index 0 without changing structural meaning. The append-only v65 receipt
binds the model, edit receipt, request receipt, request, assembly receipt, checkpoint, ResultIR,
recovery and ReportIR. Typed recovery proves active DOFs `[12,13,14,15,16,17]`, exact active
external load `[0,-1000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and fallback 0
with Python and Node lookup counts both zero.

## Claim boundary

This closes only order-only movement of one restrained DOF inside one existing `fixed_dofs`
constraint. DOF addition/deletion and value-only editing remain separate surfaces. Constraint
identity editing, constraint creation/deletion, MPC/contact/support sets, general topology, solver
or visual editing, engineering acceptance, React/TypeScript removal, and approved HIP C2 remain
open; C6 remain open.
