# G1 current-main gfx1100 evidence lane

This runbook covers the repository-verifiable part of issue #266: a dedicated,
manual-only, fail-closed `gfx1100` evidence lane. It does not close the hardware
or release claim. The repository has no current-source independent `gfx1100`
receipt, trusted hardware-identity attestation, independent operator review, or
cross-device performance sweep.

## Dispatch boundary

Do not dispatch `.github/workflows/g1-production-mgt-gfx1100-hardware.yml`
until all of these external preconditions are satisfied:

- a dedicated Linux x64 AMD runner is online with labels `self-hosted`, `linux`,
  `x64`, `amd`, `rocm`, `gfx1100`, and `g1-production-gfx1100`;
- `/dev/kfd`, `/dev/dri`, `rocminfo`, `/opt/rocm/bin/hipcc`, Python, and the
  preinstalled build/runtime dependencies are available;
- GitHub CLI supports `gh attestation verify`, and the workflow-scoped
  ephemeral `${{ github.token }}` can authenticate to `github.com`;
- no persistent runner login is accepted as the evidence credential;
- the protected environment `g1-production-gfx1100` requires reviewer approval;
- environment variables `G1_GFX1100_ORGANIZATION_ID`,
  `G1_GFX1100_EXECUTION_LOCATION`, `G1_GFX1100_RUNNER_ID`,
  `G1_GFX1100_SIGNER_PUBLIC_KEY_SHA256`, and
  `G1_GFX1100_INDEPENDENT_FROM_LOCAL_GFX1030=true` are configured;
- the Ed25519 private key is held outside the repository, workflow, runner
  checkout, and uploaded artifact.

The workflow has only `workflow_dispatch`, only accepts `refs/heads/main`, and
checks out `${{ github.sha }}` with credentials disabled. It builds one wheel
outside the checkout, requires a clean exact source tree, records the wheel's
exact SHA-256 and byte length, fails unless the default selected ROCm agent is
`gfx1100`, verifies that architecture again after execution,
queries the GitHub API for the numeric repository ID and exact `main` ref,
and binds the repository, repository ID, workflow path/ref, source ref, exact
GitHub run ID, run attempt, artifact prefix, configured runner ID, and receipt
runner ID. Immediately before attestation and again
immediately before upload it requires remote `main`, checkout `HEAD`, the clean
tree, gate replay, and archive verification to remain exact. It also checks
remote `main` after upload so a move during the upload makes the workflow run
fail. The already source-SHA-bound artifact may still physically exist in that
failed run; consumers must require a successful run and exact-head SHA rather
than infer current-main authority from artifact presence. It never starts or
reconfigures a runner service.

## Evidence products

One successful run creates these isolated files under the runner temporary
directory:

- the exact current-source wheel bytes;
- a deterministic pre-execution worker contract;
- one direct bounded Engine-v2 HIP FGMRES device receipt;
- the exact canonical bytes for detached Ed25519 signing;
- raw `rocminfo` output;
- a cross-device intake gate containing SHA-256 and byte length for every
  retained file;
- one deterministic uncompressed tar archive with an exact regular-file
  allowlist and normalized mode, uid, gid, owner names, order, and mtime;
- a GitHub/Sigstore provenance bundle for that immutable archive.

The bounded HIP translation unit is read and hashed once from the exact clean
checkout, then those captured bytes are passed directly to `hipcc` through
standard input; the compiler does not reopen the mutable checkout path. The
binary is not imported from the wheel. Therefore the device receipt keeps
`wheel_identity_bound_at_execution=false` and the wheel-execution blocker
visible. The wheel is retained and hashed only as an intake candidate; its
presence is not a same-wheel execution claim.

Every gate path is relative to a separate `artifact-root`. The serialized gate
contains no runner absolute path and no raw Stage 4 payload. Its
`stage4_diagnostic` is path-independent, has `diagnostic_only=true`, retains
only technical identity gates and receipt hashes, and fixes all product
authority fields false. The uploaded artifact contains only the tar archive and
its provenance bundle; the mutable artifact directory is never uploaded.
Every worker-contract and gate build or replay also requires explicit
`repository`, numeric `repository_id`, `workflow_path`, `workflow_ref`,
`source_ref`, `github_run_id`, `github_run_attempt`, `artifact_prefix`, and
`expected_runner_id` arguments. These must exactly match the fixed lane identity,
worker contract, and composite device-receipt runner ID; a coordinated
repository, workflow, worker, or device transplant is rejected.

The pre-execution worker contract intentionally has no hardware execution API.
Its `hardware_execution_proven`, `signed_provenance`, `release`, `performance`,
and `production_ready` claims are all fixed `false`. The device runner can
report a bounded direct hardware observation after execution, but the
cross-device gate keeps the same five product claims false until external
authority is imported. A runner label, organization string, local signature,
or GitHub workflow attestation by itself is not a trusted hardware-root claim.

The workflow attests the deterministic archive containing the gate and every
allowlisted retained byte. It then verifies the bundle against the exact workflow, source
SHA, and `refs/heads/main`. This proves workflow provenance for the retained
manifest; it does not prove that a self-hosted runner was honest or independently
operated.

## Detached Ed25519 signature

After downloading the artifact, work from a clean checkout of the exact source
SHA recorded in the receipt. Sign the canonical device-evidence file outside
the repository, then attach and replay it:

```bash
python3 scripts/run_g1_gfx1100_device_receipt.py \
  --out /secure/intake/gfx1100.device-receipt.json \
  --attach-signature /secure/intake/gfx1100.device-evidence.sig \
  --public-key /secure/intake/gfx1100.ed25519-public.pem \
  --signer-id INDEPENDENT_SIGNER_ID

python3 scripts/run_g1_gfx1100_device_receipt.py \
  --out /secure/intake/gfx1100.device-receipt.json \
  --check
```

Verify that the DER public-key SHA-256 equals the protected environment's
`G1_GFX1100_SIGNER_PUBLIC_KEY_SHA256`. Never upload or commit the private key.

Verify the GitHub/Sigstore retained-byte provenance separately:

```bash
gh attestation verify /secure/intake/gfx1100.evidence.tar \
  --repo betelgeuze-kang/Structural-Analysis \
  --bundle /secure/intake/gfx1100.provenance-bundle.jsonl \
  --signer-workflow betelgeuze-kang/Structural-Analysis/.github/workflows/g1-production-mgt-gfx1100-hardware.yml \
  --signer-digest EXACT_SOURCE_SHA \
  --source-digest EXACT_SOURCE_SHA \
  --source-ref refs/heads/main
```

## Cross-device intake

The promotion host must retain the exact wheel used by both architectures and
must have signed current-source device receipts for `gfx1030` and `gfx1100`.
Extract the archive without changing member bytes. From a clean checkout of the
exact source SHA, point `--artifact-root` at the relocated directory and use
only relative member paths:

```bash
python3 scripts/build_g1_mgt_cross_device_gate.py \
  --artifact-root /secure/intake/artifact-root \
  --repository betelgeuze-kang/Structural-Analysis \
  --repository-id 1136685613 \
  --workflow-path .github/workflows/g1-production-mgt-gfx1100-hardware.yml \
  --workflow-ref refs/heads/main \
  --source-ref refs/heads/main \
  --github-run-id EXACT_GITHUB_RUN_ID \
  --github-run-attempt EXACT_GITHUB_RUN_ATTEMPT \
  --artifact-prefix EXACT_ARTIFACT_PREFIX \
  --expected-runner-id EXACT_EXPECTED_RUNNER_ID \
  --gfx1030 gfx1030.device-receipt.json \
  --gfx1100 gfx1100.device-receipt.json \
  --worker-contract gfx1100.worker-contract.json \
  --retained-wheel wheel/structural_analysis-current.whl \
  --retained-file wheel/structural_analysis-current.whl \
  --retained-file gfx1100.worker-contract.json \
  --retained-file gfx1030.device-receipt.json \
  --retained-file gfx1100.device-receipt.json \
  --out gfx1100.cross-device-gate.json

python3 scripts/build_g1_mgt_cross_device_gate.py \
  --artifact-root /secure/intake/artifact-root \
  --repository betelgeuze-kang/Structural-Analysis \
  --repository-id 1136685613 \
  --workflow-path .github/workflows/g1-production-mgt-gfx1100-hardware.yml \
  --workflow-ref refs/heads/main \
  --source-ref refs/heads/main \
  --github-run-id EXACT_GITHUB_RUN_ID \
  --github-run-attempt EXACT_GITHUB_RUN_ATTEMPT \
  --artifact-prefix EXACT_ARTIFACT_PREFIX \
  --expected-runner-id EXACT_EXPECTED_RUNNER_ID \
  --gfx1030 gfx1030.device-receipt.json \
  --gfx1100 gfx1100.device-receipt.json \
  --worker-contract gfx1100.worker-contract.json \
  --retained-wheel wheel/structural_analysis-current.whl \
  --retained-file wheel/structural_analysis-current.whl \
  --retained-file gfx1100.worker-contract.json \
  --retained-file gfx1030.device-receipt.json \
  --retained-file gfx1100.device-receipt.json \
  --out gfx1100.cross-device-gate.json \
  --check
```

The v3 gate remains `blocked` even when its byte and pair comparisons pass.
The following are genuinely external/hardware-only blockers and must remain
visible until authoritative receipts exist:

- trusted `gfx1100` hardware identity and malicious-runner boundary;
- independent operator identity, review, and independence attestation;
- imported verification of the signed retained-byte provenance bundle;
- same-wheel current-source `gfx1030`/`gfx1100` execution pair;
- independently attested proof that CPU fallback count is exactly zero;
- terminal `ResultIR` and `DiagnosticIR` parity across `gfx1030` and `gfx1100`;
- an atomic wheel-identity measurement spanning the hardware run (the current
  outer pre/post hashes only narrow mutation risk);
- end-to-end cross-device performance sweep;
- explicit release authority.

Do not commit downloaded device output, wheel files, generated gates, or
historical readiness snapshots. Keep them in artifact storage and bind them by
hash. Closing issue #266 means the manual evidence lane is reviewable on main;
it does not mean G1, hardware execution, production readiness, or release is
closed.

## Historical #267 disposition

Closed, unmerged PR #267 is a source quarry only. Its old LFS
`release_asset`, exact pinned wheel, 70,560-DOF MGT execution path, and generated
receipts/readiness snapshots are superseded by current product contracts and
are not imported into this lane. The transient wheel built by this workflow is
retained-byte evidence for one run, not execution-bound, a release asset, or an
exact pinned commercial wheel. This lane executes only the bounded 66-equation
Engine-v2 recurrence; it does not recreate or promote the historical
70,560-DOF MGT claim.

External hardware execution, full G1 work, independently attested CPU fallback
zero, terminal `ResultIR`/`DiagnosticIR` cross-device parity, performance, and
release authority remain tracked under #257. Closing #266 closes only the
reviewable packaging and evidence-transport lane. It does not close #257, G1,
hardware authority, performance, production readiness, or release.
