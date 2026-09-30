# Separately executed direct-control candidate strategies

Source `24a8e924a2561d54fcfc90158bafb78e57c28b1a` adds
`run_rc_control_candidate_strategy` and the
`structural_analysis.benchmark.rc_control_candidate_strategy_cli` command.
Price order performs no policy-file read, feature extraction or prediction.
Learned order includes policy/training-report validation, features, prediction
and ranking. Each runs its own preparation, canonical candidate changes,
quantity/common-price calculation, complete reference paths, fresh verification
and report persistence. Neither standalone worker accepts oracle results or
executes the other strategy. Price-only calls reject learned artifacts.

The original two-arm comparison remains available with its existing report
shape. Standalone outputs use explicit strategy plan/report v1 schemas; they
are not silently passed to the two-arm Workbench search viewer. Their nested
full design comparison artifacts retain the existing comparison contract.
A process-cohort/Workbench adapter and broader held-out cases remain work.

```sh
PYTHONPATH=src python3 -m structural_analysis.benchmark.rc_control_candidate_strategy_cli \
  --strategy price_order --model baseline.json --request request.json \
  --experiment experiment.json --output price-run \
  --source-revision FULL_40_CHARACTER_SOURCE_REVISION \
  --full-analysis-budget 3 --reuse-line-search-assembly
```

For learned order, supply `--strategy learned_order`, `--policy`,
`--training-report`, and the desired `--ranking-strategy`. The new runtime
sidecar meters CLI argument parsing and input reads through final search report
persistence. It explicitly excludes interpreter/module startup, its own write,
stdout and transport/viewer review. A parent process must measure launch through
exit to include startup and runtime-sidecar output. Neither interval includes
historical training, which is retained separately and never rerun by this CLI.

## Original current-source execution

Before execution, the driver freezes the committed source archive (623 files),
copies five inputs verified against the existing cheaper-boundary inventory,
and declares eight slots: budgets 3 and 11, each in price/learned and
learned/price order. Original ten widths, seven reversing targets, 600 kN
preload, centered policy, synthetic limits/prices and cheaper-boundary ranking
remain unchanged. Assembly reuse is enabled uniformly. BLAS/OMP/MKL threads
are one with the Haswell OpenBLAS core setting. This shared host is not isolated.
The two complete-pool repetitions follow all four limited-budget runs.
No fit, new training label, retry or independent-campaign split occurs.

| Budget including baseline | Order | Price selection | Learned selection | Learned/price parent time |
| --- | --- | --- | --- | ---: |
| 3 | price then learned | None | w047 | null |
| 3 | learned then price | None | w047 | null |
| 11 | price then learned | w047 | w047 | 1.0055699995 |
| 11 | learned then price | w047 | w047 | 0.9959252886 |

The w047 selection has the same scoped synthetic estimate 157.5108 in all
applicable runs. Budget-3 timing ratios remain null because price order has no
verified feasible selection. At budget 11 all candidates are actually evaluated;
the same selected design is freshly verified on both sides. Online time
differences reverse sign with order and do not establish acceleration. The
ratios include subprocess launch through exit, but exclude the one historical
2.761753795 s training interval. No net benefit, amortization threshold,
market-price saving or independent generalization is claimed.

All eight subprocesses exit zero. The numerical parent interval is
60.707557695 s. The experiment executes 56 result rows, 112 full paths including
fresh verification, 896 core calls and 2,236 Newton iterations/linear solves.
All 56 original fresh verification records pass. Eleven distinct authored
physical models account for these repeated rows; they are not 56 independent
structures. Across repeat occurrences, 45 native checkpoint comparisons are
byte-exact. This comparison covers matching models, not different widths.

## Audit and regression boundary

The audit verifies frozen source and input bytes, report/plan/comparison hashes,
strategy/budget/request/reuse bindings, all 448 original artifact references,
complete work counters, known invocation outcomes, native checkpoints and
timing nesting. It runs no new solver or fit. Its first version fails the first
report hash check because the auditor omitted the producer's `sha256:` prefix.
That script and failure are preserved. The corrected audit also uses the
producer's UTF-8 serialization convention; it completes in 1.328441994 s.
The failed first audit cost was not separately measured. No numerical run or
acceptance criterion was changed to fix the audit implementation.

Eighty-nine search/cost/accounting regression tests pass, followed by three
additional CLI input-boundary tests (92 distinct local tests). The search tests
include real standalone price and learned executions and forbid prediction or
learning feature extraction on the price path. Ruff, scoped mypy and diff
checks pass. The eight frozen-source subprocess observations are additional
to these tests. Full hosted CI and independent qualification remain open.

The [machine summary](rc-standalone-strategies-20260913.summary.json) retains
each original timing and selection, work totals and seal. The unchanged packet
is `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-standalone-strategy-hmxpb46v`:
1,468 files / 76,741,630 bytes, all reread against the inventory. Its sibling
inventory SHA-256 is
`9d99cdce0f6115905c729696b742af59b004412fce7a29de750cc7b0920b95aa`.
Original worker/parent processes are terminal before auditing and sealing.
