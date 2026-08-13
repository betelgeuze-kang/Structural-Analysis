# ModelIR linear-elastic material edit v1

`structural-workbench model-edit-linear-material` is a bounded native edit surface for the three
SI parameters of one existing ModelIR v2 `linear_elastic_isotropic` material. It publishes a new,
independently verifiable artifact set and never modifies the source file.

```text
structural-workbench model-edit-linear-material MODEL.json \
  --material MATERIAL-ID \
  --elastic-modulus-pa E --poisson-ratio NU --density-kg-m3 RHO \
  --output-dir EDITED-DIR
```

The option order and vocabulary are fixed. The material identity contains 1 through 128 UTF-8
bytes. `E` must be finite and greater than zero, `NU` must be finite and strictly between -1 and
0.5, and `RHO` must be finite and nonnegative. The output directory must not exist and contains
exactly canonical `model-ir.json` and self-hashed `edit-receipt.json` artifacts.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before editing. It selects
one stable material identity from the canonical C++ snapshot and requires exactly
`law_id: linear_elastic_isotropic` and `parameter_set_version: "1"`. It replaces the complete
closed parameter object; it cannot change the law, version, material state schema, identity, or
references.

Direct provenance is rewritten to `structural-native-model-editor`, prior provenance is retained
under `structural-native:upstream-provenance`, and
`structural-native:model-edit-linear-material.v1` binds the material identity, law, version,
previous and edited SI parameter objects, and source content, semantic, and provenance hashes. A
matching `exact` or `canonicalized` `material` round-trip row is conservatively marked
`approximated`; other rows and already degraded dispositions are not promoted.

The edited document is strictly reparsed and crosses the same C++ semantic validator again before
create-new publication. The receipt binds the source and edited hashes, verified C++ snapshot,
analysis readiness, blocker identities, and published model bytes. A missing material, unsupported
law/version, canonical numeric no-op including signed-zero-only change, invalid parameter, invalid
source, contract drift, or invalid edited semantics fails without publishing the destination.
Semantically valid explicit blockers remain visible and are never promoted away.

CPU static and shared installed-package E2E v19 executes the command twice with an empty `PATH`,
proves byte-identical output and an unchanged source hash, revalidates and renders the edited model,
and records exact model and receipt hashes in the append-only distribution receipt. Frozen v1
through v18 receipts retain their narrower authority.

## Claim boundary

This closes only the three parameters of one existing v1 isotropic linear-elastic material. It
does not create/delete materials, change identities, laws, versions or state epochs, edit nonlinear
constitutive parameters, retarget elements, select a solver, provide visual property panels or undo
history, or make an engineering acceptance decision. General material/property editing,
React/TypeScript removal, approved HIP C2, and C6 remain open.
