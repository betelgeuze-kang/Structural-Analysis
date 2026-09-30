# Constant RC loads with accepted preload and retained coordinates

The small-displacement RC problem now supports an explicit immutable
`constant_external_loads` pattern. The physical external load is
`F_constant + lambda * F_reference`. Constants are included in the problem hash;
changing or omitting them invalidates checkpoints from the other problem.
The empty default preserves the existing contract and numerical results.

Both binary64 and rational-force assembly include the constant vector before
forming residuals and support reactions. The derivative with respect to lambda
remains the proportional reference vector alone. The reference-force norm takes
the maximum of the two pattern norms and one; opposing loads cannot cancel the
normalization scale. Existing relative tolerances remain unchanged. Rational
assembly adds the exact constant force before rounding, retaining small residuals
that would be lost by separately rounded load multiplication and addition.

`solve_stateful_fiber_frame2d_constant_load_preload` performs one actual
force-controlled solve at lambda zero from a native virgin checkpoint. Only a
successful, parent-bound equilibrium becomes the preload state. The new
constant/native-coordinate force path also checks the final assembly against
Newton's reported residual before commit. Direct displacement control refuses
an epoch-zero parent when constant loads are present. A failed preload therefore
cannot silently become the start of a lateral test.

The existing force-step adapter now supports increments from native twofold
parent coordinates and compensated terminal assembly/commit. Its initial guess
remains an absolute-coordinate proposal, converted to an increment when the
native profile requires it. Refinement and polishing must still be explicitly
compatible; no fallback silently changes the arithmetic profile. The existing
Newton solver, constitutive laws, fixed-chord formulation, commit/rollback and
checkpoint codecs remain the numerical authority.

Static learned model features include declared constant load components and a
separate loading-law context. Existing proportional-only policies therefore
cannot silently interpret constant-load inputs as their original profile.
The current v1 execution-topology arrays contain only a proportional pattern;
that boundary now rejects constant-load problems rather than omitting the new
loads from its evidence. Extending those arrays, recovery receipts and public
request/model-input formats is still required. This is an internal solver
capability, not completed public or Workbench integration.

## Verification and original-version comparison

A seven-file regression selection passes **234 tests in 67.92 s**, including
existing frame, control, checkpoint, topology, learning and feature behavior.
Additional constant-load tests cover an intentionally failed nonlinear preload,
a ready Newton result with a mismatched final assembly, and rational load
cancellation. The final **15 constant-load tests pass in 6.08 s**; the preceding
feature selection also passes its 39 existing feature tests. Selections overlap.

Initial fixture failures exposed omitted explicit polishing configuration, an
incorrect damage-metric lookup, and an elastic single-iteration preload that
correctly converged. These fixtures were corrected: failure coverage now uses an
explicit over-capacity synthetic load, and damage is read from member responses.
No numerical tolerance was relaxed. Four touched numerical/feature modules pass
mypy. Seven execution-topology mypy errors are reproduced in the archived original
`87a6f6df7` source and remain pre-existing; the full five-module type check is not
claimed green. Ruff and diff checks pass.

A separate frozen-source observation runs the original and current code in fresh
processes with the same legacy force/control inputs. Their complete serialized
results are exactly equal: **679,582 bytes**, including problem/checkpoint
identities, original histories and solver metrics. The original source is archived
from Git rather than taken from another mutable checkout. This comparison covers
that declared legacy fixture, not every possible model.

## Actual constant-load observation

The new observation uses an authored two-member, 3 m RC cantilever with constant
axial compression of 600 kN and proportional lateral reference load of -10 kN.
It is **not a reconstructed U3 experiment**. Each arithmetic profile performs
one preload, one intentionally failed control attempt, four accepted displacement
targets `[-0.0001, 0.0001, 0.01, -0.005] m`, and one exact restart comparison.
All original result payloads and the native restart checkpoint are retained.

| Observation | Binary64 | Retained arithmetic |
| --- | ---: | ---: |
| Constant-profile solver calls | 7 | 7 |
| Preload displacement error against declared elastic EA formula | -8.13e-20 m | 0 m at binary64 projection |
| Applied axial force at all four accepted lateral targets | -600 kN | -600 kN |
| Largest relative equilibrium residual over those targets | 1.61e-15 | 2.21e-17 |
| Damaged integration points at target 0.01 m | 4 | 4 |
| Exact native restart and assembly equality | yes | yes |
| Worker interval through report writing | 1.191199728 s | 2.651956678 s |

The force-controlled preload uses the same section state that is subsequently
advanced through lateral damage and reversal. Reloading its later native
checkpoint reproduces both the final checkpoint bytes and full assembly payload.
A checkpoint opened against -601 kN constant loading rejects. Intentional failed
control attempts retain the exact original preload parent.

Including both legacy comparisons, the retained packet records **18 core calls,
16 accepted calls, two intentional failed control calls, 75 Newton iterations
and 75 linear solves**. No learning fit occurs. The first worker summary looks
up a nonexistent `iterations` metric and retains null; a separate postprocess
reads `newton_iteration_count` and `linear_solve_count` from every original result
without rerunning any solve. The corrected cost audit preserves that distinction.
Per-call costs, preload runtime counters, checkpoint I/O, parent process intervals
and peak memory remain separate in the machine summary. Source preparation,
postprocessing and sealing are outside worker timings. This single shared-host
observation is not a repeated performance comparison or speedup claim.

All 598 selected current source/test files match Git before and after execution.
All workers and the observer terminate before sealing:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-constant-loads-o0uliqgm`,
**38 files / 6,491,931 bytes**, inventory SHA-256
`072b0c0ccf2fe689ca5bcdc4db6e0a89f8623e4577a4476db6091fec3daedee2`.
The [machine summary](rc-constant-load-preload-20260910.summary.json) identifies
the exact source commit and all original results, including failed calls.

This resolves the internal constant-versus-proportional load-law gap identified
in the [U3 source audit](peer-u3-model-correspondence-20260910.md). Public transport,
full-history execution, commanded/measured correspondence, reinforcement/material
reconstruction, calibration partitions, licensing and independent experimental
verification remain open. The full M1-M5/P1-P3/R1-R2 objective is not complete.
