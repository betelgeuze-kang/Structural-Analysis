# Static geometry already rules out six learned paths

A diagnostic of the completed numerical portion of the
[secant-abstention study](rc-secant-abstention-20260910.md) identifies a cheaper
possible decision point. In six of eight folds, immutable geometry or coordinate
scale already violates the fitted policy's existing feature-range condition.
Those policies cannot make a learned proposal for this model, regardless of
later committed material states. The current execution still captures and
inspects those states at every target.

This is a source-bound diagnostic, not an implemented fast path, a measured
speedup or a completed audit of all numerical states. The full runtime auditor
continues separately. The frozen numerical source is
`3d4ecef4b737703717522ef385bdc6004eba56e1`.

## Reconstruct the inputs without a structural response

Four original authored training models are compiled with their original
constant-load declarations. No validation/holdout model is executed. The existing
model-feature extractor reads only immutable declarations: no checkpoint,
constitutive trial or Newton solve supplies these inputs. The reconstructed
74-feature prefix agrees exactly with all 964 existing training rows and all
fold policies' feature-name order. The full material feature vector has 500
coordinates. This checks the prefix ordering instead of assuming that the first
74 recorded values are geometry.

Each fold policy is loaded through its original strict policy constructor.
For every static feature, the diagnostic applies the existing range rule with
`slack = max((high - low) * ood_margin, 1e-12)`. Neither the trained bounds nor the
margin changes. These conclusions apply to the material feature profile whose
static prefix is verified here; normalized history profiles need their own
corresponding transformation.

| Withheld authored case | Static violations per ridge | Examples | Observed learned proposals per ridge |
| --- | ---: | --- | ---: |
| train-a | 1 | rotation coordinate scale 2.0 outside 2.5–3.25 plus margin | 0 |
| train-b | 0 | none found in static prefix | 241 |
| train-c | 3 | node x / member length 1.75 outside 2.0–3.25 plus margin | 0 |
| train-d | 6 | node x / member length and upper node y | 0 |

Both ridges share the same feature bounds because they use the same respective
training partition. A static violation is a sufficient reason for the existing
full-vector range check to abstain; no static violation is not a permission to
accept a proposal. All existing context, material-state, dynamic-feature,
finite-value and final solver checks remain necessary.

## Recorded work and its limits

The six statically excluded folds still record **1,452 material captures**.
Their capture timers sum to **7.629103314 s**, and proposal-callback timers sum
to **8.154498097 s**. These are separate instrumented regions from the original
paths. Callback cost includes current policy handling and feature/range work;
it is not exclusively matrix inference. Copies of all original proposal path
reports are retained and their canonical path hashes are recomputed.

The approximately 15.78 s total identifies work worth examining. It is **not** a
measurement of time saved: an implementation would have its own preparation,
validation and output costs and would need an otherwise equivalent rerun. It
also does not address the two active train-b folds, whose observed whole-path
ratios are 1.1225279057646016 and 1.1247270432390961. Removing known-abstention
cost alone cannot establish a learned advantage in those active cases.

The diagnostic itself takes **4.501501191 s** internally, including reading,
compilation, copying and source checks before final reporting. Model compilation
and static-feature extraction take **0.008869691 s** within that interval. Later
Git verification and packet sealing are additional bookkeeping, not included in
that timer. There are zero structural calls, fits or new labels. All work occurs
on the shared host; no isolated-hardware performance conclusion is made.

## Next implementation criterion

A prepared policy could make this one-way rejection once per fixed model and
omit material capture/inference only when the unchanged static range test proves
that every proposal would be rejected. Such a path must bind policy, model,
arithmetic and feature profile, retain the explicit abstention strategy, charge
preparation and reporting costs, and preserve reference fallback/rollback and
accepted-result authority. It must not use a lack of static violations to bypass
the remaining checks. No such optimization is implemented by this diagnostic.
The active-case regression remains a separate learning/solver-strategy problem.

[Machine summary](rc-static-abstention-diagnostic-20260910.summary.json) includes
all violated coordinates, bounds, margins, decision counts and timing sums.
The sealed diagnostic packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-static-abstention-fxasw468`:
252 files, 190,206,523 bytes; sibling inventory SHA-256
`987ed7249a04d6c9ff18a813d972788f97b4de6bdca3f04b0cab1d3592199fc5`.
All 209 imported project source files match the frozen manifest and Git revision;
all packet files are reread and hash-checked. Original training bytes, policy
files, proposal reports, terminal result, diagnostic source and logs are retained.
This seal covers this diagnostic only. The parent experiment's original-state
and fit audit is still running and its packet remains unsealed.
