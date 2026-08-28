# OpenSees and CalculiX current-source clean runner

`.github/workflows/opensees-calculix-current-source.yml` is a main-only,
same-operator technical execution lane. It downloads the exact checksum-bound
OpenSeesPy and Ubuntu CalculiX runtime assets into `/tmp`, verifies every byte,
and invokes the reviewed combined clean runner. The container receives the
repository read-only, writes only to the receipt directory, and runs with its
runtime network disabled.

The unprivileged producer checks that the combined receipt is bound to the exact
current-main SHA, represents actual OpenSees and CalculiX execution, and clears
the `external_runtime_current_source_rerun_missing` blocker for that run. A
separate GitHub-hosted OIDC attestor performs no checkout or dependency install.
It retrieves run, job, candidate-artifact metadata and the raw ZIP through the
REST API; checks the exact run attempt, repository, workflow, hosted-runner
labels, artifact ID, digest, size, strict file set, receipt hashes, numerical
pass invariants, and non-authority boundary; then signs a handoff that binds the
immutable producer artifact. Only receipts and that provenance handoff are
uploaded. External solver packages are never retained as repository, candidate,
or final workflow artifacts.

Before the container starts, the wrapper regenerates two host product replays
from the current source while retaining the pinned historical external values.
Those replays receive no freshness credit; they exist only so the fresh
container execution is compared with the same source set and exact commit. A
source-commit or source-set mismatch fails the clean runner closed.

The `Product State Current` workflow searches only for a successful clean-runner
run at its exact source SHA, independently rechecks final-artifact REST identity,
raw ZIP digest and size, strict paths, and the handoff's Sigstore subject,
workflow, source, run ID, and run attempt before using the receipts as matrix
input. Missing, failed, stale, or
unverifiable evidence is recorded as unavailable. There is no tracked-receipt
fallback. Downloaded child and host receipts are materialized beneath the
ignored `.ci/product-state-inputs/opensees-calculix-clean-runner` staging root
with their attested repository-relative paths preserved; the tracked historical
directory is never overwritten. That complete staging root is retained in the
Product State artifact so its summary and matrix bindings can be revalidated
after extraction. The resulting attested exact-SHA Product State artifact is
the sole current-main status authority.

A prior local execution is retained at
`artifacts/vv/opensees_calculix_clean_runner/clean_runner_receipt.json`. Its
contents and counts describe only that historical source context. It is not a
GitHub-main run or GitHub provenance attestation and cannot supply current
container-parity credit. Coverage totals and freshness are intentionally read
from the exact-current Product State artifact rather than copied into this
document. Either form remains same-operator technical
evidence only: neither establishes independent operation, legal approval,
scientific promotion, Verification Level 2, design authority, commercial
equivalence, or release eligibility.
