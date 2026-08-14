# ModelIR truss3d editing v1

This slice gives the Rust-native Workbench two bounded create-new editors for the typed ModelIR v2
linear `truss_3d` product path:

```text
structural-workbench model-edit-truss-section MODEL.json \
  --section SECTION-ID --area-m2 AREA --output-dir SECTION-EDIT-DIR

structural-workbench model-edit-truss-element-properties MODEL.json \
  --element ELEMENT-ID --material MATERIAL-ID --section SECTION-ID \
  --output-dir PROPERTY-EDIT-DIR
```

The section editor replaces only `parameters.area_m2` on one existing v1 `truss_3d` section. The
property editor atomically replaces only `material_id` and `section_id` on one existing
`truss_3d` element. It requires an existing v1 `linear_elastic_isotropic` material and an existing
v1 `truss_3d` section. Element identity, index, formulation, endpoints, offsets, source ownership,
and extensions are retained; frame-only rotation and release fields are never introduced.

## Validation, provenance, and publication

Both commands bound every identity and numeric input, strictly parse the source, and cross the
single Rust -> C ABI -> C++ semantic validation boundary before mutation. They reject a missing or
wrong-family entity, incompatible property references, non-finite or non-positive area, and a
complete no-op. A matching direct round-trip row becomes `approximated`; unrelated rows and all
explicit blockers remain unchanged.

The edited model records either `structural-native:model-edit-truss-section.v1` or
`structural-native:model-edit-truss-element-properties.v1`, retains the complete prior provenance
under `structural-native:upstream-provenance`, and binds the source content, semantic, and
provenance hashes plus previous and edited values. It is then canonicalized, strictly reparsed,
and revalidated by C++. Publication atomically creates exactly `model-ir.json` and canonical
self-hashed `edit-receipt.json`; an existing destination or any late validation failure publishes
nothing. A valid blocked model stays blocked and cannot create an analysis request.

Stable-identity-only replacement for an unreferenced v1 truss section is a separate bounded
surface; see `docs/native/modelir-truss-section-identity-edit-v1.md`.

## CPU product and restart evidence

Focused E2E composes the v30 fixed vertical truss and adds alternate v1 properties `M2` and `T2`.
It first changes `T1` from `0.005 m^2` to `0.01 m^2`, then reassigns `E2` from `M1/T1` to
`M2/T2`. The baseline, section-edited, and property-edited models retain the exact active load
`[0,-10000,0,0,0,0]`, emit frame-plus-truss recovery type codes `[1,2]` and offsets `[0,12,15]`,
complete through the native FP64 CPU product with fallback 0, and produce distinct displacement
vectors. A one-real-iteration checkpoint on the final property-edited model resumes to
byte-identical ResultIR and recovery artifacts.

Installed static and shared package E2E v31 repeats both edits twice with an empty `PATH`, proves
byte-identical edit artifacts and unchanged sources, runs the bound CPU request directly and by
checkpoint resume, and binds both edited ModelIR/receipt identities plus request, ResultIR, and
typed recovery identities into the append-only distribution receipt. Frozen v1 through v30
receipts preserve their narrower authority.

## Claim boundary

This closes existing v1 truss-section area editing and compatible material/section reassignment on
one existing linear truss element. It does not create or delete arbitrary properties, change
identity, type, formulation, connectivity or offsets, support nonlinear material state, provide
shell or solid editing, select arbitrary solvers, make an engineering acceptance decision, prove
approved HIP C2, remove React/TypeScript, or authorize C6.
