# The alternate displacement path passes load factor 0.5 but remains incomplete

Following the [globalization pilots](planar-globalization-pilots-20260914.md),
this study uses the existing experimental corotational displacement-control
solver, with unchanged frozen model/source
`29af2b0f9bcd481058cae1cabb192b91f65c4506`. All 461 source identities and the
original input hash are checked before compilation.

The protocol fixes two fresh compilations and low-level paths before execution:
control roof-right node N6 UX (native global DOF 15), twenty monotone targets from
2 mm to 40 mm in 2 mm increments, dense backend and existing default tolerances,
iteration limit and line-search schedule. The **entire original proportional
force vector** is retained. Vertical force therefore varies with the solved
load factor; this is not a constant-axial-load test.

Both paths commit ten steps through 20 mm, then fail at the 22 mm target. Complete
low-level path bytes, including failure diagnostics, match between repeats.
Each path has 54 history rows and 49 line-search trials. Core path intervals are
7.257647 s and 7.159520 s; compilation costs are separately retained. Total
experiment time is 15.946555 s. These intervals exclude independent validation
and are not evidence of speedup over the different load-control problem.

Selected accepted points from the complete retained curve:

| Roof-right UX mm | Solved proportional load factor |
| ---: | ---: |
| 12 | 0.42494424704410866 |
| 14 | 0.4598918113923953 |
| 16 | 0.4731476639373157 |
| 18 | 0.4901080620419619 |
| 20 | 0.5145102207277285 |

This alternate path has an accepted state above factor 0.5. It prevents interpreting
the earlier load-control failure alone as proof of maximum structural capacity.
It does not establish matched material histories or response equivalence at a
common load factor, physical safety, or that the requested 40 mm path is feasible.

The 22 mm attempt terminates with
`line_search_failed_to_reduce_augmented_merit`; its last recorded relative
equilibrium residual is 0.030328528741139223. The unaccepted trial load factor
0.565505065652039 is **not an accepted curve point**. Both failures roll back
exactly to the 20 mm checkpoint. The audit checks checkpoint chains, committed
step gates, raw repetition equality and retained trial counts. It does not turn
this incomplete path into a public engineering result.

The [machine summary](planar-displacement-pilot-20260914.summary.json) retains
all ten accepted points, costs and failure state. Original inputs/source are in
the linked high-load packet; new full paths, protocol, runner and audit are at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-two-story-displacement-y4qvs71c`.
Inventory: six files / 22,580,834 bytes, SHA-256
`5471e429f6a5db0948bac94d6d3debf5811adc2a121c493eda3f300f53406189`.
No public profile promotion, learned benefit, independent verification or full
roadmap closure follows from this generated-model observation.
