# ModelIR truss-section identity edit v1

`structural-workbench model-edit-truss-section-identity` is a bounded native edit surface that
replaces the stable identity of one existing, unreferenced ModelIR v2 parameter-set-v1 `truss_3d`
section. It changes no section property and publishes a new artifact directory without modifying
its source.

```text
structural-workbench model-edit-truss-section-identity MODEL.json \
  --section SOURCE-ID --new-section NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement must
satisfy the ModelIR stable-ID grammar, differ from the source, and be unique in the section
namespace. The command changes only `sections[].id`. It preserves the contiguous section index,
family, parameter-set version, finite positive SI area, `source_id`, extensions, and every
unrelated structural row.

## Reference closure, validation, and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. A missing source, duplicate or malformed replacement, no-op, noncontiguous index,
non-v1 family/version, malformed retained area/source/extension field, or source/replacement
identity referenced by any element `section_id`, an unsupported-feature row, or a round-trip
mapping fails closed. This v1 surface does not infer or cascade reference changes. The edited
canonical bytes are strictly reparsed and cross the same C++ validator before create-new
publication.

The root extension `structural-native:model-edit-truss-section-identity.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `truss_section_identity_edit`, both
section identities, the retained index/family/version/SI area/source identity/extensions, all
source and edited hashes, C++ verification, readiness, blockers, and the model artifact hash.
Unrelated explicit blockers remain visible and no solver or round-trip authority is promoted.

Installed CPU static/shared distribution E2E consumes the neutral `T2` created alongside a
referenced `T1` truss section and replaces it with `T2_RENAMED` without changing structural
meaning. The append-only v71 receipt binds the model, edit receipt, request receipt, request,
assembly receipt, checkpoint, ResultIR, recovery, and ReportIR. Typed recovery proves frame and
truss element types `[1,2]`, offsets `[0,12,15]`, active DOFs `[6,7,8,9,10,11]`, exact active
external load `[0,-10000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and fallback 0
with Python and Node lookup counts both zero.

## Claim boundary

This closes only stable-identity replacement for one unreferenced existing v1 truss section. It
does not cascade element, unsupported-feature, or round-trip references; edit area, family, or
version; create or delete sections; retarget properties; edit frame/composite or other entity
identities; select a solver; provide general visual editing or engineering acceptance; remove
React/TypeScript; prove approved HIP C2; or authorize C6.
