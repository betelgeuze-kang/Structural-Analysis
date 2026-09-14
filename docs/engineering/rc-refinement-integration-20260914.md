# Response-scoped refinement and persistent RC research integration

## Scope and integration history

This local research slice integrates the #442/#448 result-reuse implementation
with #439 at `9453bc210325305569442cbf7ac2fc075f8d1be0` without replacing its
newer single-model reference evaluator. The historical private helper delegates
to the current `_reference_design_row`. Current scientific comparisons, material
laws, solver tolerances, trial-state semantics and verification rules remain.
Old workflow additions are superseded by a separate additive integration workflow;
the latest full-suite workflow and its tests are retained unchanged.

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

Local execution uses the digest-verified complete base Python wheel plus exact
affected files/fixtures, not a full repository checkout. An additive hosted job
runs these checks, formatting and lint on the committed tree. Required full-suite
checks, external-reference materialization and owner review are NOT replaced.
A successful finite-grid study is not an independent material validation, a mesh-
objective fracture model, a new spatial element refinement, a GPU acceleration
claim, or a user-facing browser integration. These remain separate work.
