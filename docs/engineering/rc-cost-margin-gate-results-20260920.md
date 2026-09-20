# Cost-margin gate fit: ten selected training rows, no measured benefit

The [fixed cost-margin protocol](rc-cost-margin-gate-protocol-20260920.md) fits all five original outer-group complements from the retained nested three-repeat observations. Every assembly contains 132 verified rows. No reserved case or new numerical solve is used.

| Excluded outer group | Selected training rows | True positive | False positive | Selected worst-repeat measured margins |
| --- | ---: | ---: | ---: | --- |
| 0 | 0 | 0 | 0 | none |
| 1 | 2 | 0 | 2 | -1.24% to -1.92% |
| 2 | 4 | 0 | 4 | -1.51% to -2.28% |
| 3 | 2 | 0 | 2 | -1.44% to -1.55% |
| 4 | 2 | 0 | 2 | -1.51% to -1.81% |

The new gate produces nonzero decisions, but all ten selected rows have negative measured worst-repeat margins. It still selects none of the 32 positive label rows across the five overlapping complements. These are training diagnostics, not independent performance measures. No policy is promoted and no full-path timing campaign is started for this candidate. Secant remains supported.

A separate read-only audit reconstructs each table from the original nested inventory, reproduces all target ratios and training normalization, validates each strict policy/hash, and recomputes its decisions. The maximum augmented-ridge normal-equation residual is `1.0880185641326534e-14`. Thus this observation does not point to an inaccurate linear solve as the reason for the failed choices. Changing binary targets to measured cost units alone has not made the existing linear feature/model combination useful. It does not prove all nonlinear representations or better data would fail.

The next learning change should address representation and verified decision quality before further whole-path timing. Preserve the original negative results, group exclusions and untouched reserved cases. Training improvement alone would still not establish net runtime benefit after gate setup/inference and full-path state evolution.

## Costs, source and bookkeeping correction

Fit source: `b6d64ea51096a12c739614adb3e43ce07876c122`. There are **five actual new gate fits**, with combined fit time 0.034132 s, enclosing driver time 0.257835 s and outer process time 2.130935 s. Those intervals are nested, not additive. The separate audit takes 0.284282 s before output. Historical source-label/seed costs remain in the fit plan; prior binary-gate development costs remain in the earlier reports. No complete cumulative research-cost total is asserted here.

The copied outer observer wrapper incorrectly reports `new_fits: 0`, although its child writes five fit receipts and policies. The original packet is preserved. A separate audit records the discrepancy and counts **five**, not zero, fits. The reusable fit driver now also emits its actual completed fit count explicitly. No fit or solve was repeated to repair the reporting counter.

- Fit packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cost-margin-fits-eozvr6pj`. All 783 payload files / 17,647,802 bytes verify; inventory `0f0486a7f1ad66d0cd9e3a04bab616361d4b4ddfafc443129c8288725f759501`.
- Audit packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cost-margin-fit-audit-8zie0plx`, inventory `d84bf39f65662c9e1781adf165cfcbe03dc2067f141b2c1394a3a02ce0f7f597`.
- The [machine summary](rc-cost-margin-gate-results-20260920.summary.json) retains exact costs, selected predicted/measured margins, source hashes and the counter correction.

This is a failed development candidate with useful diagnostic evidence, not learned acceleration, physical validation or roadmap closure.
