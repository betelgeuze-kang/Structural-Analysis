# Bounded planar external V&V matrix

`artifacts/manifests/bounded_planar_external_vv_matrix.current.v1.json`
is the machine-readable gap surface for the recommended bounded-planar Level 2
matrix. It validates the complete current code-to-code and modal/buckling
receipts before assigning any row.

Every row declares a non-empty `required_external_case_ids` set. Core and
supplemental receipt bindings expose their actual passing case inventories;
row evidence must match the binding path, artifact hash, authority state, and
exact case IDs. A receipt from an incompatible case family cannot be reused to
fill a missing row.

The exact-current Product State producer targets:

- 25 required rows;
- 9 exact-source rows from the attested OpenSees/CalculiX clean-runner;
- 16 exact-source rows from five successful GitHub-hosted technical workflows,
  whose retained Sigstore bundles are reverified again by Product State;
- 25/25 fresh current-source technical rows: 24 external-engine requirements
  and one deliberately non-engine invalid-geometry preflight;
- 0 missing technical rows; and
- 0 promotion-eligible rows.

This target is not currently satisfied. The modal/buckling lane installs
CalculiX and BLAS from a mutable apt closure, so its seal is retained only as
blocked diagnostic evidence. Product State removes the exact-source aggregate
instead of reporting fresh 25/25 until every transitive runtime byte is locked.

The tracked replay-only v1 supplemental bundle remains a historical diagnostic
input. When explicitly selected it still yields 25/25 technical references and
zero fresh rows. The current producer does not use that replay bundle as a
fallback for exact-current freshness.

The nine current-source host core rows are the cantilever, release, rigid offset,
distributed member load, settlement, prescribed displacement, column buckling,
reaction recovery, and member-force recovery requirements. The sixteen local
supplemental rows are linear portal, linear multistory, rigid mode, repeated
mode, portal buckling, mechanism, singular system, invalid geometry, unit
invariance, characteristic-length invariance, P-Delta, Lee-frame snap-through,
steel yielding, RC fiber response, section recovery, and fiber recovery. A single combined member case
may support several explicitly named feature/recovery rows, but no receipt is
credited to an incompatible row. In particular:

- an elastic corotational portal is not credited as a dedicated linear portal
  or P-Delta benchmark;
- ordinary modal eigenvalue comparisons are not credited as rigid or repeated
  modal-mode cases;
- repeated column buckling is not credited as repeated modal analysis or portal
  buckling; and
- internal section/fiber recovery is not credited without external section or
  fiber comparison metrics.

Linear portal and multistory use exact ModelIR inputs, current-product results,
metric identifiers, and OpenSeesPy runners bound by
`artifacts/vv/bounded_planar_external_linear_case_package/manifest.json`.
The preparatory package still reports `external_solver_execution=false` and
contains no external values. The separate same-operator supplemental bundle
attaches both raw results and a replayed 2/2 technical receipt, so these two
rows are now `current_product_replay_only` without becoming promotion eligible.
Its runners emit actual runtime, runner/model hashes, and a result self-hash.
Project-side intake validates those bindings and numerical tolerances but grants
no independent-operation or promotion authority. The package also binds the exact
`.github/workflows/bounded-planar-opensees-technical.yml` source. A current-main
run signs the technical receipt with GitHub/Sigstore provenance and retains the
bundle plus verification JSON; this is source-authenticated same-operator
technical evidence, not independent operation or Level 2.

The mechanism, singular-system, and invalid-geometry rows use the checksum-bound
package at
`artifacts/vv/bounded_planar_external_negative_case_package/manifest.json`.
It records three distinct current-product rejection layers: solver tangent
rejection for an explicit released mechanism, support-rank preflight for a
singular system, and ModelIR validation for duplicate-node geometry. Actual
OpenSees returned analysis code zero for the singular case, so the external
runner extracts the assembled tangent and proves numerical rank 9/10 before
assigning `external_solver_tangent_rank_rejection`. The supplemental receipt
passes all 3/3 exact classifications. In particular, the invalid-geometry runner performs a bound
preflight without invoking OpenSees and may not be described as an external
solver execution. The mechanism, singular, and invalid-geometry rows are all
`current_product_replay_only`. Invalid geometry retains its
`independent_preflight` verification method and
`fresh_current_source_external_execution=false`; it is not an external solver
run. Independent operation and promotion remain false.
The corresponding intake validates the exact package/model/runner/result hashes,
pinned runtime versions, nonzero solver rejection signals for mechanism and
singular cases, and the no-engine boundary for invalid geometry. Its unsigned
technical receipt remains non-promoting; the main-only workflow attests that
receipt and verifies its GitHub/Sigstore provenance before retention.

The unit-system and characteristic-length rows use the source-bound execution
package at
`artifacts/vv/bounded_planar_external_scaling_case_package/manifest.json`.
The unit pair preserves one normalized SI model while changing source-unit
provenance from metres to millimetres. The characteristic-length pair uses
geometric similarity with length, area, inertia, force, and moment scales of
`s`, `s²`, `s⁴`, `s²`, and `s³`, then compares normalized displacements,
rotations, reactions, and moments. Both current-product and attached OpenSees
comparisons pass, so both rows are replay-only technical evidence. The preparatory
manifest itself remains non-executing and non-promoting. Its main-only workflow executes the exact
OpenSees runners, builds a fail-closed non-promoting receipt, attests that
receipt, and verifies the retained provenance bundle.

Rigid-mode exclusion, the repeated modal eigenspace, and portal buckling use
exact canonical inputs and current-product replays bound by
`artifacts/vv/bounded_planar_external_modal_buckling_case_package/manifest.json`.
The modal cases use pinned OpenSees. The portal uses a circular section with
16 product linear elements per member mapped exactly to eight CalculiX B32
elements per member. Intake checks the rigid-mode count, flexible/repeated eigenvalues, a
basis-invariant repeated-mode subspace correlation, and portal buckling factors.
All three attached comparisons pass: modal eigenvalue relative errors are at
floating-point precision, and the two portal buckling-factor relative errors
are approximately 1.78% and 0.165% against the declared 5% tolerance. The rows
are replay-only technical evidence and receive no promotion credit.

The final six technical rows use the source-bound package at
`artifacts/vv/bounded_planar_external_nonlinear_material_recovery_case_package/manifest.json`.
The P-Delta case applies the same gravity ratios and E/A/I values to a
three-member OpenSees `PDelta` portal; the maximum declared comparison error is
below 0.8%. The Lee-frame case independently follows the first limit point and
post-limit descending/negative-load branch with OpenSees `Corotational` beam
elements; its first-limit metrics are also within 0.8%. The Steel01 monotonic
path matches the product combined-hardening envelope and post-yield tangent at
floating-point precision. The nonlinear RC section intentionally maps the
product damage law to a bounded Concrete02 envelope and stays within the
declared 12% comparison tolerance, with 9.17% maximum relative error. Separate
undamaged elastic section and fiber cases recover resultants, strains, and
stresses to machine-scale absolute error. These comparisons close only the six
named bounded rows; they do not establish general material-model equivalence,
distributed-plasticity breadth, or design authority.

The retained local
`artifacts/vv/opensees_calculix_clean_runner/clean_runner_receipt.json` does not
currently satisfy cross-environment parity: the host and container source/metric
sets differ, including the later cyclic direct-control metrics. The matrix
therefore records `same_operator_execution_binding=unavailable` with reason
`current_source_clean_runner_cross_environment_parity_missing`; no container
isolation or parity credit is granted. The checksum-bound host code-to-code and
modal/buckling receipts retain prior external results and regenerate only the
current-product comparisons, providing replay-only technical references for the
exact nine core rows.

The historical matrix path can separately attach
`artifacts/vv/bounded_planar_same_operator_supplemental_execution/receipt.json`
through `same_operator_supplemental_execution_binding=attached_replay_only`. It
binds five current package manifests, five replayed child receipts, sixteen raw
results, preserved historical model/runner/schema/package bytes, their execution
window and runtime observations, and hashes for five pinned runtime assets. The
wheel and DEB bytes are not stored, and no external runtime ran in this receipt
generation. It changes exactly the sixteen supplemental rows to
`current_product_replay_only`; independent operation, legal approval, scientific
promotion, and Level 2 remain false.

The exact-current path instead builds
`bounded-planar-current-source-supplemental-attestation.v2` after downloading
only successful exact-SHA main artifacts from the linear, negative, scaling,
modal/buckling, and nonlinear/material/recovery workflows. Product State runs
`gh attestation verify` itself for every technical receipt, requiring the exact
signer workflow and digest, exact source digest and main ref, and a GitHub-hosted
runner. The v2 aggregator and its standalone `--check` path rerun that
cryptographic command with the same restrictions. Retained verification JSON is
only a compared audit cache and cannot substitute for a successful live
verification. The aggregator then rechecks workflow-run identity, signed subject
digest, Sigstore bundle identity, package and raw-result hashes, the exact
five-family and sixteen-case inventories, and the invalid-geometry no-engine
boundary. This produces `attached_attested_current_source`, grants fresh
technical credit to the sixteen supplemental rows, and still leaves independent
operator, legal, scientific-promotion, formal Level 2, design, commercial, and
release claims false.

The matrix also checksum-binds the separate main-only
`.github/workflows/opensees-calculix-current-source.yml` lane. That workflow
acquires the exact pinned OpenSees and CalculiX assets outside the repository,
runs the combined read-only/network-disabled clean runner, and immediately
verifies provenance for the resulting summary receipt. Its distinct workflow
binding still says `current_source_execution_attached=false` because no retained
GitHub Actions run attestation is attached. That does not erase the local
same-operator execution receipt, and it does not turn local execution into a
GitHub-main attestation. The workflow binding separately records four prepared
case IDs mapped to nine requirements. `current_source_execution_prepared=true`
means only that the checksum-bound main workflow can execute that exact row; it
is not standalone package availability or promotion credit.

A distinct production builder accepts an independently signed operator bundle:

```bash
python scripts/build_bounded_planar_external_vv_matrix_from_operator_bundle.py \
  --attestation submission/operator-attestation.json \
  --bundle-root submission \
  --expected-source-commit <exact-40-character-source-commit> \
  --out submission/bounded-planar-external-vv-matrix.json
```

It verifies the RSA signature and fresh child execution through the existing
operator-intake validator, then assigns rows strictly from the signed case
inventory. Signature integrity and an independence declaration do not
authenticate the operator identity, approve licenses, complete scientific
review, or promote Level 2.

Linear, modal/buckling, negative, scaling, and nonlinear/material/recovery cases
use dedicated signed blocks that include the unchanged execution-package
manifest, technical receipt, and every raw result. Intake regenerates each
package from current source and checks result hashes, pinned solver versions,
signed execution time window, host platform, exact runner command, and
receipt-to-result binding. These sixteen case IDs are rejected from loose
`additional_receipts`, so a receipt-only attachment cannot bypass the dedicated
validation path. A bundle containing all five supplements adds exactly sixteen
named fresh-technical rows to the nine core rows; it still adds zero
promotion-eligible or Level-2 rows.

Generate or check the current status with:

```bash
python scripts/build_bounded_planar_external_linear_case_package.py
python scripts/build_bounded_planar_external_linear_case_package.py --check
python scripts/build_bounded_planar_external_negative_case_package.py
python scripts/build_bounded_planar_external_negative_case_package.py --check
python scripts/build_bounded_planar_external_scaling_case_package.py
python scripts/build_bounded_planar_external_scaling_case_package.py --check
python scripts/build_bounded_planar_external_modal_buckling_case_package.py
python scripts/build_bounded_planar_external_modal_buckling_case_package.py --check
python scripts/build_bounded_planar_external_nonlinear_material_recovery_case_package.py
python scripts/build_bounded_planar_external_nonlinear_material_recovery_case_package.py --check
python scripts/build_bounded_planar_same_operator_supplemental_execution.py --check
python scripts/build_bounded_planar_current_source_supplemental_attestation.py \
  --source-commit <exact-40-character-source-commit> \
  --repository <owner/repository> \
  --check
python scripts/ingest_bounded_planar_external_negative_results.py \
  --results-dir external-results \
  --out external-results/negative-technical-receipt.json \
  --fail-technical-blocked
python scripts/ingest_bounded_planar_external_scaling_results.py \
  --results-dir external-results \
  --out external-results/scaling-technical-receipt.json \
  --fail-technical-blocked
python scripts/ingest_bounded_planar_external_modal_buckling_results.py \
  --package-dir artifacts/vv/bounded_planar_external_modal_buckling_case_package \
  --results-dir external-results \
  --out external-results/modal-buckling-technical-receipt.json \
  --fail-technical-blocked
python scripts/ingest_bounded_planar_external_nonlinear_material_recovery_results.py \
  --package-dir artifacts/vv/bounded_planar_external_nonlinear_material_recovery_case_package \
  --results-dir external-results \
  --out external-results/nonlinear-material-recovery-technical-receipt.json \
  --fail-technical-blocked
python scripts/ingest_bounded_planar_external_linear_results.py \
  --results-dir external-results \
  --out external-results/technical-receipt.json \
  --fail-technical-blocked
python scripts/build_bounded_planar_external_vv_matrix.py
python scripts/build_bounded_planar_external_vv_matrix.py --check
```

`contract_pass=true` means the status itself is internally consistent and its
source receipts validate against current product source. It does not mean the
matrix or Verification Level 2 passes. Without a validated fresh clean-runner
summary or any one of the five exact-SHA supplemental attestations, the
corresponding current-source rows fail closed. Even with all six inputs
attached, every credited lane must also prove its immutable pre-execution
runtime-byte closure. Only then can the technical matrix be 25/25
current-source: 24 external-engine requirements and one deliberately non-engine
preflight for invalid geometry. These lanes are still same-operator automation,
not an independent operator submission.
Independent operator authentication, legal use approval, scientific decisions,
and a formal promotion receipt remain separate mandatory gates.

For a solo developer, the repository/current-source/same-operator technical
track is independently completable and may support only the bounded Developer
Preview claim. Identity authentication, counsel legal review, scientific
promotion, and Level 2 are an external promotion track. When unavailable they
remain explicit promotion blockers, but they are not repository-integrity or
technical-execution failures and must not be replaced with self-issued approval.

The Level 2 promotion gate additionally requires this matrix to be 25/25
technical, 25/25 fresh by each row's declared verification method, zero
missing, source-commit bound, and backed entirely
by receipts contained in the signed operator bundle. The v1 operator-bundle
schema binds versions and signed result bytes but does not attach the exact
OpenSees/CalculiX/BLAS runtime closure, so it is now replay/reference material
with zero fresh rows. A future runtime-byte descriptor contract may satisfy the
25/25 technical freshness condition, but freshness alone does not create Level
2. Independent identity, legal, scientific, and reviewer evidence must be bound
to the exact complete bundle rather than supplied as detached booleans.
