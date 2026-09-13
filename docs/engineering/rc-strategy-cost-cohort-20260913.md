# Matching standalone strategy cost records

Source `f789805970653b6913112767b83daed22d404428` adds
`compare_rc_control_strategy_costs` and its module CLI. It binds each standalone
plan/report to its recorded CLI runtime before comparing price and learned
executions. This is metadata and interval accounting, not a replay of original
physical artifacts. The Workbench design validation remains a separate check.

```sh
PYTHONPATH=src python3 -m structural_analysis.benchmark.rc_control_strategy_costs \
  --source-revision FULL_40_CHARACTER_ACCOUNTING_REVISION \
  --pair /absolute/price-run-1 /absolute/learned-run-1 \
  --pair /absolute/price-run-2 /absolute/learned-run-2
```

The CLI emits a separate hash-bound report and original input byte references.
Inputs remain unchanged. Runtime digests bind the supplied records; they do not
attest that a clock measurement was truthful or independently observed.

## Comparison contract

Each pair requires the same source, control request, physical pool, quantities,
common prices, performance limits, budget and assembly-reuse setting. The
declared price schedule and learned ranking are reconstructed. Reports must
complete, retain known numerical work, identify a selection consistent with
their pool/shortlist, and contain nested nonnegative safe-integer clocks.
The runtime must name that report, source, strategy and exact CLI timing scope.
Duplicate execution reports reject instead of becoming extra repetitions.

A pair receives a CLI time ratio only if both reports declare a fully verified
selection and the learned estimate is no greater than the price estimate.
Those are checked recorded declarations, not newly replayed physical evidence.
A missing selection or worse estimate stays in the cohort and blocks its
aggregate ratio. Unknown numerical or historical-label work rejects. All totals
must remain exact browser-safe integers. Zero denominators retain null ratios.

Historical training is charged once per distinct original training-report hash.
Label/fit intervals are checked as components of that total and not added again.
The report sums CLI intervals plus this historical cost. Interpreter/import
startup, runtime-sidecar/stdout writing, transport/Workbench review and separate
audits remain excluded. The sum is not campaign elapsed time. No statistical
speedup, break-even projection, independent generalization or net-benefit claim
is emitted. The cohort report is not yet wired into Workbench.

## Existing original records

The observation verifies all 24 original input files against the previously
sealed standalone experiment inventory, then runs the new CLI for all four
pairs and for the previously declared full-pool budget stratum. Both original
orders remain in that stratum; it is not a selection of faster repetitions.
Source bytes match the committed revision before and after the observation.

| Recorded group | All four pairs | Two budget-11 pairs |
| --- | ---: | ---: |
| Pairs with incomparable recorded selections | 2 | 0 |
| Price CLI interval sum (s) | 24.495854346 | 19.215370148 |
| Learned CLI interval sum (s) | 24.592134089 | 19.238868966 |
| One historical training interval (s) | 2.761753795 | 2.761753795 |
| Learned plus historical / price ratio | null | 1.1449492043 |

The groups overlap: their totals must not be added together. The full-pool
ratio is about 14.5% higher after charging the shared training artifact once
across its two price/learned pairs. It does not support learned savings and is
not a general performance estimate. Numerical inputs and original measurements
are unchanged; the observation performs zero fits or solver calls. The two
accounting CLI parent intervals are 1.412841647 and 1.374800742 s, respectively,
and are separate from the historical numerical costs above.

Seventeen focused cost tests pass, plus sixteen workflow and fourteen existing
accounting tests (47 distinct local checks). These include incomplete selection,
worse feasible estimate, different conditions, rehashed hidden work, duplicate
executions, invalid/overflow clocks and byte-bound CLI output. Ruff, scoped mypy
and diff checks pass. The development workflow includes the new module, bringing
its explicit selection to 28 modules. Hosted completion is not inferred.

The [machine summary](rc-strategy-cost-cohort-20260913.summary.json) binds source,
original inventory, groups and seal. The new packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-strategy-cost-cohort-u6cd7v_h`:
10 files / 59,673 bytes, all reread against its sibling inventory. Inventory
SHA-256: `fbeff7dbe78ea7b34ea67796933f8843091a985a589330e78a7db8f0ebf07fd3`.
It references the existing numerical packet instead of copying its physical
arrays or changing its sealed contents.

Prior research links are preserved in the
[learning/search evidence index](rc-learning-search-evidence-index.md).
Full-cost Workbench cohort delivery, broader held-out cases, independent
qualification and full roadmap closure remain open.
