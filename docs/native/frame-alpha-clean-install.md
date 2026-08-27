# Frame Alpha clean-install and cross-platform replay

The `Native Frame Alpha Clean Install` workflow builds the bounded workstation
ZIP independently on GitHub-hosted Linux and Windows builders. A second pair of
fresh hosted runners downloads those ZIPs without either Rust or Workbench build
output, verifies each archive, extracts it into a new temporary directory, and
runs the packaged example twice.

Each clean runner also exercises the source-side local installation manager:

```bash
python scripts/manage_native_frame_alpha_portable_install.py install \
  --archive frame-alpha-workstation-linux-x86_64-gnu-baseline.zip \
  --install-root frame-alpha-installation \
  --expected-source-commit "$(git rev-parse HEAD)" \
  --expected-source-tree "$(git rev-parse HEAD^{tree})" \
  --expected-archive-sha256 "sha256:<trusted-64-hex-digest>" \
  --platform-tag linux-x86_64-gnu
```

The archive SHA-256 is a trust input, not a value to calculate from an untrusted
ZIP immediately before invoking the manager. An operator must obtain it together
with the expected source commit, source tree, and platform from an authenticated
release/evidence channel. In this workflow, the separate builder emits those
coordinates and GitHub's immutable artifact coordinate carries them to the clean
runner; the current-main job later attests both packages and receipts. This does
not replace OS code signing or establish release authority.

Before any packaged binary is executed, the manager hashes the captured archive
bytes and performs a non-executing manifest preflight against all four supplied
coordinates. It then gives the full workstation verifier a private read-only
snapshot of those same bytes and extracts the captured bytes only after the
verifier succeeds. It performs all of this before creating or changing the
installation root. It then
stores the package under the deterministic
`versions/v<package-version>--<platform>--<source-commit>/` key without
overwriting an existing target. `current.json` is both the canonical audit
receipt and the current-version pointer. It contains the package, archive,
manifest, source, installed-tree and retained-version hashes; activation is one
same-filesystem atomic file replacement.

Install, update, rollback, and verification serialize on a persistent
per-installation-root operating-system file lock. Contention waits for at most
15 seconds and then fails closed; no manager operation may adopt or remove a
retained version while another operation is changing the pointer.

`update` retains the old verified directory. A lower semantic package version
is rejected unless `--allow-downgrade` is present. Builds with the same package
version but a different source commit remain distinct retained versions.
Rollback is a separate explicit operation and accepts only a key already bound
into the verified `current.json` history:

```bash
python scripts/manage_native_frame_alpha_portable_install.py rollback \
  --install-root frame-alpha-installation \
  --to-version v0.1.0--linux-x86_64-gnu--<40-character-source-commit>
python scripts/manage_native_frame_alpha_portable_install.py verify \
  --install-root frame-alpha-installation
```

Archive failure, source mismatch, downgrade rejection, target collision,
retained-version tampering, or activation failure leaves the prior pointer and
active payload byte-identical. The tool never overwrites a version directory
and rechecks retained bytes before use. This is an application-level
content-bound immutability contract, not protection against an operating-system
administrator modifying files; such modification is detected and rejected on
the next operation.

On Linux, the retained payload digest also binds the manifest-declared
executable bit to the exact installed modes (`0555` for the CLI and `0444` for
non-executable files), so `chmod` tampering fails verification. On Windows, the
retained profile is explicitly content-bound: PE execution does not use POSIX
execute bits, so content, inventory, hashes, and descriptor binding are checked
without claiming POSIX mode authority.

The clean runners additionally build and fully verify two package generations:
the exact-source `0.1.0` baseline and an ephemeral `0.1.1` source identity whose
packaged README states that it exists only for the transition test. They execute
`install -> update -> rollback`, retain all three canonical state snapshots, and
emit and immediately re-load a transition receipt through its strict schema,
self-hash, cross-generation, history-prefix, retained-state-subject, and final
rollback verifier. The package-generation version is separate from the embedded
`structural-cli 0.1.0` component version. This proves the bounded local transition
mechanism only; the ephemeral generation is not an available product update,
release candidate, signing receipt, or customer update service.

The comparison job accepts exactly one Linux and one Windows receipt for the
same source commit and requires byte-identical canonical ResultIR together with
matching result, model, solver, and ABI identities. On current `main`, a final
job checks that both the workflow definition and repository head are that exact
commit, then attests both ZIPs, both coordinate receipts, and the comparison
receipt. The Sigstore bundle is retained and immediately verified against the
repository, workflow, workflow digest, and source digest.

This establishes a portable-directory clean-runner replay and same-source
Linux/Windows result parity for the packaged Frame Alpha example, plus a bounded
offline local install/update/explicit-retained-rollback mechanism. The archive
does not contain a network updater, and the mechanism is not a system installer,
arbitrary-machine or arbitrary-model certification, browser execution,
Authenticode/notarization, customer observation, commercial permission, or
release authority. Those claims remain separate fail-closed gates.
