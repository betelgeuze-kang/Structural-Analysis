# P0-RC canonical verification and artifact freshness

The P0-RC canonical lane is an evaluation contract, not a release or image-publishing lane. Its OCI base is declared by both tag and immutable multi-platform digest in `canonical/verification-environment.v1.json`. CI selects `linux/amd64`; the platform-specific runtime identity is captured in the receipt.

## Environment contract

- CPython is pinned to a patch release inside the digest-pinned image.
- The pinned full Bookworm image inherits the `buildpack-deps` source-control toolchain. CI proves `git` is present before checkout because exact-commit export and source binding require a real Git object store; a source-download fallback is not canonical evidence.
- Every admitted Python dependency, including the build frontend and backend, is pinned with an exact version and wheel SHA-256 in `canonical/requirements-cp312-manylinux2014-x86_64.lock`.
- Installs must use `--only-binary=:all: --require-hashes`. CI first materializes the complete lock into an ephemeral wheelhouse, verifies that its file hashes are exactly the lock hash set, and installs from that wheelhouse with index access disabled. No dependency wheel is committed or vendored.
- Canonical runs use one BLAS/OpenMP/MKL thread, a fixed OpenBLAS `Haswell` dispatch target, `C.UTF-8`, UTC, and `PYTHONHASHSEED=0`.
- `SOURCE_DATE_EPOCH` is the exact checked-out commit timestamp. `build_canonical_project_wheel.py` rejects any other value, exports the exact commit twice with `git archive`, rejects submodules and LFS pointers in package inputs, injects a source-SHA/epoch build marker, and runs two independent PEP 517 isolated builds with dependency-index and cache access disabled. Both wheel filenames, byte lengths, and SHA-256 hashes must be identical. Every wheel `RECORD` payload hash is checked before the artifact is retained.
- The retained wheel is installed with `--no-index --no-deps` into two fresh temporary environments outside the source tree, both inheriting the same canonical dependency runtime. Its module and schema must resolve inside each environment; its embedded source SHA and epoch must match; and both bounded planar member-feature and prescribed-settlement cases must pass twice with identical result, engineering-result, and checkpoint hashes. This canonical-runtime repeat is an exact replay check, not an independently reviewed numerical golden.
- `build_canonical_verification_receipt.py --enforce` rejects a claimed source SHA that differs from `git rev-parse HEAD`, any wheel/receipt/source rebinding, or a runtime that differs from the Python, dependency, or environment-variable contract. It forces NumPy and SciPy linear algebra to load, hashes the actual mapped shared libraries, and requires every loaded BLAS/LAPACK binary to match a member of the exact hash-locked NumPy or SciPy wheel. Its stable fingerprint excludes installation paths while retaining provider, role, member, library, and locked-wheel hashes.

The receipt keeps the `canonical-verification-receipt.v1` envelope so the existing generated-artifact DAG path remains stable. New receipts declare `contract_profile: p0-canonical-installed-wheel.v1`; the schema conditionally requires the wheel and loaded-library bindings for that profile. Historical v1 receipts without this profile remain structurally readable but do not satisfy the strengthened P0 profile.

The OCI declaration is intentionally not published by this repository. Updating its digest, Python version, or any dependency hash is a reviewed contract change and must be accompanied by a new canonical replay.

## Generated-artifact DAG

`canonical/generated-artifact-dag.v1.json` defines one ordered authority chain:

```text
capability registry
  -> generated README/API/Python/Workbench surfaces
  -> verification receipts
  -> product-state
```

`check_generated_artifact_dag.py` hashes every declared input and output plus the current fingerprints of its dependencies. Comparing a candidate snapshot with a trusted baseline marks a changed node stale and propagates that status through every descendant. Missing files are always stale, even if a previous snapshot also recorded them as missing.

Every report node also records a producer-specific `current_binding`. The registry validator checks its schema and evidence paths, the surface generator compares exact rendered bytes, the canonical persisted-bundle validator rechecks the receipt declarations plus the exact raw wheel hash, size, `RECORD`, source marker, and replay projections, and the product-state validator rebuilds the manifest from the exact checkout, fixed external-receipt paths, and the authoritative Nightly workflow event before requiring byte equality. The product-state node also hashes the schema that constrains the current manifest. A missing result, validator exception, missing rebuild input, or failed producer check is stale and propagates downstream. This prevents a hash co-snapshot from blessing old output while allowing a legitimate producer regeneration to become current without comparison to prior main.

Use `--write-state PATH --report PATH --product-state-nightly-event EVENT` only in the exact-main product-state workflow after all declared outputs and rebuild inputs exist. It refuses to write a full state when an artifact is missing and returns failure when any producer current-binding check fails. The workflow uses bounded retries while waiting for a successful canonical-workflow run and artifact for the same source SHA, then materializes and cross-checks the environment receipt, wheel contract, and exact wheel at the paths declared by the DAG. The provenance builder independently reruns the same producer validators before accepting the state/report pair. All three canonical artifacts are retained with the full state, report, and product-state provenance bundle. Exhausting either retry remains fail-closed.

The product-state provenance bundle also binds the exact bytes of `.github/workflows/product-state-current.yml` and records the current GitHub Actions workflow ref, workflow SHA, run ID, run number, and run attempt as a third workflow identity. Before any evidence is built, the workflow requires `github.workflow_sha` to equal the nightly source SHA and checks that the checked-out workflow bytes are the blob at that commit. Immediately before the product-state build it also observes `refs/heads/main` through the GitHub API and records that value rather than assuming the Nightly event is still current. A mismatch produces an honestly blocked manifest. The emitted manifest must validate against `canonical/product-state.current.v1.schema.json`, and `refs/heads/main` is queried again immediately before attestation; any movement fails closed. The builder repeats the Git and GitHub-context checks. Both retained attestation verifications constrain the signer workflow digest, source digest, and `refs/heads/main` source ref to that same SHA. A newer default-branch workflow definition therefore cannot sign evidence for an older nightly source commit; that race fails closed and must be rerun from one exact main SHA. The current run is truthfully recorded with trigger event `workflow_run` and without a fabricated terminal conclusion.

Pull requests use `--write-candidate-state PATH --report PATH`. Candidate mode evaluates only through `verification-receipts`; it forces the main-only `product-state` node and its current-binding status to `unavailable`/`out_of_scope` even if a file happens to exist in the worktree. A candidate can have `scope_pass: true`, but its full `contract_pass` remains false and the candidate state is rejected if supplied later as a trusted `--state` baseline. State/report v2 makes this boundary and every producer validation result machine-readable while the checker and preserved schemas continue to validate legacy v1 state/report payloads.

Example:

```bash
python scripts/check_generated_artifact_dag.py \
  --write-candidate-state .ci/generated-artifact-dag-candidate-state.v2.json \
  --report .ci/generated-artifact-dag-candidate-report.v2.json
```

An artifact-DAG `contract_pass` establishes fingerprint consistency, not numerical, engineering, design, release, or commercial authority. Until an exact-main product-state workflow publishes and attests the state for a successful source-bound quality run, this mechanism does not claim P0-RC completion.
