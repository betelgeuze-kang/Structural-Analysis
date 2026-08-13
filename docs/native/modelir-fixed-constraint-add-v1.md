# ModelIR homogeneous fixed-constraint addition v1

This C5 slice adds one closed support-authoring operation without claiming general constraint or
visual model editing. The installed command is:

```text
structural-workbench model-add-fixed-constraint MODEL.json \
  --constraint NEW-CONSTRAINT-ID --node EXISTING-NODE-ID \
  --output-dir ADDED-CONSTRAINT-MODEL
```

## Contract

Rust strictly reads the bounded source ModelIR and accepts only two 1-128-byte UTF-8 identities.
The target must be an existing node with no current constraint, and the new constraint identity
must be unique in the constraint family. The operation appends exactly one contiguous-index
`fixed_dofs` row with ordered DOFs `UX, UY, UZ, RX, RY, RZ`, zero prescribed SI values, null
`source_id`, and empty entity extensions. Partial restraints, nonzero prescribed values,
multi-point constraints, contact, support sets, deletion, and retargeting are outside this command.

Both source and edited models cross Rust -> C ABI -> C++ semantic validation. The edited canonical
model carries `structural-native:model-add-fixed-constraint.v1`, upstream provenance and the exact
source content/semantic/provenance identities. Existing round-trip rows remain unchanged because
the operation creates a new top-level entity rather than modifying an entity mapped from the
source. Explicit source blockers remain visible, and no successful edit promotes analysis
readiness.

Publication is create-new and atomic. It emits `model-ir.json` plus a self-hashed
`structural-native-model-edit-receipt.v1` binding the constraint ID/index/type, target node, closed
DOF mask, zero prescribed values, source input hash, source and edited hashes, C++ snapshot status,
analysis readiness, blockers, artifact hash, and claim boundary.

## Product evidence

Focused Rust E2E composes the connected frame3d-member and N3-UY nodal-load additions, repeats the
fixed-constraint operation byte-for-byte, proves source nonmutation, and rejects missing nodes,
duplicate constraint IDs, overlapping node constraints, invalid destinations, and invalid source
semantics without publishing partial output. It then creates a model-bound CPU linear request and
completes the native solve. Typed recovery proves `active_dof_indices` changes from twelve free
N2/N3 DOFs to exactly N2 indices 6 through 11, the N3 displacement is zero, the recovered
displacement changes, and fallback 0 is preserved.

Static and shared installed-package E2E v25 repeats the complete composition with an empty `PATH`,
validates the edited model through the installed C++ boundary, compares repeated model, receipt,
request, ResultIR and recovery trees, and binds all five artifact identities into the authoritative
CPU distribution receipt.

This is not arbitrary constraint authoring, engineering acceptance, approved HIP C2, React/
TypeScript removal, or C6 decommission.
