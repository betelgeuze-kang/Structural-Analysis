# Stop at the first verified feasible candidate

The explicit `stop_mode="first_verified_feasible"` option connects candidate
search, repeated suites, fresh process workers, portable review and Workbench.
It changes the search objective: find the first fully verified feasible result
in the frozen evaluation order under the declared maximum analysis budget.
It does not establish the globally cheapest candidate or an optimal design.

The default `stop_mode=None` continues to evaluate the entire planned shortlist
and choose the lowest scoped material estimate among its verified feasible
results, including the baseline. That default is also limited to the evaluated
set. Existing default fields, versions and hash construction are preserved;
the new field is omitted from default JSON. Neither mode changes the solver,
physical verification gates, caller limits, learned target profile or training.

## Calling the option

Pass the keyword to `compare_fiber_frame_candidate_search`,
`run_fiber_frame_candidate_search_arm`, or
`run_fiber_frame_candidate_search_oracle`. The repeated in-process API accepts
it on each `FiberFrameCandidateSearchCase`. All existing model, training, price,
terminal/history/material limit and budget arguments remain required or optional
as before. Material-memory limits still require response-history limits.

```python
from structural_analysis.benchmark.fiber_frame_candidate_search import (
    FIRST_VERIFIED_FEASIBLE,
    compare_fiber_frame_candidate_search,
)

comparison = compare_fiber_frame_candidate_search(
    baseline,
    candidates,
    training=training,
    prices=prices,
    terminal_limits=terminal_limits,
    history_limits=history_limits,
    material_history_limits=material_history_limits,
    config=config,
    source_revision=source_revision,
    full_analysis_budget=3,
    exploration_slots=1,
    oracle_audit=True,
    stop_mode=FIRST_VERIFIED_FEASIBLE,
)
```

For the existing JSON process request, set the outer schema to
`rc-fiber-candidate-process-suite-request.v3` and add
`"stop_mode": "first_verified_feasible"` to each opted-in case. Other case and
request fields are unchanged. JSON explicit `null`, booleans and unsupported
strings are rejected. A v3 request must contain at least one opted-in case;
other cases in that request retain their own default mode and worker version.
The existing CLI remains:

```sh
PYTHONPATH=src python3 -m structural_analysis.benchmark.fiber_frame_candidate_process \
  --request request.json --source-revision "$SOURCE_REVISION" \
  --output-directory output
```

Repeated suites still require an even repetition count in `[2,32]`, with
warmups in `[0,5]`. The option does not permit one-repetition shortcuts or change
the alternating online order. A process worker remains isolated per
case/phase/repetition/strategy. The oracle, when requested, follows both online
arms and evaluates the complete eligible pool with its own fresh baseline.

## Evaluation and retained results

Each online arm evaluates its baseline once. If any requested baseline
verification is unavailable or fails, it stops with
`baseline_verification_unavailable`. If the baseline is fully verified, passes
all requested limits and has a scoped material estimate, it is the first feasible
result and the arm stops immediately. Otherwise candidates are evaluated once
each in the frozen shortlist order until the first result meets that same
eligibility rule, or the plan is exhausted. Predictions, OOD status and an API
`ready` status alone cannot authorize a successful stop.

The full planned `shortlist` is retained. `candidate_outcomes` remains in original
pool declaration order, while `arm.execution.attempted_candidate_ids` is a
contiguous prefix of the shortlist. The receipt also binds `stop_mode`,
`termination_reason`, `stop_candidate_id`, `unattempted_candidate_ids`,
`unused_analysis_request_budget`, the explicit first-feasible `selection_scope`
and `global_material_optimality_verified=false`. Validators reject reordered or
skipped prefix entries, a premature stop, continued evaluation after feasibility,
wrong stop IDs/reasons, missing suffixes and inconsistent unused budgets.

A planned suffix has `status="not_attempted_after_stop"`, no result, no execution
credit and no failure. Out-of-plan candidates retain `not_shortlisted` or
`preanalysis_blocked`. An attempted failed candidate retains its original failure
and known/unknown execution status, consumes a request, and permits evaluation
to continue when the baseline authority is available. A blocked search can still
have a valid worker report and valid resource observations. Such outcomes and
unlaunched slots remain in the declared suite denominator.

The genuine M2 comparison is assembled from the already evaluated baseline and
actual candidate prefix. Its candidate identities and rows follow execution
order; the full plan stays in the search report. Constructing this M2 does not
repeat an analysis. With no candidate attempts there is no M2 bundle, with reason
`stopped_before_candidate_evaluation`; the suite, baseline, receipt and raw
downloads remain reviewable. Workbench exposes the selected slot's mode,
planned/attempted order, termination, unused budget and unavailable results.

## Identity, oracle and costs

The nondefault mode binds the original request, normalized case, input binding,
every frozen plan and its hash, worker report and combined comparison. Parent
and portable-review validators regenerate the no-solve expectations and verify
the retained actual prefix. Removing the mode or changing to an older schema
while rehashing the affected report cannot bypass those expected bindings.
These are stored-contract and raw-byte checks, not independent source attestation
or numerical replay by the browser.

| Opt-in artifact | Schema |
| --- | --- |
| Combined search | `fiber-frame-candidate-search-comparison.v5` |
| Single arm / oracle | `fiber-frame-candidate-search-arm.v3` / `fiber-frame-candidate-search-oracle.v3` |
| In-process suite | `fiber-frame-candidate-search-suite.v3` |
| Process request / worker request | `rc-fiber-candidate-process-suite-request.v3` / `rc-fiber-candidate-process-worker-request.v3` |
| Process suite / portable review | `rc-fiber-candidate-process-suite.v3` / `rc-fiber-candidate-process-review-bundle.v3` |

Mixed suites use the new outer envelope when any case opts in. Each individual
case and worker retains its own mode/version. The M2 scope version is unchanged
by stopping; its existing terminal/history/material version follows the requested
verification scope. The frozen policy is reused without a fit or target change.

The exhaustive oracle retains the existing `missed_feasible` meaning: feasible
candidates outside the **planned shortlist**. The separate opt-in fields
`unrequested_feasible_count` and `unrequested_feasible_candidate_ids` count
oracle-verified, requested-limit-feasible candidates that the online arm did
**not actually request**, including a suffix skipped after success. Their
definition is `oracle_verified_requested_limits_feasible_candidate_not_requested`.
Without an oracle the count and IDs are unavailable, not zero. Deterministic
prediction counters remain unavailable, and existing false-safe scopes are
unchanged. Oracle labels are never supplied to online selection.

Actual online requests are one baseline plus the attempted prefix, not the
maximum budget or planned shortlist length. Pool preparation, learned inference,
attempted failures, stop decisions, M2 assembly and final selection remain charged.
Stop decisions and M2 assembly are inside `full_reanalysis_wall_ns`. An unknown
solver execution is not converted to zero; invalid worker observations retain
failure records and unavailable totals alongside known subtotals.

Historical generation and fit are charged once per distinct training report.
Warmups and exhaustive oracle requests remain separate actual work. Worker CPU
and parent CPU have disjoint scopes; elapsed enclosing intervals are not summed
with their subsets. Resource I/O retains the existing bounded worker input-read
and search-report persistence scope, excluding sidecars/manifests and parent suite
persistence. Peak RSS is a distribution of separate process peaks, never a sum
or a subtraction. A shorter attempted prefix alone establishes no time saving.

Equal-quality cost and conditional amortization still require fully verified
feasible selections under the same requested constraints and maximum budget,
with the learned scoped material estimate no higher than the deterministic one.
Existing readiness/resource gates also remain. Retained paired costs may exist
when that quality gate fails; they are not successful equal-quality speedups.

## Focused verification and remaining evidence

The following passing groups overlap and are deliberately not summed:

- 149 Python process/suite/review checks: 43 new stop-mode checks plus existing
  stored-review and process-contract checks. Log:
  `/tmp/structural-candidate-stop-process-suite-final.log`.
- 103 Python core stop, material row-order, history-search and material-contract
  checks; 166 separate existing suite/process and CI boundary/quality checks.
- 35 final core-stop and design-assembly checks, including a further rejection
  of continued evaluation after the first eligible result. Changed Python files
  pass Ruff and formatting checks.
- 26 new `workbench-v2-candidate-process-stop-contract.spec.ts` contracts,
  checked as 24 initial cases and two later count/exhaustion cases. A separate
  222 passing pure contracts cover the existing design-comparison,
  material-history, candidate-process and candidate-process-history specs.
- Three new stop-browser checks cover desktop, mobile and a resealed invalid
  artifact. Seven existing design-comparison browser checks passed separately
  after a server was started. Their first attempt failed because no server was
  available; that failure is retained rather than counted as a pass. The corrected
  runner is preserved under `/tmp/structural-stop-browser-scoped.xilgWJ/`.

Tests cover omitted/default fields, mixed versions, rehashed mode/prefix/receipt
mutations, real producer M2 assembly over retained rows, early baseline stops,
failed attempts, unknown costs, planned versus actual oracle coverage, quality
gating and portable incomplete review. Python row fixtures and browser transport
fixtures are synthetic or reuse retained artifacts; they do not establish a new
physical experiment. Earlier focused attempts retained test-authoring failures
(incorrect helper signature, exception-injection boundary and an inner-arm status
assumption); the final group above passed without weakening production gates.

At this implementation checkpoint the new stop mode has no actual numerical
fresh-worker experiment, repeated performance observation or demonstrated
reduction in public analysis requests. Existing damaged-candidate observations
used the full-shortlist default and remain unchanged. A later separately declared
experiment must retain all requests, failures, original results/checkpoints,
process resources and final quality before making an observed cost claim.
Independent corpus, physical verification, hosted user acceptance and release
authority remain outside this implementation evidence.
