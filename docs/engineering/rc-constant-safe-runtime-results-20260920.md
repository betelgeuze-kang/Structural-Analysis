# Completed v6 full-path runtime comparison: secant retained

Frozen source `600dd90c478f3aac4f026f609d45b7da0832044a` completed all 90 comparisons and 360 full paths. The original history/tolerance, work-accounting, group-exclusion and fit-method audit passed. Both constant-safe SVD candidates fail the unchanged minimum 1% benefit requirement.

| Ridge | Equal-case mean learned/secant total-time ratio | Decision |
| --- | ---: | --- |
| 10,000 | 1.0325188659618083 | Rejected |
| 1,000,000 | 1.0265324120775998 | Rejected |

The runtime selector retains secant. It performs 30 complementary selection fits and no winning-policy refit or promotion. All five geometry/history groups retain exactly 132 complementary original samples per fold. The reserved cases remain unexecuted. This is development-corpus comparison, not independent project generalization.

The campaign records 4,680 numerical core calls and 24,147 Newton iterations/linear solves, with 594 actual proposals and 486 abstentions. Numerical work and fitting costs are not conflated. Selection fitting took 0.773211611 s and the separate pooled metadata fit took 0.027569042 s. Driver elapsed time was 1,499.533402522 s; the enclosing process took 1,501.330490935 s. Those scopes overlap. Historical label-generation costs remain recorded separately in the summary.

The exact-constant preprocessing fix is effective as a numerical contract but does not establish runtime benefit: both measured candidates are slower than their paired secant baseline. Cross-revision differences from older experiments are not controlled causal speed measurements. Keep the method opt-in; neither lowering the acceptance threshold nor promoting it on the basis of corrected preprocessing is justified.

All 35,826 packet files (1,987,510,055 bytes) were indexed and re-read with SHA-256 and byte-length checks. Inventory creation plus re-verification took 3.837179130 s; the separate semantic audit duration was not recorded. Its audit performed no new fits or solves. Frozen source files also matched their export manifest. Inventory SHA-256: `19d600900d8972263446acb7a899c14687eb61e8307d7b4d8f62f1ef3c7f9bcf`.

Exact packet path, full case/repeat ratios, source/result identities, fit/work costs and historical label costs are in [the summary](rc-constant-safe-runtime-results-20260920.summary.json). Original failure and earlier experiment packets remain unchanged. The full roadmap, independent physical verification, licensing and release requirements remain open.
