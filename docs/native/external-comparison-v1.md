# Bounded Native External Comparison v1

## Closed profile

This slice closes C5 only for three global quantities of the bounded CPU nonlinear-NDTHA
`ResultIR`: maximum drift ratio, residual drift ratio and residual top displacement. Rust owns the
strict `structural-native-external-result.v1` input, comparison arithmetic, deterministic
`structural-native-external-comparison-ir.v1` output and a self-hashed artifact receipt.

Every input names an explicit solver family, evidence kind, run id, solver version, source
artifact SHA-256, model hash, case, coordinate frame, external location, native location, exact
ResultIR path, unit and absolute/relative tolerance. The CLI receives the source artifact itself
and verifies its bytes. A `live_external_execution` also requires an executable SHA-256 and the
exact executable artifact bytes. Missing or mismatched evidence fails before comparison.

`language_neutral_golden`, `proxy` and `live_external_execution` remain different authorities. A
MIDAS, OpenSees or CalculiX label alone never promotes a result. Numerical divergence is preserved
as a valid `diverged` comparison artifact; `--require-pass` returns a policy failure only after the
evidence has been atomically published.

## Command

~~~bash
structural-cli comparison run \
  result-ir.json external-result.json raw-solver-output \
  --output-dir comparison \
  --executable-artifact pinned-solver-binary \
  --require-pass
~~~

The executable argument is omitted for the tracked language-neutral C1 golden. A successful
publication contains:

- `external-comparison-ir.json`: typed rows, derived errors/status and a self-hash;
- `comparison-receipt.json`: content hashes and provenance identities for the comparison.

Publication uses the same new-directory write/sync/rename boundary as the bounded product. The
clean-environment E2E clears the child environment, including `PATH`, and proves repeated output
bytes are identical without Python or Node lookup. The tracked Python C1 golden is supplied as an
ordinary source artifact and its exact bytes are hash-bound; it is not invoked by the product.

## Authority boundary

This is not live MIDAS/OpenSees/CalculiX execution evidence, same-mesh proof, solver certification,
engineering acceptance or design-code compliance. Node/member mapping, local-axis response,
additional quantities, external service acquisition, HIP C2 source-result parity and final C6
fixture decommission remain open.
