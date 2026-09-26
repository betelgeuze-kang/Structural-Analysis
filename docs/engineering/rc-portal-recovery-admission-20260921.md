# Portal recovery study stops at public-profile admission

**2026-09-27 update:** A separate, explicit experimental two-fixed-endpoint direct-control profile now admits the original portal model. Its scope and full 20 mm software observation are recorded in the [follow-up note](rc-public-two-base-portal-control-20260927.md). The rejected packets and findings below remain the original study record; they are not rewritten as completed comparisons.

A planned development study constructs a 4 m by 3 m, three-member portal from the existing RC material/section definitions, with twelve concrete layers, two fixed bases, N4 horizontal reference loading and constant -25 kN vertical forces at both roof nodes. Three intended amplitude conditions are 20/40/80 mm, with reversal targets -A/2, -A, +A/2. Two repeats and two recovery modes would give twelve comparisons / 48 paths. These are authored conditions on one geometry, not independent buildings or experimental data.

No comparison returned and no complete path was produced. The first generated input was rejected because its descriptive metadata field was unsupported. After using the accepted `case_id` metadata field, the compiler rejected the two-base support arrangement: `rc_fiber_frame_support_count_unsupported`. Both twelve-row rejection packets are preserved, including the driver's `unknown_work=true` flags; no failed attempt is silently replaced with a successful result.

The current `nonlinear_fiber_frame._compile` explicitly requires a connected unbranched acyclic serial chain and exactly one fully restrained endpoint. `benchmark_rc_control_seed_paths` calls that compiler and rejects blockers before its numerical arms. The direct-control benchmark therefore does not currently admit this two-support portal, even though it fits the numerical node/DOF count. This is input capability rejection, not evidence of nonlinear nonconvergence or sparse performance.

The separate public `planar_frame` profile supports connected ModelIR load-control cases but explicitly rejects direct displacement control and arc-length with experimental reason codes. The repository also contains a separate corotational fiber displacement-control assembler. Neither its existence nor prior proportional-load portal tests establish a public constant-axial cyclic recovery path. Substituting proportional load would change the requested experiment; removing one support would change the topology. Neither workaround is used.

This identifies an integration gap between the serial-chain RC direct-control research path and broader connected planar analysis. Further extension must define the element formulation, support/load admission, accepted/restarted history contracts and independent verification boundary explicitly. No compiler guard, public capability claim or existing verification status is relaxed here. The recent 128-path recovery results remain two L-frame model results and must not be generalized to portal or multistory direct control.

## Preserved packets

- `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-portal-recovery-i1duj8d3`; inventory SHA-256 `7e292b741b180d78f6f2bffd940d878352fdb3d9c249f48bc3e8dbdcf9eadbf6`; compiler reason `rc_fiber_frame_metadata_unsupported`.
- `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-portal-recovery-cy56u8c4`; inventory SHA-256 `61a80d4d577a899ef6e974b462c4650b04f44214c9afa98c9fc77c6919319408`; compiler reason `rc_fiber_frame_support_count_unsupported`.

All inventory entries were reread. [Machine-readable admission record](rc-portal-recovery-admission-20260921.summary.json). Compiler reasons were inspected separately from the runner’s generic `supported RC model required` error; the original outputs remain unchanged.
