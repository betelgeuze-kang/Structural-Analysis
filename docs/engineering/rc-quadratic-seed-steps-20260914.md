# Causal three-state extrapolation at retained training parents

Source `5531d4c6182b4475ecf66ec94fe388bb39b0294d` was archived before
execution. This diagnostic tests a different seed direction from the earlier
scalar correction along the secant advance and the gated learned vector.
It uses no current accepted answer, new labels, fit or external data.

## Frozen proposal and scope

Use the original secant-arm parents for train-a/b/c/d at indices
1, 61, 121, 181 and 241. These are repeatedly inspected related training cases,
not an independent evaluation set. For the last three accepted targets
a, b, c and coordinates u, v, w, define d0=(v-u)/(b-a),
d1=(w-v)/(c-b), and q=(d1-d0)/(c-a). At requested target t, propose
w+(t-c)*d1+(t-c)*(t-b)*q. Set the controlled coordinate to t exactly.
Abstain to secant for insufficient history, zero increments, a reversal
within those states or into the next step, or nonfinite output.

Keep the original arithmetic profile, request and tolerances. Alternate the
reference/secant/proposal arm order and run fresh reference last. Each arm
starts from the same retained native parent. All 20 requests are one-step
comparisons; none is a new full cyclic path. Four index-1 cases lack three
accepted states and abstain; sixteen use the quadratic proposal.

## Observed work and time

| Metric across 20 parents | Secant | Proposal |
| --- | ---: | ---: |
| Core calls | 20 | 20 |
| Primary convergence rows | 46 | 45 |
| Inclusive linear solves | 78 | 73 |
| Newton assembly calls | 132 | 129 |
| Sum of arm wall time, seconds | 5.398244403 | 5.373161604 |

Five parents use fewer linear solves, fourteen tie and one uses more.
Three use fewer Newton assemblies, fifteen tie and two use more.
Despite the slightly lower summed wall time, seventeen individual proposal
arms are slower and only three are faster. This single observation per
parent is not a demonstrated runtime advantage. Proposal construction is
included in the arm measurement; per-entry proposal timing remains available.

All four arms together execute 80 core calls, 375 inclusive linear solves
and 673 Newton assemblies. All 60 response comparisons pass at the unchanged
absolute 1e-10 / relative 1e-8 tolerances; all 20 reference/fresh-reference
terminal checkpoints match exactly. The numerical loop takes 26.868737293 s,
excluding the separate audit and source preparation. No failed or unknown
work is omitted.

## Evidence and next decision

The [receipt](rc-quadratic-seed-steps-20260914.json) binds the archived source,
original input inventory, frozen protocol, runner, reports, step artifacts,
events and audit. The audit reconstructs predictions using independent
Lagrange weights, checks report/path/step hashes and recomputes response and
work comparisons. All 1,322 files / 134,725,606 bytes are reread and sealed.

The observation establishes limited causal seed headroom at some retained
parents, with regressions at others. It warrants comparing a fixed optional
quadratic baseline over complete paths before any learned selection experiment.
It does not justify adopting a runtime policy, selecting thresholds from these
results, claiming learned gain, or closing independent project/geometry/history
validation. The full roadmap remains open.

## Reusable optional benchmark function

`rc_control_seed_runtime.quadratic_seed` now exposes this proposal for explicit
callback use. It does not change `secant_seed`, the default callback selection,
solver tolerances or the caller's fallback strategy. Its sign comparisons avoid
underflow when multiplying tiny increments; nonfinite input/overflow abstains.
These additional numerical boundaries are not part of the archived runner's
source. All 20 archived parent proposals nevertheless reproduce exactly after
authenticating the source contexts and recorded events, with zero new solves.

Fourteen focused tests pass in 1.67 s with `PYTHONPATH=src`: nonuniform positive
and negative paths, polynomial reproduction, exact controlled coordinate,
unchanged input context, insufficient/duplicate/reversed history, unused older
states, nonfinite arithmetic and tiny monotone increments. Ruff and diff checks
pass. An initial invocation without `PYTHONPATH=src` failed collection because
the installed package did not contain this checkout's benchmark module; it
executed no tests. The subsequent source-bound invocation is the passing result.

A separate four-case full-path screening run was started from archived source
`259697d6ee946057bec3e8bfbe35ac155929e205` before this helper was added. It uses
the frozen original callback and is still being collected. Brief development
and source-bound unit checks overlapped that run, so its single wall-time
observations are not isolated repeated performance evidence. The later helper
must not be represented as the executed source of that earlier experiment.
