# ModelIR element identity edit v1

`structural-workbench model-edit-element-identity` is a bounded native edit surface that replaces
the stable identity of one existing, unreferenced ModelIR v2 element. It changes no topology or
property reference and publishes a new artifact directory without modifying its source.

```text
structural-workbench model-edit-element-identity MODEL.json \
  --element SOURCE-ID --new-element NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement must
satisfy the ModelIR stable-ID grammar, differ from the source, and be unique in the element
namespace. The command changes only `elements[].id`. It preserves the contiguous element index and
the exact remaining typed row, including type, formulation, node IDs, material and section
references, orientation, offsets, releases, source identity, extensions, and family-specific
fields.

## Reference closure, validation, and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. A missing source, duplicate or malformed replacement, no-op, noncontiguous index,
malformed element row, or source/replacement identity referenced by construction-stage
`active_element_ids`, an unsupported-feature `source_entity_id`, or a direct round-trip
`model_ir_entity_id` fails closed. This v1 surface does not infer or cascade reference changes. The
edited canonical bytes are strictly reparsed and cross the same C++ validator before create-new
publication.

The root extension `structural-native:model-edit-element-identity.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `element_identity_edit`, both element
identities, the retained index and exact element row without its identity, all source and edited
hashes, C++ verification, readiness, blockers, and the model artifact hash. Unrelated explicit
blockers remain visible and no solver or round-trip authority is promoted.

Installed CPU static/shared distribution E2E replaces `E1` with `E1_RENAMED` and creates a
model-bound `LC_WEAK` request. The append-only v73 receipt binds the model, edit receipt, request
receipt, request, assembly receipt, checkpoint, ResultIR, recovery, and ReportIR. Typed recovery
proves frame element type `[1]`, offsets `[0,12]`, active DOFs `[6,7,8,9,10,11]`, exact active
external load `[0,-10000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and fallback 0
with Python and Node lookup counts both zero.

## Claim boundary

This closes only stable-identity replacement for one unreferenced existing element. It does not
cascade construction-stage, unsupported-feature, or round-trip references; edit connectivity,
properties, orientation, offsets, releases, or formulation; create or delete elements; select a
solver; provide general visual editing or engineering acceptance; remove React/TypeScript; prove
approved HIP C2; or authorize C6.
