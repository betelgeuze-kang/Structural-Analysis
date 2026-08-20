# ModelIR constraint prescribed-value edit v1

`structural-workbench model-edit-constraint-value` is a bounded native edit surface for one
prescribed value on one DOF already restrained by an existing ModelIR v2 constraint. It publishes
a new, independently verifiable ModelIR artifact set and never modifies the source file.

```text
structural-workbench model-edit-constraint-value MODEL.json \
  --constraint CONSTRAINT-ID --dof UX|UY|UZ|RX|RY|RZ \
  --value SI-VALUE --output-dir EDITED-DIR
```

The option order and vocabulary are fixed. Translational DOFs use finite metres and rotational
DOFs use finite radians. The constraint identity contains 1 through 128 UTF-8 bytes. The output
directory must not exist and contains exactly:

- `model-ir.json`: strict canonical ModelIR v2 after the edit;
- `edit-receipt.json`: canonical self-hashed `structural-native-model-edit-receipt.v1`.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before editing. It finds the
named constraint in the canonical C++ snapshot and requires the named DOF to be present in that
constraint's existing `dofs` array. It changes only the matching `prescribed_values_si` entry. A
restrained DOF without an explicit entry has an implicit previous value of zero; the editor may
materialize that value but cannot add a restraint.

Direct provenance is rewritten to `structural-native-model-editor`, prior provenance is retained
under `structural-native:upstream-provenance`, and
`structural-native:model-edit-constraint-value.v1` binds the constraint identity, DOF, SI unit,
previous and edited values, and source content, semantic, and provenance hashes. A matching
`exact` or `canonicalized` `constraint` round-trip row is conservatively marked `approximated`;
already `approximated` or `unsupported` rows are never promoted.

The edited document is strictly reparsed and crosses the same C++ semantic validator again before
publication. The receipt binds both source and edited hashes, the verified C++ snapshot status,
analysis readiness, explicit blocking feature identities, and the published model byte hash. A
missing constraint, unrestrained or unknown DOF, canonical numeric no-op (including
signed-zero-only change), non-finite value, invalid source, contract drift, or invalid edited
semantics fails before the create-new output directory is published.

A semantically valid model with an explicit unsupported-feature blocker remains editable, but the
edited model and receipt preserve `analysis_ready: false` and the exact blocker identities. Editing
never promotes solver authority. Repeated edits with the same source and arguments produce
byte-identical artifacts.

CPU static and shared installed-package E2E v18 runs execute the edit twice with an empty `PATH`,
revalidate and render the edited model, prove the source hash is unchanged, and bind the identical
edited-model and receipt hashes in the append-only distribution receipt. Frozen v1 through v17
receipts retain their narrower authority.

A separate source-built bounded product slice now composes this editor with Frame3D linear CPU
execution: the edited prescribed value enters `F_a - K_ac u_c`, terminal recovery retains the exact
constrained displacement, and Workbench Run -> Resume -> Compare -> Report matches an independent
axial oracle. That composition is documented in
`modelir-frame3d-prescribed-support-linear-v1.md`; it is not installed-package v18 execution proof.

## Claim boundary

This closes only a prescribed value for one DOF already restrained by one existing constraint. It
does not add or remove restrained DOFs, create or delete constraints, retarget a constraint to
another node, edit multi-point constraints, select a solver, provide undo history or visual
manipulation, or make an engineering acceptance decision. General property/material/section/load,
constraint-topology editing, broad visual editing, React/TypeScript removal, approved HIP C2, and
C6 remain open.
