# ModelIR frame-element orientation edit v1

`structural-workbench model-edit-frame-element-orientation` is a bounded native edit surface for
the finite local-axis rotation of one existing ModelIR v2 `frame_3d` element. It publishes a new,
independently verifiable artifact set and never modifies the source file.

```text
structural-workbench model-edit-frame-element-orientation MODEL.json \
  --element ELEMENT-ID --rotation-rad VALUE --output-dir EDITED-DIR
```

The option order and vocabulary are fixed. The element identity contains 1 through 128 UTF-8
bytes and the rotation is a finite SI radian value. The output directory must not exist and
contains exactly canonical `model-ir.json` and self-hashed `edit-receipt.json` artifacts.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before editing. It selects
one stable element identity from the canonical C++ snapshot and requires `type: frame_3d`. It
retains the existing formulation and replaces only `local_axis_rotation_rad`; it cannot change
identity, connectivity, material/section references, formulation, offsets, releases, or topology.

Direct provenance is rewritten to `structural-native-model-editor`, prior provenance is retained
under `structural-native:upstream-provenance`, and
`structural-native:model-edit-frame-element-orientation.v1` binds the element identity, fixed type,
retained formulation, previous and edited radians, and source content, semantic, and provenance
hashes. A matching `exact` or `canonicalized` `element` round-trip row is conservatively marked
`approximated`; other rows and already degraded dispositions are not promoted.

The edited document is strictly reparsed and crosses the same C++ semantic validator again before
create-new publication. The receipt binds source and edited hashes, verified C++ snapshot,
analysis readiness, blocker identities, and published model bytes. A missing element, unsupported
element type, canonical numeric no-op (including signed zero), non-finite rotation, invalid source,
contract drift, or invalid edited semantics fails without publishing the destination. Semantically
valid explicit blockers remain visible and are never promoted away.

CPU static and shared installed-package E2E v20 executes the command twice with an empty `PATH`,
proves byte-identical output and an unchanged source hash, revalidates and renders the edited model,
and records exact model and receipt hashes in the append-only distribution receipt. Frozen v1
through v19 receipts retain their narrower authority.

## Claim boundary

This closes only the local-axis rotation of one existing `frame_3d` element. It does not
create/delete elements, change connectivity, formulation, offsets, releases, references or
topology, select a solver, provide visual manipulation or undo history, or make an engineering
acceptance decision. General model editing, React/TypeScript removal, and approved HIP C2 remain
open. C6 remain open.
