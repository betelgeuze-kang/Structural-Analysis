# MIDAS GEN NX / SAP2000 Frame3D full-result adapter

`scripts/ingest_commercial_frame3d_full_export.py` connects operator-attached MIDAS GEN NX or
SAP2000 linear-static result tables to the existing strict Frame Alpha
`ReferenceIR -> ComparisonIR` path. It accepts configurable CSV column names so the raw vendor
table export is retained byte-for-byte; it does not require a lossy hand-edited intermediate CSV.

## Required operator inputs

The adapter needs two JSON files beside the raw exports:

1. the existing Phase 4 operator package, following
   `phase4-commercial-operator-reference-contract.v1`; and
2. one `commercial-frame3d-full-result-export-adapter.v1` mapping manifest.

The operator package must grant comparison use, name the solver being normalized, declare the full
modeling convention, and checksum every raw model/result file. Normalized output checksums and the
second distinct reference solver are not needed for this raw-normalization pass; the existing final
Phase 4 preflight still requires both after normalization.
The relaxed call reports `raw_preflight_pass` while keeping `contract_pass=false`, so it cannot be
mistaken for Phase 4 closure.

The mapping manifest has these exact top-level fields:

| Field | Contract |
| --- | --- |
| `case_id` / `modeling_convention_id` / `reference_id` | exact package and stable ReferenceIR identities |
| `solver` | `midas_gen` or `sap2000`, exact version/run id, external origin |
| `bindings` | exact native model-content hash and exactly one load pattern/combination id |
| `raw_files` | model, node displacement, node reaction, and member-end-force paths plus SHA-256 |
| `units` | `m|mm`, `rad`, `N|kN`, `N*m|kN*m` |
| `axes` | global node, member-local force/action conventions, proper signed-permutation transform |
| `entity_mapping` | bijective external-to-canonical nodes and members, end direction and local transform |
| `semantic_mapping` | releases, rigid offsets, load, mass-source relevance, solver settings, unmapped rows |
| `tables` | encoding, delimiter, header line, exact load filter and raw-to-canonical columns |
| `unsupported_features` | must be empty for ingest credit |
| `warnings` | explicit non-blocking operator notes |

Every selected node must have exactly one displacement and one reaction row. Every selected member
must have exactly one result row at each mapped end. Unknown, duplicate, partial, non-finite, or
ambiguous rows fail before any output is written. Release and offset maps must cover every member and
must equal the declared canonical values after end/axis/unit normalization. Only material-linear,
geometrically-linear, P-Delta-off Timoshenko static settings are accepted in this bounded adapter.
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

To evaluate the existing fixed Frame Alpha tolerances, attach the exact native ResultIR and the
built Rust CLI. The four comparison arguments are atomic:

~~~bash
python3 scripts/ingest_commercial_frame3d_full_export.py \
  --operator-package operator/package.json \
  --adapter-manifest operator/sap-case-a.adapter.json \
  --reference-out operator/normalized/sap-case-a.reference.json \
  --receipt-out operator/normalized/sap-case-a.normalization-receipt.json \
  --native-result native/case-a.result.json \
  --structural-cli target/release/structural-cli \
  --comparison-id case-a.sap2000 \
  --comparison-out operator/normalized/case-a.sap2000.comparison.json
~~~

The Rust CLI remains the sole ComparisonIR evaluator. Exit `2` (an evaluated tolerance failure) is
retained as a valid ComparisonIR with `passed=false`; malformed or mismatched sources create no
adapter outputs.

## Authority boundary and remaining external work

A successful normalization proves only that the attached bytes passed checksum, permission,
coverage, mapping, and bounded semantic gates and can be represented as strict ReferenceIR. It does
not independently observe a MIDAS/SAP execution, prove the operator used the attached model, establish
physical validation, or grant design/release authority.

Promotion still requires licensed MIDAS GEN NX and SAP2000 runs, their raw full-result exports and
model files, explicit comparison/redistribution permission, an independent operator clean replay,
and reviewed modeling decisions for any non-identity axis/release/offset/load/solver mapping.
