# Optional terminal Newton correction for RC runtime comparisons

The damaged L-frame study at `24e34255649ced519991a60904efae6621f49e3c`
converged on all 18 paths but passed only 15 full-history comparisons. Three
learned paths differed from reference in near-zero forces, reactions and residuals.
Each passed the existing reference-load-scaled Newton criterion. See
`rc-fiber-damaged-learning-runtime-20260909.md` for the unchanged failed study.

`NewtonRaphsonConfig(terminal_polishing=True)` optionally attempts one final
Newton correction before a vector solution becomes an accepted checkpoint.
`FiberFrameRuntimeBenchmarkConfig(terminal_polishing=True)` applies the same
option to reference, deterministic secant, learned seeds and baseline recovery.
The public RC configuration and default execution remain unchanged. This is a
research execution option, not independent physics or new public material scope.

## Numerical and accounting contract

The solver first requires both existing residual and increment gates to pass.
If iteration budget remains, it reuses the already computed full Newton correction
as a single candidate. The candidate must have a strictly smaller residual norm
and pass the same residual tolerance. A fresh backend solve at the candidate must
pass its original diagnostics and unchanged increment tolerance. The candidate
increment need not improve relative to the original; it must satisfy that gate.
No convergence or comparison tolerance changes.

An accepted candidate becomes the final history row and is committed through the
original stateful adapter and full J1–J5 verification. A non-improving, invalid,
singular or otherwise numerically rejected candidate leaves the original converged
coordinates and history intact. Expected numerical errors and rejected sparse
diagnostics remain in an enabled-only `terminal_polishing` record. Programming and
instrumentation errors propagate. Exhausted iteration budget skips polishing;
reaction-only systems perform zero extra solves. Scalar Newton rejects the option.

All extra assemblies and backend attempts use the existing runtime recorders.
Total linear-solve count includes a rejected candidate's attempted solve; its
diagnostics stay separate from those of the selected valid path. Runtime attempt
rows retain the complete record and total solve count, including seeded attempts
and baseline recovery. An accepted polishing history row is an additional
iteration within the existing budget. Rejected work remains charged even though
it adds no selected history row.

## Binding and request versions

Disabled configuration and receipt serialization keep their original keys.
Enabled hashes add the option and `newton-vector-terminal-polishing.v1` profile.
J5 uses the explicit `stateful_fiber_frame2d_dense_or_sparse_cpu_newton.v2` solver
profile and binds attempted diagnostics. Its outer receipt schema remains unchanged;
the enabled nested contract is explicit. Full source rebuild and episode replay
still validate these fields and counts. Removing the flag and rehashing an enabled
receipt does not pass original-source validation. Other existing manual Newton
configuration hashes also include the option when enabled.

| Workload | Explicit polishing request |
| --- | --- |
| Runtime suite | `rc-fiber-runtime-process-request.v2` |
| Single strategy | `rc-fiber-strategy-process-request.v2` |
| Conditioned secant-correction learning | `rc-fiber-learning-process-request.v4` |

These profiles require `benchmark_configuration.terminal_polishing: true`.
Legacy requests accept their original fields or explicit boolean false from
current `dataclasses.asdict` callers. False is normalized out of benchmark identity.
True requires the new profile; missing/false/non-boolean values in a polishing
profile fail before execution. Use `config.to_dict()` for canonical benchmark
requests. Learning v4 retains the v3 train-only fit contract: polishing controls
evaluation, while collection uses the unchanged public reference analyzer.
The isolated-suite input compiler, child request and parent collector bind the
same option, including the parent's reconstructed solver-configuration hash.

## Verification before measurement

These are separate working-tree checks, not an exact-head full-suite or external
verification claim:

| Scope | Result |
| --- | --- |
| New algebraic vector-polishing regressions | 44 passed |
| Existing Newton configuration and extended sparse regressions | 48 passed |
| J5 and episode files | 51 tests covered across original/affected runs |
| Runtime/strategy and new integration group | 108 passed, one stale J5 failure; affected test then passed |
| Enabled fresh-worker parent collection | Passed with reference and secant workers |
| Existing process/suite, line search and reaction-only regressions | 144 passed |
| Quality-gate and product-CI boundary contracts | 44 passed |

The enabled in-process integration includes three arms, full authority checks,
reference episode replay and retained attempted diagnostics. J5/episode tests
include a four-step L-frame and rehashed tampering. Initial J5 fixture validation
used incorrect zero-based iteration arithmetic: 34 tests passed and 17 fixture
errors were retained; after correction, the affected group of 24 passed. The
first algebraic run had three stale expected reason strings, also retained before
correction. Review found a missing option in the parent collector's second hash
check; an actual worker test covers the fix. Failed attempts remain recorded.

The fixed-source observation at `936e230cec9942e10121273fed7fab336579e3bb`
reuses the original damaged-study policy and two evaluation inputs. Default
public/checkpoint bytes match the prior result exactly. All 18 paths and six
reference episodes pass with unchanged tolerances. Interior learned paths are
faster than secant in all three pairs (median 0.414968981 s), while load-OOD
fallback is slower in every pair (median 0.875481976 s). See
`rc-fiber-terminal-polishing-runtime-20260909.md` for all repetitions, rejected
corrections, complete cost scopes and saved-artifact identities. Broader
independent, licensing, hardware, hosted and owner gates remain open.
