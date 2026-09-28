# Predeclared RC cost-gate development pilot

This is a **synthetic development pilot**, not issue #480's reserved held-out
evaluation. The previously selected strategy is secant. The source pooled
metadata policy was fitted to the 165 original training rows, but its two
whole-path selection candidates failed the unchanged 1% improvement rule.
The pilot may test a new policy-use hypothesis without promoting that policy.

## Frozen question and inputs

The original development packet is
`structural-policy-runtime-q8fxqvd8`, frozen at numerical source
`7a41a1566a605ed1529563619cbc70dbbd0eef17`. Its inventory file SHA-256
is `e47a96cf34c52b3a088f15eba08a890e745da6096a7a43b5127f78df8ca2b7c0`;
selection result hash is
`sha256:ce95bc6c4cd81d815156b733764811366b48153348f8ae108d5ba9bb67df7eac`.
The unpromoted pooled policy hash is
`sha256:748ca448dc4aacea36bea9d6672057aa3d76c15ff1d8ac6db6f9ff53e40e8e48`.
The runner reads only its fifteen `train-a` through `train-e` fold inputs; it
rejects any other original case roster. Original validation and holdout files
are not used.

Two new cases, `development-pilot-f` and `development-pilot-g`, have separate
declared project, geometry and load-history identifiers. They retain the same
model topology, material laws, 20 kN axial preload, solver configuration and
twelve reversing control targets. Their horizontal/vertical member lengths are
2.85/2.30 m and 3.10/2.55 m, respectively. The source code fixes their exact
target arrays in `CASE_SPECS`; the generated plan binds canonical model and
request hashes before execution. The conservative shape and history split
preflight must pass. **All seventeen models are derived from the same authored
public RC example template.** Different IDs, numerical geometry and load-history
signatures do not establish independent source lineage or independent projects.
These two cases are therefore ineligible for issue #480's reserved-cohort claim.

The cost-aligned hypothesis uses information available before material capture.
The experimental guard sends target indices **0, 1 and 11** to deterministic
secant, and permits the learned policy only on indices **2 through 10**. Index 0
had no usable learned seed in the original policy. The first eligible and last
targets had unfavorable work in retrospective development traces. Those traces
nominate this rule; they do not verify that it will save time on the new cases.
The unchanged inference policy can still abstain on any permitted target. No
solver residual, committed response, future target outcome or evaluation timing
may alter the guard. Guard evaluation and its original receipt I/O are charged
inside the proposal path.

## Execution and decision

Run three balanced, fresh-process repetitions of each new case. Each slot runs
reference, secant, guarded learned proposal and a fresh reference from its own
genesis, using the rotated arm orders in the plan. There are **six declared
slots and twenty-four full paths**, zero warmups. Preserve failed/unknown slots
in the denominator. Keep the original `1e-10` absolute and `1e-8` relative
full-history comparisons, reference repeat, solver residual/commit/rollback and
work accounting unchanged. The pilot's diagnostic screen requires every slot to
have complete verified histories, known work and at least one seeded learned
invocation, then an equal-case mean scored proposal/secant path-time ratio below
**0.99**. A favorable pilot cannot select or promote a policy because source
lineage is shared and historical training/selection and complete lifecycle
costs have not been amortized and audited.

Prepare the plan with `scripts/run_rc_cost_gate_development_pilot.py prepare`
from a clean committed source, inspect its hash and case roster, then invoke
each `slot --index 0..5` in a separate process. The plan binds the execution
source commit, packet, policy, roster, guard, order, threshold and denominator
before any new numerical work. Run `audit` only after slots terminate. Preserve
original slot files and the hash inventory. Record external process startup
measurements separately when available; unknown scopes remain unknown rather
than zero. Benchmark, individual arm wall/CPU, guard/capture/inference and
solver work, child enclosing time, and read-only audit time remain separate;
nested timers must not be summed. Historical label/fit/selection costs remain
separate from current evaluation costs. No value from this pilot is used to
modify its gate or to open the reserved evaluation cases.

## Post-run erratum (2026-09-29)

The frozen rule and plan still declare indices 0, 1 and 11 as guard declines,
with `secant` as the configured fallback. The pre-run sentence saying all three
indices were *sent to secant* described the configured fallback, not the
realized first-target strategy. In each original path, index 0 had no prior
accepted state from which to form a secant seed and was recorded as
`abstained_to_reference` with `seed_used=false`; indices 1 and 11 were recorded
as `abstained_to_secant`. This correction does not change the guard bits, the
plan hash, any numerical execution, or the `<0.99` decision rule. A later
read-only audit revision binds the original case hashes, comparison settings
and per-target guard receipts more tightly to the frozen plan.
