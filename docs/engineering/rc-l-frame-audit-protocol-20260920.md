# L-frame campaign protocol audit

The success-only auditor now requires the declared eight processes and the exact
four counterbalanced orders used by the original campaign. It also rejects an
outcome declaring that all pairs were not comparable. Previously it checked only
the lengths of the orders and pair arrays before reconstructing pair results;
changing the declared order or process denominator could escape that boundary.
The auditor continues to reject incomplete campaigns rather than grant a ratio.
Failed process accounting remains in the campaign's retained process and pair
receipts and the generic campaign summarizer.

Four focused regressions reject unbalanced orders, a duplicate mode, a changed
process count and a failed outcome before reading numerical artifacts. Together
with existing cost-exclusion and failure-accounting checks, the test file passes
14 tests in 7.38 seconds. Ruff and whitespace checks pass.

The revised auditor was run read-only against the original
`structural-l-frame-cost-t3md3b1e/study` packet. Its complete returned object equals
the preserved `receipt-audit.json`, including the process-time ratio
0.5160566434319022. No analyses, training or measurements were rerun, and no
original packet was changed. This is an audit-contract correction, not new
physical validation or a new speed measurement.

At inspection, published head `90cc21dcd3885601bae9d3769bc71961eeb5456d`
has passing Workflow Contract CI and P0 Canonical Verification Contract runs.
Repository Python Tests run 35482427573 and Frontend Web CI run 35482400507 are
still running. This local correction is not covered by those exact-head runs.
