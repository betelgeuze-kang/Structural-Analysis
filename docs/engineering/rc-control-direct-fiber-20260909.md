# Direct coordinate-to-fiber evaluation in original RC trials

The preceding full force attribution identifies generalized-strain evaluation
as the largest ordered term at 61/58 original failures, alongside larger accepted
coordinate and native-history effects. This explicit development profile removes
the separate axial/curvature rounding before fiber projection during the actual
original solve; it does not claim that this alone resolves all force failures.

`fiber_strain_evaluation="direct-coordinate"` requires the existing exact-rational
beam strain and stable-stress material profiles. At every original section trial,
the selected section receives original local coordinates, both native components
when enabled, length, quadrature coordinate and original native material parents.
Rational Hermite expressions are combined with each finite fiber location before
one final binary64 rounding. Rounded axial strain and curvature remain available
as generalized outputs, but material inputs come from the direct expression.

The selected section contract and response carry
`coordinate-to-fiber-single-round.v1`; frame/element contracts include the section
contract. The direct section refuses standalone generalized-strain integration,
and element construction rejects incompatible strain modes. No mutable context,
cache of hidden native state or replacement accepted-force output is used. The
existing section material loop, section/element tangent and force assembly,
original Newton/control/equilibrium/binding gates, commit/rollback and recovery
remain authoritative. An internal explicit fiber vector enters the original
section loop only for the declared coordinate profile. Material instrumentation
counts every selected material trial, including nested original-law work within
the stable-stress call. Direct kinematic computation is part of total path cost.

Native material state updates remain binary64. Existing native checkpoints retain
local high/low coordinates and profile-bound section states; the original codec
rejects mixed contracts and fresh recovery reconstructs the same material inputs.
The finite input supplied to a material still rounds once to binary64. This does
not establish arbitrary-precision constitutive history or coordinate convergence.
Public API/CLI/Workbench admission and default output contracts are unchanged.

Focused checks include independent 100-digit Hermite polynomials, recovery of bits
lost by generalized rounding, three same-parent finite-difference element tangent
checks, complete material timing coverage, fresh-interpreter native continuation,
mixed-mode rejection, exact nonconvergence rollback, cyclic original recovery and
saved-force replay. Generalized-input attribution diagnostics explicitly reject
this profile until their decomposition is adapted; saved-force arithmetic replay
supports it directly.

The planned observation first compares four existing modes against frozen
preceding source in fresh interpreters (matrix/binary64, exact-strain/binary64,
exact-strain/twofold, stable-stress/exact-strain/twofold). It then runs two serial
fresh complete development probes, one per original geometry, with reference,
secant and fresh reference at the unchanged 242 targets, shared polishing and
absolute `1e-10` / relative `1e-8` physical comparisons. Only two passing complete
comparisons admit further repeated timing qualification. Every trial/recovery,
polishing, compatibility and subsequent verification cost remains explicit.

The initial related neighborhood passes 191 tests in 29.55 s. A subsequent
instrumentation guard marks custom coordinate-section overrides without timing
as unmeasured; the overlapping focused/timing suite passes 36 tests in 5.97 s,
including 14 direct-profile tests. The initial saved-force test caught a temporary
syntax error in the diagnostic profile hookup, fixed before these passing runs.
