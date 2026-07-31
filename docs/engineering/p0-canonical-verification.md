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

`check_generated_artifact_dag.py` hashes every declared input and output plus the current fingerprints of its dependencies. Comparing a candidate snapshot with a trusted baseline marks a changed node stale and propagates that status through every descendant. Missing files are always stale, even if a previous snapshot also recorded them as missing.

Use `--write-state PATH` only in the trusted exact-SHA product-state workflow after all declared outputs exist. It refuses to bless missing artifacts by default. Use `--state PATH` in check lanes; this computes the candidate in memory and does not alter the baseline. `--report PATH` is intended for CI artifacts, not tracked generated state.

Example:

```bash
python scripts/check_generated_artifact_dag.py \
  --state .ci/trusted-generated-artifact-state.json \
  --report .ci/generated-artifact-dag-report.json
```

Until a trusted product-state workflow publishes that exact-SHA baseline and its runtime receipts, this slice provides the fail-closed DAG mechanism but does not claim P0-RC completion.
