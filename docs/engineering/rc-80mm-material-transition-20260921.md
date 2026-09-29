# Material transition observed at the 80 mm failed Newton state

This noncommitting diagnostic uses the verified frozen source `a94d82d1ed60317d36bce7f5af67730576f9ff61` and original failed recovery artifacts from both orderings. It reconstructs the exact residual and Newton direction, then evaluates 41 fractions from 1 through 2^-40 per state. Baseline plus samples total 84 frame assemblies; no nonlinear solve, accepted checkpoint, policy change or new training row is produced. Parent bytes remain unchanged, and all reported diagnostics repeat exactly.

Across the sampled fractions, the only fiber whose consistent tangent changes sign relative to the baseline is member-array index 0, section-response index 0, fiber-response index 1 (all zero-based). The original canonical model identifies the first member as M1. Tangent sign changes are observed for alpha 1 through 1/64; none are observed from 1/128 through 2^-40. This screens sign changes, not all possible changes in material state or tangent magnitude.

| Sample | Total strain | Stress MPa | Consistent tangent MPa | Damage evolved |
| --- | ---: | ---: | ---: | --- |
| Failed-state baseline | -0.0010000000020770079 | -29.99999997507591 | -11999.999990030365 | Yes |
| alpha 1/64 | -0.0009999999989019062 | -29.999999967057185 | 30000 | No |
| alpha 1/128 | -0.0010000000004894566 | -29.99999999412652 | -11999.99999765061 | Yes |

The concrete material's `_traction_and_tangent` selects elastic response at history strain <= strength/modulus, and its softening expression above that threshold. Here the compression threshold is 30/30000 = 0.001. The sampled stresses are close to the common peak, while their tangents have opposite signs. This is evidence of a constitutive tangent transition near the compression peak, not proof of a stress discontinuity, an incorrect constitutive implementation, or nonexistence of an equilibrium solution. The previous small linear-system error does not remove this nonsmooth nonlinear behavior.

The extended line-search experiment already shows that locating a descending fraction alone is insufficient. Further investigation should use the same original parent and explicitly account for this branch transition, followed by unchanged native acceptance and whole-history verification. Smoothing the material or loosening the tolerance would change the problem and is not performed here. No speed or physical-accuracy claim follows.

## Original evidence

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-80mm-material-cpwt822w` retains all sampled fiber strains/stresses/tangents and residual vectors, the pre-execution plan, driver, model and summary. All inventory entries were reread. Inventory SHA-256: `f38a4bc50563e0a408b3b5a5891a78dd814ecb2e59a27573e2d7060cb64350de`. Source bytes were checked against the earlier frozen packet before import.

[Machine-readable diagnostics](rc-80mm-material-transition-20260921.summary.json). The per-sample complete fiber arrays remain in the packet. This is repeated internal evidence from one state, not a new independent specimen or full-path result.
