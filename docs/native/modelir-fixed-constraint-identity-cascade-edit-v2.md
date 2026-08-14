# ModelIR fixed-constraint identity cascade edit v2

`structural-workbench model-edit-fixed-constraint-identity-cascade` is a bounded native edit
surface that replaces one referenced ModelIR v2 `fixed_dofs` constraint identity and atomically
updates its typed ownership. It publishes a new artifact directory and never modifies the source.

```text
structural-workbench model-edit-fixed-constraint-identity-cascade MODEL.json \
  --constraint SOURCE-ID --new-constraint NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement must
satisfy the ModelIR stable-ID grammar, differ from the source, and be unique in the constraint
namespace.

## Typed cascade and validation

The command changes exactly these typed locations:

- the selected `constraints[].id`;
- every `construction_stages[].active_constraint_ids[]` value matching the source;
- every direct `roundtrip_map[].model_ir_entity_id` whose `entity_kind` is `constraint` and whose
  identity matches the source.

An `exact` or `canonicalized` mapping becomes `approximated`; an `approximated` or `unsupported`
mapping retains its status. The constraint keeps its contiguous index, `fixed_dofs` type, target
node, complete ordered DOF mask, every explicit prescribed SI value and implicit-zero meaning,
`source_id`, extensions, and every unrelated row. At least one typed construction-stage or direct
constraint round-trip reference is required; an orphan constraint continues to use the v1
non-cascading editor.

Rust strictly parses the source, then the model crosses the single C ABI into C++ semantic and
reference validation before mutation. The edited canonical bytes are reparsed and cross the same
C++ validator before create-new publication. Missing, colliding, malformed, no-op, or unreferenced
identities fail closed. Index or retained-field drift, non-`fixed_dofs` rows, malformed stage or
mapping rows, wrong-kind direct mappings, replacement ownership, unsupported-feature
`source_entity_id` ownership of either identity, and invalid source or edited semantics also fail
closed. Untyped extension references and unsupported-feature ownership are never inferred or
cascaded.

The root extension `structural-native:model-edit-fixed-constraint-identity-cascade.v2` and
self-hashed edit receipt bind operation `fixed_constraint_identity_cascade_edit`, both identities,
the retained index/type/node/DOFs/prescribed values/source identity/extensions,
construction-stage and mapping reference counts, source and edited hashes, C++ verification,
readiness, blockers, and model artifact hash.

Focused E2E separately proves a construction-stage reference is rewritten and C++-revalidated.
Installed CPU static/shared distribution E2E consumes the normalized MGT cantilever ModelIR, whose
direct constraint mapping is source-owned, and cascades `C_1` to `C1_LINKED`. The append-only v83
receipt binds model, edit/request/assembly receipts, request, checkpoint, ResultIR, recovery, and
ReportIR. Typed recovery proves frame element type `[1]`, offsets `[0,12]`, active DOFs
`[6,7,8,9,10,11]`, exact active load `[200000,0,0,0,0,0]`, byte-identical initialized restart, and
fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only one bounded referenced fixed-constraint identity cascade. Construction stages
remain outside the current linear execution projection. The command does not cascade untyped
extensions or unsupported features; edit constraint target, value, or DOF mask; create or delete
constraints; author MPC/contact/support sets; select a general solver; provide visual editing or
engineering acceptance; remove React/TypeScript; prove approved HIP C2; or authorize C6.
