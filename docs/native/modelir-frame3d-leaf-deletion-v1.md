# ModelIR frame3d leaf deletion v1

This slice provides the Rust-native Workbench with the deliberately narrow inverse of bounded
frame3d member authoring:

```text
structural-workbench model-delete-frame3d-leaf-member MODEL.json \
  --element ELEMENT-ID --node NODE-ID --output-dir DELETE-DIR
```

The command removes exactly the last contiguous `frame_3d`/`euler_bernoulli_3d` element and
exactly the last contiguous endpoint node. Both rows must have `source_id: null`; the operation
must retain at least two nodes and one element. The endpoint node must be orphaned after removal:
no other element, constraint, nodal load, construction stage, unsupported-feature source row, or
round-trip row may reference the removed node or element. It never reindexes, cascades, infers a
deletion set, or deletes properties.

## Validation, provenance, and publication

Rust bounds the source and both identities, strictly parses the source, and crosses the single
Rust -> C ABI -> C++ semantic-validation boundary before mutation. The shared frame/truss leaf
preflight rejects missing or nonterminal rows, index drift, a wrong family/formulation,
source-owned rows, endpoint mismatch, every retained reference, and topology below the minimum
retained model. The edited document is canonicalized, strictly reparsed, and C++-revalidated
before any filesystem publication.

The model records `structural-native:model-delete-frame3d-leaf-member.v1`, retains the complete
prior provenance under `structural-native:upstream-provenance`, and binds all source identities
plus the removed indices, coordinates, endpoints, compatible material/section references, local
axis rotation, offsets, and releases. Existing properties, loads, constraints, round-trip rows,
unrelated extensions, and explicit unsupported-feature blockers remain intact. Publication
atomically creates exactly `model-ir.json` and canonical self-hashed `edit-receipt.json`; an
existing destination or validation failure publishes nothing. A valid blocked model remains
blocked.

## CPU product and restart evidence

Focused E2E appends neutral frame leaf `E2/N3`, deletes it twice, and proves byte-identical model
and receipt artifacts while both source files remain unchanged. The resulting model contains only
the original `E1/N1/N2` topology, passes strict Rust and C++ validation, and completes a
model-bound `LC_WEAK` request through the native FP64 CPU product with the exact external load and
frame-only typed recovery. It records fallback 0 and a one-real-iteration checkpoint that resumes
to byte-identical ResultIR and recovery.

Installed static and shared package E2E v33 repeats the command with an empty `PATH`, proves
unchanged inputs and byte-identical artifacts, rejects a constrained endpoint without publishing
output, and binds the deleted ModelIR, deletion receipt, request, ResultIR, and recovery identities
into the append-only distribution receipt. Frozen v1 through v32
receipts keep their narrower authority.

## Claim boundary

This closes only deletion of one last contiguous neutral, unreferenced Euler-Bernoulli frame leaf
and its last orphan endpoint node. It does not delete source-owned, loaded, constrained, staged,
mapped, nonterminal, truss, shell, or solid entities; cascade or reindex topology; delete unused
materials/sections; provide a general visual editor; make an engineering acceptance decision;
prove approved HIP C2; remove React/TypeScript; or authorize C6.
