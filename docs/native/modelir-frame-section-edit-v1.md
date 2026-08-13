# ModelIR frame-3D section edit v1

`structural-workbench model-edit-frame-section` is a bounded native edit surface for the six SI
parameters of one existing ModelIR v2 `frame_3d` section. It publishes a new, independently
verifiable artifact set and never modifies the source file.

```text
structural-workbench model-edit-frame-section MODEL.json \
  --section SECTION-ID --area-m2 A --iy-m4 IY --iz-m4 IZ \
  --torsional-constant-m4 J --shear-area-y-m2 AY --shear-area-z-m2 AZ \
  --output-dir EDITED-DIR
```

The option order and vocabulary are fixed. The section identity contains 1 through 128 UTF-8
bytes. Area, both second moments, the torsional constant, and both shear areas must be finite SI
numbers greater than zero. The output directory must not exist and contains exactly canonical
`model-ir.json` and self-hashed `edit-receipt.json` artifacts.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before editing. It selects
one stable section identity from the canonical C++ snapshot and requires exactly
`family_id: frame_3d` and `parameter_set_version: "1"`. It replaces the complete closed parameter
object; it cannot change family, version, identity, element references, topology, or orientation.

Direct provenance is rewritten to `structural-native-model-editor`, prior provenance is retained
under `structural-native:upstream-provenance`, and
`structural-native:model-edit-frame-section.v1` binds the section identity, family, version,
previous and edited SI parameter objects, and source content, semantic, and provenance hashes. A
matching `exact` or `canonicalized` `section` round-trip row is conservatively marked
`approximated`; other rows and already degraded dispositions are not promoted.

The edited document is strictly reparsed and crosses the same C++ semantic validator again before
create-new publication. The receipt binds source and edited hashes, verified C++ snapshot,
analysis readiness, blocker identities, and published model bytes. A missing section, unsupported
family/version, canonical numeric no-op, nonpositive or non-finite parameter, invalid source,
contract drift, or invalid edited semantics fails without publishing the destination. Semantically
valid explicit blockers remain visible and are never promoted away.

CPU static and shared installed-package E2E v19 executes the command twice with an empty `PATH`,
proves byte-identical output and an unchanged source hash, revalidates and renders the edited model,
and records exact model and receipt hashes in the append-only distribution receipt. Frozen v1
through v18 receipts retain their narrower authority.

## Claim boundary

This closes only the six parameters of one existing v1 `frame_3d` section. It does not
create/delete sections, change identities, families or versions, edit RC/fiber/truss/shell section
families, retarget elements, change topology/orientation/releases, select a solver, provide visual
property panels or undo history, or make an engineering acceptance decision. General
section/property editing, React/TypeScript removal, approved HIP C2, and C6 remain open.
