# IFC Import Health Current-Source Evidence

The `IFC Import Health Current Source` workflow is the authoritative fresh-run
lane for the bounded ten-file buildingSMART import-health corpus. It checks out
the exact `main` SHA, acquires every IFC and both upstream license files from
commit-pinned URLs, verifies byte length and SHA-256 against the tracked
manifest, executes the existing model-health contracts, and attests the
source-bound technical receipt.

The final builder independently re-hashes all ten IFC files and both license
files, requires the exact canonical case/lane and license identities, binds the
declared source SHA to the checked-out Git commit and clean source tree, and
replays Result/Report validation. Its independent raw STEP assignment scan must
equal both parser record counts and the sum of per-entity counts.

The tracked manifest is
`benchmarks/import_health/buildingsmart_ifc_current_source.v1.json`. The raw IFC
and license files are downloaded only into the ignored `private_corpus/` tree.
They are never included in the uploaded workflow artifact. The artifact retains
the acquisition receipt, model-health result/report files, Phase 3/6 receipts,
their hashes, and the GitHub provenance bundle.

Every retained support file has a source path, an artifact-relative path, and a
SHA-256 entry in the technical receipt's 26-file support manifest. Repository
paths are preserved below `support/repository/`; files are not flattened by
basename.

## Local replay

Use an exact 40-character source commit SHA:

```bash
source_sha="$(git rev-parse HEAD)"
python scripts/acquire_buildingsmart_ifc_current_source.py \
  --source-commit-sha "$source_sha"
python scripts/acquire_buildingsmart_ifc_current_source.py \
  --source-commit-sha "$source_sha" --check
python scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py \
  --source-commit-sha "$source_sha"
python scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py \
  --source-commit-sha "$source_sha"
python scripts/build_phase3_ifc_import_health_execution_receipt.py \
  --source-commit-sha "$source_sha"
python scripts/build_phase3_ifc_source_license_receipt.py \
  --source-commit-sha "$source_sha"
python scripts/build_phase6_silent_import_loss_status.py
python scripts/build_ifc_import_health_current_source_receipt.py \
  --source-commit-sha "$source_sha" --fail-technical-blocked
python scripts/build_ifc_import_health_current_source_receipt.py \
  --source-commit-sha "$source_sha" --check
python scripts/build_ifc_import_health_current_source_receipt.py \
  --source-commit-sha "$source_sha" --check-support-bundle
```

After downloading an artifact, `--check-support-bundle` can verify the exact
support-file set and hashes without the private corpus. Its success message is
deliberately `support_bundle_integrity_consistent_nonfresh`: bundle integrity is
not fresh execution. Fresh technical and immutable-byte claims require the raw
IFC/license files, exact Git source checkout, and the normal generation/check
path.

## Claim boundary

A passing attestation establishes same-operator, current-source technical
execution for ten acquired/checksummed files, ten visible entity-accounting
results, and ten scoped silent-import-loss gates. The IFC adapter remains a STEP
text scan, so the receipt does not establish canonical geometry/topology or
solver-ready import. Recording exact CC-BY-4.0 license bytes does not itself
constitute product legal approval. Redistribution, commercial-use, Phase 3
quantity-credit, independent reproduction, and release authority remain false
until their separate authoritative approvals and receipts exist.
