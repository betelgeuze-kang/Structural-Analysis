# ModelIR Orphan Node Deletion v1

## Scope

`structural-workbench model-delete-orphan-node` owns one deliberately bounded C5 deletion:

```text
structural-workbench model-delete-orphan-node MODEL.json \
  --node N3 \
  --output-dir deleted-node
```

The command removes exactly one last contiguous neutral orphan node while retaining at least two
nodes. It performs no reindexing, cascade, element/connectivity change, support or load removal, or
solver selection.

## Fail-closed boundary

Before publication, Rust rejects:

- an empty, oversized, or non-UTF-8 node identity;
- a missing or nonterminal node and any index drift;
- a source-owned node, a node with entity extensions, or a model with only two nodes;
- any element, constraint, or nested nodal-load reference to the node;
- any unsupported-feature ownership or direct round-trip mapping; and
- an existing or otherwise unsafe output directory.

All non-node domain rows, unrelated blockers, and unrelated round-trip mappings remain unchanged.
The operation accepts only `source_id: null` and an empty entity-extension object, so it cannot
silently discard source or extension ownership.

## Transaction and provenance

Both source and edited bytes pass strict Rust parsing and the same Rust -> C ABI -> C++ semantic
validation boundary. Output is create-new and contains canonical `model-ir.json` plus a canonical
self-hashed `edit-receipt.json`. The receipt and
`structural-native:model-delete-orphan-node.v1` extension bind:

- removed node identity, terminal index, exact SI coordinates, null source ownership, and empty
  entity extensions;
- source input, content, semantic, and provenance identities; and
- edited content, semantic, and provenance identities plus C++ snapshot verification.

The editor binds the complete prior provenance object under
`structural-native:upstream-provenance` and never mutates the source file.

## Verification boundary

Focused source E2E proves deterministic add-then-delete behavior, source nonmutation, minimum,
terminal, source, extension, element, constraint, load, unsupported-feature and round-trip guards,
blocker preservation, strict C++ validation, and create-new failure semantics. Product execution
then generates a model-bound CPU linear request from the deleted model and proves exact active DOFs
and external load, typed frame recovery, initialized-active checkpoint/restart parity, native CPU
completion, and fallback 0.

Installed static and shared package E2E v41 owns the orphan-node-deleted ModelIR, edit receipt,
generated request, ResultIR, and recovery hash set. Frozen v1 through v40 receipts retain their narrower authority and cannot be used as standalone orphan-node-deletion evidence.

This is not general node or topology deletion, member deletion, cascade, reindexing, visual model
editing, engineering acceptance, approved HIP C2, or C6.
