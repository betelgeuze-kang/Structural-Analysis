# MIDAS GEN NX / SAP2000 Frame3D full-result adapter

`scripts/ingest_commercial_frame3d_full_export.py` is a **normalization-only, untrusted operator
preflight** for MIDAS GEN NX or SAP2000 linear-static result tables. It can prepare a strict Frame
Alpha `ReferenceIR` for a non-authoritative `ReferenceIR -> ComparisonIR` replay. It accepts
configurable CSV column names so the raw table export is retained byte-for-byte; it does not
require a lossy hand-edited intermediate CSV.

The utility does not parse either vendor's model format. An arbitrary file can therefore occupy the
`model_input` slot and pass the checksum portion of this lane. A successful run proves neither that
the declared entity/unit/axis/release/offset/load mapping matches that file nor that a commercial
solver executed it. The normalization receipt always records `vendor_model_parsed_by_adapter=false`,
`semantic_equivalence_prerequisite_passed=false`, and every V&V/promotion/release eligibility flag
as false.

## Required operator inputs

The adapter needs two JSON files beside the raw exports:

1. the existing Phase 4 operator package, following
   `phase4-commercial-operator-reference-contract.v1`; and
2. one `commercial-frame3d-full-result-export-adapter.v1` mapping manifest.

The operator package must declare a comparison-use permission signal, name the solver being
normalized, declare the full
modeling convention, and checksum every raw model/result file. Normalized output checksums and the
second distinct reference solver are not needed for this raw-normalization pass; the broader
operator preflight checks both after normalization but also keeps `contract_pass=false`.
The relaxed call reports `raw_preflight_pass` while keeping `contract_pass=false`, so it cannot be
mistaken for Phase 4 closure.

The mapping manifest has these exact top-level fields:

| Field | Contract |
| --- | --- |
| `case_id` / `modeling_convention_id` / `reference_id` | exact package and stable ReferenceIR identities |
| `solver` | `midas_gen` or `sap2000`, exact version/run id, external origin |
| `bindings` | operator-declared native model-content hash and exactly one load pattern/combination id |
| `raw_files` | model, node displacement, node reaction, and member-end-force paths plus SHA-256 |
| `units` | `m|mm`, `rad`, `N|kN`, `N*m|kN*m` |
| `axes` | global node, member-local force/action conventions, proper signed-permutation transform |
| `entity_mapping` | bijective external-to-canonical nodes and members, end direction and local transform |
| `semantic_mapping` | releases, rigid offsets, load, mass-source relevance, solver settings, unmapped rows |
| `tables` | encoding, delimiter, header line, exact load filter and raw-to-canonical columns |
| `unsupported_features` | must be empty for normalization preflight acceptance |
| `warnings` | explicit non-blocking operator notes |

Every selected node must have exactly one displacement and one reaction row. Every selected member
must have exactly one result row at each mapped end. Unknown, duplicate, partial, non-finite, or
ambiguous rows fail before any output is written. Release and offset maps must cover every member and
must equal the declared canonical values after end/axis/unit normalization. Only material-linear,
geometrically-linear, P-Delta-off Timoshenko static settings are accepted in this bounded adapter.
Translational releases are rejected; only the Frame Alpha rotational release subset is mapped.
Mass-source participation must be explicitly false because mass is not consumed by this static solve.

Example table mappings use vendor headers directly:

~~~json
{
  "node_displacements": {
    "path": "raw/Joint Displacements.csv",
    "encoding": "utf-8-sig",
    "delimiter": ",",
    "header_row": 1,
    "filters": {"OutputCase": "DEAD"},
    "load_filter_column": "OutputCase",
    "columns": {
      "node_id": "Joint",
      "ux": "U1", "uy": "U2", "uz": "U3",
      "rx": "R1", "ry": "R2", "rz": "R3"
    }
  }
}
~~~

For MIDAS GEN NX, the same table can map `Node`, `Load`, `DX`, `DY`, `DZ`, `RX`, `RY`, and `RZ`.
The member table maps the vendor's member id, end/station label, axial/shear/torsion/moment columns;
each member mapping declares its exact raw I/J labels, canonical direction, and signed local-axis
permutation. Station values that vary by member belong in each member mapping's `raw_i_end` and
`raw_j_end` fields.

## Normalize and compare

~~~bash
python3 scripts/ingest_commercial_frame3d_full_export.py \
  --operator-package operator/package.json \
  --adapter-manifest operator/midas-case-a.adapter.json \
  --reference-out operator/normalized/midas-case-a.reference.json \
  --receipt-out operator/normalized/midas-case-a.normalization-receipt.json
~~~

To evaluate the existing fixed Frame Alpha tolerances, pass the normalized ReferenceIR to the
repository-distributed Rust CLI directly:

~~~bash
structural-cli result compare-frame3d \
  native/case-a.result.json \
  operator/normalized/sap-case-a.reference.json \
  --comparison-id case-a.sap2000 \
  --output comparison-ir > operator/normalized/case-a.sap2000.comparison.json
~~~

The Rust CLI remains the sole ComparisonIR evaluator and performs its existing strict source replay.
The Python adapter intentionally does not wrap or reimplement that evaluator because an arbitrary
caller-supplied executable is not a comparison trust anchor. Exit `2` is an evaluated tolerance
failure with `passed=false`; malformed or mismatched sources produce no ComparisonIR.

## Authority boundary and remaining external work

A successful normalization proves only that the attached bytes passed checksum, table coverage, and
internal consistency checks against an operator-authored mapping manifest and can be represented as
strict ReferenceIR. The `semantic_gates` values are explicitly labelled
`operator_declared_*_consistent`; they are not independently verified semantic matches.
The receipt records the source commit, adapter implementation, native ReferenceIR schema, operator
package, adapter manifest, and every raw file hash. This is an input-byte audit record, not an exact
source/executable/transitive-runtime replay proof.

Caller-provided public keys, signatures, receipts, or identity declarations are not accepted as a
trust anchor and cannot change any authority flag. A positive semantic/V&V path remains blocked until
the repository implements all of the following outside this adapter:

- a repository-owned, reviewed trust registry;
- full canonical and vendor-model semantic projections covering topology, sections/materials,
  units, global/local axes, releases, offsets, loads/combinations, and solver settings;
- exact vendor executable and runtime-component-manifest byte replay; and
- an isolated, transitive runtime whose source and dependency bytes are independently bound.

Until those controls exist, even a cryptographically valid operator-supplied signature is only an
untrusted intake signal. It cannot establish independence, same-model semantics, V&V credit, or
promotion eligibility.

Promotion still requires licensed MIDAS GEN NX and SAP2000 runs, their raw full-result exports and
model files, explicit comparison/redistribution permission, an independent clean replay, actual
comparison evidence, and every other applicable product gate. No execution, legal, independent,
semantic-equivalence, V&V-credit, or release authority is created by this adapter.
