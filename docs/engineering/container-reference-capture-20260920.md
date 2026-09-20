# Fresh container reference-output capture observation

At committed source `2b41f71e7a67d61a8b721c1b219155f8c81de0a2`, the current clean-runner executed inside the existing pinned-base image, with networking disabled, the source and five checksum-verified solver assets mounted read-only, and a new external directory mounted over the designated output path. The current committed runner was invoked explicitly through the image's Python entrypoint; the older embedded runner was not used. The exact image digest and command are retained in the observation protocol.

The 230.362251246-second observation terminated with exit 1 at `product_receipt_technical_contract_failed`. Both fresh receipt generators and their check commands completed before the clean-runner rejected the failed code-to-code contract. No clean-runner summary or signed acceptance was emitted. Host references were deliberately not refreshed for this diagnostic and were not reached as a parity qualification. This is not a successful standard wrapper run.

The new capture transport preserved 16 files: four OpenSees files (driver, decoded stdout/stderr, execution binding) and twelve CalculiX files (version output, two jobs' input/output/results). All 16 inventory entries matched their byte lengths and hashes. Fifteen output hashes matched the fresh numerical receipt, and the separate OpenSees execution binding matched its runtime record. All 32 files in the enclosing observation packet were verified. The source revision remained unchanged throughout execution.

The fresh code-to-code receipt remains blocked by two original `support_N1_UX_N` comparisons:

| Case | Absolute error (N) | Absolute tolerance (N) | Relative error | Relative tolerance |
| --- | ---: | ---: | ---: | ---: |
| Planar member-feature load path | 4.96424095305589e-7 | 1e-10 | 1.000002770455857 | 1e-10 |
| Planar prescribed-settlement path | 3.631256504377234e-7 | 1e-10 | 3.631256505695832e-10 | 1e-10 |

The fresh modal/buckling receipt reports its technical contract true, but neither receipt establishes independent operator, legal, broader nonlinear-family or release approval. No tolerance or reference value was changed. Diagnostic sidecars remain outside the v1 signed summary; inventory/attestation binding remains open.

The immutable packet inventory is `9c80b578be045228f37c94eccee56b6d95b5a536a4318b32a4bee15f3d0b9cdc`. Exact paths, original error values and verification scopes are in [the summary](container-reference-capture-20260920.summary.json). The observation preserves the failed run rather than replacing historical evidence.
