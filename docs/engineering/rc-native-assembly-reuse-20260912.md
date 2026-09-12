# Native opt-in RC line-search assembly reuse

`reuse_line_search_assembly=True` now enables the measured optimization in the
RC displacement-control step, full seed-path benchmark, and repeated runtime
policy selector. All default values remain false. Native execution does not
replace module functions or install a shared cache.

## Scope and invariants

Each RC step creates a new `VectorLineSearchAssemblyReuse` bound to its existing
adapter and immutable accepted parent. The cache holds only the immediately
preceding line-search result, copying its arrays. It can be consumed once by the
next primary iteration at byte-identical coordinates, dtype and shape. An
intervening call, compensation or different coordinates prevents a hit. Binding
to another problem is rejected. Exceptions clear pending data and propagate.
The RC caller clears the cache in `finally`, including escaped solver errors.

Terminal refinement, final observations, blocked observations and post-Newton
physical verification still execute the original assembly. No tolerance,
convergence criterion, material law, commit/rollback rule or accepted-state hash
is changed. Generic Newton never enables reuse automatically: its optional cache
argument requires an explicitly certified deterministic problem. The supported
RC entry point creates this argument only for its original validated adapter.

`VectorAssemblyWorkRecorder.call_count` remains actual dispatch work. Hits are
reported separately as `line_search_reuse_hit_count`; no hit is a fictitious
assembly or a Newton-iteration reduction. Default reports omit this field.
Constant preload remains fresh; reuse applies only to control steps.

The benchmark request records
`line_search_assembly_reuse=rc-control-immediate-line-search-reuse.v1` before
execution. The repeated selector includes the same declaration in its hashed
plan and result, forwards it to every fold, and charges actual path costs. All
strategies, including fresh reference, use the same chosen implementation. The
selection score remains full path wall time with completed-history/known-work
gates; assembly counts do not replace it.

## Reproduction

The research runner defaults to native execution. Its explicitly selected
`--implementation wrapper` remains available solely to reproduce the historical
serial experiment; it is not used in native comparisons.

```bash
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 scripts/diagnose_rc_control_line_search_reuse.py \
  /absolute/new/output-directory --repetitions 2 \
  --case yielded-prefix --arithmetic retained --implementation native
```

The [previous yield/unload study](rc-yielded-reuse-20260912.md) records both the
successful retained wrapper comparison and the failed binary64 baseline. This
implementation does not clear that baseline failure, establish learned net
benefit, or close external physics/CI/release gates.

## Executed verification

The native retained-arithmetic yield/unload comparison completed two repetitions,
alternating baseline-first and reuse-first. All **128 paired step files match
byte for byte** and all **12 full-history comparisons pass**. There are 256
actual step executions across 16 complete paths. Committed steel plastic memory
first becomes positive at step index 14 on every path and remains positive after
unloading. No parameter or target search was performed.

Actual dispatches are **1,576 baseline / 1,156 reuse**, with **420 separate cache
hits** (26.65% fewer dispatches). Whole-benchmark wall ratios are 0.796367 and
0.796011; the ratio of summed times is **0.7961889129**, or **20.38% lower** in
this observation. Timing includes serialization, verification, counters and
reuse overhead. These two repetitions on one authored model and a non-isolated
host are not a general speed guarantee or learned-model benefit.

Validation groups passed: 189 core/physical-gate/reuse checks, 113 selector,
warm-start and parent-context checks, and 14 CI-contract checks. The historical
wrapper suite then passed 20 checks, 19 overlapping the first group. Its keyword
compatibility with the new dispatcher was repaired after the native experiment;
no measured numerical source changed. Initial failures in two existing test
doubles were fixed by accepting the current instrumentation arguments and
checking forged-metric rejection with reuse both off and on. Actual numerical
gates were not relaxed. Ruff and scoped mypy checks passed.

Repeated-selector tests execute actual three-order, two-withheld-case runs with
reuse off and on, keeping fit reuse, cost accounting, full-path comparison and
zero-proposal abstention requirements. This demonstrates integration, not a
learned-policy improvement. New reuse tests run in the independent development
CI job; full-suite external evidence requirements remain unchanged. Hosted
results for the new commit are not yet claimed.

The packet preserves executed source snapshots, raw paths, counters, test logs,
and separately tested wrapper compatibility sources: **1,585 files / 80,827,643
bytes**. Its adjacent inventory was reread and checked, SHA256
`ebaf94db8f06df863ed48c001f1dc1d8b98ef31e8cf31a84f16f5834831fd515`.
[The summary](rc-native-assembly-reuse-20260912.summary.json) binds exact paths,
source hashes, counters, timings and material observations. Numerical source
files were checked against the captured execution snapshots before committing.
