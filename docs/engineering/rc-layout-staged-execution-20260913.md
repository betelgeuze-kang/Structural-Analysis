# Staged RC layout execution with verified prefix rejection

Parent: `b8fcb8d0c428bdd1a4831fabdc00b3db8f17eb55`.

`run_control_layout_staged_strategy()` now connects the existing frozen candidate
schedule and incumbent cost bounds to actual short-history analysis and fresh
verification. Retained candidates run the complete original request from a fresh
state and receive the existing complete verification and performance checks.
This is a history-prefix stage using the same physics, not a coarse mesh model.

## Execution contract

- An explicit proper prefix count (integer, at least 1, less than the full target
  count) is required. Existing public search wrappers reject the new option.
- The full-request pool and candidate consideration horizon are frozen before
  the first solve. Screening does not reallocate the consideration budget.
- The baseline receives full reference analysis without prefix screening.
- A candidate strictly more expensive than an already verified eligible incumbent
  is cost-skipped before any prefix call, retaining its unknown physical status.
- Otherwise a saved cost decision announces prefix execution. A separate directory
  contains its exact prefix request, original model/result/checkpoint/verification,
  row and hashed decision. Models and all request settings except the target suffix
  remain the same; prefix checkpoints are not reused for full acceptance.
- Only a verified observed violation of a requested cumulative maximum metric can
  reject the candidate. Terminal-only limits are omitted. A prefix pass remains
  inconclusive. A known-work verification failure proceeds to full analysis;
  unknown work stops execution and retains prefix and full records in the failed
  outcome. Neither is a physical infeasibility claim.
- Accepted candidates must pass the full original path and full limits. Partial
  rows cannot become the cost incumbent or the selected full row.

New versioned plan/comparison/report and staged cost-decision schemas keep these
records separate from cost-only formats. Prefix decisions use
`experimental-rc-layout-prefix-screen.v1`. The full report's work totals include
both prefix analysis/verification and full analysis/verification. Separate counters
show prefix and full request counts and work; `request_count` remains the count of
full reference rows. Enclosing online time includes screening and I/O. Inner work
and timing components must not be added to enclosing totals again.

## Focused evidence

A real four-model test uses baseline, small, large and costly with a 2e-6 maximum
absolute fiber-strain limit. Both prefix settings select `large` only after full
reference verification. `costly` receives neither prefix nor full calls once that
incumbent exists.

| Prefix | Full rows | Prefix-rejected | Total API calls | Total steps |
|---|---|---|---:|---:|
| 1 target | baseline, small, large | none | 10 | 40 |
| 2 targets | baseline, large | small | 8 | 32 |

The tests observe frozen plan/decision files before calls, original row/request
hashes, exact call order, omission of terminal limits in the prefix, and exact
prefix response-history equality with the separately executed full oracle paths.
They preserve candidate denominators and leave coverage/cost-optimality audits
unknown. These small test cases are not an independent speed benchmark.

The layout search and cost-dominance regression suites passed 66 tests in 103.29s.
An earlier first-pass staged subset passed 9 tests; those overlap the 66 and are
not additional cases. Two subsequently added tests passed in 17.23s: unknown
prefix work stops before further candidates and preserves the failed outcome; an
actual constant-preload prefix keeps its preload response and subsequent response
history exactly equal to the full path (six prefix steps including revalidation).
Ruff and mypy passed for all three affected source modules.

Commands:

```text
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -m pytest tests/test_rc_control_layout_search.py tests/test_rc_control_cost_dominance.py -q
MYPYPATH=src python3 -m mypy --follow-imports=silent src/structural_analysis/benchmark/rc_control_prefix_screen.py src/structural_analysis/benchmark/rc_control_layout_search.py src/structural_analysis/benchmark/rc_control_cost_dominance.py
```

## Remaining work

No claim of measured staged scheduling speedup is made: prefix work can outweigh
avoided full calls. A matched process-cost experiment against the existing
cost-pruned scheduler remains necessary. HTTP admission and Workbench do not yet
accept the new staged schemas; the report keeps integration false. They must bind
original prefix decisions and separate prefix-rejected, cost-skipped, full verified
and unevaluated statuses before this becomes a reviewable product flow.

Parent-head Repository Python Tests run 34721709636 remained queued at inspection;
Issue State Current 34721709692 succeeded. This is not full hosted acceptance or
qualification of the new code. Independent verification, generalization, learned
net benefit and broader roadmap gates remain open.
