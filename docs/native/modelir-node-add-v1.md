# ModelIR Node Addition v1

## Scope

`structural-workbench model-add-node` owns one deliberately bounded C5 authoring operation:

```text
structural-workbench model-add-node MODEL.json \
  --node N3 \
  --coordinates 4 1 0 \
  --output-dir authored-node
```

The command appends exactly one node with a unique identity, three finite SI coordinates, the
next contiguous index, neutral `source_id: null`, and empty entity extensions. It does not create or
retarget a member, load, constraint, material, section, stage, or solver request.

## Fail-closed boundary

Before publication, Rust rejects:

- an empty, oversized, or non-UTF-8 node identity;
- a duplicate node identity or exact canonical coordinate triplet, including signed-zero aliases;
- non-finite coordinates;
- source ModelIR with index drift or any other invalid C++ semantics; and
- an existing or otherwise unsafe output directory.

Existing domain rows, unsupported-feature blockers, and every round-trip mapping remain unchanged.
A newly authored neutral node has no source round-trip claim to invent or degrade.

## Transaction and provenance

Both source and edited bytes pass strict Rust parsing and the same Rust -> C ABI -> C++ semantic
validation boundary. Output is create-new and contains canonical `model-ir.json` plus a canonical
self-hashed `edit-receipt.json`. The receipt and `structural-native:model-add-node.v1` extension
bind:

- node identity, contiguous index, exact SI coordinates, and neutral source ownership;
- source input, content, semantic, and provenance identities; and
- edited content, semantic, and provenance identities plus C++ snapshot verification.

The editor binds the complete prior provenance object under
`structural-native:upstream-provenance` and never mutates the source file.

## Verification boundary

Focused source E2E and installed static/shared CPU distribution E2E prove deterministic repeated
creation, source nonmutation, duplicate identity/coordinate and index-drift rejection, blocker and
round-trip preservation, strict C++ validation, and create-new failure semantics. Product execution
then composes a homogeneous six-DOF fixed constraint on the new orphan node so that the existing
frame remains nonsingular; it proves the exact unchanged active DOFs and external load, typed frame
recovery, initialized-active checkpoint/restart parity, native CPU completion, and fallback 0.

Installed static and shared package E2E v40 owns the node-added ModelIR, edit receipt,
fixed-constraint-composed ModelIR, generated request, ResultIR, and recovery hash set. Frozen v1 through v39
receipts retain their narrower authority and cannot be used as standalone node-addition evidence.

This is not general topology authoring, connectivity editing, visual placement, referenced-node or
cascade deletion, automatic support generation, engineering acceptance, approved HIP C2, or C6.
Stable-identity replacement for an existing unreferenced node is the separate bounded
`model-edit-node-identity` surface documented in
`docs/native/modelir-node-identity-edit-v1.md`.
