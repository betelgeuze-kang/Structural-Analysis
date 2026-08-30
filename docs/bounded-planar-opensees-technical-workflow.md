# Bounded planar OpenSees technical workflow

The `Bounded Planar OpenSees Technical Execution` workflow runs only from the
repository's `main` branch. It checks out the exact workflow source SHA,
installs the canonical hash-locked product runtime, downloads package-pinned
OpenSeesPy wheels into an external temporary directory, and builds a local OCI
runtime from a digest-pinned base. Before any solver starts it seals the derived
image ID, all rootfs diff IDs, every external-asset hash and size, the exact
source tree, and the isolation policy. It then selects the image by that ID and
executes with no network, a read-only root and repository, dropped capabilities,
no-new-privileges, read-only assets, a disposable tmpfs, and only the results
mount persistently writable.

The solver producer has read-only repository permission and no OIDC or
attestation authority. It uploads a sealed candidate and exposes the immutable
artifact ID and digest to the reusable `Bounded Planar Sealed Technical
Attestor`. That fresh hosted job performs no checkout or dependency install;
its inline standard-library verifier authenticates the exact source tree,
source snapshots, the self-hashed pre-execution runtime lock, receipt, and every candidate byte
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

Image construction may use mutable Debian mirrors, but that acquisition phase
ends before the local OCI content address is captured. The seal therefore
claims only that the exact bytes used in this run were locked before execution;
it does not claim that a later rebuild will reproduce the same derived image.
For modal/buckling, the pinned CalculiX, ARPACK, and SPOOLES DEBs are downloaded
without host installation, hash-checked, mounted read-only, and extracted only
to container tmpfs. No wheel, DEB, or derived image is published or uploaded.

This source change does not itself create fresh evidence. Five successful
exact-main runs and a successful downstream Product State aggregation are
required before the sixteen supplemental rows can receive current-source
technical credit.

A passing run establishes only source-authenticated, same-operator technical
execution for the exact source SHA in the attestation. It does not establish
future-build reproducibility, third-party runtime redistribution permission,
independent-operator reproduction, source-use or license approval,
Verification Level 2, engineering design authority, commercial equivalence,
or release readiness. Those claims remain false until their separate evidence
and promotion gates pass.
