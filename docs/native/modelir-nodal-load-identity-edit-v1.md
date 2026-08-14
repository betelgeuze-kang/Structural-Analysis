# ModelIR nodal-load identity edit v1

`structural-workbench model-edit-nodal-load-identity` is a bounded native edit surface that
replaces the stable identity of one existing ModelIR v2 nodal load. It changes no structural
property and publishes a new artifact directory without modifying its source.

```text
structural-workbench model-edit-nodal-load-identity MODEL.json \
  --load-pattern PATTERN-ID --load SOURCE-ID --new-load NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. All three identities contain 1 through 128 UTF-8 bytes. The replacement
must satisfy the ModelIR stable-ID grammar, differ from the source, and be unique across nodal loads
in every load pattern. The command changes only the selected `load_patterns[].nodal_loads[].id`.
It preserves the load-pattern identity and contiguous index, analysis type, nodal-load contiguous
pattern-local index, target node, all six finite SI components, `source_id`, extensions, and every
unrelated structural row.

## Reference closure, validation, and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. A missing pattern or load, duplicate or malformed replacement, no-op,
noncontiguous pattern or load index, malformed retained field, or unsupported-feature ownership of
the source or replacement identity fails closed. ModelIR v2 has no construction-stage or
round-trip entity kind that directly references a nested nodal-load identity, so this surface does
not invent such a cascade. A valid direct round-trip claim for the containing load pattern is
conservatively changed from `exact` to `approximated`; unrelated mappings are preserved. The edited
canonical bytes are strictly reparsed and cross the same C++ validator before create-new
publication.

The root extension `structural-native:model-edit-nodal-load-identity.v1` and the self-hashed
`structural-native-model-edit-receipt.v1` bind operation `nodal_load_identity_edit`, the containing
pattern and both load identities, both contiguous indices, analysis type, retained node,
components, source identity and extensions, all source and edited hashes, C++ verification,
readiness, blockers, and the model artifact hash. Unrelated explicit blockers remain visible and no
solver authority is promoted.

Installed CPU static/shared distribution E2E consumes the v66 constraint-identity-edited model and
replaces `L_WEAK_N3` with `L_WEAK_N3_RENAMED` without changing structural meaning. The append-only v67
receipt binds the model, edit receipt, request receipt, request, assembly receipt, checkpoint,
ResultIR, recovery, and ReportIR. Typed recovery proves active DOFs
`[12,13,14,15,16,17]`, exact active external load `[0,-1000,0,0,0,0]`, byte-identical
initialized-checkpoint restart, and fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only identity replacement for one existing nodal load. It does not cascade unsupported
feature ownership; change the target, components or containing pattern; create or delete loads;
edit load-pattern or combination identities; change constraints or topology; select a solver;
provide general visual editing or engineering acceptance; remove React/TypeScript; prove
approved HIP C2; or authorize C6.
