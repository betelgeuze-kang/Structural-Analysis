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
source and complete 242-target observations are recorded below. These local
checks do not establish an accepted numerical repair.

The predeclared full-path experiment uses the same two physical geometries,
original 242-target/two-reversal history, shared terminal polishing and fixed
`1e-10` absolute / `1e-8` relative comparisons as the preceding shared-polishing
study. Each geometry runs three serial fresh processes with alternating
reference/secant order and a separate fresh reference. The 18 paths and 4,356 core target entries were predeclared. Newton/linear
counts and whole wall/CPU costs, including material response, verification and I/O,
are recorded below; material calls are not separately counted in the main runs.
No failed baseline, tolerance or accepted original history is overwritten.

The final profile/diagnostic integration selection passes 85 tests in 10.37 s,
including all 19 profile tests. The saved-response diagnostic independently
reproduces the exact-profile original sections and observes zero kinematic-
evaluation contribution in the six-target test. Ruff and diff checks pass.
The profile sources and tests trigger the topology regression lane and belong
to core CI ownership. Hosted execution and full-suite acceptance are separate.

## Completed frozen full-path observation

All six serial fresh processes completed at frozen implementation
`d81cd8e9033024afcd4f800e63217ecc9abbe091` in
`/tmp/structural-rc-exact-strain.iwbm112h`. Its 413 source/script/test files match
their manifest and immutable Git blobs. The three original typed input files
match the preceding shared-polishing sealed inventory; the geometry, 242-target
schedule, two reversals, original physical comparison tolerances and shared
terminal polishing are unchanged.

All **18 paths complete 242 targets**: **4,356 core entries and 17,655 Newton/
linear counts**, with no unknown execution work. The 2,910 accepted terminal
corrections, 4,251 extra assemblies and 2,910 extra linear solves are included in
those counts and times. Every reference/fresh-reference history and native
checkpoint is exact, and each case/strategy repeats its history and native
checkpoint byte-exactly across all three processes. Serial parent time is
731.505 s, excluding source staging and separately recorded validation/diagnostics.

| Geometry | Reference median ± sample SD (s) | Secant (s) | Secant Newton/linear count | Full-history pass |
| --- | --- | --- | --- | --- |
| 2.0 / 1.5 m base | 43.353 ± 0.366 | 31.436 ± 0.049 | 743 versus reference 1,123 | 0 / 3 |
| 2.5 / 2.0 m longer | 41.516 ± 0.119 | 30.854 ± 0.024 | 712 versus reference 1,092 | 0 / 3 |

**All six secant comparisons still fail the original physical tolerances.** Base
repeats each contain 1,425 mismatches (964 member-force, 359 section, 102 reaction)
with maximum mixed-SI absolute difference 2.3283064365386963e-8. Longer repeats
contain 1,428 (965 member-force, 355 section, 108 reaction), maximum
9.778887033462524e-9. The preceding matrix-profile counts were 1,616 / 1,464;
changing these counts is not a physical pass or accepted acceleration. The prior
failed observations are retained. Cross-source timing was not interleaved and
cannot establish an isolated arithmetic-profile performance effect.

The saved-record audit verifies every original invocation, returned step, commit
gate, own-prefix context, parent chain and work count. It independently recomputes
all full-history comparisons, mismatch summaries and terminal-identity flags.
At all **26,136 integration points**, the stored strain and section trial-state
strain equal a separate exact-rational Hermite expression of the original finite
local coordinates. This audit performs no compilation, material integration,
Newton solve or refit. It verifies the new arithmetic actually entered and
survived the original solve/recovery paths; it does not prove continuum accuracy.

## Remaining error and separate diagnostic costs

After every main worker exited, the original-parent diagnostic ran on the first
full reference/secant pair of each geometry. Its 23,232 section / 325,248
constituent integrations and 5,808 original section-response verifications are
separate from the main benchmark. Whole-run wrappers count exactly the reported
section/concrete/steel calls. This diagnostic performs no Newton solves or
accepted commits, and its two model compilations and wall/CPU time are retained.

Both kinematic-evaluation contributions are zero in all 11,616 field/order pairs.
The remaining **359 / 355 failing section moments are all M2 moments**. At these
714 failed values, parent-history contribution is zero in both orders; the entire
observed resultant difference is allocated to the changed finite coordinates.
Maximum coordinate-induced moment differences are 2.950972799453666e-9 /
2.170263968537256e-9 Nm. Component-sum residuals are zero. This is an observed
constitutive allocation under the saved original parents, not a unique general
causal theorem or full global force/reaction attribution.

The result rules out kinematic-evaluation rounding as a sufficient repair for
these cases. The next numerical change must address accepted-coordinate precision
and its original checkpoint/recovery binding, while retaining the original
physical tolerances. A higher-precision strain evaluated from the same finite
coordinates alone cannot remove these remaining differences. No coordinate or
force clamping, material reset, tolerance change, learned-policy refit or promotion
of failed comparisons occurred.

## Default compatibility and sealed evidence

Corrected fresh processes using preceding source `31932bece` and candidate source
`d81cd8e90` record their actual imported module paths and distinct source revisions.
All nine original step files, three response-history/native-checkpoint pairs and
six nonlinear cyclic element responses are byte-exact between those sources.
All 412 preceding frozen source/script/test files were checked against Git again.
This verifies the observed default outputs, not timing identity or every input.

The initial compatibility harness incorrectly supplied the candidate SHA in both
benchmark report headers. Those original files remain intact. Two additional
source-corrected runs establish the final compatibility result without rerunning
the main six-process experiment. All four short compatibility studies together
perform 36 core entries / 100 Newton-linear counts; their 24 direct cyclic element
fixture responses are separate. These validation costs are not folded into the
main benchmark's 4,356-entry timing scope.

[Complete source-bound audit, costs, component groups and raw inventory](rc-control-exact-strain-20260909.summary.json).
The sealed local evidence contains **26,899 files / 1,291,902,012 bytes**. Every
file was reopened and hash-checked; inventory SHA-256 is
`ac135debd9f4889008f3915ac872b4bc623554f9c22547fb5eda5585c2025a62`.
The inventory and verification receipt are outside the sealed root. Hashes show
local consistency, not authentication or hosted raw-artifact retention. Prepared
full-repository testing, current-head hosted acceptance, broader numerical repair,
independent corpus/physics, licensing/hardware/owner requirements, current-main R1,
separate R2 and the full roadmap remain open.
