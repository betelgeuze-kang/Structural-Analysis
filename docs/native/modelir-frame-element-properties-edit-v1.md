# ModelIR frame-element property assignment edit v1

`structural-workbench model-edit-frame-element-properties` is a bounded native edit surface for
the material and section references of one existing ModelIR v2 `frame_3d` element. It publishes a
new, independently verifiable artifact set and never modifies the source file.

```text
structural-workbench model-edit-frame-element-properties MODEL.json \
  --element ELEMENT-ID --material MATERIAL-ID --section SECTION-ID \
  --output-dir EDITED-DIR
```

The fixed options are all required. Every identity contains 1 through 128 UTF-8 bytes. The output
directory must not exist and contains exactly canonical `model-ir.json` and self-hashed
`edit-receipt.json` artifacts.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before editing. It selects
one stable element identity from the canonical C++ snapshot and requires `type: frame_3d`. The
target material must be an existing v1 `linear_elastic_isotropic` material and the target section
must be an existing v1 `frame_3d` section.

Only `material_id` and `section_id` are replaced, atomically. Identity, index, element type,
formulation, ordered endpoints, local-axis rotation, offsets, releases, source identity, and
element extensions remain byte-semantically unchanged. A request may retain either one of the two
references while changing the other, but retaining both is a rejected no-op.

Direct provenance is rewritten to `structural-native-model-editor`, prior provenance is retained
under `structural-native:upstream-provenance`, and
`structural-native:model-edit-frame-element-properties.v1` binds the element identity, fixed type,
retained formulation, previous and edited material/section references, and source content,
semantic, and provenance hashes. A matching `exact` or `canonicalized` `element` round-trip row is
conservatively marked `approximated`; other rows and already degraded dispositions are not
promoted.

The edited document is strictly reparsed and crosses the same C++ semantic validator again before
create-new publication. The receipt binds source and edited hashes, verified C++ snapshot,
analysis readiness, blocker identities, and published model bytes. Missing identities,
incompatible property families or versions, an unsupported element type, a complete no-op,
invalid source, contract drift, or invalid edited semantics fail without partial publication.
Semantically valid explicit blockers remain visible and are never promoted away.

## Product evidence

Focused Rust E2E first creates M2 and S2 through the native creators, then performs the assignment
twice with byte-identical results and unchanged original/composed source bytes. It rejects existing
destinations, missing element/material/section identities, a complete no-op, a non-frame element,
an incompatible material, and invalid source semantics. It also proves that only the direct
element round-trip row is degraded and explicit blockers remain analysis-blocking.

The test runs the original M1/S1 cantilever and the M2/S2-assigned cantilever with identical
`LC_WEAK` requests. Both retain active DOFs `[6,7,8,9,10,11]` and exact active external load
`[0,-10000,0,0,0,0]`; native CPU execution completes, the recovered displacement changes, and
fallback 0 is preserved.

Static and shared installed-package E2E v29 repeats the creators, assignment, request, and run with
an empty `PATH`, compares repeated artifact trees, and binds the assigned model, edit receipt,
analysis request, ResultIR, and recovery identities into the authoritative CPU distribution
receipt. Frozen v1 through v28 receipts retain their narrower authority.

## Claim boundary

This closes only compatible material/section reference assignment for one existing `frame_3d`
element. It does not create or delete entities, change element identity/type/formulation,
connectivity, orientation, offsets or releases, expose nonlinear state, select a solver, provide
visual manipulation or undo history, make an engineering acceptance decision, prove approved HIP
C2, remove React/TypeScript, or authorize C6 decommission.
