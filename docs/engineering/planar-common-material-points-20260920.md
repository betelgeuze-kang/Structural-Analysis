# Two common-coordinate material-history probes

This post-hoc diagnostic separates sampling-location effects from accepted
section-history differences at the two maximum-damage witnesses of the completed
[128/256 comparison](planar-256-refinement-20260920.md). It does not replace that
comparison or its failed local screen. The points were selected after inspecting
the results and are not an untouched evaluation set.

The frozen `concrete_damage.py` is byte-compared with Git revision
`3e2cc1dba5c6dac1b12eb1badc9b6df09337b847` before import. Material parameters come
from the pinned canonical input. Original prefix/suffix and full 256-layer path
hashes, accepted checkpoint chains, restart and chosen section bindings are
verified. At each of forty targets, strain at the same physical y coordinate is
computed from each path's accepted axial strain and curvature, and the original
material law advances from its preceding diagnostic state.

The 128-layer replay reproduces every original chosen fiber state dictionary
(including state hashes) and stress **exactly**, at both points through all forty
targets. The 256-layer value is instead a derived common-point response: that
point lies between its actual fiber midpoints. It was not used to solve equilibrium
and must not be presented as a solver-issued accepted fiber state. The successful
probe performs 160 material integrations, zero structural solves and no fitting.

| Chosen point | Target of original projected maximum | 128-layer accepted damage | Derived 256-history damage at same y | Absolute damage difference |
| --- | ---: | ---: | ---: | ---: |
| E3 / Gauss 0 / y=0.17578125 m, tensile | 78 mm | 0.0100979983 | 0.0113292957 | 0.0012312974 |
| E3 / Gauss 2 / y=-0.23203125 m, compression | 72 mm | 0 | 0 | 0 |

The tensile absolute difference is much smaller than the original cell-projected
maximum, but is still about **10.9% of the small local derived tensile damage**.
Using a global maximum or a near-zero local denominator answers different
questions. No alternative pass threshold or local-accuracy claim is introduced.

Across the complete forty-target history of these two points, the largest
same-coordinate tensile-damage difference is 0.002105996 at 80 mm. The largest
compressive-damage difference is 0.000291742 at 80 mm. Largest stress differences
are 0.00701940 MPa (tensile witness, 72 mm) and 0.00799142 MPa (compression witness,
72 mm). These observations support a sampling-location contribution to the
projected damage-onset discrepancies. They do not establish the only cause,
all-location field agreement, asymptotic convergence or physical validity.

## Reproduction and retained evidence

Use `scripts/probe_planar_common_material_points.py` with the original packet
parent, the 256-layer packet and a new output filename. It rejects changed
material source before import and refuses to emit a successful result if the
coarse replay is not exact. Focused observer/source-integrity tests passed
**24 tests in 1.58 s**; real replay checks provide separate bounded numerical
self-consistency evidence, not independent validation.

The report, probe and shared input/chain-check helper are retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-common-material-points-2pv_4yww`:
3 payload files, 112,830 bytes; inventory SHA-256
`69488aa7d0e296529d98640986e6c3ff84fcdd7ea1b3a01d33e0303e308bfc9e`.
The adjacent summary preserves chosen coordinates, maxima, full witness-target
values and provenance. The full packet keeps every target's derived and accepted
values separately. No original solver artifact was modified.
