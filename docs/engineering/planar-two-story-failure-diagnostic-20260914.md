# Two-story failure is not a near-tolerance residual stall

This follows the [fixed high-load cohort](planar-topology-highload-20260914.md).
One additional dense-backend API execution used its unchanged input and frozen
source `29af2b0f9bcd481058cae1cabb192b91f65c4506`. All 461 source files and the
model bytes were checked against that packet before importing. A wrapper retained
the returned internal path without changing its calculation or return value.
The resulting public failure JSON is **byte-identical** to original slot 0000.

This additional diagnostic call took 2.544795594 s inside the API/capture interval.
It is not another performance repetition and is not included in the earlier
cohort's 18 executions. The original experiment remains sealed and unchanged.

The first target, 0.25, commits. At target 0.5 the five recorded iteration-start
relative residuals are:

| Iteration | Relative residual | Accepted line-search alpha | Trial count | Accepted |
| --- | ---: | ---: | ---: | --- |
| 0 | 0.25000000000012834 | 1 | 1 | true |
| 1 | 0.16726341174762732 | 1 | 1 | true |
| 2 | 0.08057912119220782 | 0.03125 | 6 | true |
| 3 | 0.07806875480024435 | 1 | 1 | true |
| 4 | 0.033626080662215445 | 0 | 6 | false |

The final residual remains far above the unchanged 1e-10 convergence tolerance.
All six final line-search trials are rejected. The final row's increment gate
is true because no move is accepted; this must not be interpreted as convergence
of the proposed Newton correction. Its residual gate is false, the step does
not commit, and the failure result retains no accepted engineering authority.

The record narrows the next investigation to the trial tangent/direction and
load-increment path. It provides no reason to loosen tolerance or attribute this
failure to a near-threshold floating-point floor. It also does not identify
physical collapse, buckling, tangent inconsistency, or prove that smaller load
steps will succeed. A changed load grid would be a separate path protocol and
would require its own complete-history checks and costs.

The [machine summary](planar-two-story-failure-diagnostic-20260914.summary.json)
links the immutable packet, containing full coordinate/residual/correction
vectors, step metrics, exact public result and reproducing script:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-two-story-diagnostic-x7ekn8kg`.
Inventory: three files / 36,613 bytes, SHA-256
`91a45669be79aadb4cc1ca1f65cc029976843d6d52a72983ab85524de21f932b`.
No model fit, accepted replacement solution or independent validation was added.
