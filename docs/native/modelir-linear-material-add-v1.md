# ModelIR linear-elastic material addition v1

This C5 slice creates one v1 `linear_elastic_isotropic` material without changing any existing
element reference. The installed command is:

```text
structural-workbench model-add-linear-material MODEL.json \
  --material NEW-MATERIAL-ID --elastic-modulus-pa E \
  --poisson-ratio NU --density-kg-m3 RHO \
  --output-dir ADDED-MATERIAL-MODEL
```

## Contract

Rust strictly reads the bounded source ModelIR. The new material identity must be a unique portable
UTF-8 identifier with 1-128 bytes. Elastic modulus must be finite and greater than zero, Poisson
ratio must be finite and strictly between `-1` and `0.5`, and density must be finite and
nonnegative. All values use the ModelIR SI contract.

The operation appends exactly one material with the next contiguous index, law
`linear_elastic_isotropic`, parameter-set version `1`, null `source_id`, and empty extensions. Its
state schema is fixed to `stateful: false`, `state_update_epoch: none`, and
`supports_trial_commit_rollback: true`. Other constitutive laws, nonlinear or history-dependent
state, section creation, member assignment, reference editing, deletion, and material editing are
outside this command.

Both source and edited models cross Rust -> C ABI -> C++ semantic validation. The edited canonical
model carries `structural-native:model-add-linear-material.v1`, complete upstream provenance, and
the exact source content/semantic/provenance identities. Existing round-trip rows and explicit
blockers remain unchanged; creating an unreferenced material never promotes analysis readiness.

Publication is create-new and atomic. It emits `model-ir.json` plus a self-hashed
`structural-native-model-edit-receipt.v1` binding the new material ID/index, law/version, complete
SI parameter object, exact state schema, source input hash, source and edited hashes, C++ snapshot
status, analysis readiness, blockers, artifact hash, and claim boundary.

## Product evidence

Focused Rust E2E repeats the operation byte-for-byte, proves source nonmutation, and rejects a
duplicate identity, invalid physical ranges, non-finite values, existing destinations, and invalid
source semantics without publishing partial output. Blocked models retain their blocker set and
complete round-trip map.

The test then composes the existing frame3d-member and homogeneous fixed-constraint creators twice:
the baseline member references the original material and the candidate member references the new
material. Both models use identical geometry, section, support, `LC_WEAK` request, and exact
`[0,-10000,0,0,0,0]` active external load. Native CPU execution completes for both, the new
material changes the recovered displacement, and fallback 0 is preserved.

The recovery-to-sparse-ResultIR binding retains exact vector self-validation and exact active
solution mapping. Its cross-artifact residual-summary comparison uses the same bounded FP64 parity
rule as sparse ResultIR validation, so recurrence-versus-physical-residual roundoff is accepted
while material divergence outside that tolerance fails closed.

Static and shared installed-package E2E v27 repeats the material/member/support/request/run
composition with an empty `PATH`, validates through the installed C++ boundary, compares repeated
artifact trees, and binds the material-added and composed model identities plus receipt, request,
ResultIR, and recovery identities into the authoritative CPU distribution receipt.

This is not general material or section authoring, element assignment editing, nonlinear material
state, arbitrary solver selection, engineering acceptance, approved HIP C2, React/TypeScript
removal, or C6 decommission.
