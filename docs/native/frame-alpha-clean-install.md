# Frame Alpha clean-install and cross-platform replay

The `Native Frame Alpha Clean Install` workflow builds the bounded workstation
ZIP independently on GitHub-hosted Linux and Windows builders. A second pair of
fresh hosted runners downloads those ZIPs without either Rust or Workbench build
output, verifies each archive, extracts it into a new temporary directory, and
runs the packaged example twice.

The comparison job accepts exactly one Linux and one Windows receipt for the
same source commit and requires byte-identical canonical ResultIR together with
matching result, model, solver, and ABI identities. On current `main`, a final
job checks that both the workflow definition and repository head are that exact
commit, then attests both ZIPs, both coordinate receipts, and the comparison
receipt. The Sigstore bundle is retained and immediately verified against the
repository, workflow, workflow digest, and source digest.

This establishes a portable-directory clean-runner replay and same-source
Linux/Windows result parity for the packaged Frame Alpha example. It is not a
system installer, arbitrary-machine or arbitrary-model certification, browser
execution, Authenticode/notarization, automatic update, rollback, customer
observation, commercial permission, or release authority. Those claims remain
separate fail-closed gates.
