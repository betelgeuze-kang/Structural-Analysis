# ModelIR last-neutral linear load-combination deletion v1

This bounded C5 Workbench slice deletes one `linear` load combination. The installed command is:

```text
structural-workbench model-delete-linear-load-combination MODEL.json \
  --load-combination ID \
  --output-dir DELETED-COMBINATION-MODEL
```

## Contract

Rust strictly reads a bounded regular ModelIR file. The requested row must be the last contiguous
load-combination row, have null `source_id` and empty entity extensions, use
`combination_type: linear`, and contain exactly two ordered terms. Both terms must reference two
distinct existing `linear_static` load patterns and carry finite nonzero factors.

Deletion fails closed before mutation for a missing or nonterminal identity, index drift, source or
extension ownership, malformed term counts, nested load-combination terms, missing or unsupported
patterns, duplicate pattern references, zero or non-finite factors, another combination reference,
direct unsupported-feature ownership, or a direct round-trip mapping. It does not cascade or
reindex any row.

Both source and edited models cross strict Rust parsing and Rust -> C ABI -> C++ semantic
validation. C++ reference and cycle validation therefore remain authoritative. The canonical
edited model retains the prior addition provenance and adds
`structural-native:model-delete-linear-load-combination.v1`, binding the removed identity, index,
type, exact ordered terms and factors, neutral ownership, source identities, and the bounded claim.
Every unrelated domain row, explicit blocker, extension, and round-trip row is preserved.

Publication is create-new and atomic. It emits `model-ir.json` and a self-hashed
`structural-native-model-edit-receipt.v1` with source and edited content/semantic/provenance
identities, C++ snapshot status, analysis readiness, blocker identities, artifact hash, and the
exact removed row.

## Product evidence

Focused Rust E2E repeats the operation byte-for-byte, proves source nonmutation and exact unrelated
row preservation, and rejects nonterminal, source-owned, extended, referenced, feature-owned,
round-trip-owned, malformed, nested, and existing-destination cases without partial publication.
It also proves an unrelated explicit blocker and round-trip map remain visible.

Installed CPU static/shared E2E v43 repeats deletion of the two distinct pattern terms under an
empty `PATH`, obtains a zero-row C++ validation snapshot, renders the native topology view, creates
a direct `LC_WEAK` CPU request,
and executes it through the product library. The evidence binds the deleted model, edit receipt,
analysis request, ResultIR, and typed recovery hashes. Exact active DOFs, active external load,
frame recovery, checkpoint/restart byte parity, and fallback 0 are verified. This proves that
deleting the sole supported combination restores direct load-pattern CPU execution. Bounded
two-pattern combination evaluation is separately covered by installed distribution E2E v44.

General or nonterminal combination deletion, term editing, cascade or reindexing,
nested or nonlinear combination deletion/evaluation, general solver selection,
visual editing, engineering acceptance, approved HIP C2, React/TypeScript removal, and C6
decommission remain open.

The exact-two v1 bytes remain frozen. Bounded three-through-64 direct deletion is an additive v2
profile documented in `docs/native/modelir-direct-linear-load-combination-deletion-v1.md`.
