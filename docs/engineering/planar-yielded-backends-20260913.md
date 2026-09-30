# Public planar parity with steel plasticity and compressive damage

Numerical source: `3c7335cf09f862a7d54d2dff6978854bf3a2a0da`.
The public load-control path now has an executed repeated backend observation
with both steel plasticity and concrete compressive damage. This is a generated
single-portal development case, not an independent structure or measured test.

## Frozen admission screen and failures

Before inspecting outcomes, three inputs multiplied every nodal load component
of `examples/planar_frame_rc_portal.json` by 30, 40 and 60. Geometry, materials,
reinforcement, four load factors, 40-iteration limit and convergence tolerances
were unchanged. One fresh dense worker ran each input, with a 180-second timeout.

All three entered the API and produced contract-valid artifacts. Only 30x
converged. Its four-step history reached steel accumulated plastic strain
0.0027202413550242756, concrete compressive damage 0.44583384340806154 and
tensile damage 0.9999941562746681. These are internal constitutive variables,
not measured physical damage or acceptable-design findings.

The 40x and 60x cases returned `not_converged`, both with source diagnostic
`line_search_failed_to_reduce_residual`. Their original results and process
costs remain retained; neither was retried with changed tolerances. They export
no committed history file, so material maxima and committed-history step counts
remain unavailable, not zero. An initial audit assumption that every slot had
a history file was corrected to preserve this distinction. The screen finished
with exit 1 and a 16.099-second enclosing interval.

## Repeated follow-up on the admitted development case

The 30x case was explicitly selected after that screen. A separate frozen request
then ran dense, legacy sparse and extended sparse backends three times each,
rotating their order without warmups. The screen's dense run is not pooled into
the repeated timing sample. The host was not independently isolated.

All nine slots converged and validated, with 36 committed steps. All six
cross-backend terminal/full-history comparisons passed the unchanged 1e-9
absolute-plus-relative tolerances. Six same-backend repeat pairs have identical
result/checkpoint/history/validation bytes. Every slot has nonzero steel plastic
strain, concrete tensile damage and concrete compressive damage.

| Backend | Median workload seconds | Ratio to dense median |
| --- | ---: | ---: |
| Dense | 3.569268 | 1.0000 |
| Sparse spsolve | 3.626644 | 1.0161 |
| Extended sparse splu | 7.399370 | 2.0731 |

The sparse backends were slower on this six-free-equation case. Workload includes
public API execution, validation, history and artifact production; it excludes
interpreter startup and separate parent validation. The enclosing experiment
interval was 69.394 seconds. No AI, fit or policy promotion occurred. The chosen
case and these timings do not establish larger-model scaling or generalized speed.

## Preservation and remaining scope

The audit checked 458 copied source files, 90 artifact identities, recomputed six
comparisons and directly checked six exact repeat pairs. It ran no new Newton
solve and provides same-solver consistency, not independent physical validation.
The [machine summary](planar-yielded-backends-20260913.summary.json) binds both
read-only packets, their inventories, failure records and unrounded material/time
observations. Counts excluding each inventory are 504 files / 9,778,856 bytes for
the screen and 759 files / 16,584,484 bytes for the repeated experiment.

The public path remains monotone. Cyclic public loading, broader topologies,
independent external/experimental validation and learned net benefit remain open.
At this source, Native PR Fast run `34733785520` passed all 15 jobs, including
native merge/product, distribution, oracle parity, restart and bounded E2E. Full
Python shards failed evidence preparation; an inspected shard retained
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. No full-suite or release
qualification is inferred.

The same-source development-contract job `103661416950` subsequently completed
with **951 passed in 890.13 seconds**. This is the explicit development selection,
not the full repository suite. The experiment report was held until that job
finished so its run was not cancelled by another push.
