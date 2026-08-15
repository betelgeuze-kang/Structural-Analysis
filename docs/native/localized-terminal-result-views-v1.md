# Localized terminal result views v1

`structural-workbench` exposes three deterministic terminal result views in the closed locale set
`en-US` and `ko-KR`:

```text
structural-workbench result-view --workspace <DIR> --locale <en-US|ko-KR> \
  [--channel <top-displacement|drift-ratio|base-shear|residual-inf>] \
  [--start-step <N>] [--count <1..256>]
structural-workbench result-deformed-view --workspace <DIR> --locale <en-US|ko-KR> \
  [--projection <isometric|xy|xz|yz>] [--step <N|1>] [--scale <F64>]
structural-workbench reaction-view --workspace <LINEAR-DIR> --locale <en-US|ko-KR> \
  [--start-row <N>] [--count <1..256>]
```

Omitting `--locale` preserves the original `en-US` bytes. The public Rust methods without a locale
remain compatibility wrappers for that same English output. Localized methods change labels and
operator guidance only: exact scientific-notation response values, selected coordinates, case and
profile selectors, ResultIR identity, model/request/state/execution/checkpoint hashes, C++ semantic
snapshot verification, and the fixed-guided adapter execution receipt remain visible. The linear
reaction view additionally preserves actual ModelIR node IDs, constrained global DOFs, exact
internal/external/reaction components, mixed force/moment units, source result/recovery hashes,
assembly identity, and its CPU ABI/fallback receipt.

All three views are UTF-8, contain no ANSI escape byte, do not depend on color, and append a SHA-256
identity computed over every preceding output byte. The response view preserves one-based step
indices because ResultIR v1 has no `dt_s`; it never reconstructs time. The deformed view applies
the surface selected by the durable profile: legacy NDTHA uses only the selected fixed-guided
global-X top displacement, while ModelIR-linear has one terminal state and applies the verified
UX/UY/UZ field to bounded two-node centerlines. The linear view reports RX/RY/RZ but does not apply
rotations, element curvature or rigid offsets.

Installed CPU and approved-ROCm distribution E2E execute the Korean top-displacement response and
Korean isometric deformed view twice with an empty `PATH`, require byte determinism and English/
Korean identity separation, reject ANSI output, and prove the durable workspace is unchanged. The
append-only distribution v12 receipt binds both Korean view hashes; frozen v1 through v11 receipts
retain their narrower authority.

Source-level ModelIR-linear clean-environment E2E separately proves repeated English/Korean bytes,
strict-ModelIR and normalized-MGT direct/restart parity, exact single-state semantics, session
nonmutation, frozen pre-reaction compatibility, invalid-step and preterminal rejection, and
receipt/source tamper rejection. Installed static/shared and rootfs publication for that linear
deformed surface remains an explicit successor receipt gate.

The reaction view's source-level clean-environment E2E separately proves repeated English/Korean
bytes, direct/restart parity, one-based windows of at most 256 rows, session nonmutation, legacy
missing-artifact rejection, wrong-profile rejection, and receipt tamper rejection. Installed
distribution publication remains an explicit later gate and is not inferred from that test.

This is a bounded C5 linear-text result-inspection slice. It is not WCAG conformance, assistive-
technology certification, general application localization, arbitrary Unicode certification,
arbitrary-topology or interactive 3D exploration, engineering acceptance, design-code compliance, C6, or
authority to remove the React/TypeScript surface.
