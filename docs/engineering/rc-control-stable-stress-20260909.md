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
