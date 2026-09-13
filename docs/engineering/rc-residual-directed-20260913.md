# Training-only residual-directed scalar diagnostic

Numerical source: `d8b22b206c0edcf66efe45b1a7c07390d9f43a7b`.
This follows the [coordinate-target diagnosis](rc-directional-target-20260913.md)
with a different objective on the same twenty already inspected training parents.
It is neither held-out evidence nor a trained policy or completed Newton path.

## Protocol and result

Four original training cases use fixed indices 1, 61, 121, 181 and 241.
From the unchanged original reference parent, assemble residual `r` and Jacobian
`K` at the deterministic secant seed. Let `d` be secant minus the last accepted
augmented coordinates, with its prescribed control component zero. Set
`alpha = clip(-dot(r, Kd) / dot(Kd, Kd), -1, 1)` (zero for zero denominator),
then assemble again at `secant + alpha*d`. This minimizes the local linearized
squared residual along that one direction. The actual nonlinear residual is
measured separately; a linearized improvement need not improve its infinity norm.
The prescribed coordinate remains fixed. No current accepted-answer coordinate
is used in this coefficient; the historical sample container does contain labels.

Across 40 explicit residual/tangent assemblies at twenty parents:

| Observation | Count |
| --- | ---: |
| Lower actual relative infinity-norm residual | 8 |
| Equal residual | 4 |
| Higher residual | 8 |
| Secant residual-gate passes | 5 |
| Proposal residual-gate passes | 5 |
| Newly passed / lost gates | 0 / 0 |

Train-b indices 61 and 181 have proposal/secant residual ratios
0.16575036014628797 and 0.0193073950852246. These reductions still do not create
new gate passes. Other small changes must not be presented as numerical or
runtime gains. Gates use each original request's unchanged tolerance; this does
not test increment convergence, commit acceptance or full-history equivalence.

## Cost, provenance and interpretation

No new policy fits, Newton paths or linear solves were performed. Forty explicit
assemblies include both arms and do not estimate a deployed strategy's overhead.
The numerical loop took 1.755283160 seconds including case compilation, input
reads and row writes, excluding initial staging/imports and the separate audit.
It is not a timing comparison or total research cost.

The audit recomputes all coefficients and proposed seeds, checks unchanged native
parent bytes, verifies source archive/extracted files and original input hashes,
and matches every baseline seed/residual/tangent exactly to the earlier source's
saved secant outputs. This is internal consistency, not independent physics.

The immutable packet contains source, protocol, execution script, rows, summary,
and executable audit; its inventory and counts are in the
[receipt](rc-residual-directed-20260913.summary.json). No previous packet was edited.

The residual objective exposes a useful distinction from coordinate loss, but
this one-direction representation has not earned a learned fit or production
integration. Keep secant. A subsequent correction representation must first show
actual work reduction on supported training cases, then be frozen before new
case-family evaluation with fitting, feature, assembly, verification and fallback
costs charged. Repeating these selected states is not independent confirmation.
The full roadmap, independent validation and public-data admission remain open.
