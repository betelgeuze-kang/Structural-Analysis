# G1 production MGT gfx1100 runner

This runbook produces an isolated `gfx1100` execution and unsigned canonical
evidence for external Ed25519 signing. The current gate treats organization,
runner, location, and signer strings as untrusted metadata until a separate
hardware-identity receipt binds them to the protected runner policy.

## Required runner

- Dedicated AMD `gfx1100` host with `/dev/kfd` and `/dev/dri` available.
- Repository-level protected environment `g1-production-gfx1100` and the unique
  dedicated-runner label `g1-production-gfx1100`.
- The same repository commit and wheel hash named by the accepted local
  `g1_mgt_gfx1030_hardware_envelope.json`.
- ROCm/HIP compiler and device libraries compatible with the runner.
- A clean checkout for every path in the FGMRES receipt source set.

The protected environment must define `G1_GFX1100_ORGANIZATION_ID`,
`G1_GFX1100_EXECUTION_LOCATION`, `G1_GFX1100_RUNNER_ID`,
`G1_GFX1100_SIGNER_PUBLIC_KEY_SHA256`, and
`G1_GFX1100_INDEPENDENT_FROM_LOCAL_GFX1030=true`. These values are not
dispatcher inputs.

The repository includes a manual-only dispatch contract at
`.github/workflows/g1-production-mgt-gfx1100-hardware.yml`. It is gated to the
`main` ref, the protected environment, and dedicated runner labels
`self-hosted`, `linux`, `x64`, `amd`, `rocm`, `gfx1100`, and
`g1-production-gfx1100`. It first checks out the trusted control plane and then the
fixed accepted source SHA into separate directories, with checkout credentials
disabled. The exact 1.3 MB wheel is retained as a Git LFS control artifact at
`dist/structural_analysis-0.3.0-py3-none-any.whl`; the historical source commit
does not contain it. The workflow verifies that control artifact and copies it
into the ignored source `dist/` path before execution. Before any solver work
it verifies the exact control-envelope, source, and wheel hashes and rejects
identity-policy drift, a dirty checkout,
inaccessible `/dev/kfd` or `/dev/dri/renderD128`, a missing pinned ROCm
compiler, or a device that does not report `gfx1100`.

Every run uses a run-ID-specific artifact prefix. Only a successful complete
bundle is uploaded, together with a hash manifest. The bundle remains marked
`promotion_eligible=false`; the workflow does not handle a private signing key
and does not claim G1 closure.

As of 2026-08-09, the repository has one registered self-hosted runner,
`betelgeuze-X570S-AORUS-ELITE`, with only `self-hosted/Linux/X64` labels and
`offline` status. Therefore the production job intentionally remains
undispatchable until an independently operated labeled gfx1100 runner exists.

Read the required source commit without editing the receipt:

```bash
python3 -c 'import json; from pathlib import Path; p=json.loads(Path("implementation/phase1/release_evidence/productization/g1_mgt_gfx1030_hardware_envelope.json").read_text()); print(p["evidence_payload"]["source"]["repository_commit_sha"])'
```

Checkout that exact commit, copy the versioned control wheel into its `dist/`
path, verify SHA-256 against the local envelope, and run:

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/run_g1_mgt_device_fgmres.py \
  --expected-architecture gfx1100 \
  --artifact-prefix g1_mgt_gfx1100_device_fgmres
```

The runner fails closed if `rocminfo` does not report `gfx1100`. It compiles
both `gfx1030` and `gfx1100`, executes only the detected expected target, and
records the two binary hashes plus the executed binary identity.

Build the unsigned envelope around the isolated receipt:

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_g1_mgt_hardware_envelope.py \
  --upstream implementation/phase1/release_evidence/productization/g1_mgt_gfx1100_device_fgmres_receipt.json \
  --out implementation/phase1/release_evidence/productization/g1_mgt_gfx1100_hardware_envelope.json \
  --organization-id YOUR_ORGANIZATION \
  --runner-id YOUR_RUNNER_ID \
  --execution-location YOUR_LOCATION \
  --independent-from-local-gfx1030
```

## Detached signature

Export the exact canonical bytes covered by the signature:

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_g1_mgt_hardware_envelope.py \
  --out implementation/phase1/release_evidence/productization/g1_mgt_gfx1100_hardware_envelope.json \
  --export-evidence g1_mgt_gfx1100_evidence.canonical.json
```

Sign that file with an Ed25519 key outside the repository. Attach the detached
signature and public key without exposing the private key:

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_g1_mgt_hardware_envelope.py \
  --out implementation/phase1/release_evidence/productization/g1_mgt_gfx1100_hardware_envelope.json \
  --attach-signature g1_mgt_gfx1100_evidence.sig \
  --public-key g1_mgt_gfx1100_ed25519_public.pem \
  --signer-id YOUR_SIGNER_ID
```

Finally, validate the receipt and every referenced artifact offline:

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_g1_mgt_hardware_envelope.py \
  --out implementation/phase1/release_evidence/productization/g1_mgt_gfx1100_hardware_envelope.json \
  --check
```

Return the upstream receipt, its isolated artifacts, the signed envelope, the
bundle manifest, and the public key. Do not return the private key. Verify that
the signing key hash matches the protected environment policy. Even a
cryptographically consistent envelope pair is not yet G1 closure evidence.

## Promotion-host verification

After importing the isolated artifacts and signed envelope on the branch that
contains the production pair verifier, run:

```bash
PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_g1_mgt_cross_device_gate.py

PYTHONPATH=$PWD/src:$PWD/scripts:$PWD/implementation/phase1 python3 \
  scripts/build_g1_mgt_cross_device_gate.py --check
```

The v1 gate remains `partial`. It can replay and compare both envelopes, but it
keeps G1 closure false until four separate promotion receipts are bound:
trusted hardware identity, observed CPU fallback count zero, terminal
ResultIR/DiagnosticIR parity, and an end-to-end performance sweep. N1 CPU
mathematical closure remains a separate gate, and unsupported actual-MGT
nonlinear material parameters are not promoted here.
