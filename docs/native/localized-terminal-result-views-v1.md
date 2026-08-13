# Localized terminal result views v1

`structural-workbench` exposes two deterministic terminal result views in the closed locale set
`en-US` and `ko-KR`:

```text
structural-workbench result-view --workspace <DIR> --locale <en-US|ko-KR> \
  [--channel <top-displacement|drift-ratio|base-shear|residual-inf>] \
  [--start-step <N>] [--count <1..256>]
structural-workbench result-deformed-view --workspace <DIR> --locale <en-US|ko-KR> \
  [--projection <isometric|xy|xz|yz>] [--step <N>] [--scale <F64>]
```

Omitting `--locale` preserves the original `en-US` bytes. The public Rust methods without a locale
remain compatibility wrappers for that same English output. Localized methods change labels and
operator guidance only: exact scientific-notation response values, selected coordinates, case and
profile selectors, ResultIR identity, model/request/state/execution/checkpoint hashes, C++ semantic
snapshot verification, and the fixed-guided adapter execution receipt remain visible.

Both views are UTF-8, contain no ANSI escape byte, do not depend on color, and append a SHA-256
identity computed over every preceding output byte. The response view preserves one-based step
indices because ResultIR v1 has no `dt_s`; it never reconstructs time. The deformed view applies
only the selected fixed-guided profile's global-X top displacement and never synthesizes missing
nodal components.

Installed CPU and approved-ROCm distribution E2E execute the Korean top-displacement response and
Korean isometric deformed view twice with an empty `PATH`, require byte determinism and English/
Korean identity separation, reject ANSI output, and prove the durable workspace is unchanged. The
append-only distribution v12 receipt binds both Korean view hashes; frozen v1 through v11 receipts
retain their narrower authority.

This is a bounded C5 linear-text result-inspection slice. It is not WCAG conformance, assistive-
technology certification, general application localization, arbitrary Unicode certification,
general nodal-field or 3D exploration, engineering acceptance, design-code compliance, C6, or
authority to remove the React/TypeScript surface.
