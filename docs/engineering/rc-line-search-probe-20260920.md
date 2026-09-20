# Retained-parent line-search diagnosis

Source `148ede4b71f87a9e0f46f4d3a6d2c4bcd0d54a0d` replays the two blocked
reference steps from the [incomplete history study](rc-training-history-coverage-plan-20260920.md).
Every run uses the exact stored native parent and accepted control prefix. Original
configuration replays reproduce the original **step hashes exactly**, not only
similar residuals. The experiment changes only the candidate line-search alphas
from 1 through 1/32 to 1 through 1/4096, retaining their halving order.

| Case | Original result | Extended result | Extended Newton iterations | Smallest accepted alpha |
| --- | --- | --- | ---: | ---: |
| A × 0.5, +2 mm target | Line search blocked | Converged | 13 | 1/128 |
| A × 1.5, -4.5 mm target | Line search blocked | Converged | 11 | 1/64 |

The extended runs retain the original 25-iteration bound, residual tolerance
1e-10, increment/control tolerance 1e-12, arithmetic, material state and target.
Final relative equilibrium residuals are approximately 2.060e-17 and 6.832e-17;
control errors are below 2.3e-35 m. Reference/fresh-reference and secant step
comparisons pass. Original blocked runs keep exact rollback. These observations
support insufficiently small configured backtracking steps as a cause of the two
specific failures; they do not show that every nonlinear failure has this cause.

Four single-step comparisons cost 12 core calls and 92 Newton/linear solves,
with 8.756 s enclosing wall time. This is post-hoc diagnosis, not a speed claim,
complete-history verification or independent physical validation. No labels are
admitted from these isolated steps. Public solver defaults are unchanged.

## Full-history follow-up protocol

The existing history-coverage runner now accepts explicit `--extended-line-search`.
Its v2 plan links the failed coverage plan and changes only the same alpha list
for all 11 declared requests. Models, targets, loads, materials, OOD margin,
ridge, iteration bound and acceptance tolerances remain unchanged. Reserved
requests receive the explicit configuration change for consistent policy context,
but their solver paths remain deferred. Their outputs have not informed this
choice. This new protocol does not retrospectively validate the failed original.

All nine training cases must complete their original full-history comparisons
before any coverage conclusion. A passing single-step probe is insufficient.
The preflight confirms three whole families and two unexecuted reserved cases.

## Evidence

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-line-search-probe-ld2xx9q2`
contains the copied source, source manifest, original input identities, four
comparisons and [audited summary](rc-line-search-probe-20260920.summary.json).
Its inventory covers 573 files / 13,504,520 bytes excluding `__pycache__`;
SHA-256 `a0c520c71e0ffca70ed39da52184d7ef688c54117f5698d83fd7faef3783162f`.
