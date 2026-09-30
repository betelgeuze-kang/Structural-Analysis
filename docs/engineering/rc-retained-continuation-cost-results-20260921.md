# Retained continuation: complete repeatability, substantial upfront cost

Frozen source: `44b440cae` (implementation unchanged from `d1f8f5ca0`).
The [fixed protocol](rc-retained-continuation-cost-protocol-20260921.md) executed
all eight comparisons / 32 complete paths: two L-frame cases, two arithmetic
profiles, two reversed mode/arm orders. Both modes explicitly use terminal
polishing. Native and complete-history tolerances are unchanged.

All repeated proposal and secant complete histories, preload responses and final
checkpoints match exactly within each case/profile. All four retained comparisons
pass fresh-reference gates. Binary64 proposal and secant comparisons still fail,
so their eligible ratios remain null even though every path completes.

| Case | Arithmetic | Sum of proposal path time, two orders | Sum of secant path time | Eligible proposal/secant ratio |
| --- | --- | ---: | ---: | ---: |
| Short / 2 mm | Binary64 + polishing | 3.093711332 s | 0.893816340 s | null: failed comparison |
| Short / 2 mm | Complete retained profile | 10.286405780 s | 2.695949106 s | 3.815504439 |
| Long / 40 mm | Binary64 + polishing | 3.883497959 s | 1.859596710 s | null: failed comparison |
| Long / 40 mm | Complete retained profile | 13.075178329 s | 6.235595223 s | 2.096861304 |

The ratio uses summed path wall time across the two orders, with proposal/trial
and artifact costs included. It is not an average of separately selected best
runs. Compilation/import and the full Workbench process are outside this timing
scope. Two repetitions are not a broad latency distribution or a new independent
physical corpus. No cross-arithmetic speed claim is made.

The full study accounts for 132 ordinary native calls plus 128 internal trial
calls = **260 calls**. Ordinary paths use 928 Newton iterations and internal
trials use 612 = **1,540 iterations**. All work is known. Four arms per comparison,
including the fresh reference, remain in these totals. Each proposal performs
sixteen extra native trials. The observed retained agreement therefore does not
justify using upfront continuation as an accelerator on these ordinary-solvable
cases; same-profile secant is faster and passes the same history gates. No
learned policy is fitted, selected or promoted.

## Verification and retained evidence

The separate audit checks the original inventory, canonical report/path/native
hashes, report/path agreement, all stage artifact byte hashes and lengths,
parent hashes, stage counts and Newton totals. It compares complete repeated
histories/checkpoints and only computes the timing ratio when both arms are
complete, their fresh-reference comparisons pass and repeated histories match.
The audit reader initially compared a prefixed stage digest with a bare digest;
that checker error was corrected before the audit passed. Numerical artifacts
were not changed or regenerated to resolve it.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-retained-cost-uk6x2y7i`.
The source archive, predeclared plan, actual driver, inputs, original reports,
trial files and audit are retained. All 1,941 audited inventory entries were
reread and hash/length checked. `audited-inventory.json` SHA-256:
`0e45b8398634e4278e8abab2ba8965f5532329c0a9fcd864bd1927c763f91689`.
The initial inventory remains intact alongside the audited inventory.

[Machine-readable audit](rc-retained-continuation-cost-results-20260921.summary.json).
These are internal numerical repeatability/cost observations. External physics,
full user-workflow acceleration, learned benefit, and product/design approval
remain unproved. Failure-only retained recovery is a separate next comparison;
its cost cannot be inferred from the earlier binary64 failure-only campaign.
