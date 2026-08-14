# ModelIR Truss Section Deletion v1

## Scope

`structural-workbench model-delete-truss-section` owns one deliberately bounded C5 deletion:

```text
structural-workbench model-delete-truss-section MODEL.json \
  --section T2 \
  --output-dir deleted-truss-section
```

The command removes exactly the last contiguous neutral `truss_3d` section with
`parameter_set_version` `1`. At least one other `truss_3d` section must remain. The removed row
must contain exactly one finite positive SI `area_m2` parameter. No section is reindexed,
substituted, or retargeted.

## Fail-closed reference boundary

Deletion is rejected before mutation when:

- the identity is missing, nonterminal, source-owned, or has index/family/version/parameter drift;
- the model would retain no `truss_3d` section;
- any element `section_id` references the row;
- an unsupported feature owns the section through `source_entity_id`; or
- a round-trip row maps directly to the section.

There is no cascade, replacement-section selection, element rewrite, cross-family deletion, or
general property deletion in this slice.

## Transaction and provenance

Both the source and edited bytes pass strict Rust parsing and the same Rust -> C ABI -> C++ semantic
validation boundary. Output is create-new and contains canonical `model-ir.json` plus a canonical
self-hashed `edit-receipt.json`. The receipt and
`structural-native:model-delete-truss-section.v1` extension bind:

- removed section identity and contiguous index;
- `truss_3d` family and parameter-set version;
- exact removed SI area;
- source input, content, semantic, and provenance identities; and
- edited content, semantic, and provenance identities plus C++ snapshot verification.

Unrelated ModelIR families, existing provenance history, and explicit analysis blockers are
preserved.

## Verification boundary

Focused source E2E and installed static/shared CPU distribution E2E prove deterministic repeated
deletion, source nonmutation, element-reference and ownership rejection, exact retained truss
section and active load, typed frame-plus-truss recovery, checkpoint/restart parity, native CPU
completion, and fallback 0. The static and shared receipts must bind identical deletion model, edit
receipt, analysis request, ResultIR, and recovery hashes.

Installed static and shared package E2E v39 owns this exact hash set. Frozen v1 through v38
receipts retain their narrower authority and cannot be used as truss-section-deletion evidence.

This is not general section deletion, cross-family deletion, cascading topology mutation,
automatic retargeting, engineering acceptance, approved HIP C2, or C6.
