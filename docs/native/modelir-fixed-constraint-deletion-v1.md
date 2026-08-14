# ModelIR fixed-constraint deletion v1

This C5 slice provides the deliberately narrow inverse of homogeneous fixed-constraint authoring:

```text
structural-workbench model-delete-fixed-constraint MODEL.json \
  --constraint CONSTRAINT-ID --output-dir DELETE-DIR
```

The command removes exactly the last contiguous `fixed_dofs` constraint while retaining at least
one constraint. The row must have `source_id: null`, the ordered closed DOF mask `UX, UY, UZ, RX,
RY, RZ`, and exactly six zero prescribed SI values. It does not retarget, partially edit, infer,
reindex, or cascade a deletion set.

## Validation, references, and provenance

Rust bounds the source and identity, strictly parses the source, and crosses the single
Rust -> C ABI -> C++ semantic-validation boundary before mutation. Preflight rejects missing or
nonterminal rows, index drift, a wrong constraint type, source ownership, a partial or nonzero restraint, and
every construction-stage `active_constraint_ids`, unsupported-feature source, or round-trip
reference to the deleted identity. The edited model is canonicalized, strictly reparsed, and
C++-revalidated before publication.

The model records `structural-native:model-delete-fixed-constraint.v1`, retains prior provenance
under `structural-native:upstream-provenance`, and binds the source identities plus the removed
constraint ID, index, type, target node, DOF mask, and prescribed values. Unrelated topology,
properties, loads, constraints, stages, mappings, extensions, and explicit blockers remain intact.
Publication atomically creates exactly `model-ir.json` and a canonical self-hashed
`edit-receipt.json`; an existing destination or validation failure publishes nothing. A valid
blocked model remains blocked.

## CPU product and restart evidence

Focused E2E composes a neutral second frame member, an N3 nodal load, and a neutral N3 fixed
constraint, deletes the constraint twice, and proves byte-identical artifacts plus source
nonmutation. The result retains the original base constraint, passes strict Rust and C++
validation, and completes a model-bound `LC_WEAK` CPU request with twelve active DOFs, the exact N2
and N3 external loads, two typed frame recovery rows, and fallback 0. A one-real-iteration
checkpoint resumes to byte-identical ResultIR and recovery. Focused guards also reject nonterminal,
source-owned, staged, mapped, partial, nonzero, and colliding-output cases before publication.

Installed static and shared package E2E v34 repeats the command with an empty `PATH`, proves
deterministic create-new artifacts and direct/restart parity, rejects nonterminal deletion without
publishing output, and binds the deleted ModelIR, deletion receipt, request, ResultIR, and recovery
identities into the append-only distribution receipt. Frozen v1 through v33
receipts keep their narrower authority.

## Claim boundary

This closes only deletion of one last contiguous neutral, unreferenced, homogeneous six-DOF zero
`fixed_dofs` row while leaving another constraint. It does not delete source-owned, staged, mapped,
partial, nonzero, MPC, contact, support-set, nonterminal, or arbitrary constraint topology; edit
nodes or loads; select a solver; provide a general visual editor; make an engineering acceptance
decision; prove approved HIP C2; remove React/TypeScript; or authorize C6.
