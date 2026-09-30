# RC control section error attribution

The completed seed/learning observations retain strict force and moment comparison
failures. A saved-stress summation-only diagnostic did not remove them; exact
arithmetic on finite accepted coordinates also found nonzero curvature. The next
diagnostic separates current-coordinate, kinematic-evaluation and material-parent
contributions while leaving every original accepted state and tolerance intact.

`scripts/diagnose_rc_control_section_error.py` reads one complete original
reference/candidate study and recompiles its unchanged model. For every section
at every target it restores the original reference and candidate material parents
through the native round-trip checked codec. Original stored generalized strains
reproduce the entire original section response, including all fiber responses,
tangents and trial states, before a diagnostic result can be emitted. Original
path identities, schedules, committed problem bindings and input bytes are checked.
The output must be new and outside the original study.

Hermite axial strain and curvature are evaluated as exact rational expressions
of the original finite local coordinates, length and quadrature coordinate, then
rounded once to binary64. This is neither the exact continuum solution nor a
higher-precision material trajectory. Eight actual section integrations per point
use each original parent with four strain choices: original reference, rational
reference, rational candidate and original candidate. All diagnostic children
are discarded; original parents must remain byte-exact. No Newton solve or
accepted-state commit is made.

Two telescoping orders allocate the observed candidate-minus-reference resultant
difference (N/Nm) to reference kinematic evaluation, finite-coordinate difference,
candidate kinematic evaluation and parent-history difference. One changes strain
under the reference parent before changing parent; the other changes parent first
and strain under the candidate parent. Nonlinear interactions can change this
allocation, so neither order is a unique causal explanation. Their component sum
residuals are retained separately. This is a counterfactual constitutive diagnostic,
not an equilibrium-verified repair or new performance/physical acceptance.

The predeclared full-path application uses the first complete reference/secant
pair from each of the two shared-polishing geometries, plus reference/secant and
reference/learned pairs from the completed cyclic-learning validation geometry.
Every pair includes all 242 original targets, both members and all three section
integration points. Original tolerances remain `1e-10` absolute / `1e-8` relative.
The original sealed bundles are read-only. New diagnostics, logs, source identities
and input hash verification will be stored separately; original solver work is
not rerun or relabeled as diagnostic work.

Local validation passes 66 related tests in 7.87 s, including nine new diagnostic
cases, a real three-target cyclic study, exact original section replay, preserved
nonlinear parent effects, order dependence, invalid kinematic inputs and rejection
of a tampered original resultant. Initial harness mistakes (string instead of a
Path, dictionary resultants indexed as an array, and a mistyped test filename)
are retained in development logs. Ruff and diff checks pass. The diagnostic and
tests are registered with the topology regression and core ownership lists;
registration is not evidence of an executed hosted or full-repository suite.

## Completed original-path application

At committed diagnostic source `31932bece43ef9bf07e8b25bfd50397f7783657f`, four
serial child processes completed all four predeclared comparisons. All 412 frozen
source/test/script files match their manifest and immutable Git blobs. Every one
of the 487 files read per comparison matches its original preexisting sealed
inventory before the diagnostic and stays unchanged afterward. This includes
original inputs from numerical sources `3f6c952d5` and `889e78c2b2`; those solver
observations were not rerun.

The application verifies **11,616 entire original section responses**, performs
**46,464 section integrations / 650,496 constituent integrations**, and makes
zero Newton solves or accepted-state commits. Separate wrappers counted every
actual section, concrete and steel integration from model compilation through
diagnosis, and exactly match the reported evaluation counts. Four model
compilations and all decoding, integration, hashing and reporting costs remain
part of the retained diagnostic execution. Serial parent wall time is 57.424 s;
this is diagnostic cost, not a benchmark of an improved solver.

| Original comparison | Failed section moments | Unique largest finite-coordinate contribution | Largest coordinate contribution (Nm) |
| --- | --- | --- | --- |
| Base geometry, secant | 424 | 204 | 3.987e-9 |
| Longer geometry, secant | 423 | 337 | 2.643e-9 |
| Validation geometry, secant | 396 | 316 | 2.154e-9 |
| Validation geometry, learned | 355 | 294 | 1.752e-9 |

All **1,598 failing section values are M2 moments**. There are no failing section
axial forces in these four comparisons. At these failing values the parent-history
contribution is exactly zero in both telescoping orders, and the two allocations
are identical. The finite-coordinate contribution is the unique largest term in
1,151 failures; ten further failures tie it with a kinematic-evaluation term.
Reference and candidate kinematic-evaluation effects reach 2.722e-9 / 3.119e-9 Nm
in the base case. Signed terms can cancel; each group's maxima need not occur at
the same target. Every recorded component-sum residual is zero across all fields
and points in this application. The nonlinear unit case separately demonstrates
that different material parents can affect allocation order; zero here is an
observed property of these failing M2 sections, not a general material theorem.

This narrows the next correction to precision of accepted coordinates and their
strain evaluation for these cases. It does not prove a change to a matrix dot
product alone will fix them: exact finite-coordinate strains still differ, and
coordinate-driven and evaluation-driven effects coexist. A subsequent repair must
retain the original physical tolerances and verify full reference recovery,
member forces, reactions and material histories under the changed formulation.
No material-memory reset, force clamping, tolerance widening or replacement of
an accepted state is justified by this diagnostic. Global force/reaction mismatch
attribution and an equilibrium-verified numerical repair remain open.

[Complete component groups, counts and source-bound evidence](rc-control-section-error-20260909.summary.json).
The separately sealed diagnostic bundle contains 446 files / 21,409,803 bytes;
all files were reopened and checked. Inventory SHA-256 is
`41ee841e8fdb649d798cf32faeb98c3e6ebaa336c5c615fd15403eda84e40568`.
The original large evidence roots remain unchanged. These are local consistency
checks, not external authentication, raw-artifact retention or independent physics.
