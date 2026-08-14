# ModelIR linear-static load-pattern deletion v1

This C5 slice is the deliberately narrow inverse of atomic linear-load-pattern authoring:

```text
structural-workbench model-delete-linear-load-pattern MODEL.json \
  --load-pattern PATTERN-ID --output-dir DELETE-DIR
```

The command removes exactly the last contiguous `linear_static` pattern. The pattern must have
`source_id: null`, zero self-weight, and exactly one index-zero nodal load. That nested load must
also have `source_id: null`, target an existing node, contain exactly six finite SI components,
and be nonzero. At least one other load pattern remains. The command does not delete the target
node, reindex, retarget, or cascade.

## Validation, references, and provenance

Rust bounds the identity, strictly parses the source, and crosses the single Rust -> C ABI -> C++
semantic-validation boundary before mutation. Preflight rejects a missing or nonterminal pattern,
pattern/load index drift, a non-`linear_static` analysis type, source ownership, nonzero or malformed
self-weight, zero/malformed/multiple nested loads, and a minimum one-pattern model. It also rejects
every load-combination `terms[].ref_id`, construction-stage `load_pattern_ids`, unsupported-feature
`source_entity_id`, or direct round-trip `model_ir_entity_id` reference to the pattern or nested
load before mutation.

The model records `structural-native:model-delete-linear-load-pattern.v1`, retains prior provenance
under `structural-native:upstream-provenance`, and binds the removed pattern ID/index/type/self-weight
plus nested load ID/index/node/components and source identities. Unrelated topology, properties,
patterns, combinations, stages, mappings, extensions, and explicit blockers remain intact. The
edited model is canonicalized, strictly reparsed, and C++-revalidated before atomically creating
`model-ir.json` and a self-hashed `edit-receipt.json`. Invalid input or an existing destination
publishes nothing; a valid blocked model remains blocked.

## CPU product and restart evidence

Focused E2E composes a second frame member, N3 nodal load, N3 fixed constraint, and the neutral
`LC_CUSTOM` pattern, deletes that pattern twice, and proves byte-identical artifacts plus source
nonmutation. The result retains the original four patterns and completes a model-bound `LC_WEAK`
CPU request with N2 active DOFs, the exact N2-FY external load, two typed frame recovery rows, and
fallback 0. A real nonterminal checkpoint resumes to byte-identical ResultIR and recovery. Guards
reject nonterminal/source-owned/multiple-load/combined/staged/unsupported-feature-owned/mapped and
colliding-output cases before publication.

Installed static and shared package E2E v36 repeats this path with an empty `PATH`, proves
deterministic create-new artifacts and direct/restart parity, and binds the deleted ModelIR,
deletion receipt, request, ResultIR, and recovery identities into the append-only distribution
receipt. Frozen v1 through v35 receipts retain their narrower authority.

## Claim boundary

This closes only deletion of one last contiguous neutral, unreferenced, zero-self-weight
`linear_static` pattern containing one neutral nonzero six-component nodal load. It does not delete
source-owned, combined, staged, mapped, multiple-load, self-weight, nonlinear, time-function,
node, member, constraint, or general load topology; reindex or cascade; select a solver; provide a
general visual editor; make an engineering acceptance decision; prove approved HIP C2; remove
React/TypeScript; or authorize C6.
