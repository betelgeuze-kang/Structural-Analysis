# Frame Alpha clean-install and cross-platform replay

The `Native Frame Alpha Clean Install` workflow builds the bounded workstation
ZIP independently on GitHub-hosted Linux and Windows builders. A second pair of
fresh hosted runners downloads those ZIPs without either Rust or Workbench build
output, verifies each archive, extracts it into a new temporary directory, and
runs the packaged example twice.

Each clean runner also exercises the source-side local installation manager:

```bash
python scripts/manage_native_frame_alpha_portable_install.py install \
  --archive frame-alpha-workstation-linux-x86_64-gnu.zip \
  --install-root frame-alpha-installation \
  --expected-source-commit "$(git rev-parse HEAD)" \
  --platform-tag linux-x86_64-gnu
```

The manager completes the full workstation archive smoke and checks the expected
source and platform before creating or changing the installation root. It then
stores the package under the deterministic
`versions/v<package-version>--<platform>--<source-commit>/` key without
overwriting an existing target. `current.json` is both the canonical audit
receipt and the current-version pointer. It contains the package, archive,
manifest, source, installed-tree and retained-version hashes; activation is one
same-filesystem atomic file replacement.

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
