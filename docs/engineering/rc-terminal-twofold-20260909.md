# Retained coordinate correction in original Newton terminal polishing

The complete rational-history attribution identifies finite-coordinate differences
as the largest component at all 28 remaining fixed-comparison failures. A bounded
follow-up examines the 20 original reference/secant steps at all ten failed target
indices. It reuses each saved pre-polishing coordinate, proposed correction and
original native material parent, comparing ordinary versus retained augmented
coordinate addition and ordinary versus retained load-factor conversion.

The original candidate residual is reproduced byte-exactly at every examined
step. Ordinary arithmetic improves the original residual in 9/20 trials. Retaining
the coordinate sum improves 19/20 and reduces median residual infinity norm from
1.1143549497956271e-13 to 1.607312094377384e-14. Retaining only the load quotient
still improves 9/20, with median 1.0704404727315908e-13; retaining both improves
19/20 with median 1.4654071585671975e-14. This is a local boundary probe, not a new
accepted history or evidence that all full-history comparisons will pass.

The boundary probe performs two compilations, 40 original frame trial assemblies,
3,360 selected plus 3,360 nested base material integrations, and 80 dense linear
solves. It makes no nonlinear Newton solve or native commit. Function time is
1.890682 s and whole process time 4.337706 s. Its initial attempt rejected
noncanonical checkpoint JSON before any frame/material/linear trial; that failed
attempt and its one compilation are retained, with elapsed time unavailable.

The implementation therefore adds explicit benchmark-only
`terminal_coordinate_precision="twofold"`. The frame problem contract binds this
selection and requires the existing native twofold/rational assembly profiles.
The benchmark requires original terminal polishing to be enabled. Newton's
ordinary iteration and line search remain in use. At the existing one-correction
terminal attempt, the selected mode splits the exact sum of the finite original
coordinate and correction into canonical high and low components. The original
problem assembles the retained pair and applies the unchanged strict residual
improvement, residual and increment gates. Rejected candidates cannot replace the
converged coordinate. This does not add polishing iterations or change tolerance.

An accepted low component is explicit in the Newton solution, convergence history
and metrics. Final Newton reassembly, control-step assembly, original transition
recovery and native checkpoint coordinates all consume that same pair. Solver,
assembly, compensation and parent bindings must agree before commit. The load
factor still uses the original finite conversion. Original constitutive updates,
force/tangent arithmetic and native schemas remain authoritative; the selected
frame contract distinguishes the experimental precision mode. Default profiles
omit the new optional fields from their wire encodings.

Focused checks include a sub-ulp correction whose high coordinate is unchanged,
rejected-candidate preservation, full cyclic transition recovery, fresh-interpreter
native continuation, profile mismatch, exact failure rollback and rejection of a
one-ulp alteration of the compensation component. Broader regression checks also
exercise original and sparse Newton, existing polishing and RC recovery.

Those regression checks expose an existing v1 checkpoint-collector incompatibility:
its dataclass restore assumed every optional native expansion field was present
in legacy wire payloads. The preceding frozen source reproduces the missing
`free_coordinates_m` error. The collector now uses defaults for fields omitted by
the validated schema. Required fields, unknown fields, canonical bytes and state
hashes remain checked; explicit corruption tests retain these rejection gates.

The related regression neighborhood passes 313 tests in 57.92 s, including
six terminal-twofold checks and the new legacy corruption check. Initial related
results (310 passed/two collector failures in 57.12 s) remain retained.

Before full observation, seven preceding profiles must reproduce short saved
steps and native histories exactly in fresh processes. Two serial development
probes then retain both original 242-target geometries, all three paths, shared
one-attempt polishing, fixed absolute `1e-10` / relative `1e-8` comparisons and full
solve/recovery costs. Only both full physical passes admit repeated timing. Prior
negative observations, boundary trials and failed local checks remain visible.
No independent physical validation, public admission or roadmap closure is implied.
