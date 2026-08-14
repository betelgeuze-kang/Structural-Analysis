# ModelIR fixed-constraint identity edit v1

`structural-workbench model-edit-fixed-constraint-identity` is a bounded native edit surface that
replaces the stable identity of one existing, unreferenced ModelIR v2 `fixed_dofs` constraint. It
changes no structural property and publishes a new artifact directory without modifying its
source.

```text
structural-workbench model-edit-fixed-constraint-identity MODEL.json \
  --constraint SOURCE-ID --new-constraint NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes, and the replacement
must satisfy the ModelIR stable-ID grammar, differ from the source, and be unique in the constraint
namespace. The command changes only `constraints[].id`. It preserves the contiguous index, type,
target node, complete ordered DOF mask, every explicit prescribed SI value and implicit-zero
meaning, `source_id`, extensions, and all unrelated rows.

## Reference closure, validation, and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. A missing source, duplicate or malformed replacement, no-op, noncontiguous index,
non-`fixed_dofs` type, malformed retained field, or source/replacement identity owned by a
construction stage, unsupported-feature row, or round-trip mapping fails closed. This v1 surface
does not infer or cascade reference changes. The edited canonical bytes are strictly reparsed and
cross the same C++ validator before create-new publication.

The root extension `structural-native:model-edit-fixed-constraint-identity.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `fixed_constraint_identity_edit`, both
constraint identities, the retained index/type/node/DOFs/prescribed values/source identity and
extensions, all source and edited hashes, C++ verification, readiness, blockers, and the model
artifact hash. Unrelated explicit blockers remain visible and no round-trip or solver authority is
promoted.

Installed CPU static/shared distribution E2E consumes the v65 constraint-DOF-reordered model and
replaces `BC_N3` with `BC_N3_RENAMED` without changing structural meaning. The append-only v66
receipt binds the model, edit receipt, request receipt, request, assembly receipt, checkpoint,
ResultIR, recovery, and ReportIR. Typed recovery proves active DOFs `[12,13,14,15,16,17]`, exact
active external load `[0,-1000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and
fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only identity replacement for one unreferenced existing `fixed_dofs` constraint. It
does not cascade construction-stage, unsupported-feature, or round-trip references; edit other
top-level entity identities beyond the separate bounded linear-load-pattern and linear-material surfaces; change
target/value/mask/topology; create or delete constraints; author MPC/contact/support sets; select a
solver; provide general visual editing or engineering acceptance; remove React/TypeScript; prove
approved HIP C2; or authorize C6.
