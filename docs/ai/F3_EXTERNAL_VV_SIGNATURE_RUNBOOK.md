# F3 external V&V signature runbook

F3 v2 is a fail-closed evidence-audit lane. It separates each stage's technical
vertical contract from public-product promotion while replaying the ten ordered
stages, nine required product surfaces per stage, canonical predecessor
bindings, and exact Git source identities. It also verifies detached Ed25519
signatures, but deliberately separates cryptographic consistency from trusted
external identity.

The repository-owned trusted-signer set is empty in v2. No production adapter
yet binds the exact Planar product-replay and external-V&V prerequisites.
Therefore:

- `status` is always `partial`;
- all ten valid stage receipts can report `contract_pass=true` and
  `vertical_stage_contract_passed=true`;
- a valid signature-verifier waiver is technical-only and every stage records
  `public_product_promotion_passed=false`;
- `planar_product_replay_prerequisite_bound` and
  `planar_external_vv_prerequisite_bound` are always `false`;
- `all_independent_external_vv_signatures_verified` is always `false`;
- `f3_signed_promotion_closure` is always `false`;
- an arbitrary valid Ed25519 signature is reported as cryptographically valid,
  never as independently trusted.

Adding a signer trust anchor is a separate authority review. An envelope,
command-line argument, environment variable, or status receipt cannot extend
the trust policy. Likewise, callers cannot inject Planar prerequisite booleans
or hashes. A future prerequisite adapter must verify canonical repository paths,
schemas, source epochs, and claims in a separate authority review.

## Source epoch prerequisites

Create envelopes only after the F3 stack and this gate code are committed. The
source commit must contain the builder and schema and must retain every recorded
stage source commit in its Git ancestry. For each stage, the builder verifies:

1. the exact canonical stage-receipt path and committed blob;
2. the stage source commit and tree identity;
3. ancestry from the stage source to the aggregate source;
4. every recorded input checksum at the stage source;
5. the same input checksums at the aggregate source;
6. canonical predecessor path, receipt hash, replay source, and order;
7. runner-defined predecessor replay-hash semantics reconstructed from either
   the canonical replay object or the canonical predecessor stage gate;
8. technical predecessor closure independently of promotion ancestry.

The load-control predecessor replay hash is fully reconstructable from its
canonical replay object and must exactly equal the stage-gate hash. Later
runner generations hash a freshly executed predecessor stage gate. V2 compares
that hash with the same-source canonical predecessor receipt, so all ten rows
can close current-source binding without treating predecessor public promotion
as a technical prerequisite.

An additive change to a shared source input still makes the old stage evidence
non-current. The status remains partial until that stage is replayed in a later,
separately reviewed evidence update.

## Create an unsigned candidate envelope

Use the exact committed source SHA and the fixed canonical signature path:

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_f3_external_vv_signature_status.py \
  --source-commit EXACT_F3_GATE_SOURCE_SHA \
  --stage frame3d_linear \
  --create-envelope \
  --organization-id YOUR_INDEPENDENT_ORGANIZATION \
  --signer-id YOUR_SIGNER_ID \
  --independent-from-repository-operator \
  --independence-authority-receipt-sha256 sha256:EXACT_AUTHORITY_RECEIPT_HASH \
  --envelope implementation/phase1/release_evidence/productization/f3_external_vv_signatures/frame3d_linear.json
```

The organization, signer, independence flag, and authority-receipt hash are
signed claims. They become trusted only if they exactly match a separately
reviewed repository-owned anchor containing the organization, signer, Ed25519
SPKI SHA-256, and independence-authority receipt SHA-256.

## Export and sign canonical bytes

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_f3_external_vv_signature_status.py \
  --envelope implementation/phase1/release_evidence/productization/f3_external_vv_signatures/frame3d_linear.json \
  --export-evidence frame3d_linear.external-vv.canonical.json
```

Sign the exported bytes using an Ed25519 private key outside the repository.
Return only the detached signature and public key. Never return, commit, or log
the private key.

## Attach and inspect

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_f3_external_vv_signature_status.py \
  --envelope implementation/phase1/release_evidence/productization/f3_external_vv_signatures/frame3d_linear.json \
  --attach-signature frame3d_linear.external-vv.sig \
  --public-key independent-vv-ed25519-public.pem

PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_f3_external_vv_signature_status.py \
  --envelope implementation/phase1/release_evidence/productization/f3_external_vv_signatures/frame3d_linear.json \
  --check-envelope
```

`--check-envelope` prints both signature state and trusted classification. With
the v2 empty trust-anchor set, a correctly signed candidate prints
`state=verified | trusted=false`.

Repeat in order for:

1. `frame3d_linear`
2. `frame3d_load_control`
3. `frame3d_direct_control`
4. `frame3d_stateful_material`
5. `modal_buckling`
6. `sdof_authenticated_transient`
7. `mdof_linear_transient`
8. `nonlinear_mdof`
9. `shell`
10. `contact`

The aggregate consumes envelopes only from the fixed directory
`implementation/phase1/release_evidence/productization/f3_external_vv_signatures/`.
A status payload cannot redirect replay to another directory.
Repository evidence paths also reject a symlink in any component, whether it
points inside or outside the repository root.

## Regenerate the partial aggregate

After committing the builder, schema, tests, and runbook, replay and commit all
ten stage receipts against that exact code source. Then regenerate the status
against the stage-receipt commit so the aggregate source tree contains every
canonical receipt:

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_f3_external_vv_signature_status.py \
  --source-commit EXACT_F3_STAGE_RECEIPT_COMMIT_SHA

PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_f3_external_vv_signature_status.py --check
```

Commit the regenerated status separately. The complete ordering is code commit,
ten-stage current-source replay commit, then aggregate receipt commit. It binds
the aggregate to committed builder/schema bytes and all ten canonical receipt
blobs while keeping `status=partial`, trusted signatures `0/10`, and public
promotion false.
