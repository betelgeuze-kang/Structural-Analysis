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

## Completed development observation

Numerical source `2821165054f1107ca512fc428830d8f156b55ffd` is frozen in
421 files verified against Git. Eight fresh compatibility workers compare four
existing modes with preceding source `de7b0d634`: 36 short step-file pairs and
12 short history/checkpoint pairs are byte-exact, costing a separate 72 core calls
and 172 Newton iterations / linear solves. Actual module paths and revisions are
checked; original model/request bytes match the preceding sealed inventory.

Two serial fresh probes complete all six original 242-target paths: **1,452 core
calls and 6,068 Newton iterations / linear solves**. Shared terminal polishing is
included: 1,452 attempts/assemblies and 1,153 accepted corrections/linear solves.
Parent-process elapsed time is 370.898585 s, including worker/output overhead.

| Geometry | Reference / secant / fresh-reference seconds | Newton-linear counts | Secant failures: member / section / reaction | Full physical pass |
| --- | --- | --- | --- | --- |
| base | 67.751039 / 48.095360 / 67.969775 | 1151 / 769 / 1151 | 54 / 0 / 25 | no |
| long | 64.234526 / 46.841901 / 64.414865 | 1118 / 761 / 1118 | 51 / 0 / 24 | no |

Compared with the preceding stable-stress observation, total failures decrease
from 263/244 to **79/75**, or 507 to 154 across the two geometries. The fixed
absolute `1e-10` / relative `1e-8` comparisons still fail in both cases, so further
repeated timing qualification is not admitted. Maximum absolute differences over
mixed SI fields are `6.984919309616089e-10` and `4.656612873077393e-10`.
Single-probe times include the direct kinematic work and do not qualify acceleration.

Original Newton/control/equilibrium/binding gates, complete parent chains, original
step hashes, step-to-history bindings and work counts verify. All reference/fresh
histories and terminal native checkpoints are exact; all six terminal checkpoints
reopen and serialize exactly using the original codec. Full comparisons and
mismatch locations are recomputed from the saved original histories.

A separate audit verifies **121,968 accepted fiber strains** against a separately
written exact rational Hermite polynomial including native coordinate compensation.
It then performs **121,968 original base-material integrations** at those actual
inputs and original parents: 104,544 concrete and 17,424 steel. Every native state
update, parent binding and branch decision matches the selected stable-stress
trial. This is same-input state preservation, not proof of identical histories
between reference and secant. Stable-vs-base maximum same-input stress differences
are `9.186926750840985e-15` MPa (concrete) and `5.684341886080802e-14` MPa (steel).
The audit makes two model compilations, no Newton solves and no state commits.
Its internal record/material/strain loop takes 21.152454 s; whole audit-process
elapsed time, including startup and source/input verification, is 23.170224 s.
Both costs remain separate from the nonlinear observation.

The remaining failures must next be attributed under this actual direct-fiber
profile, separating accepted-coordinate and persistent material-history effects.
Earlier attribution counts cannot be assumed unchanged after new original trials.
No further state-precision repair, accepted acceleration, learned-policy benefit,
independent physics validation or public API/Workbench admission is claimed.

The sealed bundle contains **9,662 files / 462,488,048 bytes**, all reread/hash-checked,
at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-direct-fiber.84pa6t3b`.
Inventory SHA-256:
`e4eec3542f60c42b59cbd1b0c819fa5665aa071aca73653981cee98df60b38c5`.
All numerical workers and the audit process are terminal; earlier observations
remain unchanged. The [machine summary](rc-control-direct-fiber-20260909.summary.json)
retains source identities, path times/counts/native hashes and verification limits.
Published-head hosted/full-suite acceptance remains unproven; independent corpus,
licensing, hardware, owner, R1/R2 and the full roadmap remain open.
