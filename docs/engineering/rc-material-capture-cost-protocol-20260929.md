# Predeclared RC committed-material capture cost experiment

This is a synthetic development-only cost-reduction experiment. It starts from
draft #496 head `82d1510c2b42ef56ef7f837af2c710b5fe9b4db9`. The source
policy remains the unpromoted pooled metadata policy identified by
`sha256:748ca448dc4aacea36bea9d6672057aa3d76c15ff1d8ac6db6f9ff53e40e8e48`.
The original development packet is `structural-policy-runtime-q8fxqvd8`, with
inventory SHA-256 `e47a96cf34c52b3a088f15eba08a890e745da6096a7a43b5127f78df8ca2b7c0`.
Only its fifteen authored A–E **training** inputs and the already declared F/G
synthetic development cases may be read. The two reserved validation/holdout
cases must not be read or executed. All seventeen cases derive from one public
example template; their identifiers do not establish independent source
lineage.

## Fixed comparison

The candidate changes only the optional committed-material snapshot producer:
it retains native-checkpoint validation and the exact feature names, values,
source/parent hashes, JSON bytes and snapshot hash, while replacing a redundant
parse and re-hash of freshly produced JSON with equivalent direct validation.
The original producer remains selectable as the baseline. Neither arm changes
the solver, policy weights, model, load history, guard, acceptance tolerances,
fallback or accepted-state authority. A mismatch in output bytes, malformed
state admission, failed response-history check, unknown solver work, or missing
slot makes that observation ineligible.

Use F and G exactly as `CASE_SPECS` in
`scripts/run_rc_cost_gate_development_pilot.py`: 2.85/2.30 m and 3.10/2.55 m
members, their original twelve reversing targets, 20 kN preload, retained
twofold refinement arithmetic, and the original 0/1/11 target guard. Each
mode/case/repetition is a separate fresh Python process and runs reference,
secant, guarded learned proposal, and fresh reference from that case's genesis.
Three repetitions per case and mode give twelve declared slots and 48 full
paths, zero warmups. Rotate the three benchmark arm orders as in #496. Alternate
the baseline/direct process order across six matched case/repetition pairs.
Preserve each failed, incomplete or unrun slot in the twelve-slot denominator.
Source revision, case/model/request hashes, arm order, mode, policy/guard hashes,
all tolerances and the schedule must be frozen in a plan before the first slot.

Record separate wall/CPU scopes for parent process launch-through-exit where
available, input loading/preflight, each full benchmark, each path, committed
material capture, proposal callback, guard callback, numerical attempts,
recovery and read-only audit. Report actual proposal and fallback counts and
known/unknown solver work. These scopes overlap and must not be summed. Prior
label generation, fits and selection are historical costs, not zero costs; this
campaign does not establish full AI lifecycle break-even.

Compare the direct/baseline capture and complete proposal-path times within
each matched pair, then report per-case distributions and their equal-case
means. Recompute the existing diagnostic cost-gate statistic separately for
each mode: equal-case mean of each case's three guarded-proposal/secant whole-path
ratios, strictly below `0.99`, with all slots fully verified and at least one
seeded learned invocation per slot. Keep all six ratios in each mode visible.
This is a fixed diagnostic rule, not policy promotion. The V6 cohort showed a
positive mean invocation-time difference even under hypothetical zero capture
and proposal overhead; reducing capture cost alone need not make learned starts
faster. No favorable synthetic result authorizes reserved evaluation, physical
accuracy, generalized speedup or net savings claims.
