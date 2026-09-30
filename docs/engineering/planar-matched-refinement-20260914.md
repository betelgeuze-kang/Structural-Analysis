# Matched-load response differences across concrete layer counts

This follows the [section discretization sensitivity](planar-section-refinement-20260914.md).
Three low-level dense paths use the same frozen source
`3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`, original model files for 8/16/32
concrete layers, and common load targets 0.25, 0.5 and 0.75. Original input and
461 source hashes are checked before import/compilation. All three complete
this prefix with unchanged Newton residual/increment tolerances and configuration.
The original target 1.0 is not attempted or claimed completed in this study.

Before execution the protocol fixes an **exploratory 1% refinement screen** for
five response groups: roof-right UX, all translations, all rotations, support
forces, and support moments. The score is the infinity norm of coarse-minus-fine
response divided by the finer response infinity norm, with declared denominator
floors of 1e-12 m/rad and 1e-9 kN/kNm. It is a group norm, not a bound on every
small response component. This screen is not a solver tolerance, design criterion
or independent accuracy reference.

| Layer pair | Load factor | Roof UX difference % | All rotations difference % | All five groups within 1% |
| --- | ---: | ---: | ---: | --- |
| 8 → 16 | 0.25 | 1.170991 | 1.288865 | no |
| 8 → 16 | 0.5 | 1.094748 | 1.123218 | no |
| 8 → 16 | 0.75 | 1.856580 | 1.934886 | no |
| 16 → 32 | 0.25 | 0.274877 | 0.299715 | yes |
| 16 → 32 | 0.5 | 0.167207 | 0.162468 | yes |
| 16 → 32 | 0.75 | 0.697693 | 0.737396 | yes |

The largest 16-to-32 difference among all tested groups/targets is about 0.7374%.
This supports bounded prefix response stability under this refinement pair; it
does not establish asymptotic convergence, response equivalence at untested loads,
or physical accuracy. Material fibers differ between grids, so their histories
are deliberately not equated by row position. Member/integration discretization,
material calibration and independent comparison remain separate requirements.

Core path times are 3.929297, 5.547421 and 11.336770 s for 8/16/32 layers;
compilation and enclosing costs are separately retained in the
[machine receipt](planar-matched-refinement-20260914.summary.json). These are
single observations of different numerical models, not speedup measurements.
The three paths retain respectively 22/21/25 history rows and 19/20/30 line-search
trials. All checkpoint chains and committed step gates are checked from original
artifacts. The audit recomputes every comparison from original response arrays.

The immutable packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-matched-refinement-7q_xoc5w`
contains the predeclared protocol, generator, full paths, audit code and results.
Inventory: eight files / 30,288,019 bytes; SHA-256
`c5af102531c35431d3380b3a72daed00969c87e441f54bf61e7881103bc3f457`.
No training fit, public-profile promotion or full failed-path recovery is added.
