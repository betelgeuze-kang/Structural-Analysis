# Stable material stress evaluation with original state updates

The preceding saved-force diagnostic locates the largest ordered contribution
at retained stress/load differences for 590 of 599 failing twofold end-force and
reaction values. M1 also retains material-history differences. This experiment
changes stress arithmetic during original trials and recovery; it does not
replace saved forces or claim to repair the remaining native history precision.

`material_arithmetic="stable-stress"` selects explicit material and section
implementations in the internal seed benchmark. The default original materials
are unmodified. Steel and concrete first run their original integration to
preserve branch decisions, rounded plastic multiplier, damage/history updates,
dissipation and native state bytes for identical inputs. New responses then
provide the following stresses to the original section/element/frame assembly:

- Elastic steel uses a rational product of the finite modulus and exact
  difference of the supplied finite total and parent plastic strains.
- Yielded steel uses parent backstress plus the signed yield radius and hardening
  increment, rather than subtracting the plastic correction from a large trial
  stress. It retains the original rounded multiplier; the final yield-function
  metric is recomputed from the returned stress and original updated state.
- Concrete recomputes its original finite exponential survival from retained
  maximum strain, avoiding subtraction of the rounded damage from one. Stress
  and tangent products use rational intermediates and one final binary64 round.
  The original nextafter damage cap/survival floor, history-tolerance decisions
  and unclipped-derivative cap semantics remain explicit. This is not a change
  to the original damage/history or dissipation update.

Mathematical constitutive expressions are unchanged in ideal arithmetic, but
these are different finite numerical evaluations. Original steel tangents and
concrete history/derivative branches remain; the concrete tangent is evaluated
from survival. Constitutive state fields and fiber input strains are still
binary64. Parent-state rounding, exponential evaluation, fiber strain projection,
section/element/global sums and Newton coordinate precision remain potential
error sources. No general arbitrary-precision material or native state scheme
is introduced.

The selected section contract includes the arithmetic profile and original
parameter/layout contract. The frame's members and response-projection section
list select the same sections. Old-profile section/frame parents are rejected;
the existing strict native checkpoint codec carries the selected contract.
Material response dictionaries identify `stable-stress-original-state.v1`.
Original Newton, control/equilibrium, parent binding, commit/rollback and fresh
transition recovery keep authority. Every trial pays for the original state
integration and additional stable evaluation; whole-path costs retain both.
Public API/CLI/Workbench and learned-policy admission do not select this mode.

Focused checks cover identical native state updates under cyclic same-input
trials, survival cancellation, original damage-cap/underflow semantics,
perfect-plastic yield stress, same-parent finite-difference tangents, mixed-profile
parent rejection, exact native restart in a fresh interpreter, complete cyclic
reference/secant/fresh-reference recovery and genuine nonconvergence rollback.
The initial related neighborhood passes 162 tests in 21.64 s. Later saved-force
and original-parent diagnostic integration is checked separately. The earlier
short recovery failure exposed a mismatched response-projection section list;
the integration now requires both compiled representations to select the profile.

Before longer numerical work, fresh source-verified workers will compare the
three existing modes (matrix/binary64, exact-strain/binary64 and exact-strain/
twofold) against their preceding implementation for default byte compatibility.
Then two serial fresh development probes retain the original two geometries,
242 targets, shared terminal polishing and fixed absolute `1e-10` / relative
`1e-8` physical comparisons. Each probe runs reference, secant and fresh reference
with the stable material mode and complete original recovery. Only if both probes
pass every fixed full-history comparison will the work expand to repeated timing
qualification. Failing probes remain complete negative observations, with costs
and failures retained. Neither short checks nor counterfactual arithmetic qualify
independent physics, accepted acceleration or release closure.


## Completed development probes

Numerical source `de7b0d634a30921fff7c0b562cf1e0f09d1e13ed` is frozen in
417 files verified byte-for-byte against Git. Actual worker import paths are
checked. Existing matrix/binary64, exact-strain/binary64 and exact-strain/twofold
profiles match the preceding implementation in 27 step-file pairs and nine
complete short history/checkpoint pairs. Those six fresh compatibility workers
cost a separate 54 core calls / 132 Newton iterations and linear solves.

Both serial fresh development probes complete all three 242-target paths: six
paths, 1,452 core calls and 6,048 Newton iterations / linear solves. Shared terminal
polishing attempts 1,452 times, accepts 1,133 corrections and performs 1,452
assemblies / 1,133 linear solves; this work is included in the main path costs.
The parent process takes 344.696893 s, including output and process overhead.

| Geometry | Reference / secant / fresh-reference seconds | Newton-linear counts | Secant mismatches: end forces / sections / reactions | Fixed full-history pass |
| --- | --- | --- | --- | --- |
| base | 61.685435 / 44.259601 / 62.803020 | 1151 / 762 / 1151 | 183 / 0 / 80 | no |
| long | 59.877740 / 44.021779 / 60.270664 | 1112 / 760 / 1112 | 165 / 0 / 79 | no |

All reference/fresh-reference histories and native checkpoints are exact. All six
terminal checkpoints reopen through the original native codec and serialize
exactly. Original step hashes, parent chains, Newton/control/equilibrium/binding
gates and invocation counts are verified from complete records. Full comparisons
are independently recomputed at unchanged absolute `1e-10` / relative `1e-8`
tolerances. Maximum absolute differences across mixed SI fields are
`1.1641532182693481e-9` (base) and `9.313225746154785e-10` (long). Compared with
the preceding twofold observation, section tolerance failures fall from one per
geometry to zero and total counts from 339/262 to 263/244. This is not a full
physical pass. The predeclared repeat-admission condition fails in both cases;
no repeated timing qualification or accepted acceleration is claimed.

A separate original-record audit compiles two models and replays **121,968 original
material integrations** at every saved accepted fiber input and original native
parent: 104,544 concrete and 17,424 steel calls. All original native state updates,
parent hashes and branch decisions match the stable-profile trials exactly.
Maximum same-input stress differences are `9.186926750840985e-15` MPa (concrete)
and `5.684341886080802e-14` MPa (steel); maximum tangent differences are
`7.275957614183426e-12` MPa and zero. The audit takes 19.627653 s, includes the
record checks and native reopen work, and performs no Newton solve or state
commit. This additional audit cost is separate from the development probes.
State preservation is for identical inputs and parents; it does not imply equal
reference/secant histories or a repair of material-state precision.

## Remaining original force differences

The saved-force diagnostic subsequently verifies both complete reference/secant
pairs, with two model compilations, 968 original step-force replays and 7,260
selected force-component comparisons. Instrumented original and stable material,
section, element and Newton entry points confirm zero integration/solve calls;
there are no commits. Its two case times are 6.025674 s and 5.960665 s. All input
hashes remain unchanged, and each ordered rational decomposition closes exactly.

| Geometry | Original member / reaction failures | Exact stored-coefficient arithmetic | Exact geometry coefficients | Exact stored-stress section sums |
| --- | --- | --- | --- | --- |
| base | 183 / 80 | 190 / 83 | 190 / 83 | 205 / 90 |
| long | 165 / 79 | 173 / 83 | 173 / 83 | 154 / 74 |

Among the 507 originally failing selected values, retained stress/load differences
have the largest absolute contribution at 489, and section-resultant rounding at
18, under the declared order. Geometry-coefficient contributions at failed values
are below `2.3e-26` SI. Re-summing stored stresses does not eliminate the failures.
These counterfactuals are not new equilibrium solutions or replacement recovery
outputs. The next scoped investigation must distinguish finite fiber-strain
projection from persistent native material-history precision at failed force
values before further changes to original trial/commit/recovery arithmetic.

The later focused integration suite passes 15 tests in 7.05 s, overlapping the
initial 162-test neighborhood. Default public API/CLI/Workbench admission is
unchanged. The sealed local evidence contains **9,541 files / 465,975,673 bytes**,
all reread/hash-checked, at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-stable-stress.n9nh6e2x`.
Inventory SHA-256:
`de596f3aea3311a39aab61b1c4e0e0e71c371fc7f350c89494c13186787ac8f2`.
All recorded workers are terminal; prior observations remain intact.
The [machine summary](rc-control-stable-stress-20260909.summary.json) retains
source identities, per-path costs, native hashes, diagnostic stages and limits.
Published-head hosted/full-suite acceptance remains unproven; prior inspected CI
input preparation stopped at `legal_approval=False`. Independent validation,
licensing, hardware, owner, R1/R2 and the full roadmap remain open.
