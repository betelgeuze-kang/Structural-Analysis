# ModelIR linear-material identity edit v1

`structural-workbench model-edit-linear-material-identity` is a bounded native edit surface that
replaces the stable identity of one existing, unreferenced ModelIR v2 parameter-set-v1
`linear_elastic_isotropic` material. It changes no constitutive property and publishes a new
artifact directory without modifying its source.

```text
structural-workbench model-edit-linear-material-identity MODEL.json \
  --material SOURCE-ID --new-material NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement must
satisfy the ModelIR stable-ID grammar, differ from the source, and be unique in the material
namespace. The command changes only `materials[].id`. It preserves the contiguous material index,
law, parameter-set version, all three physical SI parameters, the complete stateless
trial/commit/rollback state schema, `source_id`, extensions, and every unrelated structural row.

## Reference closure, validation, and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. A missing source, duplicate or malformed replacement, no-op, noncontiguous index,
non-v1 law/version, malformed retained parameter/state/source/extension field, or source/replacement
identity referenced by an element `material_id`, a section `steel_material_id` or
`concrete_material_id`, an unsupported-feature row, or a round-trip mapping fails closed. This v1
surface does not infer or cascade reference changes. The edited canonical bytes are strictly
reparsed and cross the same C++ validator before create-new publication.

The root extension `structural-native:model-edit-linear-material-identity.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `linear_material_identity_edit`, both
material identities, the retained index/law/version/SI parameters/state schema/source identity/
extensions, all source and edited hashes, C++ verification, readiness, blockers, and the model
artifact hash. Unrelated explicit blockers remain visible and no solver or round-trip authority is
promoted.

Installed CPU static/shared distribution E2E consumes the neutral `M2` created by the existing
material-authoring surface and replaces it with `M2_RENAMED` without changing structural meaning.
The append-only v69 receipt binds the model, edit receipt, request receipt, request, assembly
receipt, checkpoint, ResultIR, recovery, and ReportIR. Typed recovery proves active DOFs
`[6,7,8,9,10,11]`, exact active external load `[0,-10000,0,0,0,0]`, byte-identical
initialized-checkpoint restart, and fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only stable-identity replacement for one unreferenced existing v1 linear-elastic
material. It does not cascade element, composite-section, unsupported-feature, or round-trip
references; edit parameters, laws, versions, or state; create or delete materials; retarget
properties; edit other entity identities; select a solver; provide general visual editing or
engineering acceptance; remove React/TypeScript; prove approved HIP C2; or authorize C6.
