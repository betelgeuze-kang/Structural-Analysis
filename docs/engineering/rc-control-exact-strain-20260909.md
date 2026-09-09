# Experimental RC control with exact finite-coordinate strain evaluation

The preceding original-parent diagnostic attributes all 1,598 failing section
moments to M2 coordinate and kinematic-evaluation differences, with zero material
parent contribution at those failed values. This implementation tests one part
of that finding through full Newton and recovery, rather than replacing saved
forces after an analysis.

`StatefulFiberBeam2D(strain_evaluation="exact-rational")` evaluates axial strain
and Hermite curvature as rational functions of the supplied finite binary64
coordinates, member length and integration coordinate. Only the final two strain
values are rounded to binary64. Exact coefficients are cached in a bounded
1,024-entry geometry cache. Unsupported profiles, nonfinite inputs and final
strains outside binary64 range are rejected. No near-zero strain or force is
clamped. Constitutive response, tangent, global assembly, Newton tolerances,
control constraints and commit/rollback authority remain the original routines.

This is an explicit experimental arithmetic profile. Default `matrix` evaluation
keeps its previous contract and output shape. The exact profile changes member
and compiled problem identities and records its profile in element responses and
the benchmark's input/comparison identity. Parents from a different arithmetic
profile are rejected. Exact-profile state validation re-evaluates the finite
coordinates and requires identical strain values; the default state gate is
unchanged. Trial and recovery use the same profile and original parent.

`benchmark_rc_control_seed_paths(..., strain_evaluation="exact-rational")`
selects the profile before any output or numerical work. It applies equally to
reference, secant, any requested proposal and fresh reference. The saved-section
diagnostic now reads the declared benchmark profile and verifies its native
compiled contract before restoring parents. Its independent rational expression
can check that kinematic-evaluation contributions vanish under the exact profile.
This does not expand the public control API, CLI, Workbench or learned-policy
admission boundary. Exact arithmetic cannot reconstruct precision absent from
accepted coordinates, and the unchanged binary64 material/global routines still
have their own rounding effects.

The initial 19 profile tests pass, including independent 100-digit polynomial
comparisons, finite-difference tangent verification, mixed-parent rejection, exact
state-strain binding and a real six-target cyclic reference/secant/fresh-reference
study. An initial broader neighborhood passes 278 tests in 38.03 s. Subsequent
saved-diagnostic integration is verified separately; overlapping counts are not
independent test coverage. Default compatibility against an immutable preceding
source and complete 242-target observations remain required before any numerical
improvement claim.

The predeclared full-path experiment uses the same two physical geometries,
original 242-target/two-reversal history, shared terminal polishing and fixed
`1e-10` absolute / `1e-8` relative comparisons as the preceding shared-polishing
study. Each geometry runs three serial fresh processes with alternating
reference/secant order and a separate fresh reference. All 18 paths and 4,356
core target entries are planned counts until original outcomes prove completion;
Newton, linear, material, verification, I/O and wall/CPU costs must remain visible.
No failed baseline, tolerance or accepted original history is overwritten.

The final profile/diagnostic integration selection passes 85 tests in 10.37 s,
including all 19 profile tests. The saved-response diagnostic independently
reproduces the exact-profile original sections and observes zero kinematic-
evaluation contribution in the six-target test. Ruff and diff checks pass.
The profile sources and tests trigger the topology regression lane and belong
to core CI ownership. Hosted execution and full-suite acceptance are separate.

## Frozen observation status

The full experiment is running at frozen implementation
`d81cd8e9033024afcd4f800e63217ecc9abbe091` in
`/tmp/structural-rc-exact-strain.iwbm112h`. Its 413 source/script/test files and
three unchanged inputs are copied before execution. The raw root is not yet
sealed and the planned six-process outcome is not yet complete.

Separate preceding-source (`31932bece`) and candidate-source processes first
verified the default profile: nine original three-target step files, three
response-history/native-checkpoint pairs and six nonlinear cyclic element
responses are byte-exact. This verifies the observed default outputs, not timing
identity or every possible input.

The first base-geometry repeat completes all three 242-target paths and has an
exact reference/fresh-reference history and checkpoint. Its secant comparison
still fails at 1,425 values with maximum absolute difference 2.3283e-8 in mixed
SI fields. No accepted acceleration or repaired solver is established. Remaining
predeclared repeats continue without a restart; all original failure observations
remain unchanged. [Live source-bound status and completed reports](rc-control-exact-strain-20260909.summary.json).
