# Initial-iteration evidence from a completed runtime-tuning fold

The frozen [runtime-selection observation](rc-runtime-selection-20260910.md)
contains a completed train-b fold at ridge 10,000. Its learned path takes
74.280740 s versus secant's 66.166223 s, a ratio of 1.122638. The four path
comparisons pass in that fold's recorded report; the complete observation's
original-state and physical-response audit is still pending.

A read-only diagnostic compares all 242 target positions in its secant and
proposal paths. A separate recount reads all **484 original step files**, checks
their recorded SHA-256 identities, binds each step's parent to its path entry,
and reconstructs every stored diagnostic row and total. Neither script imports
solver or fitting modules, fits weights, integrates materials or runs Newton.
This is verification of the existing trace, not an independent solver result.

## Where the additional iterations occur

| Recorded quantity | Secant | Learned path |
| --- | ---: | ---: |
| Initial iteration passes both residual and increment gates | 117 | 0 |
| Base iterations before terminal polishing | 478 | 598 |
| Accepted terminal corrections | 392 | 369 |
| Total reported Newton iterations / linear solves | 870 | 967 |

At all 117 target positions where secant passes both gates on its first
iteration, the learned path does not pass both. Learned first residuals are
larger at 175 of 242 positions. The median learned/secant initial relative
residual ratio is **10.349100**; all 242 secant denominators are positive.
The difference is 120 additional base iterations and 23 fewer accepted terminal
corrections, for 97 more reported Newton iterations and linear solves.

The frozen `newton.py` source is checked against Git
`664f128896dc08eeb3337264881fa2d869badc4e`. Its first convergence-history row
records the starting coordinates and residual. The increment gate already
requires an assembled tangent and a linear solve; these observations do not
imply that baseline convergence can be detected without computation. Terminal
polishing still follows a successful gate check and is counted separately.

Only **two paired positions have exactly equal parent checkpoint hashes**.
The two arms evolve their own accepted states. The remaining comparisons are
matched target positions, not exact-parent counterfactuals. This diagnostic
therefore does not prove that the learned correction alone caused each failure
or isolate a constitutive regime such as elastic unloading.

## Implication for the next learning experiment

The trace supports testing whether a correction policy preserves an already
successful deterministic baseline, in addition to reducing coordinate error.
Any proposed gate must be trained using training cases alone, compared with
secant over complete histories, and charged for its own assembly, inference and
retry costs. Repetition and all historical training costs remain necessary for
a net-saving claim. No such gate or new policy is implemented by this diagnostic,
and the running numerical protocol is unchanged.

Public experiments can widen the represented geometries, material behavior and
loading histories once their source/model correspondence is established. Their
measured response channels do not directly provide a solver's internal warm-start
coordinates or material states. Those labels still require a corresponding,
validated model and explicitly accounted reference analyses. Source diversity
and a runtime-relevant objective address different unresolved parts of M3.

## Retained evidence and cost

The [machine summary](rc-first-iterate-diagnostic-20260910.summary.json) identifies
the original diagnostic and recount under the active runtime-selection packet's
`development-diagnostics/` directory. The 242 paired rows and all 484 original-file
identities remain in `train-b-ridge10000-first-iterates.json`, SHA-256
`70a21a40cdd8a2d26bfe9f6aff8f2c0104587cb79c8bc871b1707e1483662dc3`.
Both scripts are retained beside it. The diagnostic takes 0.895858 s internally;
the recount takes 0.909874 s internally. Their separate process setup and outer
coordination costs are not included in those intervals. Both read completed
files while the broader cost benchmark remains on the shared host; no isolated
hardware timing claim follows.

The containing packet is still unsealed. A separate audit supervisor waits for
the original numerical parent and worker to terminate successfully before
launching one full original-record audit. It never restarts numerical work.
Audit completion, learned gain, public-data admission and full-roadmap closure
remain unproved.
