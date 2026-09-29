# Same-operator nonlinear/material/recovery technical replay

This packet records six bounded planar OpenSeesPy cases run against the exact
source commit `2ddb2deff53ec4e5b7bb6c047709f914a5dd554e` (tree
`5c01d707a8a2bfbb8f2335a5af419d3c81291415`). It keeps the generated
package, a pre-execution runtime lock, the isolated-container outputs, the
same-operator host outputs, and the technical comparison receipt together.

The package was generated from that commit. The locked OCI image was
`sha256:626da371dca6e8195a5aad4c32b7749a68ad5dc7fe252467f4864e68d2c5eb1a`;
the runtime lock records the pinned OpenSeesPy 3.7.1.2 wheel hashes and the
no-network, read-only container policy. Wheel bytes and the OCI image are not
redistributed here. The lock was prepared at
`2026-09-28T15:05:13.688947+00:00`, before the six retained container outputs
at `15:06:02`–`15:06:03` UTC. An initial container attempt used a `noexec`
`/tmp` mount and could not load the OpenSees shared library; it produced no
accepted case output. The retained results come from the successful rerun with
an executable scratch mount.

All six external result contracts passed. The receipt reports `technical_pass`
for 42 declared product/external metric comparisons under their per-metric
absolute-or-relative tolerances. The 57 raw metrics across all six cases match
the separately retained host outputs exactly. These are six narrow technical
cases, not a general accuracy or performance benchmark.

From this repository root, rerun the read-only checks:

```bash
python3 scripts/bounded_planar_runtime_lock.py image-id \
  --manifest artifacts/vv/bounded_planar_nonlinear_material_recovery_2ddb2def_same_operator/runtime-preexecution-lock.json
PYTHONPATH=src python3 scripts/ingest_bounded_planar_external_nonlinear_material_recovery_results.py \
  --package-dir artifacts/vv/bounded_planar_nonlinear_material_recovery_2ddb2def_same_operator/package \
  --results-dir artifacts/vv/bounded_planar_nonlinear_material_recovery_2ddb2def_same_operator/container-results \
  --out /tmp/bounded-planar-2ddb2def-replayed-receipt.json --fail-technical-blocked
cmp artifacts/vv/bounded_planar_nonlinear_material_recovery_2ddb2def_same_operator/technical-receipt.json \
  /tmp/bounded-planar-2ddb2def-replayed-receipt.json
```

The receipt deliberately leaves fresh-current-source execution attestation,
independent-operator attestation, legal-use approval, Verification Level 2, and
verification-matrix credit false. This same-operator packet does not close
those dependencies or authorize release or structural design decisions.
