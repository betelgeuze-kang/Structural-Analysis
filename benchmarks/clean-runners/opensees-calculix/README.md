# OpenSees/CalculiX container clean-runner candidate

This package reproduces the two non-promoting external technical receipts in a container with
three enforced boundaries:

- the repository is mounted read-only;
- only `artifacts/vv/opensees_calculix_clean_runner/` is over-mounted read-write;
- runtime networking is disabled after the image has been built.

The runner consumes the five exact external package files already pinned by
`scripts/run_external_code_to_code_technical_receipt.py`. It checks every SHA-256 before
extracting or executing anything. Solver packages are never copied into the repository.
The OpenSees receipt includes the public one-bay corotational portal's four-step
elastic-state load path and compares terminal free-node displacements and support reactions.
It deliberately stays below the declared material yield and damage thresholds; it is not a
material-nonlinear or cyclic validation.
The CalculiX receipt also compares a six-member tetrahedral `T3D2` spatial truss under a
combined three-axis apex load, covering three apex displacements and nine base reactions.
That bounded linear-truss case is not frame/shell or nonlinear-family validation.

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

The generated product receipts bind the exact source bytes by SHA-256 and record the Git base
commit. This permits a candidate bundle to be generated before its containing commit without
pretending the base commit alone contains those bytes.

When only a current-product replay is possible, refresh both child receipts with their
`--refresh-product-replay` modes and then run:

```bash
python benchmarks/clean-runners/opensees-calculix/run_clean_runner.py \
  --repo-root . \
  --output-dir artifacts/vv/opensees_calculix_clean_runner \
  --refresh-product-replay-summary
```

This preserves the earlier actual container execution but marks both child descriptors as
non-fresh, clears the current-source container-reproduction claim, and adds
`external_runtime_current_source_rerun_missing`. It must not be represented as a substitute
for rerunning the pinned container.

The summary schema deliberately fixes `independent_operator_attestation`, legal and
redistribution approval, Verification Level 2, commercial equivalence, design authority, and
release readiness to `false`. A second operator must reproduce and sign the bundle before it
can be considered for hierarchy promotion.

CalculiX execution is retained as a shared regression in this package. It does not close the
separate second-solver roadmap item, which still requires independent operator evidence and
the stated breadth and review gates.
