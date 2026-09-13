# Positional ACI reader and source-specific test conventions

Source `ce2d539b536c756822398231b4890ee8d3f0629c` adds
`structural_analysis.io.aci_column_archive`. The reader accepts hash-bound original
bytes in the [acquired archive layout](aci-archive-table-intake-20260913.md), with
fixed positional headers, a separate opaque descriptor row, `DATASTART`, unique
positive record IDs and the original empty trailing field. Repeated column names
never become dictionary keys. Altered headers, widths, markers or duplicate IDs
reject; unknown descriptor semantics are not repaired by shifting columns.

Raw strings, quoted line breaks and decimal spellings remain intact. Explicit
positional numeric lookup preserves source precision and signed zero,
while empty, textual, nonfinite or unrepresentable numeric tokens reject instead
of becoming zero. Numeric magnitude alone does not establish units, observed
physical zero or the meaning of an unachieved endpoint. The reader exposes
`descriptor_alignment_verified=false` and `training_admission_granted=false`.
It does not construct a canonical model or enter a learning partition.

## Actual source-byte check

All **19,234 data cells** across 326 records and all **118 header/descriptor cells**
match a separate raw CSV read. All **17,278 numeric tokens** match exact Decimal
parsing, without unit conversion. Both reads use Python's standard CSV parser;
this is consistency of the captured source, not independent parser qualification.
The source module matches its committed Git blob before and after the check.
One decoder interval is 4,782,045 ns; whole-process time was not recorded and no
speedup claim is made. No structural solve or fit was invoked.

The new reader and workflow contracts pass **38 tests in 1.92 s**. They cover
duplicate labels with different bar values, embedded reference newlines, opaque
misaligned descriptors, same specimen names under different records, exact
decimals, signed zero, malformed/rehashed layouts and byte-hash mismatch.
One-file mypy, Ruff/format and diff checks pass. The development workflow now
selects 42 modules; these local results do not qualify a new hosted run.

## The accompanying thesis resolves some definitions, not the export shift

The publisher-linked archive provides Balaji Sivaramakrishnan's 2010 UT Austin
thesis, *Non-Linear Modeling Parameters for Reinforced Concrete Columns Subjected
to Seismic Loads*. The acquired PDF is 8,361,854 bytes, SHA-256
`f0d40c7f62680f7fcd2d2f35ea91e0f9069cf1cbacfc5eb4c774195e17e4a821`.
PDF pages 34–36 (printed 20–22) were rendered and visually inspected.

Table 3.1 assigns configuration codes 1, 2 and 3 to single cantilever, double
cantilever and double curvature. Figure 3.1 distinguishes database force and
displacement from full-rig quantities: double-cantilever shear is half the applied
rig load, and the double-curvature sketch labels full relative displacement as
twice the database displacement. The text defines database column length as the
actual clear specimen length, rather than PEER's equivalent cantilever length.
These distinctions must be retained when reconstructing loads, coordinates and
comparison channels; no universal factor is applied to the original samples here.

The same pages describe constant axial loading and mixed origins for response
curves, including researcher-provided and digitized observations. A table row
does not identify which provenance applies to its curve. The thesis text describes
319 rectangular cases, while the acquired CSV has 326. Its version relationship
and specimen-level original-source definitions still require review.

The raw configuration token counts are 120 for `1`, 104 for `2`, and 102 for `3`.
Those are metadata counts, not counts of compatible or independent validation
models. First reconstruction should require the original setup/material/steel
detail and an explicit source-to-model force/displacement mapping. Selecting a
single-cantilever label alone cannot establish a valid material or failure model.

## Evidence boundary

The [machine summary](aci-positional-reader-20260913.summary.json) identifies the
new sealed packet, source references, exact source checks and reviewed pages.
The earlier CSV packet is unchanged. Raw third-party PDF and rendered pages stay
outside Git. This thesis is a database compilation, not a replacement original
test report. Source reuse terms, descriptor alignment, version correspondence,
physical model adequacy and independent evaluation remain unresolved. No public
measured training rows were admitted by this change.
