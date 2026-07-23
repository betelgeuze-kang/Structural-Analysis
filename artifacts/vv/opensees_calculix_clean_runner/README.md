# OpenSees/CalculiX clean-runner candidate bundle

This directory contains the output of
`scripts/run_external_vv_clean_runner.sh <external-asset-directory>` generated on
2026-07-23. The asset directory was external to the repository; the five solver
package files are not included here.

`clean_runner_receipt.json` binds the pinned container, exact external asset
hashes, read-only source/no-network isolation result, child receipt hashes, and
host/container numerical parity. The two JSON child receipts record fresh
OpenSees/CalculiX execution, while `mode_vectors/` contains the four
checksum-bound little-endian binary64 matrices referenced by the modal/buckling
receipt.

The recorded Git SHA is the candidate's base commit. Exact candidate source
bytes are bound by the child receipts' `input_checksums` and `source_set_hash`.
This is same-operator technical evidence. It is not an independent operator
attestation, legal or redistribution approval, Verification Level 2 promotion,
commercial equivalence, design authority, or release readiness.
