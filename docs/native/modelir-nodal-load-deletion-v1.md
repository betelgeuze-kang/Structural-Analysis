# ModelIR nodal-load deletion v1

This C5 slice provides the deliberately narrow inverse of bounded nodal-load authoring:

```text
structural-workbench model-delete-nodal-load MODEL.json \
  --load-pattern PATTERN-ID --load LOAD-ID --output-dir DELETE-DIR
```

The command removes exactly the last contiguous nodal-load row from one existing `linear_static`
pattern. The row must have `source_id: null`, exactly six finite SI components, and at least one
nonzero component. The pattern and target node remain, and another nonzero nodal load must remain
in the same pattern. The command does not reindex, retarget, cascade, or delete a pattern or node.

## Validation, references, and provenance

Rust bounds both identities, strictly parses the source, and crosses the single Rust -> C ABI -> C++
semantic-validation boundary before mutation. Preflight rejects a missing pattern or load,
nonterminal or drifting indices, a non-`linear_static` pattern, source ownership, malformed or zero
components, a zero/empty retained pattern, and unsupported-feature or direct round-trip ownership
of the deleted load identity. Construction stages and combinations refer to the retained pattern,
not its nested load row, so their identities are unchanged.

The model records `structural-native:model-delete-nodal-load.v1`, retains prior provenance under
`structural-native:upstream-provenance`, and binds the pattern ID/index plus the removed load ID,
index, target node, six components, and source identities. A valid load-pattern round-trip row is
preserved and conservatively changed from `exact` or `canonicalized` to `approximated`. Unrelated
topology, properties, loads, constraints, combinations, stages, mappings, extensions, and explicit
blockers remain intact. The edited model is canonicalized, strictly reparsed, and C++-revalidated
before atomically creating `model-ir.json` and a self-hashed `edit-receipt.json`. An existing
destination or validation failure publishes nothing; a valid blocked model remains blocked.

## CPU product and restart evidence

Focused E2E composes a neutral second frame member and N3 nodal load, deletes the added load twice,
and proves byte-identical artifacts plus source nonmutation. The result retains the original N2
load, passes strict Rust and C++ validation, and completes a model-bound `LC_WEAK` CPU request with
twelve active DOFs, the exact retained N2 load and zero N3 load, two typed frame recovery rows, and
fallback 0. A one-real-iteration checkpoint resumes to byte-identical ResultIR and recovery.
Focused guards also reject nonterminal, source-owned, minimum-pattern, and colliding-output cases.

Installed static and shared package E2E v35 repeats the command with an empty `PATH`, proves
deterministic create-new artifacts and direct/restart parity, rejects nonterminal deletion without
publishing output, and binds the deleted ModelIR, deletion receipt, request, ResultIR, and recovery
identities into the append-only distribution receipt. Frozen v1 through v34
receipts retain their narrower authority.

## Claim boundary

This closes only deletion of one last contiguous neutral, unreferenced, nonzero six-component
nodal load from an existing `linear_static` pattern while retaining another nonzero nodal load. It
does not delete source-owned, mapped, zero, nonterminal, distributed, member, self-weight, pattern,
combination, stage, time-function, node, or general load topology; reindex or cascade; select a
solver; provide a general visual editor; make an engineering acceptance decision; prove approved
HIP C2; remove React/TypeScript; or authorize C6.
