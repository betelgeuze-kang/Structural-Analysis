# Fixed higher-load planar connectivity cohort

Numerical source `29af2b0f9bcd481058cae1cabb192b91f65c4506`. Following the
[lower-load cohort](planar-topology-cohort-20260914.md), the same two generated
connectivities were assigned **30 times the original portal nodal load** before
execution (six times the preceding cohort's load). All other input construction,
materials, sections, supports, four monotone steps, solver and comparison
tolerances remained fixed. Each of three CPU backends ran three repetitions per
case, with rotating order, fresh processes, no warmups, no retries, and a 180 s
timeout per slot. Both outcomes were retained; no learned policy participated.

All 18 declared slots entered the API and produced intact, contract-valid
artifacts and eligible resource measurements. Nine converged and nine failed:

| Model | Converged / declared | Dense median s | spsolve median s | Extended splu median s |
| --- | ---: | ---: | ---: | ---: |
| Two-story | 0 / 9 | 2.581542 | 2.598251 | 2.742018 |
| Two-bay | 9 / 9 | 4.389952 | 4.420748 | 10.709710 |

These are API/validation/history/persistence workload medians, including failures;
interpreter startup and the separate audit are outside that interval. The full
experiment took 128.305576 s. Per-repeat times and population standard deviations
are in the [machine summary](planar-topology-highload-20260914.summary.json).

All nine two-story paths commit the first load step, then fail at factor 0.5
with `line_search_failed_to_reduce_residual`. They retain ten convergence-history
rows across two attempted steps and exact failed-step rollback to the accepted
parent. These rows do not count every assembly or solve. No accepted engineering
history or resumable checkpoint is exposed for the failed result, and complete
API work accounting remains false. Failed groups receive **null speed ratios**,
not an apparent speedup from stopping early. Material maxima are unavailable.

The two-bay histories develop concrete tensile damage up to 0.973963347604064,
but zero compressive damage and zero steel accumulated plastic strain. Six
cross-backend terminal/full-history comparisons pass; the six failed-case
comparisons remain unavailable. Six converged repetition pairs match result,
validation, checkpoint and history bytes. Six failed repetition pairs separately
match result and validation bytes; these are repeatable diagnostics, not accepted
physical solutions. The converged spsolve/dense median ratio is 1.007015 and
extended/dense is 2.439596: no sparse speed benefit was observed.

The separate original-record audit checks 461 source files, 162 artifact
identities, frozen inputs and all twelve comparison records. This adds a
generated multi-bay tensile-damage path and a repeatable multi-story failure;
it does not qualify independent physics, steel yielding or general cyclic paths.
The two-story convergence limit requires diagnosis without relaxing tolerances
or converting a failed execution into performance credit.

The immutable packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-topology-highload-ltygx_ms`.
It retains inputs, frozen protocol, generating runner, source, workers and audit.
Inventory: 845 files / 19,207,583 bytes, SHA-256
`b0892015b420debae2ff4cdeb4506bfaecf1cc9c69112ae848a95a2c3646a56a`.
The entire roadmap, independent validation and learned net benefit remain open.
