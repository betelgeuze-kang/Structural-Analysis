# Local section response refinement over the accepted prefix

This is a read-only extension of the
[matched-load response audit](planar-matched-refinement-20260914.md). It reuses
the three original low-level paths at source
`3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`; their full artifact hashes are checked
before reading. No structural solve, assembly or model fit is added.

For each of three accepted load targets, both refinement pairs match six member
IDs and three integration locations per member. Integration abscissae and weights
must be identical. Axial strain, curvature, axial force and moment are then
compared at all 18 corresponding section positions. This gives 108 matched
section pairs across the two refinement pairs and three loads.

The previous exploratory 1% screen is applied to each quantity's group infinity
norm, using the finer-grid norm and explicit small denominator floors. This is
not a pointwise relative-error bound: full per-location values and the worst
absolute-difference witness are retained. Individual fiber stresses, damage and
history variables are not matched because the fibers differ between grids.

| Pair | Load | Axial strain difference % | Curvature difference % | Axial force difference % | Moment difference % |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 → 16 | 0.25 | 0.537508 | 1.420450 | 0.537508 | 0.195117 |
| 8 → 16 | 0.5 | 1.738620 | 1.160823 | 0.797442 | 0.316947 |
| 8 → 16 | 0.75 | 2.182979 | 1.785179 | 1.621751 | 0.836635 |
| 16 → 32 | 0.25 | 0.134821 | 0.338437 | 0.134821 | 0.038210 |
| 16 → 32 | 0.5 | 0.185658 | 0.206793 | 0.139816 | 0.058844 |
| 16 → 32 | 0.75 | 0.900672 | 0.774259 | 0.538512 | 0.108335 |

All twelve 16-to-32 quantity/load comparisons stay inside this exploratory
screen, with axial strain at factor 0.75 the largest difference. The 8-to-16
pair fails it at each load. This extends the observed prefix stability to the
listed local generalized responses; it does not establish material-history
equivalence, untested-load behavior, asymptotic convergence or physical accuracy.
The original factor-1 path remains failed. Member-length/integration refinement
and independent validation remain open.

The [machine summary](planar-local-refinement-20260914.summary.json) retains
normalizers, absolute differences, witnesses and aggregation cost. Full original
per-location comparisons and the reproducible audit script are sealed at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-local-refinement-y5iu7p_3`.
Inventory: two files / 123,864 bytes, SHA-256
`e4b5f85d16e85ea7e12c0bd77cb1a23fc1bdfd5004e871a49ab3d4a8c60c5e76`.
The original source/path packets are unchanged and no default policy is promoted.
