# Count actual Newton assembly dispatches during RC path comparisons

The [same-parent iteration diagnostic](rc-parent-iteration-cost-20260910.md)
showed why fewer inclusive convergence rows need not mean less work. Its old
records cannot establish total assembly calls. New comparisons can now record
actual vector-Newton assembly dispatches, including rejected and raised trials.
Historical records are not backfilled with inferred counts.

## Implementation and scope

`VectorAssemblyWorkRecorder` is an optional caller-owned sidecar for
`newton_raphson_vector`. It records ordered calls in six phases: primary
iteration, line search, terminal refinement, final observation, blocked
observation and the no-free-equations observation. Normal and compensated
coordinate dispatches are distinguished. An exception remains a spent call and
the original exception propagates through the existing solver handling.

The recorder forwards the original coordinate objects exactly once. It does not
alter residuals, tangents, corrections, tolerances, accepted states or numerical
result fields. A detached snapshot contains calls, returns, exceptions and any
in-flight call; a returned assembly is not a convergence claim. One adapter
dispatch may contain many element/material evaluations, which remain uncounted.

`benchmark_rc_control_seed_paths(..., record_assembly_work=True)` passes a fresh
recorder into every numerical invocation in every arm, including the fresh
reference and constant-load preload. Its declared request includes the recording
profile, and invocation outcomes retain `newton_assembly_work` alongside the
unchanged core/iteration/linear-solve accounting. Default recording is false.
An invalid non-boolean flag is rejected before output creation. A failed
numerical invocation retains its partial dispatch counts and the existing
unknown-work/failure state; known assembly calls do not make missing Newton work
known or qualify an incomplete path.

**This is not total application assembly work or assembly timing.** Adapter
terminal observations outside Newton, checkpoint recovery, separate verification,
material integrations and storage are outside this counter. The sidecar leaves
outside-Newton counts, material evaluation counts and time null. Existing whole
path elapsed time still includes the opted-in instrumentation and serialization;
the counters do not establish a performance improvement. The same-parent mode
remains a single-target comparison, even when recording is enabled.

## Verification

Focused tests exercise dense/sparse backtracking, accepted/rejected/raised
compensated terminal refinements, singular tangent, exhausted iteration budget,
unsupported backend, failed line search, empty-equation observations and escaped
exceptions. Actual adapter call observations are checked independently against
the recorder. Returned snapshots cannot mutate the caller's recorded rows.

Real RC fixtures compare recording off/on for binary64 and retained-coordinate
arithmetic, both with and without a constant-load preload. All four arms execute
three lateral targets with a reversal. Each numerical step file must be byte
identical across off/on runs, including its native parent, accepted state and
step hash. The four fixture combinations cover 56 paired step records (112
numerical invocations across both variants), not 56 independent structures.
Additional focused direct-step checks preserve parent bytes and step hashes.
These are local authored fixtures, not external experimental validation.

The recorded half of those paired runs contains 276 Newton assembly dispatches:
96 primary, 40 line-search, 84 terminal-refinement and 56 final-observation calls.
Its inclusive convergence counter is 164. This demonstrates why those counters
cannot be substituted for each other; it does not compare learned speed against
secant. The proposer in these fixtures is the deterministic secant callback.

The first resumed test failed because its file glob included four separate
preload-recovery outcomes as Newton invocations. The test now maps each numerical
step to its own outcome explicitly, retaining the recovery boundary. No solver
or comparison tolerance was changed to address that failure.

The independent development CI lane now includes both complete new test modules
(22 modules in total). The required full-suite preparation and aggregate gates
are unchanged. The machine summary records the final local command/result,
source hashes, fixture counts and separately inspected hosted results.

The final local run passes **303 tests in 117.96 seconds**, covering 14 complete
focused modules. Ruff, six-source scoped mypy and diff checks pass. The
[machine summary](rc-newton-assembly-work-20260912.summary.json) binds the source
snapshot and separate retained fixture records; the full repository suite was
not run locally.

## Repeated policy-selection integration

`run_rc_control_runtime_selection(..., record_assembly_work=True)` now carries
the same option through every ridge/case/repetition. The final frozen plan and
result declare the recording profile; each original fold report retains its
invocation sidecars, including preload and fresh-reference calls. Recording is
off by default and does not replace wall-time selection with a call-count proxy.
The recorded path time includes this instrumentation; original training-label
generation, fitting and independent evaluation remain separate accounting scopes.

The actual counterbalanced selection test uses two authored training cases, one
ridge, two withheld-case SVD fits and three repetitions per case. Its six folds
execute 24 complete paths, each with preload and four lateral targets, for 120
runtime numerical invocations. The test checks recording in every invocation,
unchanged reference/secant physical comparisons, frozen fit reuse, the complete
arm schedule and continued exclusion of the validation case from tuning. Both
static model gates abstain, so this fixture cannot demonstrate learned speedup.

The first integration run had 57 passes and one failure: repeated-plan formatting
overwrote the new cost-scope sentence. Applying the recording declaration after
the final repetition description fixes the frozen plan before hashing. A named
keyword also resolves the conditional-kwargs static typing error. The
[selection integration summary](rc-runtime-selection-assembly-20260912.summary.json)
records the final source/test result and retained repeated-execution files.

The final full selection-module run passes **58 tests in 118.91 seconds**; Ruff,
scoped mypy and diff checks pass. The six retained folds contain 648 recorded
Newton assembly dispatches across the 120 numerical invocations. Secant and
abstaining-proposal dispatch counts agree in every fold. These counts exclude
the fixture's original label-generation study and other tests in that module.
The sealed packet has 1,168 files / 63,621,317 bytes; inventory SHA-256
`9a4df1e1fd7253cbc8a9dc65215bdaabb680fcdab186f506b6783e74543a0641`.

## Hosted integration boundary (assembly-counter implementation)

The completed [9b21d748d run](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34452206521)
predates this implementation. Its original development JUnit artifact was
downloaded and its published SHA-256 checked. Full repository shards remain
blocked before their test steps; all **448 development tests** passed. This hosted
result does not include the new assembly recorder. Development-lane success is
not a full-suite
pass. The earlier inspected c1470918 shard log explicitly names
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Those external requirements
are not weakened by this change.
## Follow-up experiment

[Immediate line-search reuse](rc-line-search-reuse-20260912.md) uses the actual
dispatch counter to measure a bounded deterministic optimization: 128 fewer
assemblies with 224 byte-exact paired step records. Default solver behavior and
the unproved status of learned net benefit remain unchanged.
