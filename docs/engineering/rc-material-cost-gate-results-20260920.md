# Material-input cost gate: 2 training true positives, 25 false positives

The [fixed representation experiment](rc-material-cost-gate-protocol-20260920.md)
completed at `72d28a432cdb2f77073632c5dd56058891a1cde5`. All five fits retain
132 original rows with the entire outer group excluded. The only input change
is appending the 27 verified accepted-material statistics. Cost targets,
ridge, threshold, normalization rules and reference labels are unchanged.

| Excluded group | Proposals | True positive | False positive |
| --- | ---: | ---: | ---: |
| 0 | 1 | 0 | 1 |
| 1 | 8 | 1 | 7 |
| 2 | 8 | 0 | 8 |
| 3 | 3 | 0 | 3 |
| 4 | 7 | 1 | 6 |

The complements overlap; these 27 decisions are not 27 independent cases.
All 25 selected false positives have negative measured worst-repeat margins.
The two selected positives have measured margins 14.7615% and 10.8547% in
their original local comparisons. These are original training targets, not
new runtime measurements or full-path savings. The earlier prefix-only cost
gate selected zero positives and ten false positives. Adding material summaries
found two positives but increased false positives to 25. This does not establish
a useful selection policy. No full-path campaign or online adapter is added.

A separate read-only audit reconstructs the five joined tables against the
original label, seed and material-summary inventories; all tables and their
hashes agree. Normalization is exactly training-only. Strict policy hashes and
all inference decisions reproduce. The largest ridge normal-equation residual
is `1.5210055437364645e-14`. This result therefore does not implicate numerical
solution error as the explanation for the poor choices. It also does not prove
that all material representations or nonlinear models would fail.

All 1,390 fit-packet files / 127,913,980 bytes verify. Five actual fit receipts
agree with the enclosing process counter. Combined fit time is 0.050106 s,
driver time 0.322196 s, and outer process time 2.215882 s; these intervals are
nested. The separate audit takes 0.450283 s before output and performs zero
fits or solves. Concurrent numerical work means these are observed costs, not
an isolated speed benchmark. Extraction and guard cost are absent from the
original target and would have to be added before runtime claims.

The [machine summary](rc-material-cost-gate-results-20260920.summary.json)
preserves exact source, packet/inventory hashes, costs and every selected
predicted/measured target. Reserved cases remain unexecuted. Secant remains
supported; no policy is promoted and no roadmap requirement is closed.
