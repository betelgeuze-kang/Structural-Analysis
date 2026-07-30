# OpenSees and CalculiX current-source clean runner

`.github/workflows/opensees-calculix-current-source.yml` is a main-only,
same-operator technical execution lane. It downloads the exact checksum-bound
OpenSeesPy and Ubuntu CalculiX runtime assets into `/tmp`, verifies every byte,
and invokes the reviewed combined clean runner. The container receives the
repository read-only, writes only to the receipt directory, and runs with its
runtime network disabled.

The workflow checks that the combined receipt is bound to the exact current-main
SHA, represents actual OpenSees and CalculiX execution, and clears the
`external_runtime_current_source_rerun_missing` blocker for that run. It then
creates and immediately verifies GitHub artifact provenance for the summary
receipt against the exact source SHA, main ref, repository, and workflow. Only
receipts and the provenance bundle are uploaded; external solver packages are
not retained as repository or workflow artifacts.

The authored workflow is not execution evidence. No passing current-main run
attestation bundle is retained, so its dedicated matrix binding remains
`current_source_execution_attached=false`.

A prior local execution of the exact wrapper is retained at
`artifacts/vv/opensees_calculix_clean_runner/clean_runner_receipt.json`. Its
five assets match the workflow hashes, but its host/container source and metric
sets no longer match the current host receipts. The matrix therefore records
`same_operator_execution_binding=unavailable` and grants no current container
parity credit. Current-product replay receipts give replay-only technical credit
to the 9/25 core rows. A repository-local, non-container-attested supplemental
receipt preserves the historical execution-input bytes and binds sixteen more
current-product replay cases. The combined matrix therefore has 25/25 technical
references, all replay-only, and zero fresh current-source rows. The retained
clean-runner receipt is not a GitHub-main run or
GitHub provenance attestation. Either form remains same-operator technical
evidence only: neither establishes independent operation, legal approval,
scientific promotion, Verification Level 2, design authority, commercial
equivalence, or release eligibility.
