# AI nonlinear analysis and cost exploration workbench

Product direction updated 2026-09-07 from the owner's attached proposal.
Repository baseline: `f76239629d3b51a99376871c60cffa0d30c5339e` (PR #431).
This is an implementation plan and claim boundary, not a generated readiness
receipt or evidence of commercial closure.

## Product objective

Help an engineer compare repeated material and section changes in one bounded
structure family. Every selected alternative must link changed member quantities,
a common price basis, structural performance, and the full reference load-path
verification. Measure three different outcomes separately:

1. Wall time and work for one nonlinear solve at unchanged convergence criteria.
2. Total time and number of high-fidelity evaluations needed to select a design.
3. Material/construction estimate differences for an actual physical design change.

An AI prediction, a simpler constitutive law, and fewer integration points do not
by themselves establish construction savings. The reference solver continues to
own equilibrium, material trial/commit/rollback, and accepted result authority.

## Reconciled repository baseline

The previous PR #431 wait is obsolete: it is merged and all 22 main-push workflow
runs on the baseline SHA passed, including Native run `34069566088` (attempt 1).
This is not evidence that the release chain is closed. At inspection the same SHA
had no Nightly, Product State, or Evidence Index run. PR #432 and its stacked Draft
#434 remain separate unfinished supplemental-artifact work. Do not merge them into
this AI change or copy older workstation/RC receipts onto a new source SHA.

The code already includes a bounded RC fiber API and a replay-bound shadow
SolverEpisode adapter. Reuse these instead of adding a second solver or AI
authority system:

- `src/structural_analysis/api/nonlinear_fiber_frame.py`
- `src/structural_analysis/assembly/stateful_fiber_frame2d_solver.py`
- `src/structural_analysis/ai/fiber_frame_solver_episode_adapter.py`

The adapter currently observes/replays; its runtime profile says time is not
captured, and shadow proposals are not executed. It is not a measured accelerator.

## First change: truthful experiment inputs and outputs

| Area | Change | Remaining boundary |
| --- | --- | --- |
| GNN heuristic | Keep internal scalar reduction separate from solver residuals; unavailable physical metrics cannot pass the downstream correction gate | No learned weights, engine recomputation, or demonstrated speedup |
| Surrogate training | Pre-analysis feature allowlist; reject missing/mismatched/nonfinite arrays; fit preprocessing on training only | Member-group holdout does not establish project/geometry/load-history generalization |
| Promotion | Old v1 cards and opt-in flags cannot establish a validated production dataset | Research artifacts require a future independently replayed provenance validator |
| Material cost | Share quantity-times-price calculation, sum members within a group, retain a fixed quantity/price basis during search | Proportional candidate quantities are approximate and need final takeoff |
| Cost meanings | Expose construction estimate and optimization penalty separately; retain legacy `total_cost` as an objective alias | Default units are an uncalibrated index, not KRW; fitted calibrator coefficients are separate evidence |
| Baseline report | Record price identity/scope and actual proxy-search wall time | Solver time, AI time, speedup and confirmed monetary savings stay unavailable |

The legacy NDTHA correction gate has no implemented physical recompute verifier.
An asserted `contract_pass`, even with invented numeric corrections, cannot close
that gate. The original solver-raw hard-limit check remains available separately.
Likewise the surrogate builder does not execute a solver fallback, so its fallback
receipt states a requirement rather than a verified replay. Missing drift-response
acceptance criteria leave overall surrogate validation incomplete; passing the
existing DCR/cost checks alone is insufficient.

Candidate projections from newly aggregated states use proportional rebar and
thickness changes from the original member quantities. Detailing-quality changes
alone cannot reduce material cost. Old hand-authored states without quantities
retain their legacy ranking proxy, not a construction-cost interpretation. The
budgeted solver-loop and delivery-report paths still need a reviewed migration to
the same physical quantity and price contract; this change does not claim they
are all converted.

The independent synthetic `meta_learning_task_stub.py` and other historical
experiments are not validated physics models. Any remaining synthetic accuracy
labels must be removed before those paths are used in the product.
The existing `report_ml_multi_objective_status.py` source-import scan must also be
migrated before adding model imports to production runners: source text presence
cannot override the executed model/data validation gate.

## Next executable milestone: one nonlinear structure family

Start with the existing `planar_serial_cantilever_explicit_rectangular_rc.v1`
profile: XY serial cantilever, explicit rectangular RC fibers, supported steel and
concrete models, and proportional nodal quasi-static loading. Its published
limitations remain applicable; this plan does not add general 3D frames, geometric
nonlinearity, dynamics, shell/contact, or design-code approval.

### 1. Measure the reference and non-AI baseline

Capture material update, assembly, linear solve, iteration/retry, recovery and I/O
time using monotonic clocks. Keep timing out of deterministic numerical identity.
Bind each observation to source, dependency/environment, model, load history,
convergence settings, and complete accepted material/checkpoint state.

Compare unchanged reference Newton, existing cached/secant-start improvements,
then a proposed warm start. Use repeated runs, identical inputs and tolerances,
and report dispersion, iterations, residual evaluations, failed retries, peak
memory, and total CPU/GPU work. Do not turn unavailable timing into zero.

The bounded implementation now lives in
`structural_analysis.benchmark.fiber_frame_runtime`. It runs fresh reference,
deterministic secant and explicitly opted-in predictor arms against the same
compiled problem, load history and Newton configuration. Runtime remains a
volatile sidecar: Newton assembly/linear-solve work, the stateful terminal trial
assembly, guard evaluation, inference, fallback and J1--J5 verification are
separate fields. Unmeasured data generation, training, I/O, CPU/GPU work, memory,
quantities and currency remain `null` with reasons. A source revision is required
for the measurement contract, caller-injected clocks are non-evidentiary, and no
positive timing ratio is a correctness gate. The existing baseline-only
SolverEpisode schema is verified on the reference path in a separately timed,
non-comparable phase; candidate warm starts are not mislabeled as baseline
step-size actions.

Warm starts are stored with each load step so deterministic J5 and baseline
SolverEpisode replay use the exact executed coordinates. A rejected or failed
seed leaves the parent checkpoint byte-identical and retries ordinary Newton from
that same parent. The accepted solver path alone proceeds to constitutive commit
and full-history force/material comparison. This is executable acceleration
plumbing and measurement discipline, not a trained-model or speedup claim.

### 2. Create paired design-change data

For each baseline/candidate pair retain model hashes, changes in physical section
and material quantities, pre-analysis features, optional low-fidelity outputs,
and independently computed high-fidelity targets. Partition by project, geometry
family and load history before fitting preprocessing. Reserve parameter boundaries
and unfamiliar materials for OOD evaluation. Record numerical nonconvergence,
invalid input, unsupported semantics and verified physical limit states separately.

### 3. Add an opt-in, reversible warm start

The predictor proposes displacement only. Evaluate it from the previous committed
material state using the existing constitutive response, physical residual and
convergence rules. Adopt, damp or reject the proposal based on those checks.
Newton must still confirm acceptance. On invalid inference or failed trial,
restore the exact previous state and execute the baseline path. Final candidates
replay the full required load history, not only final-displacement equilibrium.

Exit: matched response/history/recovery within predetermined tolerances, rollback
parity for injected failures, and measured net savings including inference and
fallback. A local passing unit test is not that performance evidence.

### 4. Connect multi-fidelity selection and cost review

Select promising, uncertain and near-limit candidates for full analysis. Report
missed-feasible/false-safe outcomes, high-fidelity solve count, total search time,
data generation/training cost and break-even reuse count. Compare against the
same non-AI candidate search. Confirm final candidates against fixed required
constitutive models and load scenarios; do not optimize the verification model.

The UI should link each proposed member change to quantities, price-table hash,
currency/date/source when supplied, performance differences and full-history
verification status. Hard structural/detailing violations reject a final candidate;
adding an optimization penalty does not waive them. Include labor/fabrication only
with defined scope and prevent double counting. No verified quote or detailed
takeoff means no confirmed currency savings claim.

## Verification and integration

Focused tests use temporary outputs, not checked-in productization receipts.
Keep existing source-quarry and product CI boundaries intact. Refresh evidence by
its real workflow after a future merge; never edit generated readiness status to
claim the new behavior. External V&V, licensing decisions, independent operators,
clean-platform runs and customer observation remain separate outstanding work.
