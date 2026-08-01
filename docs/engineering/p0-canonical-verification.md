# P0-RC canonical verification and artifact freshness

The P0-RC canonical lane is an evaluation contract, not a release or image-publishing lane. Its OCI base is declared by both tag and immutable multi-platform digest in `canonical/verification-environment.v1.json`. CI selects `linux/amd64`; the platform-specific runtime identity is captured in the receipt.

## Environment contract

- CPython is pinned to a patch release inside the digest-pinned image.
- Every admitted Python dependency, including the build frontend and backend, is pinned with an exact version and wheel SHA-256 in `canonical/requirements-cp312-manylinux2014-x86_64.lock`.
- Installs must use `--only-binary=:all: --require-hashes`. The project itself is installed with dependency resolution disabled after the lock is installed.
- Canonical runs use one BLAS/OpenMP/MKL thread, `C.UTF-8`, UTC, and `PYTHONHASHSEED=0`.
- `build_canonical_verification_receipt.py --enforce` rejects a runtime that differs from the Python, dependency, or environment-variable contract. The receipt records the source SHA, OS/libc, NumPy/SciPy versions, NumPy BLAS/LAPACK build identity, loaded linear-algebra library hashes, thread limits, locale, timezone, and hash seed.

The OCI declaration is intentionally not published by this repository. Updating its digest, Python version, or any dependency hash is a reviewed contract change and must be accompanied by a new canonical replay.

## Generated-artifact DAG

`canonical/generated-artifact-dag.v1.json` defines one ordered authority chain:

```text
capability registry
  -> generated README/API/Python/Workbench surfaces
  -> verification receipts
  -> product-state
```

`check_generated_artifact_dag.py` hashes every declared input and output plus the current fingerprints of its dependencies. The exact 40-hex source commit SHA is retained once as the top-level provenance binding; it is deliberately excluded from node fingerprints, so commit movement alone does not misclassify byte-identical generated artifacts as stale. Comparing a candidate snapshot with a separately retained baseline marks a changed node stale and propagates that status through every descendant. Missing files are always stale, even if a previous snapshot also recorded them as missing.

Every invocation requires `--source-sha SHA`. The canonical PR lane uses `--require-through verification-receipts`: registry, generated capability surfaces, and the freshly materialized canonical receipt are strict, while the downstream product-state node remains visible as deferred and may honestly be absent. Its digest-pinned slim container does not carry Git, so source binding is established by the workflow SHA passed to both the receipt and top-level DAG state, with an explicit `receipt.source_commit_sha == GITHUB_SHA` check. The exact-main product-state workflow has Git available, uses `--verify-head`, and uses `--require-through product-state` only after all declared outputs exist.

Both lanes write and schema-validate a provenance DAG state. They do not compare that state with itself, because such a comparison cannot establish freshness. A real stale-evidence decision requires a separately retained, trusted state from an earlier run; wiring and authenticating that cross-run artifact baseline remains pending and is not claimed by this slice. Missing artifacts in the required prefix still fail closed while the provenance state is written.

Example:

```bash
python scripts/check_generated_artifact_dag.py \
  --source-sha "$(git rev-parse HEAD)" \
  --verify-head \
  --require-through verification-receipts \
  --write-state .ci/generated-artifact-dag-state.json
```

The exact-main workflow obtains the canonical runtime receipt from a separate job running the same digest-pinned container as the PR lane, observes `refs/heads/main` through the GitHub API immediately before product-state construction, and refuses attestation if that observation changes before signing. A source/observed-main mismatch is recorded as blocked rather than as a false current match. The workflow retains its complete provenance state and runtime receipt as artifacts. PR and product-state checks deliberately do not yet download or trust a historical-main DAG state, so stale cross-run invalidation remains an explicit pending gate and this wiring does not claim P0-RC completion.
