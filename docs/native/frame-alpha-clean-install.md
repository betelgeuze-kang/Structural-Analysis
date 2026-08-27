# Frame Alpha clean-install and cross-platform replay

The `Native Frame Alpha Clean Install` workflow builds the bounded workstation
ZIP independently on GitHub-hosted Linux and Windows builders. A second pair of
fresh hosted runners downloads those ZIPs without either Rust or Workbench build
output, verifies each archive, extracts it into a new temporary directory, and
runs the packaged CLI twice with the extracted package root as its working
directory. Before a coordinate can pass, the verifier checks the complete
tracked ResultIR schema, independently recomputes the canonical ResultIR hash,
replays the persisted ResultIR through the Rust report contract, and binds the
result ID plus all three ModelIR identities to the extracted example and
`LC_WEAK` request.

The comparison job accepts exactly one Linux and one Windows receipt for the
same source commit and requires byte-identical canonical ResultIR together with
matching result, model, solver, and ABI identities. On current `main`, a final
job checks that both the workflow definition and repository head are that exact
commit, then attests both ZIPs, both coordinate receipts, and the comparison
receipt. The Sigstore bundle is retained and immediately verified against the
repository, workflow, workflow digest, and source digest.

This establishes a portable-directory clean-runner replay and same-source
Linux/Windows result parity for the packaged Frame Alpha example. It is not a
system installer or arbitrary-machine/arbitrary-model certification.

An additional isolated Linux job re-verifies and safely extracts the downloaded
ZIP, starts only its packaged CLI and static Workbench, and drives Chromium
through ModelIR upload, same-origin submit, worker execution, polling, bundle
integrity replay, and ResultIR display. It requires the returned ResultIR to
bind the packaged model, `LC_WEAK` with no combination, and the requested result
identity; the receipt is schema-validated before its create-new write. The
browser receipt remains distinct from clean-install and cross-platform receipts
and is included in the current-main attestation.

The browser automation is not a human new-user observation, accessibility
review, Authenticode/notarization, automatic update, rollback, customer
deployment, commercial permission, or release authority. Those claims remain
separate fail-closed gates. The hosted jobs do not enforce or observe network
isolation, so their receipts record network use as unknown and make no offline
execution claim.
