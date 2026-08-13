# ModelIR node-coordinate edit v1

`structural-workbench model-edit-node` is a bounded native edit surface for one existing ModelIR v2
node. It replaces exactly that node's three SI coordinates and publishes a new, independently
verifiable ModelIR artifact set. The source file is never modified.

```text
structural-workbench model-edit-node MODEL.json \
  --node NODE-ID --coordinates X Y Z --output-dir EDITED-DIR
```

The option order and vocabulary are fixed. Coordinates are finite metres. The output directory must
not exist and contains exactly:

- `model-ir.json`: strict canonical ModelIR v2 after the edit;
- `edit-receipt.json`: canonical self-hashed `structural-native-model-edit-receipt.v1`.

## Validation and provenance

The command strictly parses the source and crosses Rust -> C ABI -> C++ before editing. It edits the
canonical C++ snapshot, rewrites direct provenance to the neutral `structural-native-model-editor`
identity, retains the prior provenance under `structural-native:upstream-provenance`, and records the
operation under `structural-native:model-edit-node.v1`. The operation binds the node identity,
previous and edited coordinates, and the source content, semantic, and provenance hashes. A matching
`exact` or `canonicalized` round-trip node row is marked `approximated` rather than preserving a
false direct mapping claim; an already `unsupported` row is never promoted.

The edited document is strictly reparsed and crosses the same C++ semantic validator again before
publication. The receipt binds both source and edited hashes, the verified C++ snapshot status,
analysis readiness, explicit blocking feature identities, and the published model byte hash. A
missing node, canonical numeric no-op (including signed-zero-only change), non-finite value,
contract drift, or invalid edited geometry fails before the create-new output directory is
published.

A semantically valid model with an explicit unsupported-feature blocker remains editable, but the
edited model and receipt preserve `analysis_ready: false` and the exact blocker identities. Editing
never promotes solver authority.

Repeated edits with the same source and arguments produce byte-identical artifacts. CPU static and
shared installed-package E2E runs execute the edit twice with an empty `PATH`, revalidate and render
the edited model, prove the source hash is unchanged, and bind both output identities in the
append-only distribution receipt.

## Claim boundary

This closes only a provenance-bound, C++-revalidated node-coordinate command. It is not visual
dragging, arbitrary property/material/section/load/constraint editing, topology creation/deletion,
solver selection, undo history, collaborative editing, engineering acceptance, or general desktop
Workbench parity. Deformed/modal/contour exploration, broad visual editing, React/TypeScript removal,
approved HIP C2, and C6 remain open.
