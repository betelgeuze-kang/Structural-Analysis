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
