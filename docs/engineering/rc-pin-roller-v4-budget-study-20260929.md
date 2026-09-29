# Synthetic pin–roller v4 candidate search under a fixed budget

On exact [PR #503](https://github.com/betelgeuze-kang/Structural-Analysis/pull/503) head `12c36ff537e7c88be37d334cd0747a0774efcd37`, one predeclared local study ran the existing v4 [pin–roller model](../../examples/research/rc_reuse_campaign/pin-roller-steel-plastic.model.json) and [four-target reversal request](../../examples/research/rc_reuse_campaign/pin-roller-steel-plastic.request.json). Those authored source files matched the commit bytes (SHA-256 `22b5eb4a70cb6a5ef226e70c6d883ce788e8fbb3614e16e8b6bcccfe5f76b201` and `5dc17d29a2b4e9228532e9acb1040ad4d87913d62e359ff50e18d2288b2cf883`). The frozen local plan preceded training and search; its SHA-256 is `f329e83b5ffc6373b74f8b76b221c069a0ee5c7cdeb525382173436c9fd3d115`.

Training used section widths **0.30, 0.36, 0.48, 0.58 m**. The disjoint search pool was the **0.42 m baseline** plus **0.34, 0.38, 0.46, 0.50, 0.54 m** alternatives. Each online arm had **three complete analysis requests including a fresh baseline**, below the six-model pool. The existing `feasibility_then_price.v1` ranking ran without cost pruning or line-search assembly reuse. The exhaustive oracle reanalyzed the complete pool only after both online arms finished. The synthetic maximum history fiber strain screen of `0.0001585` was chosen using prior same-engine observations from the [0.40/0.50 m pair](rc-pin-roller-design-pair-20260929.md), intentionally constructing a feasible-versus-infeasible contrast. Other requested screens were broad development limits. Training and search share one synthetic topology; the contrast does not show independent model generalization.

| Pool model | Price-order shortlist | Learned shortlist | Later oracle strain | Requested screen | Invented scoped estimate |
| --- | :---: | :---: | ---: | :---: | ---: |
| Baseline 0.42 m | ✓ | ✓ | 0.000158604844 | Fail | 94.05684 |
| 0.34 m | ✓ | | 0.000159017752 | Fail | 84.93684 |
| 0.38 m | ✓ | | 0.000158792682 | Fail | 89.49684 |
| 0.46 m | | | 0.000158445706 | **Pass** | **98.61684** |
| 0.50 m | | ✓ | 0.000158309157 | Pass | 103.17684 |
| 0.54 m | | ✓ | 0.000158190706 | Pass | 107.73684 |

Price order selected no feasible model within its budget. Learned order selected verified `0.50 m`; the oracle selected `0.46 m` as this declared pool's cheapest feasible model. The policy predicted `0.46 m` strain as `0.0001585392918629824`, just above the screen, whereas full reanalysis gave `0.00015844570617459222`, below it. That false negative kept the cheaper feasible model out of the learned shortlist. The learned selection's **4.56** higher estimate is an invented common-price arithmetic gap, not real currency savings or a global optimum. Both online arms executed **three** full requests, so learned ordering saved **zero actual evaluations** relative to price order; it obtained a feasible selection at the same fixed budget.

| Execution | Models analyzed | Full solver invocations including fresh replay | Attempted target steps | Known Newton iterations / linear solves | Unknown work attempts |
| --- | ---: | ---: | ---: | ---: | ---: |
| Historical training labels | 4 | 8 | 32 | 134 | 0 |
| Online price order | 3 | 6 | 24 | 104 | 0 |
| Online learned order | 3 | 6 | 24 | 104 | 0 |
| Later full-pool oracle | 6 | 12 | 48 | 206 | 0 |

All 16 model rows completed four authored targets and fresh same-engine verification; no row failed execution or retained unknown work. The four training model analyses and eight solver invocations are historical setup cost, counted once outside the two online arms; equal online budgets do not imply net work savings. The original packet at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-v4-budget-study-receipt/` holds the plans, policy, comparisons, result/checkpoint/replay artifacts, launcher timing, and an arithmetic/byte audit. Its `search/result.json` SHA-256 is `db880ed494695cd6fb1fff9a6410158d58d4a8921affbef340f9a9b8dbb615df`; the audit checked all **128** referenced artifact lengths and hashes and passed with zero violations (`audit.json` SHA-256 `a3c35f7db362e8b1a55fa35e48dff5a41b9179c3e6a30452df7cae6079ba24da`). The packet path is a local retention pointer, not a published archive. Source revision is a binding label, not independent attestation of solver results.

Focused checks on this source passed: `PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -m pytest -q tests/test_rc_control_pin_roller_candidate_search.py tests/test_rc_control_candidate_cost.py tests/test_rc_control_candidate_search.py` (**88 passed in 45.17 s**). Prices are invented rates of 100 KRW/m³ gross concrete and 1 KRW/kg straight longitudinal rebar; the quantity scope excludes transverse reinforcement, anchorage/laps, waste, formwork, labor, fabrication, transport, and tax. This one fixed-family, same-engine study establishes neither runtime speedup nor physical accuracy, design-code compliance, independent validation, actual cost savings, or production readiness.
