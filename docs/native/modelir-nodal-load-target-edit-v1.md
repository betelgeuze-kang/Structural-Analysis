# ModelIR nodal-load target edit v1

`structural-workbench model-edit-nodal-load-target` is a bounded native edit surface that moves one
existing ModelIR v2 nodal load from its current node to a distinct existing node. It preserves the
load and pattern identities and publishes a new artifact directory without modifying its source.

```text
structural-workbench model-edit-nodal-load-target MODEL.json \
  --load-pattern PATTERN-ID --load LOAD-ID --node NEW-TARGET-NODE-ID \
  --output-dir EDITED-DIR
```

The option order is fixed and each identity contains 1 through 128 UTF-8 bytes. The command changes
only the selected load's `node_id`. Pattern and load indices, analysis type, all six finite SI
components, `source_id`, extensions, and unrelated ModelIR rows are retained exactly.

## Validation and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. Missing pattern, load or replacement node identities, a same-node no-op,
noncontiguous indices, malformed retained fields, duplicate IDs, dangling references, or invalid
source semantics fail closed. The edited canonical bytes are strictly reparsed and cross the same
C++ validator before create-new publication.

The root extension `structural-native:model-edit-nodal-load-target.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `nodal_load_target`, both node identities,
pattern and load indices, the retained analysis type, components, source identity and extensions,
all source and edited hashes, C++ verification, readiness, blockers, and the model artifact hash. A
matching load-pattern round-trip row is conservatively degraded to `approximated`; no round-trip or
solver authority is promoted.

Installed CPU static/shared distribution E2E uses the prior connected N3 frame-member artifact,
retargets `LC_WEAK/L_WEAK_N2` from N2 to N3, and creates an exact model-bound CPU request. The
append-only v61 receipt binds the model, edit receipt, request receipt, request, assembly receipt,
checkpoint, ResultIR, recovery and ReportIR. Typed recovery proves active DOFs
`[6,7,8,9,10,11,12,13,14,15,16,17]`, exact active external load
`[0,0,0,0,0,0,0,-10000,0,0,0,0]`, byte-identical initialized-checkpoint restart, and fallback 0
with Python and Node lookup counts both zero.

## Claim boundary

This closes only target-node replacement for one existing nodal load. Component and identity edits,
creation and deletion are separate bounded C5 surfaces; pattern content editing and reference
cascades remain open, while unreferenced linear-pattern identity replacement is the separate v68
surface. General
topology, solver or visual editing, engineering acceptance, React/TypeScript removal, approved HIP C2,
and C6 remain open.
