# Retained concrete projection error: history and spatial sampling terms

This diagnostic advances the unresolved 128/256-layer concrete comparison by
separating two terms using existing accepted fibers and the already retained
fine-history common-coordinate observations. No structural solve or material
integration is performed. The material law, loads and original screen are unchanged.

At each original coarse midpoint, let C be accepted coarse damage, M the derived
fine-history damage at that same coordinate, and L/R the accepted fine child
damages. The signed identity is:

`C - (L + R)/2 = (C - M) + (M - (L + R)/2)`.

The first term compares histories at the same coordinate. The second compares
the center value and child average under the fine history. This is an algebraic
decomposition, not a proof that either term is an independent physical cause.
M remains derived and did not participate in fine equilibrium. Signed components
can cancel; their absolute sums are not mutually exclusive error percentages.

## Complete observation and original-result cross-check

All 2,304 points through forty targets are included for both damage fields:
184,320 point/target/field decompositions. Every closure residual is exactly zero
in the recorded arithmetic. All **80 original target/field maximum absolute
errors and their witness locations match exactly** against the original pinned
projection audit. The 34/240 failed groups remain failures.

| Original maximum witness | Total signed error | Same-coordinate history term | Fine-history sampling term |
| --- | ---: | ---: | ---: |
| Tensile, 78 mm, E3/Gauss 0/cell 101 | -0.06683061524 | -0.001231297365 | -0.06559931787 |
| Compressive, 72 mm, E3/Gauss 2/cell 14 | -0.008742755568 | 0 | -0.008742755568 |

Values are dimensionless damage differences, not percentages. At the tensile
maximum the two terms have the same sign and the sampling term accounts for
98.1576% of the total magnitude; at the compression maximum it accounts for the
entire difference. Both witnesses have one damaged fine child and one undamaged
child. These statements concern these particular original maxima, not all points.

Cancellation matters elsewhere: at 78 mm, 1,177 of 2,304 tensile points have
opposite-signed components. The global sum of absolute sampling terms is
0.3569908111 while the sum of absolute total errors is 0.3611403835; neither is a
volume integral. For compression at 72 mm the absolute sampling sum even exceeds
the absolute total sum, so treating these sums as additive percentages would be
incorrect. All target-level descriptors remain in the machine summary.

## Implication for the next numerical experiment

At these controlling witnesses, a large projected discrepancy remains even when
coarse/fine histories are compared through the same fine-history observation.
This makes spatial resolution around damage onset a specific next investigation
target. It does not justify changing the material law, fitting an AI correction,
using small mean errors in place of the local screen, or declaring convergence.
A subsequent resolution/quadrature experiment must preserve the same model and
history, include these neighborhoods and all other points, and retain the original
screen alongside integrated descriptors. No such new solve is claimed here.

## Provenance and verification

Observer revision: `5bbd295b2` (full revision in the summary). The observer pins
the original all-point inventory and fine result, verifies the fine accepted
checkpoint chain, member/section/fiber bindings and strain locations, and checks
the complete unique point/target roster. It reads the original fine result and
saved derived observations; it executes no archived material source.

The [machine summary](planar-concrete-error-decomposition-20260920.summary.json)
records all forty targets, original pins, cross-check receipt and final packet
inventory. The process took 21.987757428 seconds, including reading, validation,
decomposition and output; this is not a solver speed measurement. Thirty-seven
localization/decomposition tests pass, including sign cancellation, history-only
and sampling-only cases, invalid damage and duplicate-point rejection. Lint and
whitespace checks pass. Independent physics and all roadmap closure requirements
remain open.
