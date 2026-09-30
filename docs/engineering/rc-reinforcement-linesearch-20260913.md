# Explicit line-search refinement for the smaller-bar design

The smaller-bar-area alternative that previously failed at target eight now
completes all 242 authored targets and fresh full-path reference verification
under a separately declared line-search configuration. The original failed
observation is unchanged. No production solver defaults were modified.

Execution uses the preserved numerical source `94302f49a`; every numerical
source file was verified against the current `1882c85f9` checkout before launch.
Original inputs, source hashes, runner commands and outcomes are retained.

## Diagnostic and full-path observations

The only request change appends step sizes `1/64, 1/128, 1/256, 1/512, 1/1024`
to the existing backtracking list. Residual/increment/control tolerances, maximum
Newton iterations, material parameters and displacement targets remain unchanged.
There are no intermediate targets or learned proposals.

The first diagnostic compares the original and extended lists on the original
first eight targets, using the baseline and smaller-bars alternative. The original
configuration reproduces the same failure; the extended configuration passes
both designs and fresh verification. At the previously failed step, the third
Newton line search accepts `1/64` after seven trial evaluations. The rest of the
step then converges. This identifies an effective request-level recovery for this
case, not a general proof that the larger line-search list is always preferable.

| Observation | Verified designs | Attempted steps including verification | Newton / linear counts | Study elapsed |
| --- | ---: | ---: | ---: | ---: |
| Original eight-target diagnostic | 1/2 | 32 | 174 | 11.523 s |
| Extended eight-target diagnostic | 2/2 | 32 | 186 | 11.836 s |
| Extended 242-target comparison | 2/2 | 968 | 3,842 | 289.805 s |

All work is known; failed attempts remain included. The complete sequence costs
1,032 attempted steps and 4,202 Newton/linear counts over twelve numerical API
entries. Line-search trial evaluations are additional assembly work, not extra
Newton iterations; their cost is inside the observed execution intervals. The
full-study parent interval is 291.542 s. These single serial observations do not
establish a speed ratio: the original and extended diagnostic outcomes differ,
and no matched repeated full-path timing campaign was performed.

## Full-path performance and quantities

| Quantity | Baseline | Smaller bars |
| --- | ---: | ---: |
| Gross concrete, m³ | 0.84 | 0.84 |
| Straight longitudinal rebar, kg | 85.0626 | 65.9400 |
| Common synthetic material estimate | 169.0626 | 149.9400 |
| Maximum absolute fiber strain | 0.0067335994 | 0.0069295804 |
| Maximum steel accumulated plastic strain | 0.0097565363 | 0.0096892607 |
| Maximum translation, m | 0.0369080277 | 0.0375854531 |

The smaller-bars candidate is selected under the existing permissive fixture
screens and synthetic common prices. Both designs reach concrete tensile damage
close to one; these screens do not establish design-code compliance. The estimate
difference of 19.1226 is declared arithmetic, not confirmed construction savings.
This two-design pool does not contain the fewer-bars candidate from the earlier
three-design observation. The two observations must not be merged into a single
uniform-protocol exhaustive comparison.

The saved-data auditor verifies source and artifact bytes, report self-hashes,
unaltered targets and tolerances, model quantities/common-price arithmetic, fresh
verification bindings, complete accepted paths and strain peaks. The sealed
packet contains 80 files / 140,279,329 bytes at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-reinforcement-linesearch-zf8050in`.
Its reread inventory SHA-256 is
`0891d6d92064bcc28e18e67050b29dde704928c959e50543bc0e8945a4155f8d`.
The [summary](rc-reinforcement-linesearch-20260913.json) retains diagnostic and
full-study work/costs separately. No new code behavior or external validation is
claimed; independent physics, learned net benefit and the broader roadmap remain
open. The [original failure](rc-reinforcement-full-path-20260913.md) and its
Workbench inspection remain valid historical evidence.
