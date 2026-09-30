# Mixed converged and failed public planar backend cohort

Numerical source: `abe9f2abf217a50df79f8e17af145970d98e2683`.
The protocol fixed three related generated portal variants before execution:
2.4 m height / 30x nodal loads, 3.6 m / 30x, and the existing 3 m / 40x failure
condition. The original span is 4 m. Sections, material laws and supports are
unchanged. These are development cases from one fixture family, not independent
projects, measured experiments, or training/holdout admission.

Each case ran on dense, sparse spsolve and extended sparse splu CPU backends,
three repetitions each, with rotating order and fresh workers. All 27 slots were
declared and retained, with no warmups, retries, outcome-based admission or
tolerance changes. Each used four monotone load factors, residual tolerance
1e-10, increment tolerance 1e-12, 40 Newton iterations and 180 s timeout per slot.
Full-history and terminal comparison tolerances remained absolute plus relative
1e-9. No cyclic-public or independent physical qualification is implied.

All 27 workers entered the API, produced valid artifacts and retained eligible
resource measurements. Nine converged; eighteen failed. The enclosing experiment
took 139.726 s. Workload medians below include valid failed executions and exclude
interpreter startup and separate parent validation; they are not total user time.

| Case | Converged / declared | Dense median s | spsolve median s | extended splu median s |
|---|---:|---:|---:|---:|
| short_30 | 9 / 9 | 2.945830 | 2.976082 | 6.772223 |
| tall_30 | 0 / 9 | 2.347336 | 2.375750 | 2.478076 |
| base_40 | 0 / 9 | 2.024640 | 2.074833 | 2.206669 |

Only the converged case receives backend ratios: 1.01027 and 2.29892 relative
to dense. Neither sparse backend accelerated this small case. Failed cases have
null speed ratios and null paired performance comparisons; stopping earlier is
not a speedup. No learned policy was used or promoted.

Six converged cross-backend comparisons passed both terminal SI and full-history
checks. Twelve failed-case comparisons stayed unavailable. Six same-backend
converged repeat pairs were byte-identical across result, validation, checkpoint
and history. Twelve failed repeat pairs separately had byte-identical result and
validation files; these are repeated diagnostics, not accepted physical results.

The new observed-path diagnostics expose computation previously hidden behind an
empty public failure history. Every tall_30 execution attempted four steps,
committed three and retained 23 convergence-history rows. Every base_40 execution
attempted three steps, committed two and retained 18 rows. Both terminate with
`line_search_failed_to_reduce_residual`; every failed step rolls back exactly to
its parent checkpoint. These row counts do not measure all solves or assemblies.
No failed result exposes accepted engineering rows or a resumable checkpoint.

The converged short portal develops concrete tensile damage (maximum about
0.986410), but zero observed steel accumulated plastic strain and zero compressive
damage. This cohort does not extend the previously observed steel-plastic range.
Material maxima for failed paths remain unavailable rather than zero.

The audit checked 458 source files against both the frozen snapshot and current
source, 234 artifact identities, all input identities, and recomputed all 18
comparison records. Original packets are immutable at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-mixed-cohort-eto8cjp_`.
The inventory covers 924 files / 18,228,962 bytes, excluding itself; its SHA-256 is
`e3a6901d1a0434e02b0b3bd4a20a56daf45e0f8e42ff8dff2d9ec835586f4fb6`.
It includes the protocol, generating runner, inputs, full source, worker records,
audit code and audit results. Earlier sealed experiments remain unchanged.

This closes the new bounded mixed-outcome measurement, not the full roadmap.
Independent verification, net learned benefit, broader structural families and
public cyclic scope remain open. At the preceding published `ba15cefcf`, Native
PR Fast run 34734647479 passed all 15 jobs; full Python run 34734647531 failed
external evidence preparation before the full tests. The inspected shard retained
`legal_approval=False`, `external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. These are prior-head CI facts,
not qualification of this numerical source.

The preceding-head development-contract job 103663741296 subsequently completed
successfully: 951 tests passed in 1003.64 s. Publication waited for this job to
finish. This does not replace the new numerical source's 161 local checks or
qualify its full repository suite.
