# Retained rational trial strain with original native state updates

The actual direct-fiber attribution places finite accepted-coordinate differences
and force arithmetic above native history at the remaining 154 failed fields.
This explicit development profile tests another precision boundary: conversion
of the direct rational fiber strain to binary64 before material stress evaluation.
It does not predict that removing this boundary alone eliminates all failures.

Paired `material_arithmetic="retained-strain"` and
`fiber_strain_evaluation="retained-coordinate"` require exact-rational beam strain.
The original local coordinate expression, including native compensation, remains
a Fraction through the selected material call. Original rounded total strain is
still reported and passed to the original base material to determine its branch,
plastic multiplier, native damage/history and dissipation updates. Those updates
are kept verbatim. The response additionally records the exact trial numerator
and denominator and `retained-rational-strain-stress80-original-state.v1`.

Elastic steel stress evaluates `E * (exact_trial_strain - parent_plastic_strain)`
rationally before one stress rounding. For yielded steel the existing stable
stress expression retains its original rounded multiplier and flow direction,
then adds the exact affine branch correction `E*H/(E+H) * (exact - rounded strain)`.
Original native state and tangent fields stay unchanged; the final yield metric
uses the returned stress and original next state. This is not a replacement
exact plastic return map or arbitrary-precision native plastic history.

Concrete uses the original rounded max-history choice, tension/compression,
threshold, history-tolerance and derivative-underflow branches. For a selected
current-strain history, its stress-only history retains the exact trial magnitude;
otherwise it uses the original parent history. The selected exponential survival,
stress and tangent are evaluated at 80 decimal digits with a fixed half-even
context independent of ambient Decimal settings. Original damage-cap survival
floor and unclipped-derivative cap semantics remain. The native updated history,
damage and energy still come from the original rounded-input integration. This
finite stress evaluation is not a claim of universally correctly rounded nonlinear
constitutive response or a repair of native material-state precision.

The selected section/frame contracts include the profile and decimal precision.
The existing original section material loop consumes the retained Fraction and
keeps rounded strain arrays for compatibility with reporting. Every selected
material call includes the original base integration and additional stress work;
whole-path costs retain both. Original force/tangent assembly, Newton, control and
equilibrium gates, native commit/rollback and exact transition recovery remain
in use. No hidden state, accepted-force replacement or public API/CLI/Workbench
admission is introduced. Existing generalized/direct attribution diagnostics do
not pretend to evaluate this retained-input profile; saved-force replay supports
it through the declared compiled contracts.

The related neighborhood passes 213 tests in 36.69 s, including 16 new tests:
sub-ulp elastic steel response, original cyclic native updates and branches,
independent 100-digit concrete stresses, ambient Decimal-context independence,
three same-parent element finite-difference checks, material timing coverage,
fresh-interpreter native continuation, mixed-profile rejection, exact failure
rollback, cyclic original recovery and saved-force replay. Ruff/diff checks pass.

Before full work, five existing modes will be compared with frozen preceding
source in fresh processes. Two serial fresh three-arm development probes then
retain both original geometries, all 242 targets, shared polishing and fixed
absolute `1e-10` / relative `1e-8` physical comparisons. Only both complete physical
passes admit further repeated timing qualification. Negative probes and every
additional verification cost remain visible. All roadmap requirements remain open
until their own evidence is established.

## Completed source-bound development probes

Numerical source `e7ade453688bb0851d2d69ce3ba0758ea8cf4b01` is frozen in
423 files verified against Git, with actual worker import paths checked. Ten
fresh compatibility workers compare five existing modes against preceding frozen
source `282116505`: 45 short step-file pairs and 15 short history/checkpoint pairs
are byte-exact. This costs a separate 90 core calls / 214 Newton iterations and
linear solves. All original model/request bytes match the preceding inventory.

Both fresh serial development probes complete all six 242-target paths: **1,452
core calls / 6,079 Newton iterations and linear solves**. Polishing is included:
1,452 attempts, 1,446 assemblies and 1,164 accepted corrections/linear solves.
The parent-process time is 393.162760 s, including worker and output overhead.

| Geometry | Reference / secant / fresh-reference seconds | Newton-linear counts | Secant failures: member / section / reaction | Full physical pass |
| --- | --- | --- | --- | --- |
| base | 71.493030 / 50.861709 / 71.735373 | 1159 / 766 / 1159 | 35 / 0 / 14 | no |
| long | 68.570427 / 49.880658 / 69.039662 | 1118 / 759 / 1118 | 28 / 0 / 12 | no |

Total failures decrease from 79/75 to **49/40**, or 154 to 89 over both geometries.
The absolute `1e-10` / relative `1e-8` full-history comparisons remain unchanged
and fail in both cases. Repeated timing is therefore not admitted. Maximum
absolute differences across mixed SI fields are `4.656612873077393e-10` in each
geometry. Single observations and fewer mismatches do not qualify acceleration.

Every original step hash, parent chain, history binding, Newton/control/equilibrium
and binding gate, and invocation count verifies. All reference/fresh-reference
histories and terminal native checkpoints are exact. All six terminal checkpoints
reopen and serialize exactly with the original codec; physical comparisons and
mismatch locations are recomputed from complete original histories.

A separate audit verifies **121,968 rational fiber inputs** against a separately
written Hermite polynomial and their recorded numerator/denominator identities.
At 111,776 accepted fiber trials, the retained input differs from its rounded
binary64 value. **121,968 returned stresses** match a separate 100-digit evaluation
of the declared steel/concrete stress policies. This is independent arithmetic
cross-checking of the declared profile, not independent physical validation.

The same audit makes **121,968 original base-material integrations**, 104,544
concrete and 17,424 steel, using the actual rounded inputs and original parents.
All native state updates, parent identities and branch decisions match exactly.
Maximum retained-vs-original-rounded stress differences are
`9.186926737606095e-15` MPa (concrete) and `8.526512829121202e-14` MPa (steel);
maximum tangent differences are `9.094947017729282e-12` MPa and zero. It performs
two model compilations, no Newton solves and no commits. Its internal audit loop
takes 25.010656 s; full audit-process elapsed time, including startup and source/
input verification, is 26.923621 s. These calls and times are separate from the
nonlinear probes and compatibility work.

The remaining fixed-comparison failures keep original force/tangent accumulation
precision in scope. Any next change must execute during original trial assembly,
retain the new rational input identity and native parent contracts, and repeat
complete fixed comparisons with all costs. Counterfactual or rounded replacement
forces cannot substitute for accepted original recovery. No native history repair,
accepted acceleration, learned-policy benefit, independent physics qualification
or public API/CLI/Workbench admission is claimed.

The sealed local bundle contains **9,787 files / 488,523,035 bytes**, all reread and
hash-checked, at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-retained-strain.378uz_ln`.
Inventory SHA-256:
`0628acd78438aa2678487908745cc5431adf07ec424289c7c4615e5d3f00c6ca`.
All workers and the audit are terminal; previous observations remain intact.
The [machine summary](rc-control-retained-strain-20260909.summary.json) retains
source identity, per-path times/counts/native hashes and verification boundaries.
The full roadmap, hosted/full-suite acceptance, independent corpus, licensing,
hardware, owner and R1/R2 requirements remain open.
