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
