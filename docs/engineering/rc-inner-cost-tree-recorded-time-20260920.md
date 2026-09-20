# Fixed cost-tree retained-time diagnostic

The fixed offline tree has a small positive arithmetic margin in saved same-parent timings, but no demonstrated whole-path or net runtime benefit. This diagnostic does not change the policy, thresholds, labels or promotion decision in [the tree evaluation](rc-inner-cost-tree-results-20260920.md).

All 1,980 original comparison reports were checked against their pinned inventory, producing policy, parent identity, completion, response checks and saved timing ratio. Across 20 overlapping folds, each repeat contains 660 decisions from 165 unique source samples; only two decisions select the learned proposal. These are not 660 independent projects.

| Saved repeat | Secant total (s) | Hypothetical selected total (s) | Difference (ms) | Difference / secant |
| --- | ---: | ---: | ---: | ---: |
| 0 | 182.733107272 | 182.698159330 | 34.947942 | 0.019125% |
| 1 | 183.337324421 | 183.305184061 | 32.140360 | 0.017531% |
| 2 | 183.091805691 | 183.055937607 | 35.868084 | 0.019590% |

The selected true positive saves 38.786–39.962 ms per repeat; the selected false positive loses 3.765–6.645 ms. A separate direct lookup of those six reports reproduced every total difference. The other 658 decisions retain the original secant timing arithmetically.

This is a post-hoc mixture of separately measured step timings. It does not propagate a switched state through subsequent steps, execute the policy online, or measure feature construction, guard checks, loading and result validation. The saved offline decision calls took 9.822754 ms for one 660-decision pass. That timing has a different execution context and is not subtracted to claim net acceleration. Original fitting took 1.155721395 s for all 20 folds; a deployment amortization claim would require a defined reuse workload. No new fit or structural solve was performed, and reserved cases were not opened.

The arithmetic margin is too small to justify promoting this tree on these observations. Keep the current reference strategy. Further model development must target repeatably expensive solver decisions and predeclare a total-cost comparison; changing a threshold against these same observed cases would remain development, not independent confirmation.

The retained audit took 0.596044819 s. Packet inventory SHA-256 is `0b24121acd9151d9484764608626740d1acb2b2dc3c10596419e7efff88e66eb`. The immutable packet includes its auditor source. Exact paths, pinned input inventories, integer timings and the separate six-report arithmetic check are in [the summary](rc-inner-cost-tree-recorded-time-20260920.summary.json). No CI, physical-validation or release gate is closed by this report.
