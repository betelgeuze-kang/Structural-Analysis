# ModelIR node identity edit v1

`structural-workbench model-edit-node-identity` is a bounded native edit surface that replaces the
stable identity of one existing, unreferenced ModelIR v2 node. It changes no coordinate or topology
and publishes a new artifact directory without modifying its source.

```text
structural-workbench model-edit-node-identity MODEL.json \
  --node SOURCE-ID --new-node NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement must
satisfy the ModelIR stable-ID grammar, differ from the source, and be unique in the node namespace.
The command changes only `nodes[].id`. It preserves the contiguous node index, exact finite SI
coordinates, `source_id`, extensions, and every unrelated structural row.

## Reference closure, validation, and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. A missing source, duplicate or malformed replacement, no-op, noncontiguous index,
malformed retained coordinate/source/extension field, or source/replacement identity referenced by
any element `node_ids`, constraint `node_id`, nodal-load `node_id`, unsupported-feature row, or
round-trip mapping fails closed. This v1 surface does not infer or cascade reference changes. The
edited canonical bytes are strictly reparsed and cross the same C++ validator before create-new
publication.

The root extension `structural-native:model-edit-node-identity.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `node_identity_edit`, both node identities,
the retained index/coordinates/source identity/extensions, all source and edited hashes, C++
verification, readiness, blockers, and the model artifact hash. Unrelated explicit blockers remain
visible and no solver or round-trip authority is promoted.

Installed CPU static/shared distribution E2E creates neutral unreferenced `N3`, replaces it with
`N3_RENAMED`, then composes a homogeneous six-DOF support on the renamed node. The append-only v72
receipt binds the model, edit receipt, request receipt, request, assembly receipt, checkpoint,
ResultIR, recovery, and ReportIR. Typed recovery proves frame element type `[1]`, offsets `[0,12]`,
active DOFs `[6,7,8,9,10,11]`, exact active external load `[0,-10000,0,0,0,0]`, byte-identical
initialized-checkpoint restart, and fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only stable-identity replacement for one unreferenced existing node. It does not
cascade element, constraint, nodal-load, unsupported-feature, or round-trip references; edit
coordinates; create or delete nodes; retarget topology, loads, or supports; select a solver;
provide general visual editing or engineering acceptance; remove React/TypeScript; prove
approved HIP C2; or authorize C6.
