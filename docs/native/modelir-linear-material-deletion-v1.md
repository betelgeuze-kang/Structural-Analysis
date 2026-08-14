# ModelIR Linear Material Deletion v1

## Scope

`structural-workbench model-delete-linear-material` owns one deliberately bounded C5 deletion:

```text
structural-workbench model-delete-linear-material MODEL.json \
  --material M2 \
  --output-dir deleted-material
```

The command removes exactly the last contiguous neutral `linear_elastic_isotropic` material with
`parameter_set_version` `1`. At least one material must remain. The removed row must use the exact
stateless v1 state schema and valid finite SI parameters. No material is reindexed, substituted, or
retargeted.

## Fail-closed reference boundary

Deletion is rejected before mutation when:

- the identity is missing, nonterminal, source-owned, or has index/law/version/state drift;
- the model would retain no material;
- any element `material_id` references the row;
- any section `steel_material_id` or `concrete_material_id` references the row;
- an unsupported feature owns the material through `source_entity_id`; or
- a round-trip row maps directly to the material.

There is no cascade, replacement-material selection, section rewrite, element rewrite, or general
property deletion in this slice.

## Transaction and provenance

Both the source and edited bytes pass strict Rust parsing and the same Rust -> C ABI -> C++ semantic
validation boundary. Output is create-new and contains canonical `model-ir.json` plus a canonical
self-hashed `edit-receipt.json`. The receipt and
`structural-native:model-delete-linear-material.v1` extension bind:

- removed material identity and contiguous index;
- `linear_elastic_isotropic` law and parameter-set version;
- exact removed SI parameters and state schema;
- source input, content, semantic, and provenance identities; and
- edited content, semantic, and provenance identities plus C++ snapshot verification.

Unrelated ModelIR families, existing provenance history, and explicit analysis blockers are
preserved.

## Verification boundary

Focused source E2E and installed static/shared CPU distribution E2E prove deterministic repeated
deletion, source nonmutation, element-reference and ownership rejection, exact retained material
and active load, typed frame recovery, checkpoint/restart parity, native CPU completion, and
fallback 0. The static and shared receipts must bind identical deletion model, edit receipt,
analysis request, ResultIR, and recovery hashes.

Installed static and shared package E2E v37 owns this exact hash set. Frozen v1 through v36
receipts retain their narrower authority and cannot be used as material-deletion evidence.

This is not general material deletion, nonlinear state deletion, cascading topology mutation,
automatic retargeting, engineering acceptance, approved HIP C2, or C6.
