# Response-scoped refinement and persistent RC research integration

## Scope and integration history

The initial local research slice integrated the #442/#448 result-reuse implementation
with #439 at `9453bc210325305569442cbf7ac2fc075f8d1be0` without replacing its
newer single-model reference evaluator. The historical private helper delegates
to the current `_reference_design_row`. Current scientific comparisons, material
laws, solver tolerances, trial-state semantics and verification rules remain.
The integration uses an additive job in the existing reviewed CPU workflow. Its
regressions and diagnostics remain separate from the required full-suite shards.

The shared neutral JSON loader now rejects duplicate keys at any nesting level,
NaN/Infinity and overflowing exponents, invalid UTF-8/lone surrogates and excessive
nesting. The file path entry point reads at most the existing 16 MiB bound plus
one byte. Valid units/defaults/model interpretation and original input hashes are
unchanged. This is input validation, not a new structural capability.

## Finite refinement observations, not an accuracy guarantee

`run_rc_refinement` accepts a frozen ladder of three to six increasing concrete
layer counts in [2, 32]. It changes only concrete quadrature in the existing
rectangular RC profile. Geometry, reinforcement, material definitions, loads and
solver settings stay identical. Each level begins from virgin material state,
performs a complete reference solve plus fresh full replay, or explicitly reuses
an original previously verified under exactly the same physical/runtime key.
No material state is interpolated across grids and no public limit is raised.

Every original, checkpoint and verification stays attached to its own model and
quantity hash. Physical takeoff must be invariant, but model/quantity hashes are
expected to change. Prices and supported response screens may be changed without
repeating the physical computation. A new grid is a new physics key.

The caller supplies absolute and relative tolerances per response, with units.
No engineering tolerances are inferred. Full histories (including preload) are
compared at matching nodes, reactions or authored steel locations. Steel fiber
ordinal indices are NOT treated as physical identity after concrete refinement.
The numerical comparison is `abs(a-b) <= absolute + relative*max(abs(a),abs(b))`.
The final two adjacent comparisons must meet the declared criteria. Earlier
comparisons remain in the report. This finite comparison does not bound continuum
error, prove asymptotic convergence or independently validate physical behavior.

Concrete tensile/compressive envelope responses compare the sampled maximum at
each unchanged member/integration location. They are not pointwise damage-field
agreement and are labelled separately. `concrete_damage_field` remains explicitly
not comparable: no interpolation/field-correspondence authority is invented.
Unknown or failed fine levels, missing identities and absent responses cannot
inherit a coarse pass. If requested screens change their boolean outcome over
the final three levels, the scoped candidate decision remains unknown even when
some numerical response comparisons meet their tolerances.

## Candidate search and budget

`run_refined_candidate_search` evaluates one price-ordered finite pool (baseline
plus 1..16 alternatives), with a shared 0..102 new-model budget. A model evaluation
includes its original reference solve and full replay. Cache hits cost zero NEW
numerical work and retain their original work separately. Unknown cheaper designs
block the minimum. A cheaper candidate is not rejected using only a coarse result.
Expensive candidates may remain unexecuted after a qualifying incumbent is found;
their physical responses remain unknown. The certificate is scoped to the finite
pool, declared material prices and specified refinement/response screens. It is
not global design optimality, construction-price saving or structural approval.

## CLI

The existing model, RC-control request and design-experiment formats are reused.
Supply one new small configuration file, for example:

```json
{
  "schema_version": "local-rc-refinement-input.v1",
  "levels": [8, 16, 32],
  "responses": [
    {"response": "node_translation", "absolute": 0.000001, "relative": 0.01},
    {"response": "reaction_force", "absolute": 0.001, "relative": 0.01},
    {"response": "steel_strain", "absolute": 0.000001, "relative": 0.01}
  ]
}
```

These are I/O examples, NOT recommended engineering acceptance limits. Select
responses relevant to the use case: imposed control displacement alone can be
uninformative. Concrete fields are not qualified by omitting them from a report.

```sh
PYTHONPATH=src python -m structural_analysis.benchmark.rc_control_refinement_cli \
  --model /path/model.json --request /path/control.json \
  --experiment /path/design.json --refinement /path/refinement.json \
  --source-revision <reviewed-40-character-sha> \
  --max-new-model-analyses 6 --output /new/refinement-output
```

Optional `--store-root` uses the single-host POSIX repository from #448 with the
host credential in `STRUCTURAL_RC_STORE_TOKEN`. Protect this local directory. This
is not a network identity service, arbitrary result import or hostile-OS boundary.
Exit 0 means a finite-pool minimum under the declared comparison screens was
confirmed; 2 means unresolved selection; 1 means invalid input/I/O. No exit status
confers design approval. Existing cancellation/time-budget CLI remains available;
this refinement slice has a model-count budget, not an in-solver time/RSS limit.

The inherited read-only `local_runtime_doctor` remains inventory only. It does not
launch a HIP kernel, qualify a driver or assert GPU performance. No AMD hardware
was available for this development environment. No new AI policy is trained.

## Cost and verification boundaries

Native numeric-library hashing now streams 1 MiB chunks instead of materializing
an entire library byte string. Digest contents and repeated change detection are
unchanged. This bounds that hash buffer, not total RSS, and claims no speedup.

Focused tests include valid-input equivalence, same-key/persistent reuse, different
discretization keys, exact original preservation, missing-budget/fine-failure and
unknown-work rejection, concrete-field unavailability, screen-outcome instability,
finite-pool comparison against exhaustive refinement, and separate-process CLI
repricing. Synthetic fault injection is not a physical experiment.

The initial local execution used the digest-verified complete base Python wheel
plus exact affected files/fixtures, not a full repository checkout. An additive hosted job
runs these checks, formatting and lint on the committed tree. Required full-suite
checks, external-reference materialization and owner review are NOT replaced.
A successful finite-grid study is not an independent material validation, a mesh-
objective fracture model, a new spatial element refinement, a GPU acceleration
claim, or a user-facing browser integration. These remain separate work.

## Current-source integration on 2026-09-29

PR #450 now retains the full heads of #444
(`264cd592b295c5d72481c029e7390561643c0fed`) and #446
(`2e1c2b41048ee6ea3caea7263de7a216be47a4a0`), together with current development
base `3021a69b54d073b6f5dee7e329545bbe4f1237a7`. The missing durable research note
is restored with its original bytes. All original local, durable, persistence,
resource and AMD-discovery regression functions are preserved. Later atomic
first-owner publication, strict work accounting and source checks remain intact.
The combined diagnostic job covers both predecessor slices; the current parent
full-shard execution and result retention remain required.

A clean full checkout of integration source
`7a35d59f107737b0502ebe56aeedfe30e63e9d7d` passed **418 tests across 19 complete
test files**, with no skips or deselections. The scope includes actual small RC
solves, second-interpreter reuse, chunk pause/reopen, interrupted writes and
process reservations, cooperative budgets, finite refinement/candidate decisions,
current durable/preload behavior, strict input, source inventory and workflow
contracts. The tracked checkout remained clean after execution. Formatting and
lint passed for all 21 files selected by the integration job. Shared fixture
registration was made explicit without changing the original test functions;
formatting of the current reference evaluator preserved its Python AST.

This document is the only change after that execution. Current-head hosted CI,
review and main integration remain outstanding; #443, #445 and #449 remain open.
The local software checks do not establish independent physical accuracy,
general AI acceleration, GPU execution, live browser delivery or release approval.
