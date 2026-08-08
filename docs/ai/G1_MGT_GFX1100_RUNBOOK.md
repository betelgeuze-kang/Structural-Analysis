# G1 production MGT gfx1100 runner

This runbook produces an isolated, self-verifying `gfx1100` execution and an
optional Ed25519-signed hardware envelope. It does not itself assert runner
independence; the supplied organization, runner, location, signer, and public
key identities are retained for the cross-device gate.

## Required runner

- Dedicated AMD `gfx1100` host with `/dev/kfd` and `/dev/dri` available.
- The same repository commit and wheel hash named by the accepted local
  `g1_mgt_gfx1030_hardware_envelope.json`.
- ROCm/HIP compiler and device libraries compatible with the runner.
- A clean checkout for every path in the FGMRES receipt source set.

Read the required source commit without editing the receipt:

```bash
python3 -c 'import json; from pathlib import Path; p=json.loads(Path("implementation/phase1/release_evidence/productization/g1_mgt_gfx1030_hardware_envelope.json").read_text()); print(p["evidence_payload"]["source"]["repository_commit_sha"])'
```

Checkout that exact commit, verify the wheel SHA-256 against the local
envelope, and run:

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

Return the upstream receipt, its isolated artifacts, the signed envelope, and
the public key. Do not return the private key. G1 cross-device closure remains
false until the imported `gfx1030` and `gfx1100` envelopes pass same-source,
same-wheel, distinct-runner/organization/signer, signature, numerical,
checkpoint, material, and KPI gates.
