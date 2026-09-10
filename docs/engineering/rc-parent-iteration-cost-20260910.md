# Same-parent cost: fewer accepted refinements did not accelerate Newton

The completed [968-parent study](rc-same-parent-cost-study-20260910.md) supplies
same-native-parent and same-prefix comparisons of the frozen learned proposal
and secant. Its original-record audit and seal are complete. All 968 comparisons
pass, all original secant children reproduce, and all **3,872 numerical calls /
17,648 inclusive Newton iterations and linear solves** were recounted. No policy
was fitted or adopted by that study.

## What the complete comparison shows

| Development case | Parents | Secant inclusive iterations | Proposal inclusive iterations | Summed proposal/secant one-step time |
| --- | ---: | ---: | ---: | ---: |
| train-a | 242 | 969 | 969 | 1.023361 |
| train-b | 242 | 870 | 974 | 1.131556 |
| train-c | 242 | 990 | 990 | 1.025590 |
| train-d | 242 | 852 | 852 | 1.027529 |

These times sum separate one-target executions from stored parents. They are not
sequential whole-path timings. Full material capture and policy evaluation are
charged even on abstention; the static rejection optimization is disabled in
this protocol. Therefore this table is not a matched comparison with the
[counterbalanced full-path study](rc-counterbalanced-runtime-20260910.md).

Only train-b receives actual learned proposals: **241**, excluding its initial
target. Of these, **28** have fewer inclusive iterations, **105** have the same
count and **108** have more. All 28 lower-count proposals nevertheless have
higher recorded total one-step time. Only three proposals have lower total time;
none of those three reduces the inclusive iteration count.

## The inclusive count hides two different kinds of work

Source `2d280a399` adds `summarize_rc_control_iteration_cost`. It checks original
step hashes, ordered convergence rows, refinement origins and acceptance,
terminal assembly/linear-solve counters and line-search trials. It separates
primary convergence rows from appended accepted terminal corrections. Rejected
terminal trials retain the assembly work already spent on them.

The solver's existing `iteration_count` and `newton_iteration_count` both include
accepted terminal corrections in these records. Neither is silently redefined.
The new diagnostic reports the components separately and leaves **total solver
assembly calls null**: convergence history alone does not enumerate every
assembly evaluation. It supplies no physical validation, training admission or
performance credit.

The diagnostic was applied to **all 3,872 original numerical step records** and
reconciled their inclusive iteration and linear-solve totals. Among the 241
actual learned proposals:

| Recorded component | Secant | Learned proposal | Difference |
| --- | ---: | ---: | ---: |
| Primary convergence rows | 476 | 596 | +120 |
| Accepted terminal corrections | 391 | 375 | -16 |
| Inclusive convergence rows | 867 | 971 | +104 |
| Line-search trials | 235 | 355 | +120 |
| Terminal assembly calls | 478 | 479 | +1 |

**No actual learned proposal reduces primary convergence rows** in this roster:
121 are equal and 120 are higher. This is a result for these frozen policies and
development cases, not a statement about all learned warm starts.

For the 28 proposals with lower inclusive counts, primary rows total **78 → 79**,
accepted terminal corrections **56 → 27**, line-search trials **50 → 51** and
terminal assembly calls **56 → 55**. In 27 of those 28 comparisons, primary rows,
line-search trials and terminal assembly calls are each unchanged. The remaining
comparison adds a primary row/search trial while using one fewer terminal
assembly. Thus the lower inclusive count mostly records fewer accepted terminal
corrections after the expensive trial assembly was already performed.

## Timing decomposition and the learning decision

Across the 241 actual proposals, total extra time is **8.754587 seconds**:
numerical execution contributes +6.761559 s, material capture +1.267142 s,
proposal processing +0.566264 s, recovery -0.001743 s and remaining path I/O and
bookkeeping +0.161365 s. Under the assumption that numerical execution stays
unchanged, removing feature overhead alone would still leave a numerical cost
increase for this always-propose policy.

The 28 lower-count proposals spend **6.941351 → 6.946613 s** in numerical
execution and **8.949743 → 9.277630 s** in total. Their reduced small linear-system
solve count did not correspond to measured numerical acceleration.

The three lower-total-time observations gain a summed 0.192834 s in this single
shared-host observation. Their numerical execution is slightly longer; the
observed decrease is in recovery and I/O/bookkeeping. The cause is not identified
by these phase timers. A post-hoc chooser with perfect knowledge and zero selector
cost would reduce train-b's recorded summed one-step time by only about **0.29%**.
That is an optimistic envelope over these recorded alternatives, not an
executable policy or a whole-path saving: it reuses secant origins regardless of
earlier choices and omits selector overhead. Timing each parent once also does
not establish repeatable per-parent timing labels.

The next gate must not learn “smaller inclusive iteration count” as if it meant
less expensive computation. This roster contains no positive primary-iteration
example for the current proposal policy. Keep secant as the selected baseline;
test a materially different proposal/target or harder supported cases before
fitting a selector. Any later strategy still needs unchanged accepted-result
verification, explicit feature/inference costs and fresh whole-path evaluation.

## Verification and provenance

The new diagnostic and workflow contracts pass **32 tests in 4.09 s**, including
18 diagnostic cases. A direct retained-coordinate solver fixture supplies nine
real step records; controlled cases distinguish a rejected terminal correction
from genuinely reduced primary work and reject inconsistent/missing counts,
boolean indices, wrong hashes and failed steps. Ruff, scoped mypy and whitespace
checks pass. The whole diagnostic module is included in the independent
development CI job. This does not close full repository CI or external V&V.

The source numerical packet is sealed at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-same-parent-cost-e_rj5919`:
**38,265 files / 1,859,898,767 bytes**, adjacent inventory SHA-256
`7e33f7153577b2be79114abe5ac144a227ff6fd33c258554062675a0d6cb1d2d`.

The separate observer packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-parent-cost-observer-jl23i87y`:
**17 files / 3,977,364 bytes**, adjacent inventory SHA-256
`9e49318e8e9bb64f8e39998a1f26139a98307d2372114c389cc0861aeae37093`.
Its initial timing observations retain their audit-pending snapshot; a later
binding records the completed source audit and seal. All observed files were
matched to the sealed inventory. The full iteration breakdown took 28.719 s and
performed no solver calls or fitting. Both packets were reread before sealing.

The [cost observer](rc-parent-iteration-cost-20260910.cost-observer.py.txt),
[phase observer](rc-parent-iteration-cost-20260910.phase-observer.py.txt) and
[iteration observer](rc-parent-iteration-cost-20260910.iteration-observer.py.txt)
are archived exactly for review. They require the declared local source packets;
they are experiment reproduction records, not general-purpose production CLIs.
