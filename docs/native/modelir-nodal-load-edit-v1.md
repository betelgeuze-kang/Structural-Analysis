# ModelIR nodal-load edit v1

`structural-workbench model-edit-nodal-load` is a bounded native edit surface for the six SI
components of one existing ModelIR v2 nodal load. It publishes a new, independently verifiable
ModelIR artifact set and never modifies the source file.

```text
structural-workbench model-edit-nodal-load MODEL.json \
  --load-pattern PATTERN-ID --load LOAD-ID \
  --components FX FY FZ MX MY MZ --output-dir EDITED-DIR
```

The option order and vocabulary are fixed. `FX`, `FY`, and `FZ` are finite newtons; `MX`, `MY`,
and `MZ` are finite newton-metres. Both identities contain 1 through 128 UTF-8 bytes. The output
directory must not exist and contains exactly:

- `model-ir.json`: strict canonical ModelIR v2 after the edit;
- `edit-receipt.json`: canonical self-hashed `structural-native-model-edit-receipt.v1`.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before editing. It finds the
named load only inside the named load pattern in the canonical C++ snapshot, replaces exactly the
six `components_si` values, rewrites direct provenance to
`structural-native-model-editor`, and retains prior provenance under
`structural-native:upstream-provenance`. The root extension
`structural-native:model-edit-nodal-load.v1` and the receipt bind both identities, named previous
and edited components, and the source content, semantic, and provenance hashes.

ModelIR v2 round-trip rows identify a load pattern rather than a nested nodal load. Therefore a
matching `exact` or `canonicalized` `load_pattern` row is conservatively marked `approximated`;
already `approximated` or `unsupported` rows are never promoted.

The edited document is strictly reparsed and crosses the same C++ semantic validator again before
publication. The receipt binds both source and edited hashes, the verified C++ snapshot status,
analysis readiness, explicit blocking feature identities, and the published model byte hash. A
missing pattern, missing nested load, canonical numeric no-op (including signed-zero-only change),
non-finite component, all-zero invalid load pattern, contract drift, or other invalid edited
semantics fails before the create-new output directory is published.

A semantically valid model with an explicit unsupported-feature blocker remains editable, but the
edited model and receipt preserve `analysis_ready: false` and the exact blocker identities. Editing
never promotes solver authority. Repeated edits with the same source and arguments produce
byte-identical artifacts.

CPU static and shared installed-package E2E v17 runs execute the edit twice with an empty `PATH`,
revalidate and render the edited model, prove the source hash is unchanged, and bind the identical
edited-model and receipt hashes in the append-only distribution receipt. Frozen v1 through v16
receipts retain their narrower authority.

## Claim boundary

This closes only six-component replacement for one existing nodal load. Target-node replacement is
a separate bounded C5 surface. It does not create or delete patterns or loads, edit self-weight or
load combinations, select a solver, provide undo history or visual manipulation, or make an
engineering acceptance decision. General property/material/section/constraint editing, broad visual editing,
React/TypeScript removal, approved HIP C2, and C6 remain open.
