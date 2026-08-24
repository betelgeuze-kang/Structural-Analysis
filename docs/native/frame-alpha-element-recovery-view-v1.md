# Frame Alpha element-recovery view v1

Status: bounded read-only product projection. This document does not grant design, code-check,
commercial, validation, or release authority.

## Input boundary

The view is available only from a complete Frame Alpha Workbench bundle containing the exact
`ModelIR`, `ResultIR`, and `ReportIR` artifacts. A standalone `ResultIR` can still display its
native member-force rows, but it cannot display ModelIR member indices or i/j connectivity.

Before publishing the joined view, the Workbench consumer:

1. rejects duplicate JSON keys and unexpected ModelIR root fields;
2. reproduces the Rust ModelIR content, semantic, and provenance hashes;
3. requires all three hashes, model ID, and selected load identity to match `ResultIR`;
4. requires exact node and member identity coverage;
5. requires unique stable member indices, two distinct existing endpoints, and the bounded
   linear Timoshenko Frame3D formulation; and
6. joins all twelve finite local i/j end-force components by member ID and orders rows by the
   stable ModelIR index.

Any mismatch blocks the complete bundle view. No partial recovery projection is displayed.

## Product behavior

Each verified row exposes:

- member ID and stable index;
- i and j node IDs;
- the explicit `member_local` coordinate frame; and
- `FX`, `FY`, `FZ`, `MX`, `MY`, and `MZ` at both ends in the ResultIR SI units.

Selecting a row uses the existing Workbench member-focus state, so the recovery table and model
viewport share one member identity. This is a projection of already verified native recovery
values; it does not recompute forces in the browser.

## Authority boundary

This view is not a stress contour, section stress recovery, utilization or code-compliance
check, support design, engineering acceptance, external validation, or release-readiness claim.
It carries forward the useful identity and presentation invariants from PR #307 without restoring
the superseded Rust Workbench or its historical distribution authority graph.

