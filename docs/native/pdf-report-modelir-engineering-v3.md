# ModelIR linear engineering-summary PDF v3

## Closed profile

For a current `model_ir_linear_cpu_v1` Workbench session with typed constrained reactions,
`report-export-pdf` now selects an append-only engineering-summary profile. The renderer first
reproduces the durable standard-font sparse PDF and receipt, then strictly verifies the sparse
ResultIR, typed displacement/element recovery, constrained-reaction ResultIR, ReportIR, and exact
Markdown projection before publishing a create-new localized output directory.

The single A4 page exposes the case, maximum global displacement, separate translational-force and
rotational-moment reaction extrema, active residual, Frame3D record count, and signed extrema for
axial force, shear force, torsional moment, and bending moment. Each member extreme names the stable
element index and local-end component. A Truss3D count and axial-force extreme remain present for
the already-supported typed recovery family. Result, recovery, reaction, report, execution, and
checkpoint hashes remain visible on the page.

## Compatibility and receipt

The nonlinear-NDTHA localized v2 profile, standalone sparse-linear localized v2 profile, and both
standard-font v1 PDFs remain byte-identical. A frozen pre-reaction ModelIR-linear workspace without
the optional reaction artifact also retains the sparse-linear v2 export. Only a reaction-bearing ModelIR-linear
session emits
`structural-native-model-ir-linear-engineering-localized-pdf-report-receipt.v3` with profile
`model_ir_linear_cpu_engineering_summary_v1`.

The v3 receipt binds source ResultIR, recovery, reaction, ReportIR, Markdown, PDF, locale, embedded
font, OFL-1.1 license, font provenance, artifact length, authority boundary, and its own canonical
self-hash. Locale changes fixed labels only; every engineering value and identity remains exact and
language-neutral. Repeated exports are byte-identical, `en-US` and `ko-KR` outputs are distinct, and
export does not mutate the durable session.

## Authority boundary

This is a deterministic bounded summary, not a complete member schedule or force diagram. It does
not interpolate distributed-load diagrams, calculate design utilization, select governing load
combinations, assess serviceability, approve supports or connections, or claim engineering
acceptance. Arbitrary Unicode, multipage tables, HTML parity, PDF/A, tagged PDF, PDF/UA,
accessibility conformance, live commercial-solver parity, protected HIP parity, and C6 remain open.
