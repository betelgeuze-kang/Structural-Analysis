# Original PEER source intake: 253 property records and one measured history

Implementation `e1a9a003a0002c3200bae14d5e225a7b10de9c97` adds explicit PEER
rectangular-table and force-displacement readers in
`structural_analysis.io.peer_structural_performance`. They preserve source bytes'
hashes, all ordered cells, repeated observations and decimal values. They do not
create canonical solver models or grant training/physics/licensing admission.

The [original rectangular property table](https://nisee.berkeley.edu/spd/rectangular_properties.txt)
contains **253 records with 44 fields each**. All **11,132 cells** compare exactly
against the original TSV reader in the source audit. Three labels occur twice:
intermediate bar count, hoop set count and hoop spacing. The importer uses the
declared position and a distinct semantic key for each direction/spacing region;
it never collapses them into a dictionary keyed only by the printed header.
Header/row changes and duplicate source record numbers are rejected. Empty and
declared missing tokens remain distinct from a reported numeric zero.

The [publisher's format description](https://nisee.berkeley.edu/spd/about.html)
defines the observed displacement in mm and lateral load in kN, using an equivalent
cantilever representation even when the original test geometry differs. The
reader preserves the full declared pair count and original numeric tokens. Its
mm-to-m conversion changes the decimal exponent without rounding under a caller's
low-precision Decimal context. It does not center the origin, sort, smooth, trim,
resample or reinterpret sensor samples as commanded loading targets.

## Original specimen inspection

The first named candidate is [PEER-SPD-104, Saatcioglu and Ozcebe 1989, U1](https://nisee.berkeley.edu/spd/servlet/display?format=html&id=104).
The original record links its [measured force-displacement file](http://depts.washington.edu/columdat/rectcol/txfiles/saatu1.txt),
which was fetched successfully with **1,751 pairs**. Every original numeric token
and every decimal pair passes a separate audit. The initial 0 mm / 0.0005 kN
observation remains unchanged. The observed ranges are -58.9 to 84 mm and -251.3
to 276.2 kN. There are 47 sampled increment-sign changes; these have not been
verified as the original commanded loading reversals.

Eight property values and their units agree between the table and the original
XML. The record reports a 350-by-350 mm section, 1,000 mm equivalent cantilever
length, zero axial load, 43.6 MPa concrete strength, 430 MPa corner-bar yield
stress, eight longitudinal bars and 25 mm corner-bar diameter. Its P-delta code
denotes provided shear. These are reported source properties, not independently
verified constitutive inputs or a completed analytical model.

An unresolved source conflict is retained: the wide-spacing hoop diameter is
**0 in the TSV and XML, but 10 mm in HTML**. The source also reports zero ultimate
strength in three steel fields and leaves the XML copyright field blank. Zero
axial load, zero material strength and missing reuse information are not given
the same interpretation. None is silently replaced with a convenient default.

A metadata-only screen for cantilever configuration, reported flexural failure,
zero splice length and zero axial load finds seven source record numbers:
104, 181, 182, 196, 201, 203 and 206. They are candidates for original-report
inspection, not seven admitted training or independent-validation cases.

The original paper/drawing, material response parameters, source-specific reuse
basis, conflict resolution, original commanded loading protocol and compatible
model physics remain to be verified. Campaign-level deduplication and frozen
train/calibration/evaluation splits must precede fitting. No externally measured
curve or source property has entered the currently frozen learning repetitions.

## Validation and retained evidence

Focused source-intake checks pass **12 tests in 1.56 s** after an initial 12-test
pass in 1.61 s. They cover duplicate label preservation, missing versus zero,
source identity, altered layouts, repeated/reversing measured observations,
nonzero measured origin, exact unit conversion and corrupt counts/numbers.
Ruff, format and diff checks pass. The one-file mypy check passes after replacing
an unsafe Decimal-exponent type assumption with an explicit finite exponent guard.

The actual source audit exits zero and performs no Newton solve, fit, material
integration, model compilation or commit. Its internal wall time is
0.015637913 s; full parent elapsed time was not recorded. Its first attempt
incorrectly expected the TSV wide-spacing diameter to be 10. Inspection showed
TSV/XML both report zero; correcting that harness expectation retains the HTML
conflict. Both attempt sources and the failed log are preserved. No original
data value or numerical acceptance gate was changed.

Raw external files remain outside Git in
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-public-intake.b74grmgi`.
The source bundle contains **20 files / 166,739 bytes**, all reread exactly after
the fetches and audit completed. Inventory SHA-256:
`55ea2cc927574e49cb8896a15cd8bb88ca9512e520242d737fcb7a7ebf815e14`.
The parser hash is also checked against its committed Git blob. Fetch URLs,
HTTP outcomes, file hashes, failed attempts and the [machine summary](peer-spd-source-intake-20260909.summary.json)
are retained. Checksums establish consistency of captured bytes, not source
authentication or permission to reuse them. This is completed data intake;
external training and independent physical validation remain unadmitted.


## Optional axial-channel extension

The [subsequent format extension](peer-spd-axial-intake-20260909.md) supports the
manual-defined third axial-load column while preserving all original U1 and
property-table results. Twenty tests pass; actual three-column specimen auditing
and external training admission remain open. The original packet above is unchanged.
