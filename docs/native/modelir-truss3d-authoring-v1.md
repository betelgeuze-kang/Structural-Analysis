# ModelIR truss3d authoring v1

This slice adds two bounded Rust-native authoring commands for the existing typed ModelIR v2
`truss_3d` CPU product path. Both commands publish new artifacts and never modify their source.

```text
structural-workbench model-add-truss-section MODEL.json \
  --section SECTION-ID --area-m2 AREA --output-dir SECTION-DIR

structural-workbench model-add-truss3d-member MODEL.json \
  --node NODE-ID --coordinates X Y Z \
  --element ELEMENT-ID --from-node EXISTING-NODE-ID \
  --material MATERIAL-ID --section SECTION-ID --output-dir MEMBER-DIR
```

The section command appends one unique, contiguous-index v1 `truss_3d` section. Its only
parameter is a finite positive SI cross-sectional area. The member command appends one unique
finite-coordinate node and one unique, contiguous-index `truss_3d` / `linear_truss_3d` element.
It requires an existing distinct endpoint, an existing v1 `linear_elastic_isotropic` material,
and an existing v1 `truss_3d` section. The new element has zero global endpoint offsets and, as
required by the truss schema, no frame-only local-axis-rotation or release fields.

## Validation, provenance, and publication

Each command strictly parses the source and crosses Rust -> C ABI -> C++ semantic validation
before mutation. New entities have `source_id: null`, empty entity extensions, and contiguous
indices. Existing entities and every round-trip row remain unchanged. The editor replaces direct
provenance with `structural-native-model-editor`, retains the entire prior provenance under
`structural-native:upstream-provenance`, and binds the source content, semantic, and provenance
hashes into either `structural-native:model-add-truss-section.v1` or
`structural-native:model-add-truss3d-member.v1`.

The edited model is canonicalized, strictly reparsed, and sent through the same C++ validator a
second time. Publication then atomically creates exactly `model-ir.json` and a canonical
self-hashed `edit-receipt.json`; an existing destination is never replaced. Duplicate identities
or coordinates, non-finite or non-positive area, missing references, an incompatible section or
material version/family, invalid source bytes, and edited schema or semantic drift fail without a
partial artifact. Valid explicit blockers remain visible and keep `analysis_ready: false`.

## CPU product and restart evidence

Focused E2E starts with the two-node frame cantilever, adds area `0.005 m^2` as `T1`, adds a
vertical `E2` truss from existing `N2` to new `N3`, and fixes `N3` through the existing bounded
constraint creator. The original and composed models use the same `LC_WEAK` request. The composed
run retains active DOFs `[6,7,8,9,10,11]`, exact active load `[0,-10000,0,0,0,0]`, changes the
recovered displacement, emits recovery type codes `[1,2]` with offsets `[0,12,15]` and a nonzero
three-value truss axial record, and reports fallback 0. A one-real-iteration checkpoint resumes to
byte-identical ResultIR and recovery artifacts.

The mixed frame/truss case also exposed two valid FP64 residual evaluations with different
summation orders: element recovery and canonical CSR. Their parity check now permits only a
force-scale-bounded `64 * epsilon` rounding envelope in addition to the existing absolute metric
tolerance; the sparse ResultIR still independently verifies convergence against exact `Kx-b`,
and material residual divergence remains fail-closed.

Static and shared installed-package E2E v30 repeats section/member/fixed-support composition twice
with an empty `PATH`, validates byte-identical artifacts, runs the CPU product, verifies typed frame-plus-truss recovery
and fallback 0, and binds the section, member, composed model, request, ResultIR,
and recovery identities into the append-only distribution receipt. Frozen v1 through v29
receipts preserve their narrower authority.

## Claim boundary

This closes one v1 truss section and one connected linear truss3d member, plus their composition
through the existing CPU linear C4/C5 product. It does not edit or delete truss entities, create
general topology, expose frame releases on trusses, add nonlinear material state, provide shell,
modal, buckling, transient, or visual authoring, select arbitrary solvers, make an engineering
acceptance decision, prove approved HIP C2, remove React/TypeScript, or authorize C6.
