# ModelIR frame3d section addition v1

This C5 slice creates one v1 `frame_3d` section without changing any existing element reference.
The installed command is:

```text
structural-workbench model-add-frame-section MODEL.json \
  --section NEW-SECTION-ID \
  --area-m2 A --iy-m4 IY --iz-m4 IZ \
  --torsional-constant-m4 J \
  --shear-area-y-m2 AY --shear-area-z-m2 AZ \
  --output-dir ADDED-SECTION-MODEL
```

## Contract

Rust strictly reads the bounded source ModelIR. The new section identity must be a unique portable
UTF-8 identifier with 1-128 bytes. Area, both second moments, torsional constant, and both shear
areas must be finite SI values greater than zero.

The operation appends exactly one section with the next contiguous index, family `frame_3d`,
parameter-set version `1`, null `source_id`, empty extensions, and the complete six-value parameter
object. Other section families, section editing or deletion, member assignment, reference editing,
topology changes, and visual authoring are outside this command.

Both source and edited models cross Rust -> C ABI -> C++ semantic validation. The edited canonical
model carries `structural-native:model-add-frame-section.v1`, complete upstream provenance, and the
exact source content/semantic/provenance identities. Existing round-trip rows and explicit blockers
remain unchanged; creating an unreferenced section never promotes analysis readiness.

Publication is create-new and atomic. It emits `model-ir.json` plus a self-hashed
`structural-native-model-edit-receipt.v1` binding the new section ID/index, family/version, complete
SI parameter object, source input hash, source and edited hashes, C++ snapshot status, analysis
readiness, blockers, artifact hash, and claim boundary.

## Product evidence

Focused Rust E2E repeats the operation byte-for-byte, proves source nonmutation, and rejects a
duplicate identity, zero/negative/non-finite parameters, existing destinations, and invalid source
semantics without publishing partial output. Blocked models retain their blocker set and complete
round-trip map.

The test then composes the existing frame3d-member and homogeneous fixed-constraint creators twice:
the baseline member references the original section and the candidate member references the new
section. Both models use identical geometry, material, support, `LC_WEAK` request, and exact
`[0,-10000,0,0,0,0]` active external load. Native CPU execution completes for both, the new section
changes the recovered displacement, and fallback 0 is preserved.

Static and shared installed-package E2E v28 repeats the section/member/support/request/run
composition with an empty `PATH`, validates through the installed C++ boundary, compares repeated
artifact trees, and binds the section-added and composed model identities plus receipt, request,
ResultIR, and recovery identities into the authoritative CPU distribution receipt.

This is not general section or material authoring, element assignment editing, reference editing,
arbitrary solver selection, engineering acceptance, approved HIP C2, React/TypeScript removal, or
C6 decommission.
