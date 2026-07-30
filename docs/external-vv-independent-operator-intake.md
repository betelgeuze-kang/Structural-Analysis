# Independent external V&V operator intake

This intake closes a submission-integrity gap; it does not itself promote the
bounded planar profile. The existing clean runner proves a same-operator,
container-isolated OpenSees/CalculiX technical comparison. A second operator
must execute that runner from the exact candidate source and submit a signed
bundle before independence review can begin.

## Required bundle

The submission directory must contain:

- `clean_runner_receipt.json` from a fresh clean-runner generation;
- `external_code_to_code_receipt.json` from the same generation;
- `external_modal_buckling_receipt.json` from the same generation;
- all four checksum-bound binary mode-vector artifacts;
- the operator's public signing key and detached signature;
- one populated `structural-analysis-external-vv-operator-attestation.v1` file.

The validator rejects product-only replay and retained external execution. Both
child receipts must say that the external runtime executed in that generation,
that execution was not reused, and that the current-product replay passed. The
summary and children must have the same source commit, exact file hashes,
artifact hashes, source-set hashes, and mode-vector data hashes. All three JSON
receipts are revalidated against their complete packaged schemas.

The operator template is
`docs/templates/external_vv_operator_attestation.template.json`. Every
`OWNER_INPUT_REQUIRED` value must be replaced. A template is never evidence.

## Portal and multistory execution package

The preparatory package at
`artifacts/vv/bounded_planar_external_linear_case_package/` adds exact portal
and multistory inputs that are not present in the current technical receipts.
Its pinned OpenSees runners emit the actual runtime versions, runner/model file
hashes, execution timestamp, metric set, and result self-hash. After receiving
both result files, run:

```bash
python scripts/ingest_bounded_planar_external_linear_results.py \
  --package-dir artifacts/vv/bounded_planar_external_linear_case_package \
  --results-dir external-results \
  --out external-results/technical-receipt.json \
  --fail-technical-blocked
```

This intake proves only result self-consistency and bounded numerical
comparison. It deliberately keeps fresh-current-source execution,
independent-operator attestation, legal approval, matrix credit, and Level 2
false. It does not replace the signed bundle required below.

## Scaling-invariance execution package

The preparatory package at
`artifacts/vv/bounded_planar_external_scaling_case_package/` binds exact
unit-system and characteristic-length similarity pairs. Its runners normalize
OpenSees displacements, rotations, forces, and moments before applying the
invariance gate. After receiving both result files, run:

```bash
python scripts/ingest_bounded_planar_external_scaling_results.py \
  --package-dir artifacts/vv/bounded_planar_external_scaling_case_package \
  --results-dir external-results \
  --out external-results/scaling-technical-receipt.json \
  --fail-technical-blocked
```

This receipt authenticates package bytes and checks external-to-product
normalized metrics, but remains same-operator technical evidence until the
signed independent-operator, legal, scientific-decision, and promotion gates
are separately satisfied.

For signed intake, place the unchanged package manifest, both raw result files,
and the technical receipt in `bundle.bounded_planar_scaling`. Include the exact
two package-relative OpenSees commands in
`execution.supplementary_runner_commands`. The validator regenerates the
package from current source, replays result/schema/version/comparison checks,
and binds result timestamps and platforms to the signed execution window.

## Nonlinear, material, and recovery execution package

The package at
`artifacts/vv/bounded_planar_external_nonlinear_material_recovery_case_package/`
binds six exact cases: a gravity-prestressed P-Delta portal, Lee-frame
snap-through, monotonic steel yield, one nonlinear RC fiber-section state,
elastic section-resultant recovery, and elastic per-fiber recovery. Run all six
package-relative `runner/run_case.py` commands, then ingest only the six raw
result JSON files:

```bash
python scripts/ingest_bounded_planar_external_nonlinear_material_recovery_results.py \
  --package-dir artifacts/vv/bounded_planar_external_nonlinear_material_recovery_case_package \
  --results-dir external-results \
  --out nonlinear-material-recovery-technical-receipt.json \
  --fail-technical-blocked
```

For signed intake, place the unchanged manifest, six raw results, and technical
receipt in `bundle.bounded_planar_nonlinear_material_recovery`, and append the
exact six package commands to `execution.supplementary_runner_commands`. The
validator regenerates the package from current source, validates the pinned
OpenSees versions, result and receipt schemas, model/runner hashes, metric
comparisons, execution timestamps, and host platform, then binds the complete
inventory to the detached signature. This dedicated path is required even when
a result happens to match the product at floating-point precision.

## Modal and portal-buckling execution package

The preparatory package at
`artifacts/vv/bounded_planar_external_modal_buckling_case_package/` binds the
exact free-free rigid-mode, repeated bending-mode, and three-member portal
buckling models. The modal cases run in pinned OpenSees and the portal runs in
pinned CalculiX. After receiving all three result files, run:

```bash
python scripts/ingest_bounded_planar_external_modal_buckling_results.py \
  --package-dir artifacts/vv/bounded_planar_external_modal_buckling_case_package \
  --results-dir external-results \
  --out external-results/modal-buckling-technical-receipt.json \
  --fail-technical-blocked
```

The intake checks package/model/runner hashes, solver versions, rigid and
flexible mode separation, the repeated-mode eigenspace, and two portal buckling
factors. Its receipt remains same-operator technical evidence and keeps
independent identity, legal use, matrix promotion, and Verification Level 2
false.

The current repository-local same-operator bundle at
`artifacts/vv/bounded_planar_same_operator_supplemental_execution/receipt.json`
already binds a passing 3/3 run. The modal comparison uses `J = Iy + Iz` so the
product and OpenSees torsional mass terms describe the same problem. The portal
maps 16 product linear elements per member onto eight circular-section CalculiX
B32 elements per member; its two factors pass the declared 5 percent tolerance.
This local, non-container-attested run is technical evidence only and is not a
substitute for the signed independent intake described below.

For signed independent intake, place the package manifest, all three raw result
files, and the technical receipt in the dedicated
`bundle.bounded_planar_modal_buckling` block. The attestation must also contain
the exact three `runner/run_case.py` commands in
`execution.supplementary_runner_commands` and declare
`supplementary_results_executed_by_operator=true`. The validator replays package
source hashes, result schemas, product comparisons, solver versions, host
platform, execution timestamps, receipt bindings, and the detached signature.
An unsigned `additional_receipts` entry is not a substitute for this dedicated
path.

## Negative-path execution package

The package at
`artifacts/vv/bounded_planar_external_negative_case_package/` binds the
mechanism, singular-system, and invalid-geometry rejection cases. For signed
intake, submit the unchanged manifest, all three raw results, and the technical
receipt in `bundle.bounded_planar_negative`, together with the exact three
package-relative OpenSees commands. The validator regenerates the package from
current source, verifies hashes and pinned versions, replays each rejection
classification, and binds timestamps and host platforms to the signed window.

Only mechanism and singular-system rows have external-engine rejection
authority. The singular row derives that authority from the assembled OpenSees
tangent rank, so analysis return code zero cannot be mistaken for a passing
well-posed solve. Invalid geometry remains an independently executed checksum-bound
preflight with `external_solver_execution=false`; the signed bundle cannot
upgrade that authority.

Additional matrix receipts may be included under
`bundle.additional_receipts`. Each must be self-hashed, source-commit bound,
technically passing, and expose its exact passing `case_id` inventory. The
signed intake validation preserves those inventories so the promotion gate can
reject matrix rows backed by an absent, unsigned, or case-incompatible receipt.
Case IDs covered by the dedicated linear, modal/buckling, negative, scaling, or
nonlinear/material/recovery blocks are forbidden in `additional_receipts`; the
loose form cannot bypass raw-result, package, execution-window, platform, or
runner-command validation.

## Solo-developer authority boundary

A solo developer can complete repository integrity, current-source package
generation, deterministic replay, result self-consistency, and same-operator
technical comparison. Those gates support a bounded Developer Preview and do
not require the developer to self-authenticate as an independent operator or
issue a legal opinion to themself.

The current repository attaches replay-only same-operator host receipts for the
exact nine core matrix rows plus five local supplemental replay families
covering the other sixteen rows. The resulting bounded technical inventory is
`25/25` replay-only and technically passing, with zero fresh rows. The retained
container clean-runner has
mismatched host/container source and metric sets, so its current binding is
unavailable; the host and supplemental lanes are not container-attested. In all
cases the operator is still the developer, and no receipt carries an independent
identity credential, counsel approval, scientific promotion decision, or Level
2 promotion authority.

The V&V matrix records a further non-authority distinction. Nine
receipt-backed rows have `current_source_execution_prepared=true` because the
checksum-bound OpenSees/CalculiX main workflow contains their exact execution
path. This does not set `execution_package_available`,
`fresh_current_source_external_execution`, or any promotion field: a prepared
workflow is neither a standalone operator package nor an attached run receipt.

Independent real-world identity authentication, counsel-backed legal approval,
scientific promotion, and Verification Level 2 form a separate external
promotion track. When those services are unavailable, their evidence status
remains `unavailable`; they block only independent/Level-2/release claims, not
the truthful completion of the solo-developer technical track. License
inventory, SPDX notices, redistribution boundaries, and source-use declarations
should still be completed internally, but must not be relabeled as legal advice.

## Detached signing procedure

Generate and retain the private key outside the repository and outside the
submission bundle. Only the public key is submitted.

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out /operator-private/operator-private-key.pem
openssl pkey -in /operator-private/operator-private-key.pem \
  -pubout -out submission/operator-public-key.pem
sha256sum submission/operator-public-key.pem
```

Put the public-key SHA-256 in both
`operator.signer_public_key_sha256` and `signature.public_key_sha256`. Populate
the attestation body and bundle hashes, then emit the exact canonical signing
payload. The signature block is excluded from this payload; the signed operator
body still contains the public-key fingerprint.

```bash
python scripts/validate_external_vv_operator_attestation.py \
  --attestation submission/operator-attestation.json \
  --emit-signing-payload /tmp/operator-attestation-payload.json

openssl dgst -sha256 \
  -sign /operator-private/operator-private-key.pem \
  -out submission/operator-attestation.sig \
  /tmp/operator-attestation-payload.json

sha256sum /tmp/operator-attestation-payload.json \
  submission/operator-attestation.sig
```

Record those two hashes in `signature.signed_payload_sha256` and
`signature.signature_sha256`, then validate the complete submission:

```bash
python scripts/validate_external_vv_operator_attestation.py \
  --attestation submission/operator-attestation.json \
  --bundle-root submission \
  --out submission/operator-attestation.validation.json
```

The validator resolves every referenced path below the declared bundle root,
rejects traversal and symlink targets, verifies the detached RSA-SHA256
signature with OpenSSL, and emits a source- and artifact-bound validation
receipt.

After validation, build the exact fresh technical matrix from the same signed
bundle:

```bash
python scripts/build_bounded_planar_external_vv_matrix_from_operator_bundle.py \
  --attestation submission/operator-attestation.json \
  --bundle-root submission \
  --expected-source-commit <exact-40-character-source-commit> \
  --out submission/bounded-planar-external-vv-matrix.json
```

The builder revalidates the signature and every bundle byte. It credits only
case IDs actually present in signed passing receipts. A core bundle therefore
fills the existing nine rows; the signed portal/multistory supplement adds only
those two rows, while the dedicated modal/buckling supplement adds only
`modal.rigid_mode`, `modal.repeated_mode`, and `buckling.portal`; the dedicated
negative and scaling supplements add only their three and two named rows.
Missing cases remain missing. The emitted
`operator_intake_binding` records signature verification while keeping operator
identity authentication and Verification Level 2 false.

## Authority boundary

A cryptographically valid submission proves possession of the submitted key;
it does not prove who owns that key. The validation receipt therefore keeps
`independent_operator_identity_authenticated=false` and
`verification_hierarchy_level_2=false`. Separate project-side identity and
conflict review, product legal/license approval, a formal scientific decision,
and a hierarchy operator manifest are still required. Commercial equivalence,
design authority, and release readiness remain false.

The fail-closed project-side continuation is documented in
`docs/external-vv-level2-promotion-gate.md`. It revalidates this original signed
bundle and will not promote from the intake validation receipt alone.
