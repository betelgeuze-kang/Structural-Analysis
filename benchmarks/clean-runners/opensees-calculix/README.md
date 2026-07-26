# OpenSees/CalculiX container clean-runner candidate

This package reproduces the two non-promoting external technical receipts in a container with
three enforced boundaries:

- the repository is mounted read-only;
- only `artifacts/vv/opensees_calculix_clean_runner/` is over-mounted read-write;
- runtime networking is disabled after the image has been built.

The runner consumes the five exact external package files already pinned by
`scripts/run_external_code_to_code_technical_receipt.py`. It checks every SHA-256 before
extracting or executing anything. Solver packages are never copied into the repository.

The Docker base is pinned to
`python:3.11-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba`.
The build installs exact Python numerical/schema package versions. Debian library versions and
the derived image ID are captured in the generated receipt because the Debian package mirror
is not snapshot-pinned in this v1 runner.

## Inputs

Place these files in one external asset directory; do not add them to Git:

| File | SHA-256 |
| --- | --- |
| `openseespy-3.7.1.2-py3-none-any.whl` | `1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65` |
| `openseespylinux-3.7.1.2-py3-none-any.whl` | `63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a` |
| `calculix-ccx_2.17-3_amd64.deb` | `3e2001110e080e8cd01176ca171ee73993fa3a23e73e9febda3241b031a2b65e` |
| `libarpack2_3.8.0-1_amd64.deb` | `07a4b576bd52ae9b0f487a3739b8922183ac88ceb1b2f2e943e3e68b8a12108a` |
| `libspooles2.2_2.2-14_amd64.deb` | `34dd2bf283347402d49b7a9f3e07dc118385e62d8f63ce3fe245b612d2f3a917` |

## Reproduction

From the repository root, run
`scripts/run_external_vv_clean_runner.sh <external-asset-directory>`. The wrapper builds the
pinned image with BuildKit provenance disabled so identical cached layers produce a stable
local image ID, captures that ID, rejects an asset directory inside the repository, and runs
with explicit mounts. The runtime command uses `--network none`,
`--read-only`, a writable `/tmp` tmpfs, a read-only repository mount, and the nested read-write
output mount.

The runner emits:

- `external_code_to_code_receipt.json`;
- `external_modal_buckling_receipt.json`;
- four checksum-bound binary mode-vector artifacts;
- `clean_runner_receipt.json`.

The summary schema deliberately fixes `independent_operator_attestation`, legal and
redistribution approval, Verification Level 2, commercial equivalence, design authority, and
release readiness to `false`. A second operator must reproduce and sign the bundle before it
can be considered for hierarchy promotion.
