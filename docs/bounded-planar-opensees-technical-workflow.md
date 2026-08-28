# Bounded planar OpenSees technical workflow

The `Bounded Planar OpenSees Technical Execution` workflow runs only from the
repository's `main` branch. It checks out the exact workflow source SHA,
installs the canonical hash-locked product runtime and package-pinned
OpenSeesPy wheels in an external temporary directory, executes the portal and
multistory cases, and builds a fail-closed technical comparison receipt.

The solver producer has read-only repository permission and no OIDC or
attestation authority. It uploads a sealed candidate and exposes the immutable
artifact ID and digest to the reusable `Bounded Planar Sealed Technical
Attestor`. That fresh hosted job performs no checkout or dependency install;
its inline standard-library verifier authenticates the exact source tree,
source snapshots, runtime-lock metadata, receipt, and every candidate byte
before signing. The third-party wheel bytes are neither copied into the
candidate nor uploaded in the final artifact; only their pinned digest, size,
version, filename, and authority URL are sealed. After downloading the final
artifact, verify the immutable
handoff with:

```bash
source_sha="$(jq -r .source_commit_sha \
  .ci/bounded-planar-opensees/artifact-handoff.json)"
gh attestation verify \
  --repo betelgeuze-kang/Structural-Analysis \
  --bundle .ci/bounded-planar-opensees/artifact-handoff.sigstore.json \
  --signer-workflow betelgeuze-kang/Structural-Analysis/.github/workflows/bounded-planar-sealed-technical-attestor.yml \
  --source-digest "$source_sha" \
  --source-ref refs/heads/main \
  --deny-self-hosted-runners \
  .ci/bounded-planar-opensees/artifact-handoff.json
```

The modal/buckling producer may retain observed results, but its Ubuntu apt
CalculiX/BLAS dependency closure is not an immutable pre-execution byte lock.
Its seal is therefore explicitly non-promoting, and neither the hosted
aggregate nor the v1 signed-operator-bundle path may report fresh 25/25 credit.

A passing run establishes only source-authenticated, same-operator technical
execution for the exact source SHA in the attestation. It does not establish
independent-operator reproduction, source-use or license approval,
Verification Level 2, engineering design authority, commercial equivalence,
or release readiness. Those claims remain false until their separate evidence
and promotion gates pass.
