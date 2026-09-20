# Opt-in adaptive failed-target continuation

`benchmark_rc_control_seed_paths(..., frozen_parent_continuation=True,
continuation_on_failure=True, continuation_all_failed_targets=True,
continuation_adaptive=True)` enables the separate experimental profile
`experimental-frozen-parent-adaptive-failed-target-64.v1`.

Ordinary native execution must fail with known work and exact rollback before
recovery starts. The adaptive search holds the original material parent fixed,
starts with fraction increment 1/16, doubles a successful increment up to 1/16,
and halves after failure without advancing the accepted fraction or seed. It
stops below 2^-20 or at 64 trial calls and returns no seed on those limits or
unknown work. A returned seed must still pass the ordinary original-target solve.
Intermediate accepted trial checkpoints never advance the material history.
All native tolerances and original requested targets remain unchanged.

Existing fixed-sixteen profiles and defaults are preserved. The new option
requires explicit all-target failure recovery and has its own profile identity.
The report declares at most 64 additional calls per requested target; the
single-parent comparison declares the corresponding bound of 70 total calls.
The original-artifact replayer propagates the new profile and arithmetic options.

## Fixed-source full-path confirmation protocol

After focused regression checks pass, freeze the implementation source. Reuse the
short/40 mm L-frame with N3 UY targets (-20, -40, +20) mm and constant N3 FY =
-25 kN. Run binary64 and complete retained arithmetic, both with terminal polishing,
in two reversed arithmetic/arm orders: four comparisons / sixteen paths with a
fresh reference in each. Preserve all original failed attempts, adaptive trials,
full histories, work and source provenance. Compare repeated complete proposal
histories and final checkpoints. Failed references prohibit qualified speed
ratios. This does not promote a production policy or supply independent physics.

## Focused implementation checks

The strategy/replay, parent-step, initial-residual and warm-start suites pass
111 tests in 132.07 s. They include actual complete short/40 mm paths in both
arithmetic profiles and fresh original-artifact replays, invalid option preflight,
no-trial behavior on successful ordinary paths, and the adaptive parent-step
budget. Synthetic scheduler tests cover minimum increment, the 64-trial limit and
unknown-work interruption; they are control-flow tests, not physical evidence.
Ruff and `git diff --check` pass. Complete adaptive proposals still have incomplete
ordinary references, so these tests do not establish a qualified speed ratio.
