# ModelIR linear frame3d member addition v1

`structural-workbench model-add-frame3d-member` is a bounded native topology-authoring surface.
It appends exactly one new node and one connected linear `frame_3d` element to an existing strict
ModelIR v2 document. The source file is never modified.

```text
structural-workbench model-add-frame3d-member MODEL.json \
  --node NEW-NODE-ID --coordinates X Y Z \
  --element NEW-ELEMENT-ID --from-node EXISTING-NODE-ID \
  --material EXISTING-MATERIAL-ID --section EXISTING-SECTION-ID \
  --output-dir ADDED-DIR
```

The option order and vocabulary are fixed. Coordinates are finite metres. The new node and element
receive the next contiguous stable indices. The new element has this closed construction:

- type `frame_3d` and formulation `euler_bernoulli_3d`;
- ordered endpoints `[EXISTING-NODE-ID, NEW-NODE-ID]`;
- one existing v1 `linear_elastic_isotropic` material and one existing v1 `frame_3d` section;
- local-axis rotation zero, zero global offsets, and no end releases;
- neutral `source_id: null` because the new entities have no upstream source row.

The output directory must not exist and contains exactly canonical `model-ir.json` and a
self-hashed `structural-native-model-edit-receipt.v1` `edit-receipt.json`.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before mutation. It rejects
duplicate new identities, a missing existing endpoint, material, or section, duplicate node
coordinates, unsupported material/section families, non-finite coordinates, and ModelIR family
limits. It appends both entities to the canonical C++ snapshot, records
`structural-native:model-add-frame3d-member.v1`, retains the complete upstream provenance, and
rewrites direct provenance to `structural-native-model-editor`.

The edited bytes are strictly reparsed and cross the C++ semantic validator again. Contiguous
indices, dangling references, zero length, unsupported geometry, explicit blockers, and all other
ModelIR semantics therefore fail closed before create-new publication. Existing round-trip rows
remain unchanged; no direct source mapping is invented for the two new native-authored entities.

A semantically valid source with an explicit unsupported-feature blocker remains authorable, but
the same blocker and `analysis_ready: false` are preserved. The bounded linear request creator then
refuses that model. An analysis-ready added-member model is accepted by ABI v1.13 C++ assembly and
the generated PCG request, and the CPU linear product converges with typed ResultIR and element
recovery in the product E2E.

Repeated additions from the same source and arguments produce byte-identical artifacts. CPU static
and shared installed-package E2E v23 repeats the operation under an empty `PATH`, proves source
nonmutation, deterministic topology rendering, C++ validation, linear-request creation and native
linear execution, and binds the model, edit receipt, request, and ResultIR identities. Earlier
distribution receipts retain their narrower authority.

## Claim boundary

This closes one connected linear frame3d node/member addition. It does not create arbitrary
elements, materials, sections, constraints, loads, combinations or stages; it does not delete or
reorder entities, select arbitrary formulations/backends/solvers, provide visual manipulation,
infer engineering acceptance, prove protected HIP C2, replace React/TypeScript, or authorize C6.
