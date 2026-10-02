# Canonical Actions artifact admission followup

The earlier Product State intake selected a successful exact-source P0 workflow
run but downloaded its artifact by a SHA-only name. A rerun can keep the run ID
and source SHA while changing `run_attempt`; that name did not connect the saved
run metadata to the producer attempt of the receipt and wheel.

The P0 producer now runs the complete tracked-source guard after checkout and
again immediately before staging. The latter composes the existing 22 exact
producer content exceptions with the single named canonical untracked receipt.
It adds no tracked-path exception. Capability surfaces are checked without
`--write`, and canonical wheel source stamping happens in temporary Git exports.
The existing source guard remains unchanged.

The producer stages exactly these three files under one fresh directory and
uploads that directory with hidden files included:

- `artifacts/manifests/canonical_verification_environment.current.v1.json`
- `.ci/canonical-project-wheel-contract.json`
- `.ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl`

The artifact name is now
`canonical-verification-environment-<run-id>-<run-attempt>-<source-sha>`.
The consumer requires one such artifact in a complete, bounded REST inventory,
agreement with its direct immutable artifact API response, and the producer run
ID, repository IDs, main branch, and exact source SHA. Numeric identity fields
must be positive JSON integers, including in both artifact API representations.
The exact canonical workflow location accepts the REST optional `@ref` suffix;
the provenance bundle continues to record the normalized workflow location.

Artifact timestamps must satisfy
`run_started_at <= created_at <= artifact.updated_at <= run.updated_at`.
This rejects an artifact carrying the current attempt name but created before
that attempt started, and an artifact dated after the completed run snapshot.
The consumer re-fetches the run after downloading the archive so a changed
attempt cannot reuse the earlier selection.

Before materialization, the raw ZIP byte count and SHA256 must match the REST
`size_in_bytes` and `digest`. The ZIP must contain exactly the three paths above,
with regular file types, bounded sizes and supported compression. Basename-only
matches, extra or duplicate entries, traversal paths, and symlinks fail closed.
Explicit DOS directory metadata also rejects, including when the exact filename
has no trailing slash; ordinary mode-zero DOS regular-file entries remain valid.
The existing receipt schemas, contract profile, source SHA, installed wheel
replay fields, wheel length and wheel digest checks remain in the workflow.
The CLI checks regular-file metadata and size bounds before reading the archive.
Downstream replay also checks each sealed member's bounded, exact byte count
before reading it. Sparse oversized files fail without payload reads.

The new `.ci/product-state-inputs/canonical-actions-artifact-identity.json` pins
the selected run and attempt, list/direct artifact identity, raw archive digest
and all three member digests. The candidate seal requires it and the saved API
responses. The authenticated downstream job replays those sealed snapshots and
the materialized member bytes before rebuilding the DAG and provenance. That
replay does not make a fresh live API or raw-archive observation; the archive
digest was checked during intake and is carried by the authenticated seal.

Narrow searches found no other live consumer of the previous SHA-only canonical
artifact name in workflows, scripts, tests, docs or canonical declarations.
Legacy names intentionally receive no fallback. Existing hosted artifacts must
be produced again by an approved exact-source P0 attempt after publication.

The API contract assumes the configured GitHub Actions service exposes a SHA256
artifact digest, complete artifact metadata, and `run_started_at` for the current
attempt. It also requires artifact timestamps to fall within the successful run
snapshot and the ZIP transfer bytes to match REST size/digest. Missing or changed
service fields stop admission. The [artifact REST documentation](https://docs.github.com/en/rest/actions/artifacts)
and [workflow run REST documentation](https://docs.github.com/en/rest/actions/workflow-runs)
describe these fields;
synthetic fixtures do not confirm a hosted service, pinned upload action, runner,
or later commit. Explicit directory staging fixes the package root without
depending on wildcard common-ancestor behavior.

This followup uses only new synthetic API/archive tests and a new mini Git
pre-stage integration case: the initial 74-case followup passed locally, along
with Ruff and syntax/format checks. Earlier 29/41/30 test receipts and the base253d source
admission remain immutable historical evidence. Local uncommitted changes need
their own approved exact commit and hosted receipts before current-source CI
credit; none of this grants physical, design, release or commercial authority.
The first 74-case followup receipt is also preserved. Independent review exposed
the DOS-directory metadata contradiction; the repaired helper and two focused
metadata cases have a separate superseding verification receipt; the prior
74-case receipt remains immutable. After the production admission repair, the
complete affected new suite passed all 76 checks on the final helper. Older
completed suites and fixtures were not repeated.
