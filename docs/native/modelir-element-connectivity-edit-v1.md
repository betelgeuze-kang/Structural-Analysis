# ModelIR element-connectivity edit v1

`structural-workbench model-edit-element-connectivity` is a bounded native edit surface for the
ordered two-node connectivity of one existing ModelIR v2 element. It publishes a new,
independently verifiable artifact set and never modifies the source file.

```text
structural-workbench model-edit-element-connectivity MODEL.json \
  --element ELEMENT-ID --nodes I-NODE-ID J-NODE-ID --output-dir EDITED-DIR
```

The option order and vocabulary are fixed. All three identities contain 1 through 128 UTF-8 bytes,
the endpoint identities must differ, and the output directory must not exist. Publication contains
exactly canonical `model-ir.json` and self-hashed `edit-receipt.json` artifacts.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before editing. It selects
one stable element identity from the canonical C++ snapshot, verifies that both requested endpoint
nodes exist, and replaces only the ordered `node_ids` pair. Element identity, type, formulation,
material/section references, orientation, offsets, releases, and all other entities remain intact.

Direct provenance is rewritten to `structural-native-model-editor`, prior provenance is retained
under `structural-native:upstream-provenance`, and
`structural-native:model-edit-element-connectivity.v1` binds the element identity, retained type
and formulation, previous and edited endpoint pairs, and source content, semantic, and provenance
hashes. A matching `exact` or `canonicalized` `element` round-trip row is conservatively marked
`approximated`; other rows and already degraded dispositions are not promoted.

The edited document is strictly reparsed and crosses the same C++ semantic validator again before
create-new publication. That validator remains authoritative for dangling references, identical
endpoints, zero effective length, profile-specific parallel-member rules, graph connectivity,
section/material compatibility, and analysis blockers. The receipt binds source and edited hashes,
verified C++ snapshot, analysis readiness, blocker identities, and published model bytes. Missing
identities, an ordered-pair no-op, invalid source, contract drift, or invalid edited semantics fail
without publishing the destination. Reversing the ordered pair is a real edit because it changes
element orientation semantics. Semantically valid explicit blockers remain visible.

CPU static and shared installed-package E2E v21 executes the command twice with an empty `PATH`,
proves byte-identical output and an unchanged source hash, revalidates and renders the edited model,
and records exact model and receipt hashes in the append-only distribution receipt. Frozen v1
through v20 receipts retain their narrower authority.

## Claim boundary

This closes only endpoint retargeting for one existing two-node element. It does not create or
delete nodes/elements, alter identity, type, formulation, property references, orientation,
offsets, releases or other entities, select a solver, provide visual manipulation or undo history,
or make an engineering acceptance decision. General topology authoring and solver selection,
React/TypeScript removal, and approved HIP C2 remain open. C6 remain open.
