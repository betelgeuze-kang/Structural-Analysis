# Accepted-coordinate divergence precedes the force mismatch

This audit consumes hash-checked original steps, contexts and proposals from
the sealed `22977c86fde3422666a9c38da06ca036f9e29352` yielded-prefix study.
No Newton solve, material integration, new full path or training was executed.

All 16 secant proposals reproduce exactly from the recorded causal contexts
using the documented two-state extrapolation and controlled-coordinate
assignment; the initial insufficient-history proposal is null. The non-null
proposals equal the first recorded Newton coordinates. The first target has
identical accepted reference/secant coordinates. The second target, index 1,
is the first distinct accepted state, with maximum augmented-coordinate
difference 2.168404344971009e-19. This mixed augmented-vector norm is not a
physical displacement error bound.

| Target index | Reference / secant iterations | Reference / secant terminal polishing | Reference / secant final relative residual |
| --- | --- | --- | --- |
| 0 | 2 / 2 | rejected / rejected | 1.61056e-15 / 1.61056e-15 |
| 1 | 6 / 4 | rejected / accepted | 1.70530e-15 / 1.70530e-15 |
| 2 | 9 / 4 | accepted / accepted | 7.82896e-16 / 2.84217e-16 |

At index 1 the reference starts from the previous accepted coordinates,
whereas secant starts from their extrapolation. Their accepted line-search
alphas are `[0.5, 0.5, 1, 1, 1]` and `[1, 1]`. At index 2 the reference uses
`[0.125, 0.5, 0.5, 0.03125, 0.5, 1, 1]` and secant again uses `[1, 1]`.
The two strategies are not taking the same Newton trajectory.

For all 32 original steps, recorded contract, residual, increment, equilibrium
and control gates pass. Relative residuals and final increment norms satisfy
their declared limits. Every accepted polishing candidate strictly improves
the recorded relative residual and supplies the final coordinates; every
rejected candidate leaves the original coordinates. This verifies consistency
of saved acceptance records, not an independent re-solve of their residuals.

At index 2 both final relative residuals are below the solver's 1e-10 limit,
yet recovered response fields fail the separate whole-history comparison.
Normalized equilibrium/increment convergence does not imply agreement of
every dimensional response field under a different absolute/relative contract.
The saved records do not show a bypassed solver gate or incorrect secant
formula. They also do not justify relaxing the response comparison, clipping
near-zero values or ranking either path as physically superior. Paired reuse
cost remains null. Any further arithmetic experiment must retain this failed
binary64 observation and compare under the original response gates.

Read-only audit packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-yielded-newton-origin-tsry4o3a`.
External inventory SHA-256:
`8661533d80819fd48b8a2694241c8477438effd93e6e79e618bb04167302e6cb`.
