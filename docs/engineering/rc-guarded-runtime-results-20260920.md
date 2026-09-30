# Fixed trained gate: complete-path result remains negative

Frozen numerical source: `75a12b2a4f042eb49c637b21575f4cecd00557dc`. All **45 comparisons / 180 full paths** completed and passed the original full-history checks. The five fitted gates nevertheless declined **all 540 decisions**: no material capture, seed-policy inference or learned proposal was invoked on the guarded arm. The policy parser cache remains empty (zero hits/misses).

The equal-case mean guarded/secant path-time ratio, including per-comparison gate/seed construction and callback setup, is **1.0051856020874972**. This observed 0.519% longer time does not establish a causal overhead estimate; small individual case means also fall below one despite no AI proposal. The fixed runtime eligibility rule fails, so secant remains the supported choice. There is no measured learned acceleration or net training-cost benefit.

Work across all arms and fresh references: **2,340 core calls, 12,024 Newton iterations and 12,024 linear solves**. Driver time before outcome write: **746.594859450 s**; enclosing execution: **747.997767237 s**; separate read-only audit: **5.142544736 s**. Nested timers are not additive. Historical original labels, nested labels, seed fitting, successful gates and the failed gate-fit attempt remain separately bound in the plan. They have not been amortized.

All **17,447 packet files / 805,543,598 bytes** passed hash/length verification. Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-guarded-runtime-24nhflp9`; inventory SHA-256 `4efe7fd210740f5cbf64f708c042a01593ed70930ee65dcd1a698facb701c4d0`.

## Why every decision declined

A separate post-hoc, read-only diagnostic replays all frozen gate decisions from original pre-capture contexts:

- **222** decisions are outside individual training-feature bounds. Groups A and C account for 216 of these; six are from B at amplitude 1.5.
- **318** decisions are within individual bounds but below the fixed score threshold 0.75. Their scores range from **-0.03157649646950531 to 0.2710464841424901**.
- No fitting, threshold change, structural solve or reserved evaluation occurs in this diagnostic. These regression scores are not probabilities and individual bounds do not prove joint support.

Diagnostic packet: `structural-guard-decision-diagnostic-wu3y5byh`, inventory `d3b49a7d33e65360eb46b647fa913590de355998df8d8036161cdcaf4d11fb55`, read-only time 1.284069484 s.

A second check verifies **1,170 byte-exact paired files** between secant and proposal arms: each comparison has twelve step files, twelve context files, the preload step and preload response. Original inventory identities are checked before comparing bytes. This confirms numerical equivalence for the all-decline behavior, not AI benefit. Packet: `structural-guarded-secant-equivalence-q_vj_khc`, inventory `79063ff1f0e501e2d8da5dc5d82fb07a155f38e1bb14c5f961d859e2d52de74d`, time 0.283044115 s, zero new solves/fits. Both diagnostic packet names are under the same mounted root as the main packet.

## Consequence for the roadmap

The retained-parent experiment found 32 positive local labels, but this fixed linear gate did not identify an actionable full-path opportunity in the excluded groups. Lowering the threshold after observing these outer cases cannot be called independent confirmation. Preserve this negative result, keep the deterministic baseline, and treat any revised features/model/decision rule as a new development experiment requiring a new predeclared evaluation protocol.

No public solver default is changed and no trained gate is promoted. Reserved evaluation remains untouched. All five roadmap goals, independent physical validation, licensing, operator/hardware and signature dependencies remain open. See the [fixed protocol](rc-guarded-runtime-protocol-20260920.md) and [nested labels and fits](rc-nested-switch-results-20260920.md).
