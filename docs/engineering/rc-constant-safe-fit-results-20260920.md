# Fixed ten-fit v6 preprocessing comparison

Frozen source `a81bf6973070598522257c5ec3de10046e581365` completed the ten predeclared v6 fits using the original 99-row complementary training sets, original ridge values and OOD margins. Each fit was compared on its 66 excluded training-corpus rows. No reserved evaluation case, new structural solve or hyperparameter search was used.

The 48 spurious constant directions are removed in every fit, and nonconstant feature transformations remain byte-for-value identical. Correction-coordinate error nevertheless increases in every excluded-set aggregate. Fixing the preprocessing changes the effective regularization; it does not imply improved prediction or runtime.

| Fit | Excluded v6/v5 SSE | Rows within feature bounds | Within-bounds v6/v5 SSE |
| --- | ---: | ---: | ---: |
| 0 | 1.031129 | 29 | 1.028110 |
| 1 | 1.082444 | 0 | unavailable |
| 2 | 1.042083 | 0 | unavailable |
| 3 | 1.055568 | 14 | 1.042114 |
| 4 | 1.037786 | 33 | 1.027058 |
| 5 | 1.027957 | 66 | 1.027957 |
| 6 | 1.035715 | 66 | 1.035715 |
| 7 | 1.058236 | 33 | 1.046878 |
| 8 | 1.089764 | 0 | unavailable |
| 9 | 1.045726 | 66 | 1.045726 |

The 307 feature-bound-admitted overlapping rows have an aggregate SSE ratio of 1.034915103. This is a coordinate-error diagnostic in the existing correction representation, not equilibrium residual, physical energy or a runtime score. Passing feature bounds alone does not establish that all runtime guards accept a proposal. The 660 excluded rows overlap and derive from the same 165 original samples; they are not 660 independent structures.

Total new fitting time was 0.222275633 s. Source export, inventory reading and later audit time are outside that fit-only scope. All 1168 packet files were re-read and checked against their inventory. Stored prediction/target arrays independently reproduce every reported SSE; that check is not a second independent fitting implementation.

Keep v6 opt-in and preserve v5 artifacts. Do not promote or reject a runtime candidate solely on this error metric, and do not search a new ridge value against these observed excluded errors as if the cases were untouched. If continuing the candidate, predeclare same-parent repeated solver comparisons and then complete-path cost evaluation. The current result provides no acceleration or independent-validation credit.

Packet inventory: `86cca994cd7be7119f81a6b1f55f4f5b179f80b8bc306c8c5492bb3e831d2cc2`. Exact roots, fit costs, policy identities and excluded sample hashes are in [the summary](rc-constant-safe-fit-results-20260920.summary.json).
