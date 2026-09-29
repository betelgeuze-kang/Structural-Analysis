# Full common-coordinate concrete history diagnostic

The [two-point probe](planar-common-material-points-20260920.md) is now extended
to all 128 coarse concrete midpoints in each of the 18 retained sections, through
all forty targets. This removes selection of only two witnesses from the spatial
diagnostic. It remains post-hoc analysis of the same single geometry and load
history, not an untouched evaluation set or independent physical validation.

At every coordinate, the frozen concrete material law advances separately along
the accepted 128-layer and 256-layer section-strain histories. All **92,160**
coarse point/target state dictionaries (including hashes) and stresses reproduce
the actual accepted coarse fibers exactly. The two previously retained witness
objects also match exactly, including every target and derived fine value.
There are **184,320 material integrations and zero structural solves**. The fine
common-coordinate responses remain derived observations between fine fiber
midpoints; they did not participate in equilibrium or become accepted fibers.

## Observed absolute differences across all coordinates and targets

| Field | Maximum absolute difference | Target | Member / Gauss / coarse cell |
| --- | ---: | ---: | --- |
| Tensile history strain | 5.111594e-7 | 80 mm | E1 / 2 / 0 |
| Compressive history strain | 2.691738e-7 | 72 mm | E3 / 2 / 20 |
| Tensile damage | 0.002616624 | 72 mm | E3 / 0 / 100 |
| Compressive damage | 0.000332552 | 72 mm | E3 / 2 / 13 |
| Dissipated energy density | 5.676237e-6 MJ/m³ | 72 mm | E3 / 2 / 12 |
| Stress | 0.008256768 MPa | 72 mm | E3 / 2 / 33 |

Cell and Gauss indices are zero-based. Strain and damage are dimensionless.
Both damage maxima exceed those found in the two-point-only history check and
occur at neighboring cells at 72 mm. Thus the original two witnesses did not
bound the full common-coordinate differences. At this target the equal-point
mean absolute tensile and compressive damage differences are 1.188690e-5 and
1.877856e-6. Means do not cancel signed differences and are neither volume nor
energy integrals; they cannot replace local maxima or acceptance criteria.

The unchanged original projected 128/256 field screen still fails 34/240 groups.
Common-coordinate differences answer a different question from cell projection.
This diagnostic neither introduces a new pass threshold nor establishes
asymptotic convergence. It supplies all-coordinate witnesses for further
resolution studies while retaining the same material law and load history.

## Provenance and verification

Observer revision: `e4c82c5b9fd734c390282e74d3dde4a157f2be6a`.
Numerical source remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`.
The observer verifies the original material source against Git, pins the input
and all three path hashes, and checks accepted checkpoint chains, restart,
targets and section/fiber bindings. Each section binding is cached after
verification to avoid repeating large dictionary comparisons for each fiber.

The new packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-all-common-points-x71ahi_4`.
Its eight payload files total 114,553,071 bytes; inventory SHA-256 is
`48a9f4d2fafada99a732599e24212e2ba734c6e9f23a0fa59db60f663903ac8d`.
All listed lengths and hashes were checked after execution. The packet retains
the observer sources, protocol, every point/target observation, process receipt
and logs. The successful enclosing observer process took 36.120687030 seconds;
this includes reading, verification, material replay and output, not a solver
speed measurement. Original packets were unchanged.

Synthetic checks cover unsigned mean error, maximum location, duplicate points,
missing targets, unverified replay and nonfinite observations. Combined with
existing localization and steel audit checks, **35 tests pass in 1.72 seconds**.
Ruff, whitespace checks and the offline 480-entry source inventory pass. No
fresh GitHub metadata authentication is implied. The companion summary retains
all forty target-level maxima and means, with the full point rows in the packet.
