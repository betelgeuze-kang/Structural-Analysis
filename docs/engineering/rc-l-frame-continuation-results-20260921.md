# L-frame breadth exposes prefix failures and near-zero comparison limits

Frozen source `ce7a8615d` executes all 24 comparisons / 96 attempted paths for the two-member, six-free-coordinate L-frame protocol. Fifty-six paths complete. The full record contains 326 ordinary and 160 proposal native calls (486 total), with 1,566 ordinary and 494 proposal Newton iterations (2,060 total). No failed case is removed.

| Geometry / maximum target | Proposal completion, both modes and orders | Complete paired-history comparison | Ordinary fresh-reference result |
| --- | --- | --- | --- |
| short / 2 mm | complete | fails near-zero force/moment limits | failure-only passes; upfront fails |
| short / 20 mm | fails at first requested target | unavailable | incomplete |
| short / 40 mm | fails at first requested target | unavailable | incomplete |
| long / 2 mm | complete | passes | both pass |
| long / 20 mm | complete | passes | ordinary reference incomplete; secant completes |
| long / 40 mm | complete | fails near-zero moment limits | failure-only passes; upfront fails |

At short/20 and short/40, first-target ordinary relative residuals remain 0.7191606729 and 1.6186330487 with line-search failure. These occur before any accepted direction reversal, so the reversal-only strategies perform zero continuation trials and do not resolve them. This is a trigger-scope limitation, not evidence that frozen-parent continuation itself was attempted and failed on those targets.

The complete-but-different cases do not establish different physical roots. In short/2, four final force/moment fields near zero exceed the unchanged 1e-10 absolute comparison allowance; the largest absolute difference is 1.3931595923e-10 in mixed SI response fields. In long/40, five near-zero moment fields exceed that allowance, with maximum absolute difference 4.4098058538e-10. These remain failed comparisons: no tolerance relaxation, speed credit or equivalence claim is applied. Failure-only matches ordinary results because it avoids unnecessary proposals there.

Only long/2 and long/20 have qualified complete paired proposal histories. Their failure-only/upfront enclosing path-time ratios of two-order sums are 0.361877 and 1.152811 respectively. Long/20 still lacks a complete ordinary reference. Larger displacement is not monotonically harder: the long/40 ordinary path completes while long/20 does not. These six synthetic geometry/history combinations are not independent projects or experiments and do not train a switching model.

All report/path identities, stage artifacts, work counts and paired-history gates were audited; all 3,620 inventoried non-cache files were reread. Inventory SHA-256: `f31af49736e847b4c51b62bdbb00c77f0b6d59fb3d4e7e72899f49ee82064921`. The [summary](rc-l-frame-continuation-results-20260921.summary.json) preserves every case, failed invocation and null timing ratio. Independent physics, corotational/3D/sparse qualification and product approval remain open.

The next scoped implementation may apply the existing failure-triggered frozen-parent search to a failed nonreversal target as well. It must retain the same original parent within each search, count up to sixteen additional calls per failed target, and preserve first-attempt failure and every unchanged reference/comparison gate.
