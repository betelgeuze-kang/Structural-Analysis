# Resumed 128-layer reference and complete-history comparison

This study restores the accepted 28 mm state from the fourteen-target 128-layer
run, then requests the remaining twenty-six targets from 30 through 80 mm. It
preserves the complete preceding material history while avoiding a redundant
solve of the already retained first fourteen targets. It is research-only
numerical refinement, not a public 128-layer API extension or physical validation.

The frozen source remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`. Source files,
canonical input and the original prefix path identity are checked before use.
The same 128-layer problem is reconstructed from the source geometry, steel and
materials. No load vector, control DOF, integration order, solver tolerances,
maximum iterations or search factors change. Vertical and horizontal forces
remain proportional; constant-axial loading is not claimed.

## Restart identity

The original prefix file SHA-256 is
`bf45ac18cc8cba25df3d79df3753b8f72f27bbb6fe556629b2605942e533dcc2`.
Its final checkpoint is serialized in the existing canonical checkpoint format
and loaded through the source package's strict checkpoint loader against the
reconstructed 128-layer problem. The restored state exactly equals the original
checkpoint, including 28 mm control displacement. Canonical checkpoint SHA-256:
`954bdc921d065a9fd8eb5d36e644b943d5c50c6b3ba14b240304f3446fb1c40e`.
Loading those same bytes against the original 32-layer problem is rejected.
These checks establish bounded model/state correspondence, not independent
signatures, physical accuracy or a general restart qualification.

The comparison auditor checks that the suffix initial checkpoint equals the
prefix final checkpoint. It then traverses all accepted transitions, requiring
the same forty target displacements as the 64-layer path, full parent chains and
member/section/steel accepted-state bindings. The prefix and suffix remain
separate immutable solver artifacts. Their concatenation is an in-memory
observation view, never written as a purported fresh solver-issued full path.

The exploratory comparison retains the previous 1% group infinity-norm screen
and denominator floors. Different concrete fiber locations are not matched;
steel positions and integration locations/weights are matched. No training,
policy promotion or performance-ratio claim is part of this study.

## Executed full-history observations

All twenty-six remaining targets commit and the suffix contract passes. Together
with the preserved prefix this provides forty accepted targets through 80 mm.
The restart boundary and every accepted checkpoint transition are verified. All
400 group comparisons across those forty targets pass the unchanged exploratory
1% screen. This supports bounded 64-layer nodal/steel-history agreement with the
128-layer comparator for this exact model and path. It does not establish an
exact continuum solution or unmeasured concrete fiber-history convergence.

| Group | Maximum 64-to-128 difference over all targets | Target |
| --- | ---: | ---: |
| Translations | 0.008088% | 48 mm |
| Rotations | 0.022725% | 80 mm |
| Support forces | 0.013918% | 2 mm |
| Support moments | 0.016020% | 14 mm |
| Load factor | 0.013993% | 2 mm |
| Steel stress | 0.093571% | 48 mm |
| Plastic strain, accumulated plastic strain, backstress, energy density | 0.733736% each | 24 mm |

The largest steel internal-state difference remains the previously retained
24 mm witness; none of the remaining targets produces a larger difference.
At 80 mm the proportional load factors are 0.7993986519469385 (64 layers) and
0.7994212313412383 (128 layers). Neither reaches factor 1. The earlier 32-layer
history still exceeds its comparison screen and is not rehabilitated by this
finer pair's agreement.

The suffix core path takes 196.921283 s. Its reported 2.664016 s setup interval
includes compilation, section reconstruction, prefix parsing and checkpoint
validation. The suffix experiment interval including serialization/hashing is
213.088327 s. Prefix and suffix core solve times sum to 306.390927 s; their
separately measured experiment intervals sum to 330.206277 s. Separate source
verification and auditing costs are outside those intervals. This is neither a
fresh uninterrupted 128-layer timing nor a statistical speed comparison.

The original prefix artifact and resumed suffix remain distinct. An uninterrupted
repeat was not performed; reproducibility of the 32-layer complete path was
measured separately. No independence, learned benefit, physical validation,
release acceptance or main integration is inferred from the restart result.

## Retained packet

The suffix protocol, runner, strict-restored initial checkpoint, restart-binding
receipt, full suffix result, run summary, auditor and full-history comparisons
are retained at:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-128-resumed-displacement-tp205v5p`

Eight payload files, 470,146,438 bytes; inventory SHA-256:
`5559121f56ef80326203b2d334c0fc8ea37f49cdffc35be99825e15e58ae7a96`.
Suffix path SHA-256:
`468ab97a53f92305f0bfc84807f0fe88a773df3800255e362eff445c484f48a5`.

The runner creates a new packet and records its location in
`/tmp/structural-128-resumed-displacement-root.txt`. The auditor verifies source
path hashes, joins observations only in memory and retains both execution
segments' provenance. All forty comparisons and floors are recorded in the
adjacent summary. The numerical scope does not override the independent
verification, material-law suitability, licensing and training-admission gates.
