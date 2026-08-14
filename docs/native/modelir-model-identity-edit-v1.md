# ModelIR root model identity edit v1

`structural-workbench model-edit-model-identity` is a bounded native edit surface that replaces the
declared root `model_id` of one ModelIR v2 document. The caller supplies the exact expected source
identity, so selecting the wrong model fails before publication.

```text
structural-workbench model-edit-model-identity MODEL.json \
  --model-id SOURCE-ID --new-model-id NEW-ID --output-dir EDITED-DIR
```

The option order is fixed. Both identities contain 1 through 128 UTF-8 bytes. The replacement must
satisfy the ModelIR stable-ID grammar and differ from the source. The command changes the root
`model_id`, then binds explicit native edit provenance; it does not change an entity identity or
infer any reference cascade.

## Retention, validation, and provenance

The source is strictly parsed in Rust and crosses the single C ABI into C++ semantic validation
before mutation. The editor removes `model_id` from an in-memory copy of the verified canonical
snapshot and hashes every retained byte-canonical field. After inserting the replacement, it
removes `model_id` again and requires the hash to be identical before provenance is added. This
binds the schema version, capability profile, units, coordinate system, DOF components, every
entity family, round-trip row, unsupported feature, and unrelated root extension.

A mismatched expected source identity, malformed replacement, no-op, retained-document drift,
invalid source or edited semantics, or unsupported-feature `source_entity_id` ownership of either
the source or replacement identity fails closed. The edited canonical bytes are strictly reparsed
and cross the same C++ validator before create-new publication.

The root extension `structural-native:model-edit-model-identity.v1` and self-hashed
`structural-native-model-edit-receipt.v1` bind operation `model_identity_edit`, both identities,
retained schema/profile, the source-document-without-identity hash, exact retained family counts,
all source and edited hashes, C++ verification, readiness, blockers, and the model artifact hash.

Installed CPU static/shared distribution E2E consumes the v74 combination-identity-edited model,
replaces `engine-v2-frame-cantilever` with `engine-v2-frame-cantilever-renamed`, and creates a
model-bound request selecting retained `COMBO_RENAMED`. The append-only v75 receipt binds the model,
edit receipt, request receipt, request, assembly receipt, checkpoint, ResultIR, recovery, and
ReportIR. Typed recovery proves frame element type `[1]`, offsets `[0,12]`, active DOFs
`[6,7,8,9,10,11]`, exact combined active external load `[25000,-12000,5000,0,0,0]`, byte-identical
initialized-checkpoint restart, and fallback 0 with Python and Node lookup counts both zero.

## Claim boundary

This closes only expected-source-bound replacement of the root ModelIR identity. It does not edit
entity identities, topology, properties, loads, constraints, solvers, time functions, construction
stages, or visual presentation; cascade unsupported-feature ownership; provide engineering
acceptance; remove React/TypeScript; prove approved HIP C2; or authorize C6.
