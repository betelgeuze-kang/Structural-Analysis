# More line-search candidates and finer load grids do not complete the path

These bounded pilots follow the [directional diagnosis](planar-two-story-direction-20260914.md).
They use the existing low-level load-path solver and explicit `NewtonRaphsonConfig`,
with checked frozen source `29af2b0f9bcd481058cae1cabb192b91f65c4506` and the
high-load generated models. No public API result was constructed, default policy
changed, tolerance relaxed, or failed result promoted. Each configuration ran
once; elapsed observations are not repeated performance estimates.

First, six paths were frozen: two models, each with six, seven or twelve halving
line-search candidates starting at one. Four load targets, residual tolerance
1e-10, increment tolerance 1e-12, maximum 40 iterations and the dense backend
remain identical.

| Two-story policy | Committed / attempted steps | History rows | Line-search trials | Failed relative residual | Core path s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default six | 1 / 2 | 10 | 19 | 0.0336261 | 1.902773 |
| Seven | 1 / 2 | 11 | 27 | 0.0323110 | 2.357366 |
| Twelve | 1 / 2 | 13 | 52 | 0.0321506 | 3.882404 |

All three stop at load factor 0.5 with exact rollback. The extra descent point
does not produce a converged step. The two-bay control completes all four targets
with 21 history rows and 17 line-search trials under every policy; its complete
low-level path bytes are identical across all three. The two-story first step
is also identical across policies. Original artifacts, attempt-count recounts,
compile costs and timings are in the
[line-search receipt](planar-line-search-pilot-20260914.summary.json). The enclosing
six-path experiment takes 17.663994 s. This evidence does not justify a new public
line-search option as a solution to the observed failure.

Second, two separately frozen paths use eight and sixteen uniform load increments
with the original six-candidate line search. Changing the load grid changes the
material path; there is no cross-grid equivalence or speedup claim.

| Grid | Last committed factor | Failed factor | Committed / attempted steps | History rows | Line-search trials |
| --- | ---: | ---: | ---: | ---: | ---: |
| Eight | 0.375 | 0.5 | 3 / 4 | 20 | 22 |
| Sixteen | 0.4375 | 0.5 | 7 / 8 | 35 | 34 |

Both again fail line search and roll back exactly. Their failed relative residuals
are 0.0335123 and 0.0251946, with core path intervals 2.887522 s and 4.838878 s.
All costs, raw paths and chain/count checks are in the
[load-grid receipt](planar-load-grid-pilot-20260914.summary.json).

These observations rule out claiming that these simple changes resolve this
case. They do not prove physical collapse or that no equilibrium exists. Further
work should investigate the nonlinear response path and control strategy, not
continue increasing arbitrary iteration/backtracking budgets. Any alternative
control method requires explicit load/response matching, accepted-history checks
and full costs before it can support the public roadmap.
