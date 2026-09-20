# Retained failed-target recovery: avoided work and a persistent hard failure

Frozen source `8589636cd`; implementation remains the published retained seed
support. The [fixed protocol](rc-retained-failure-cost-protocol-20260921.md) ran
sixteen comparisons / 64 paths across four cases, two recovery modes and two
reversed orders. Both modes use the complete retained profile and terminal
polishing. Native/full-history tolerances and the sixteen-stage search budget
are unchanged. **34 paths complete; 30 remain incomplete.**

| Case | Upfront proposal | Failed-target proposal | Additional calls across two repeats, upfront → failed-target | Qualified failed-target/upfront wall ratio |
| --- | --- | --- | ---: | ---: |
| Short / 2 mm | Complete | Complete | 32 → 0 | 0.455728165 |
| Long / 40 mm | Complete | Complete | 32 → 0 | 0.326872506 |
| Short / 20 mm | First target fails | All three targets complete | 0 → 32 | null |
| Short / 40 mm | First target fails | First target still fails | 0 → 16 | null |

The completed easy cases match between recovery modes under fixed history limits,
and complete histories/checkpoints repeat exactly within each mode. The recovered
short/20 mm proposal also repeats exactly, but ordinary/fresh references remain
incomplete; it does not qualify a speed ratio. Incomplete short/40 mm prefixes
are explicitly not counted as repeated complete histories.

## What accounts for the speed differences

The easy cases never invoke failed-target continuation. Their proposal runs use
the ordinary reference initial values, so the savings against upfront mode come
from avoiding unnecessary sixteen-trial searches. They do not demonstrate that
recovery or AI accelerates an already convergent native solve.

Against same-profile secant, the failed-target proposal costs 1.683951159 times
on short/2 mm and 0.705339688 times on long/40 mm. The short case uses 36 ordinary
Newton iterations per proposal path versus secant's 25. The long case uses four
ordinary native calls / 32 iterations versus secant's five / 41, including one
failed seeded attempt. Proposal and reference use the same ordinary work in
both easy cases. There is no universally superior starting strategy here.

Path wall time sums over both orderings and includes artifact/proposal costs.
It excludes import/compilation and the complete user workflow. Two repeats on
these fixed examples are not broad performance or independent physical evidence.

## The hard case is not repaired by retained arithmetic

Short/20 mm recovery uses sixteen internal trials to reach the first -10 mm
requested target, then completes the original history. Short/40 mm recovery
stops at internal trial eight, target -0.010134046179437273 m, with relative
residual 0.05823129344568924 and `line_search_failed_to_reduce_residual`.
This agrees with the prior binary64 failure location and residual to numerical
precision; retained arithmetic alone does not resolve that failure. No material
state from an intermediate trial is adopted. Neither the original target history
nor the comparison tolerance is weakened to turn this into a pass.

All ordinary and internal work is retained: **202 ordinary + 112 additional =
314 native calls**, and **1,326 + 654 = 1,980 Newton iterations**. Every report
accounts for known work. Failed first attempts and unsuccessful internal stages
remain in these totals.

## Audit and retained packet

The separate audit checks the original inventory, all canonical report/path/native
hashes, canonical input/request binding, exact arithmetic and recovery identities,
all stage artifact digests/lengths, full parent equality across internal stages,
outer-entry parent binding, absolute coordinate handoff, stage/iteration counts,
complete repeat comparisons and timing eligibility. The repository summary
compacts comparison examples; full observations remain in the sealed packet.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-retained-failure-cost-g4u_085h`.
All 2,447 audited inventory entries were reread and hash/length checked.
`audited-inventory.json` SHA-256:
`6c2e9ac71afbb207fbfd4463cd4af80744e992fe23531c4bcd120428874307ef`.
[Machine-readable summary](rc-retained-failure-cost-results-20260921.summary.json).

The result supports investigating bounded recovery only when ordinary solving
fails, while retaining deterministic baselines and explicit failure reporting.
It does not promote a production policy, qualify independent physics or establish
learned net benefit. Resolving the short/40 mm failure requires a separate
convergence investigation; increasing precision has now been tested and is
insufficient in this fixed case.
