# `planar_frame_verified_alpha.v1`

This profile is a public Developer Preview and is explicitly not release-eligible.
It is a source-bound alias over the existing connected planar ModelIR v2 nonlinear
load-control path. It does not add solver breadth or promote existing experimental
solvers.

The currently executable slice accepts 2–128 nodes, 1–256 members, UX/UY/RZ planar
behavior, explicit steel and concrete materials with RC fiber sections, prescribed
settlement, finite rigid offsets, RZ end releases, chord-bound local axes, uniform
local member loads, and explicit mass-per-length global-gravity self-weight. The
result carries the bound execution plan, EquationScaling identity when available,
engineering ResultIR, residual/increment history, checkpoint ancestry, and
factorization diagnostics inherited from the connected-frame path.

Python callers load a `ModelIRDocument` whose `capability_profile` is exactly
`planar_frame_verified_alpha.v1`, then call `analyze_planar_frame(document,
PlanarFrameConfig(...))`. The wheel exposes the equivalent
`structural-analysis-planar-frame` command. Executed analyses return `converged`
or `not_converged` with the matching Boolean. Unsupported routing returns
`status="not_run"` and `converged=null`.

Only `control="load_control"` is supported by this public profile. Direct
displacement-control and arc-length fail closed with the stable reason codes
`planar_frame_direct_displacement_control_experimental` and
`planar_frame_arc_length_experimental`; they remain separate experimental paths.
The reason is recorded under `unsupported_features`, and no silent fallback occurs.

The M1–M5/L1–L2 corpus under
`verification/planar_frame_verified_alpha_v1/` currently contains checksum-bound,
deterministic fixture definitions only. It is not execution, platform-parity,
external-V&V, crash/OOM, or release evidence. The profile grants no design-code,
final-design, commercial, or release-readiness authority.
