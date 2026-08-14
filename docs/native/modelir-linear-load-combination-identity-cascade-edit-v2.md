# ModelIR linear load-combination identity cascade edit v2

`structural-workbench model-edit-linear-load-combination-identity-cascade` is a bounded native edit
surface that replaces one referenced ModelIR v2 linear load-combination identity and atomically
updates its typed downstream references. It publishes a new artifact directory and never modifies
the source.

```text
structural-workbench model-edit-linear-load-combination-identity-cascade MODEL.json \
  --load-combination SOURCE-ID --new-load-combination NEW-ID \
  --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement must
satisfy the ModelIR stable-ID grammar, differ from the source, be unique among load combinations,
and not name a load pattern.

## Typed cascade and validation

The command changes exactly these typed locations:

- the selected `load_combinations[].id`;
- every downstream `load_combinations[].terms[].ref_id` whose `ref_kind` is
  `load_combination` and whose identity matches the source;
- every direct `roundtrip_map[].model_ir_entity_id` whose `entity_kind` is
  `load_combination` and whose identity matches the source.

An `exact` or `canonicalized` mapping becomes `approximated`; an `approximated` or `unsupported`
mapping retains its status. The target combination keeps its contiguous index, type, ordered typed
terms, factors, source identity, extensions, and every unrelated row. The cascade requires at least
one downstream typed combination reference; an orphan root continues to use the v1 non-cascading
editor.

The accepted direct profile has two through 64 unique `linear_static` pattern terms. The accepted
nested profile is acyclic, has at most eight combination levels, and expands to at most 64 terms.
The target expansion and the mathematical expansion of every affected downstream combination are
verified unchanged. Rust strictly parses the source, then the model crosses the single C ABI into C++ semantic validation
before mutation. The edited canonical bytes are reparsed and cross the same
C++ validator before create-new publication.

Missing, colliding, malformed, no-op, load-pattern-ambiguous, unreferenced, or out-of-profile
identities fail closed. Index or retained-row drift, a malformed typed term or direct mapping,
wrong-kind direct mapping, replacement mapping ownership, unsupported-feature `source_entity_id`
ownership of either identity, expansion drift, and invalid source or edited semantics also fail
closed. Untyped extension references and unsupported-feature ownership are never inferred or
cascaded.

The root extension
`structural-native:model-edit-linear-load-combination-identity-cascade.v2` and self-hashed edit
receipt bind operation `linear_load_combination_identity_cascade_edit`, both identities, retained
target row, profile and expansion, downstream and mapping reference counts, source and edited
hashes, C++ verification, readiness, blockers, and model artifact hash.

Installed CPU static/shared distribution E2E cascades `COMBO_RENAMED` to `COMBO_BASE_LINKED`
beneath `COMBO_PARENT`, then creates a model-bound request for the retained parent. The append-only v81
receipt binds model, edit/request/assembly receipts, request, checkpoint, ResultIR, recovery, and
ReportIR. Typed recovery proves frame element type `[1]`, offsets `[0,12]`, active DOFs
`[6,7,8,9,10,11]`, exact combined load `[35000,-12000,5000,0,0,0]`, byte-identical initialized
restart, and fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only one bounded referenced linear load-combination identity cascade. It does not
cascade untyped extensions or unsupported features; edit term factors, reference kinds, order, or
count; create or delete combinations; select a general solver; provide visual editing or engineering
acceptance; remove React/TypeScript; prove approved HIP C2; or authorize C6.
