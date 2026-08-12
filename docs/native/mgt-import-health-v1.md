# Bounded Native MGT Import Health v1

## Closed profile

This slice closes C5 only for bounded MGT import health and one exact numeric frame/truss
normalization profile. Rust owns the original bytes, byte length, encoding disposition, source
SHA-256, section counts, every non-comment row disposition and deterministic diagnostics. It never
uses lossy decoding. Strict UTF-8 and UTF-8 with BOM are accepted; unsupported encoding is emitted
as blocked health data while the exact original bytes remain an artifact.

Every source row is assigned one explicit disposition:

- `mapped`: consumed by the bounded native grammar and assigned target IDs;
- `preserved_only`: retained byte-for-byte but intentionally not used for structural semantics;
- `dropped`: a recognized structural family outside this profile, such as shell elements;
- `unsupported`: malformed, ambiguous, dangling or otherwise unmapped input.

`dropped` and `unsupported` rows are blockers. There is no implicit default material, section,
constraint or load. Missing required families are also blockers, so incomplete existing foundation
fixtures produce import-health evidence but no invented ModelIR.

## Exact ModelIR subset

ModelIR publication requires one supported force/length unit row and complete numeric rows for:

- nodes with positive integer IDs and finite XYZ coordinates;
- linear materials with E, Poisson ratio and density;
- FRAME sections with A, Iy, Iz, J, Ay and Az, or TRUSS sections with A;
- BEAM/FRAME/COLUMN or TRUSS elements with valid material, section and node references;
- binary six-DOF constraint masks;
- exactly one static load case and at least one six-component nodal load.

All quantities are converted to SI. Rotation input is degrees, and the provenance record makes the
fixed mass/time/rotation convention explicit. The result is strict canonical ModelIR v2 with a
canonicalized roundtrip map. Rust then sends it through the existing C ABI typed descriptor; C++
must report both `contract_valid` and `analysis_ready`, and its canonical snapshot must retain all
three Rust identities.

## Public command and artifacts

~~~bash
structural-cli import mgt source.mgt \
  --model-id imported-model-v1 --output-dir import-health

structural-cli import mgt source.mgt \
  --model-id imported-model-v1 --output-dir import-health \
  --require-normalized
~~~

The source must be a regular non-symlink file no larger than 64 MiB. Publication is create-new and
atomic. Every outcome contains `source.mgt`, `import-health.json` and a self-hashed
`import-receipt.json`. A normalized outcome also contains `model-ir.json`,
`native-validation.json` and `native-snapshot.json`. `--require-normalized` returns exit code 2 for
a blocked import after publishing its diagnostic bundle; without it, blocked health is successful
data rather than a parser crash.

## Evidence and authority boundary

The language-neutral oracle covers two exact profiles and all four existing
`foundation_realish/*.mgt` fixtures. Python independently freezes original byte hashes, line counts,
section counts and the original exact profile's closed-form structural inputs. Rust consumes that golden,
checks every disposition/count/diagnostic, rejects duplicate and dangling identities, and binds
source mutation into health and ModelIR hashes. A clean-environment Rust CLI test proves C++
validation/snapshot equality, frozen artifact hashes, policy behavior, symlink rejection and
non-overwrite publication without Python or Node lookup.

The second exact profile uses the same independently frozen stiffness, mass and loading as the
bounded NDTHA product fixture. `structural-workbench import-mgt` retains the original MGT bytes,
health JSON, MGT receipt and C++ snapshot in its immutable import stage, then executes
Import -> Validate -> Run -> Resume -> Compare -> Report. Separate-process restart and one-shot
flows are byte-identical, and reopening the workspace deterministically reproduces the import and
C++ snapshot before trusting any later stage.

This is not general MGT authority. CP949 and other encodings, repeated `USE-STLD` association,
self-weight, load combinations, shell/wall/solid elements, offsets, links, thickness, writeback,
broader solver execution and C6 Python decommission remain open.
