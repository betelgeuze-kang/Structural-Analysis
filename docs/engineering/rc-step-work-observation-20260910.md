# Step work: separate trajectories do not supply causal learning labels

Source `e2efc9c1269ff71bbded22d663eeb1176e8a97ac` adds
`analyze_rc_control_step_work` and includes its tests in the independent
development CI job. The diagnostic checks complete original comparisons and
ordered input contexts, then reports step work, direction changes, parent hashes
and accepted-coordinate-prefix identities. It executes no solver or fitting.

This addresses the next learning question: which decisions actually reduce
accepted-result work? A smaller displacement prediction error is insufficient.
Likewise, choosing the smaller iteration count from two different trajectories
does not establish an executable policy or a realizable faster complete path.

## Observation from the completed original study

The input is the sealed [secant-abstention study](rc-secant-abstention-20260910.md),
not the currently running counterbalanced experiment. Its eight folds contain
four authored training cases and two ridge candidates. Every path has 242 targets.
Only `train-b` receives actual learned proposals, 241 per ridge:

| Ridge | Secant Newton iterations | Proposal Newton iterations | Fewer / equal / more iterations per target | Matching parent and complete prefix |
| --- | ---: | ---: | --- | ---: |
| 10,000 | 870 | 967 | 32 / 102 / 108 | 2 of 242 |
| 1,000,000 | 870 | 975 | 28 / 100 / 114 | 2 of 242 |

All observed reductions occur after the trajectories have acquired different
origins. The two matching positions are the initial target, which has no learned
proposal, and target index 1. At index 1, the original parent objects and complete
accepted prefixes match; secant uses **2** Newton iterations and the learned
proposal uses **4**, under both policies. These are two policies applied to one
case, not independent physical evidence.

The remaining six folds abstain to secant and have identical work and matching
prefixes at all 242 targets. For the active folds, classifying the two direction
reversals alone is insufficient to explain the total excess: the continuation
segments contribute +96 and +106 Newton iterations, while the reversal segments
contribute +1 and -1. These are retrospective observations, not an adopted gate.

## What is checked and what remains unresolved

The implementation retains every target in the complete-path denominator,
including equal-work and fallback positions. Numerical retry counts are summed.
Failed comparisons, incomplete paths, unknown work and invalid work values reject;
they cannot become zero-cost training examples. Context order, control DOF,
problem identity and requested targets must correspond to the original path.

A matching final parent hash does not imply a matching earlier secant coordinate.
Both are reported separately. The accepted prefix is compared through canonical
serialization, preserving signed zero differences. Material capture fields are
not part of that prefix; native material identity belongs to the separate parent
hash. External source-file bindings remain the original-record auditor's job.
Even matching local identities never grant causal training admission.

An initial actual-source smoke check exposed an incorrect observer assumption:
accepted control coordinates were required to equal commanded targets exactly.
At context 98, original accepted coordinates for a zero target include
`7.069476367493669e-36` and `-1.1708691679929801e-35`. The solver's previously
verified outputs were not changed. The observer now preserves both coordinates
and commands and records their exact-match status. It does not impose a new
numerical tolerance or replace either value with zero.

The next cost-label experiment must execute alternatives from the **same native
parent and the same complete accepted prefix**, with unchanged model, target,
arithmetic and tolerances. Every retry, rollback, feature capture, inference and
verification must remain charged. Cases and target-selection rules must be fixed
before observing those outcomes. A policy trained or selected from such local
comparisons must still pass a subsequent complete-path, independent-case cost
evaluation; isolated step savings cannot close the runtime roadmap.

## Verification and retained evidence

The final focused diagnostic and workflow-contract selection passes **35 tests
in 1.74 s**; Ruff and scoped mypy pass. Initial synthetic tests had eight fixture
indexing errors, corrected before the final run. The independent CI job now
includes 18 complete modules, while the required full-suite gate remains intact.
Hosted results for this new source are not claimed by the preceding 387-test run.

The actual observer verifies **11,638 original files** against the parent packet's
sealed inventory. It matches **7,744 original invocation outcomes** to the path
reports and independently recounts the historical 7,744 core calls and 35,194
Newton iterations/linear solves. These counts describe previous execution;
this observation performs **zero new solver calls and zero fits**. Its elapsed
4.719965741 seconds excludes final output and sealing. This is shared-host
diagnostic cost, not numerical speedup.

The new sealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-step-work-v2cr6ir7`:
**20 files / 4,149,861 bytes**, inventory SHA-256
`b7f67287f8ad876654ff034521f7262e610a7a6f1aed6a0da809daefa2e1b186`.
Original inputs remain in the bound, unchanged parent packet; the new packet
retains their identities, the observer, code, tests, complete diagnostic rows and
same-parent witnesses. Inventory and seal are excluded from payload totals.
[Machine summary](rc-step-work-observation-20260910.summary.json).

No new learned policy, activation gate, causal training dataset, independent
physical validation or full-path speedup is admitted. The ongoing repeated
runtime experiment and its audit supervisor remain unchanged.
