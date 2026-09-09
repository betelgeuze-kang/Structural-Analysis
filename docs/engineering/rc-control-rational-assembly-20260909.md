# Rational accumulation during original RC trial assembly

The retained-strain development probes still fail 89 fixed physical comparisons
across the two complete histories. The next explicit benchmark-only profile,
`force_accumulation="rational"`, retains finite returned material stresses and
tangents through the original force/tangent assembly without intermediate
binary64 sum or product rounding. It requires the existing retained-coordinate,
retained-strain material profile. Public API, CLI and Workbench defaults retain
the existing binary64 assembly.

Section integration uses exact fractions of the finite returned stress, tangent,
fiber area and ordinate. Element integration uses exact Hermite coefficients from
the finite original length and quadrature points, with exact quadrature products.
Each original element response records canonical numerator/denominator identities
for its local force and tangent under `rational-fiber-to-frame.v1`. Section and
member reporting arrays are rounded binary64 projections of those exact values.
The original finite transformation matrix is applied rationally, followed by exact
global addition, external load-factor products, residual subtraction and physical
coordinate scaling. The solver receives the final rounded residual and Jacobian.

Consequently, the reported residual can differ from subtracting already rounded
internal and external display arrays. Its authority is the original rational
assembly and explicit element identities plus the compiled problem, not a second
postprocessing solve or a replacement recovered force. The original rounded
material history updates, branch decisions, native coordinates and compensation,
Newton/control/equilibrium gates, commit/rollback and recovery checks remain in
force. The section contract binds the selected accumulation profile; mixed frame
profiles and mismatched native checkpoint contracts are rejected. Existing modes
retain their original response wire shapes and arithmetic paths.

A separate read-only verifier reconstructs exact section and member force/tangent,
transformation, global loads, residual, Jacobian and reactions from original saved
fiber responses. It uses a separately expressed Hermite polynomial and dense
matrix equations rather than the production accumulation helpers. Every explicit
rational identity and rounded reporting field must match. It performs no material
integration, Newton solve or commit. The older saved-force diagnostic rejects this
profile so that its binary64 replay cannot misrepresent rational assembly.

Focused tests cover cancellation, independent original-record reconstruction,
tampered exact and reported records, scaled-frame finite differences, material
runtime coverage, fresh-interpreter native continuation, contract rejection,
genuine failure rollback and cyclic original recovery. The related frame and benchmark
regression neighborhood passes 556 tests in 453.75 s, including all 11 new
rational-accumulation tests; Ruff and diff checks pass. All resulting local test and
verification costs remain separate from nonlinear path costs.

Before full observation, six existing profiles are compared with the preceding
frozen retained-strain source in fresh processes. Two serial fresh development
probes retain both original geometries, all 242 targets, three original paths,
shared polishing and fixed absolute `1e-10` / relative `1e-8` comparisons. Both
complete physical passes are required before repeated timing qualification.
Negative results are retained, and single observations cannot establish speedup,
independent physical validation, public capability admission or roadmap closure.

## Completed source-bound observations

Numerical source `bb95be6ba24f51b419bbee7f667b6b82170f55c9` is frozen in
427 source/script/test files checked against Git, with actual worker imports
verified. Twelve fresh compatibility workers compare six existing modes with the
preceding retained-strain source `e7ade4536`: 54 short step-file pairs and 18
history/checkpoint pairs remain byte-exact. Their separate work is 108 core calls
and 258 Newton iterations/linear solves. All original input bytes match the
preceding sealed inventory.

Both serial development probes complete all six 242-target paths: **1,452 core
calls / 6,072 Newton iterations and linear solves**. Included polishing work is
1,452 attempts, 1,450 assemblies and 1,157 accepted corrections/linear solves.
Whole parent-process time, including worker and output overhead, is 496.903418 s.

| Geometry | Reference / secant / fresh-reference seconds | Newton-linear counts | Secant failures: member / section / reaction | Full physical pass |
| --- | --- | --- | --- | --- |
| base | 91.746449 / 63.941229 / 92.151194 | 1150 / 777 / 1150 | 17 / 6 / 0 | no |
| long | 87.353048 / 62.416180 / 87.708041 | 1115 / 765 / 1115 | 4 / 1 / 0 | no |

Total fixed-comparison failures decrease from 49/40 to **23/5**, or 89 to 28 over
both geometries. Reaction comparisons now pass in both cases, while seven section
fields exceed tolerance where the preceding observation had none. The original
absolute `1e-10` / relative `1e-8` comparisons remain unchanged and both full
comparisons still fail. Repeated timing is not admitted. Maximum absolute
mixed-SI differences are `3.4924596548080444e-10` and
`2.3283064365386963e-10`; some large-field differences satisfy relative tolerance.
Single elapsed observations and fewer differences do not qualify acceleration.

All original step hashes, parent chains, response-history bindings, work counts,
Newton/control/equilibrium and assembly-binding gates verify. Both reference/fresh
histories and terminal native checkpoints are exact; all six native checkpoints
reopen and serialize exactly. Full comparisons and mismatch locations are
recomputed from complete original histories.

The independently expressed arithmetic verifier reconstructs **1,452 original
frame assemblies, 2,904 member responses and 8,712 section responses**, checking
all exact local numerator/denominator identities and all section/member/global
force, tangent, residual, Jacobian and reaction projections. This takes
30.213241 s, with zero material integrations, Newton solves or state commits.

The separate material audit verifies **121,968 rational coordinate-to-fiber
inputs** and **121,968 returned stresses** using an independently written Hermite
polynomial and 100-digit stress expressions. Of these inputs, 111,574 retain
components lost by binary64 strain rounding. It also performs **121,968 original
base-law integrations** (104,544 concrete / 17,424 steel) at the actual rounded
inputs and native parents. All native state updates and branch decisions match.
The full audit uses two model compilations and no Newton solves or commits. Its
internal loop, including arithmetic reconstruction, is 55.896889 s; whole audit
process time is 57.867850 s. Arithmetic reconstruction is included in these audit
times, not an additional charge. All audit and compatibility costs are separate
from nonlinear probe time. These are arithmetic and native-state checks of the
declared implementation, not independent physical validation.

The sealed local bundle contains **9,915 files / 513,186,136 bytes**, all reread and
hash-checked, at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-rational-assembly.3qcp6t9q`.
Inventory SHA-256:
`a9bfef54599e729f080bf0fd1e42d55d33d4815f18433b736d3c5515021cc36b`.
All workers and the audit are terminal; earlier observations are unchanged.
The [machine summary](rc-control-rational-assembly-20260909.summary.json) retains
source identity, per-path times/counts/native hashes and separate verification.

The remaining original member and section differences require attribution under
the rational assembly contract: finite accepted coordinates, returned material
stress rounding and actual native-parent histories must be distinguished before
selecting another solver change. A counterfactual may diagnose these terms but
cannot replace accepted outputs. Native material-history precision, accepted
acceleration, public API/CLI/Workbench admission, hosted/full-suite acceptance,
independent validation, external dependencies and the full roadmap remain open.
