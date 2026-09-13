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

After the numerical observation at `aedcf1b0e`, a focused binding guard also
rejects a metrics-only compensation declaration when the actual solution has no
compensation. This malformed-result change is not part of the frozen numerical
source. Its new rejection/rollback check and the control-step neighborhood pass
**68 tests in 11.23 s**; the seven terminal-twofold tests are included. Valid
observed records already satisfy the audited presence/absence bindings. The full
numerical observations were not rerun for this invalid-metadata guard.

Before full observation, seven preceding profiles must reproduce short saved
steps and native histories exactly in fresh processes. Two serial development
probes then retain both original 242-target geometries, all three paths, shared
one-attempt polishing, fixed absolute `1e-10` / relative `1e-8` comparisons and full
solve/recovery costs. Only both full physical passes admit repeated timing. Prior
negative observations, boundary trials and failed local checks remain visible.
No independent physical validation, public admission or roadmap closure is implied.

## Completed full-history observations

Numerical source `aedcf1b0efcf12f7f2bcd7d6c5a50db74b847f03` is frozen in 431
Git-verified source/script/test files, with actual worker imports checked. Fourteen
fresh workers compare seven preceding modes with the original rational-assembly
source `bb95be6ba`: 63 short step-file pairs and 21 history/checkpoint pairs remain
byte-exact. Their separate cost is 126 core calls and 306 Newton iterations/linear
solves. All original model/request bytes remain unchanged.

Both serial probes complete six 242-target paths: **1,452 core calls / 6,354
Newton iterations and linear solves**. This includes 1,452 original one-correction
polishing attempts and assemblies, with **1,439 accepted corrections and additional
linear solves**. Whole parent-process time, including workers/output, is 502.388586 s.

| Geometry | Reference / secant / fresh-reference seconds | Newton-linear counts | Failed member / section / reaction fields | Full physical pass |
| --- | --- | --- | --- | --- |
| base | 92.769936 / 64.495296 / 93.233862 | 1201 / 820 / 1201 | 2 / 0 / 1 | no |
| long | 88.723188 / 63.053130 / 88.579937 | 1171 / 790 / 1171 | 0 / 0 / 0 | yes |

Total fixed-comparison failures decrease from **28 to 3**; full passes increase
from **0/2 to 1/2**. The absolute `1e-10` / relative `1e-8` rules are unchanged.
The maximum absolute mixed-SI difference is `2.3283064365386963e-10` in each
geometry; larger nonzero fields may satisfy relative tolerance. Both main cases
must pass to admit repeated timing, so the declared three repeats per geometry
remain unexecuted. These single observations do not qualify acceleration.

The remaining base failures all occur at target index 146: both M1 local axial
end forces and the corresponding horizontal support reaction express the same
signed axial imbalance. Reference and secant M1 end-i forces are
`5.325454871304651e-11` and `-6.956875971514331e-11` N, a difference of
`1.2282330842818983e-10` N. Every section comparison passes in both geometries.

All original gates, work counts, native parent chains and step/history bindings
verify. Reference/fresh histories and terminal checkpoints are exact, and all six
native checkpoints reopen and serialize exactly. Every one of the **1,452 terminal
candidate high/low pairs** is checked in rational arithmetic against the exact sum
of its original finite coordinate and correction. All **1,439 accepted pairs**
agree with the explicit solver compensation and selected coordinate records;
rejected compensation does not enter the selected state.

Independent arithmetic reconstruction verifies 1,452 original frame assemblies,
2,904 members and 8,712 sections, including exact force/tangent identities and
reported residual/Jacobian/reaction projections. It takes 31.113195 s and performs
no material integrations or Newton solves. The separate material audit verifies
121,968 rational fiber inputs and 121,968 stresses against exact/100-digit
expressions, and executes 121,968 original base-law replays (104,544 concrete /
17,424 steel). All original native state updates and branch decisions match.
The complete audit uses two compilations, no Newton solves and no commits. Its
internal time is 57.302836 s and whole process time is 59.252405 s; the arithmetic
reconstruction time is included, not an additional charge.

## Additional original-parent refinement probe

At the remaining base target, both original paths had accepted their first
terminal correction. A separate local probe preserves each original pre-step
native material parent, reconstructs the accepted assembly exactly, and applies
one additional retained-coordinate correction from the stored next Newton
increment. It creates trial assemblies only and does not commit a new history.

Both candidates strictly improve residual and pass the original residual/increment
gates. Reference residual infinity norm decreases from 5.368453624154143e-14 to
1.51843381738653e-14; secant decreases from 6.956875971514332e-14 to
6.029924555133495e-14. Their trial M1 axial difference becomes
**5.49829521466714e-11 N**, below the fixed absolute tolerance. This supports
implementing bounded additional refinement in the original solver; it is not a
replacement accepted result or proof that both complete histories will pass.

This extra probe costs one compilation, four frame trial assemblies, 336 selected
plus 336 nested material calls, and two dense linear solves. Its measured function
time is 0.199090 s; separate process startup time was not recorded. No nonlinear
Newton solve or state commit occurs. These costs and the preimplementation boundary
probe costs remain separate from full-path and audit costs.

The main terminal bundle contains **10,049 files / 522,854,203 bytes**, all reread
and hash-checked, at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-terminal-twofold.7sz3md_7`;
inventory SHA-256
`147807671357a7d223c0bae11d4885380c0ae879b226c34951f2754f7ca9efa8`.
The separate successful boundary bundle is sealed at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-newton-boundary.zvlzbj06`
(5 files / 24,928,648 bytes; inventory
`dedb71385c6369e5cd7543b2c6a8029c6c41b1a85fd89d311269910726dff72c`).
Its initial failed attempt is separately sealed and retained. All numerical
processes are terminal; previous evidence is unchanged.

The [machine summary](rc-terminal-twofold-20260909.summary.json) retains source,
per-path timings/counts, compensation verification, separate diagnostic costs and
acceptance limits. Next work must implement a bounded additional retained-coordinate
terminal refinement with the same original native parent, strict improvement and
original gates, retaining all attempts and full recovery costs. Both full fixed
comparisons must pass before repeated timing. Public admission, hosted/full-suite
acceptance, independent physics/corpus, licensing, hardware, owner, R1/R2 and the
full roadmap remain open.
