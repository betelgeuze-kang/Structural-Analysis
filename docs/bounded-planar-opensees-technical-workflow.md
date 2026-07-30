# Bounded planar OpenSees technical workflow

The `Bounded Planar OpenSees Technical Execution` workflow runs only from the
repository's `main` branch. It checks out the exact workflow source SHA,
installs the package-pinned OpenSeesPy runtime, executes the portal and
multistory cases, and builds a fail-closed technical comparison receipt.

The workflow signs the technical receipt with GitHub artifact provenance. The
receipt binds the external result file hashes, runner bytes, ModelIR bytes,
runtime versions, product values, and package manifest. After downloading the
artifact, verify the receipt provenance with:

```bash
source_sha="$(jq -r .package_binding.source_commit_sha \
  .ci/bounded-planar-opensees/technical-receipt.json)"
gh attestation verify \
  --repo betelgeuze-kang/Structural-Analysis \
  --bundle .ci/bounded-planar-opensees/technical-receipt.sigstore.json \
  --signer-workflow betelgeuze-kang/Structural-Analysis/.github/workflows/bounded-planar-opensees-technical.yml \
  --source-digest "$source_sha" \
  --source-ref refs/heads/main \
  --deny-self-hosted-runners \
  .ci/bounded-planar-opensees/technical-receipt.json
```

A passing run establishes only source-authenticated, same-operator technical
execution for the exact source SHA in the attestation. It does not establish
independent-operator reproduction, source-use or license approval,
Verification Level 2, engineering design authority, commercial equivalence,
or release readiness. Those claims remain false until their separate evidence
and promotion gates pass.
