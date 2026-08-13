# Localized ModelIR terminal topology view v1

## Closed surface

`structural-workbench model-view` accepts the closed, case-sensitive locale set `en-US` and
`ko-KR` in addition to the existing `isometric`, `xy`, `xz`, and `yz` projections:

```text
structural-workbench model-view MODEL.json --locale en-US --projection isometric
structural-workbench model-view MODEL.json --locale ko-KR --projection isometric
```

Omitting `--locale` preserves the original `en-US` bytes exactly. The compatibility Rust
functions likewise delegate to `WorkbenchReportLocaleV1::EnUs`; localized callers use
`render_model_topology_view_file_localized` or `render_model_topology_view_localized`.

Only fixed presentation labels and guidance change. Schema tokens, projection names, capability
profiles, booleans, blocker and analysis-type identifiers, SI coordinates, node/element IDs,
connectivity, flags, canvas cells, and content/semantic/provenance identities remain stable data.
Both locales strictly parse ModelIR and render only the verified Rust -> C ABI -> C++ canonical
snapshot. Each output is deterministic UTF-8 without ANSI escapes and self-hashes every preceding
byte.

## Installed-product evidence

CPU and protected ROCm distribution E2E run the installed binary in an empty `PATH`. They prove
that default English and explicit `en-US` are byte-identical, two `ko-KR` runs are byte-identical,
English and Korean identities differ, and the Korean output retains the verified C++ marker and
analysis-readiness value. The append-only distribution v13 receipt binds the Korean identity;
frozen v1 through v12 receipts keep their narrower authority.

## Open boundary

This is a bounded linear terminal localization slice, not general localization, arbitrary-Unicode
coverage, WCAG or assistive-technology conformance, graphical accessibility, visual editing,
perspective/3D exploration, result contouring, solver selection, or engineering approval. It does
not change the open React/TypeScript removal, approved HIP C2, clean-machine publication, or C6
gates.
