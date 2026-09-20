# 2,048-layer complete history: one concrete group still exceeds 1%

All 40 targets from 2 to 80 mm complete and commit with `contract_pass=true`.
The unchanged numerical source is `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`;
the frozen driver/auditor source is `2f5d5d6dc671ae6e09d16ca87d5297155de02b24`.
The original proportional force vector, control DOF 15, material parameters,
reinforcement and tolerances are retained. This is not the separate constant
axial-load RC learning experiment.

The complete 1,024/2,048 comparison passes all **400 nodal/steel groups** and
**239 of 240 concrete groups** at the original 1% screen. The remaining failure
is tensile damage at **74 mm, E3:gauss-2, coarse cell 269** (zero-based). Its
relative group difference is **1.08501989%**, with exactly one projected cell
above the original group-normalized screen. The absolute damage difference is
0.01085019889046962. The screen remains 1%; it is not rounded into a pass.

| Concrete field | Maximum group difference | Target |
| --- | ---: | ---: |
| Tensile history strain | 0.0181010% | 2 mm |
| Compressive history strain | 0.0148752% | 58 mm |
| Tensile damage | **1.0850199% — fails** | 74 mm |
| Compressive damage | 0.1241516% | 80 mm |
| Dissipated energy density | 0.0605652% | 34 mm |
| Stress | 0.1104935% | 80 mm |

Across successive layer pairs the failed concrete-group counts are now
70 → 34 → 27 → 14 → 1. The maximum tensile-damage difference drops from
2.1472% in the previous pair to 1.0850%. Compression, which previously rebounded
to 1.2014%, is now below the screen. This is useful refinement evidence, but
does not prove a convergence order, uniform convergence across arbitrary
histories, physical accuracy or qualification of a larger public API.

## Costs, storage and verification

- Setup: 0.620551 s; numerical path: **4,506.764094 s (75.1 min)**.
- Through full artifact hashing: 5,086.989949 s; enclosing numerical process:
  5,101.172651 s. These intervals contain earlier work and must not be added.
- Separate complete comparison audit: **492.752631 s**, zero new solves/fits.
- Maximum numerical-child RSS: **1,431,092 KiB**; audit RSS: **2,246,348 KiB**,
  with zero swaps. The incremental writer and bounded reader operate on the
  complete larger artifact; these observations are not a matched speed ratio
  against the earlier differently sized/implemented observation.
- The numerical packet contains 508 verified files / **21,294,980,598 bytes**;
  the controller packet contains 969 verified files / 19,095,126 bytes. Keeping
  both the original full JSON and per-step copies deliberately increases disk
  usage. Lower peak memory does not make the full research evidence cheap.
- A separate post-completion inventory verification checks every payload file
  in 12.983177 s. No numerical work is repeated to report the result.

The [machine summary](planar-2048-refinement-20260920.summary.json) preserves
all maxima, the sole failure, exact original/source/index/inventory hashes,
costs and resource receipts. The final path hash is
`434faa33ae5360b332897d3e0c7171844a95182630082d9f9689a885d7ff71f6`;
the final index hash is
`e1fabd392c7a32648cac7afd610483940fff467cdcf0413bce2e1a057a66878d`.
Both numerical and audit processes exit zero and the controller is terminal.

The next physical-model task remains resolving the fixed-screen local tensile
damage failure with an explicitly scoped diagnostic or refinement, while
retaining independent validation requirements. No 4,096-layer run, new
tolerance or public-range promotion is implied by this result. The separate
prepared learning-label campaign may now be admitted without overlapping this
completed numerical/audit workload.
