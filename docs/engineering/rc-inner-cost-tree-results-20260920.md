# Fixed offline prefix cost-tree development result

The predeclared depth-three/minimum-eight/0.01 policy completed 20 fits at source `ce6c18f24a8597e7976c0bf2eec94bba0e06f15e`. This is a post-hoc model-family development comparison after inspecting the linear results, not a fresh independent holdout.

| Outcome | Count |
| --- | ---: |
| True positive | 1 |
| False positive | 1 |
| True negative | 627 |
| False negative | 31 |
| Unknown | 0 |

The 660 overlapping validation decisions come from 165 source samples. Each fold uses 99 triple-excluded training rows and 33 excluded validation rows. Both proposals occur in outer group 2 / validation group 1. Precision is 50% on two proposals; recall is 1/32 (3.125%). These small counts do not establish generalization or runtime benefit. No policy is promoted and no full-path campaign follows this result. Reserved cases remain untouched. The original linear results and thresholds are unchanged.

Total fitting took 1.155721395 seconds; the driver took 2.884950647 seconds and its enclosing process 4.720658331 seconds. Those scopes overlap. Historical label generation, preflight inventory verification, deployment feature extraction and full-path execution are not included in the fit duration. No structural solve was added.

A separate retained-output audit verified all 2,565 packet files, reconstructed input bindings, excluded cases, sample disjointness, training bounds, every node partition/support and leaf mean, original three-repeat targets, and all validation decisions. It took 1.811965860 seconds with no refit or solve. It is not a second implementation of optimal split selection. Focused implementation coverage previously passed 155 tests; the workflow selection contract passed separately.

Evaluation inventory: `eb06c7a18a4e2a6100d24f3cfc3004878d11ad77870fd6d55a0bc3d8fdc62483`.
Audit inventory: `caaec1eb86c672ff0b61a2ebb67b661142653764f3e1a63fc6db6a7454aa7ae1`.
Exact roots, selected rows and timing scopes are retained in [the summary](rc-inner-cost-tree-results-20260920.summary.json).

The fixed tree detects one beneficial decision missed by both linear variants, but misses 31 others and selects one harmful decision. This does not justify online integration. Further development must keep model-family selection separate from untouched project-level confirmation and include actual policy overhead.
