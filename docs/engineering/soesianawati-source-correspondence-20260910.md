# Soesianawati cohort: identify data before using the accompanying drawing

Follow-up: [NIST specimen table and force conventions](soesianawati-nist-correspondence-20260910.md)
now support No. 1-specific hoop details and the equivalent-cantilever mapping.
The original 1986 full text and complete physical model reconstruction remain open.

A source review identifies a flexure-classified PEER cohort and establishes the
numerical relationship between an existing public calibration example and one
of its histories. It also finds a specimen mismatch between that example's
response data/axial load and its detailed reinforcement illustration. This is
source intake and correspondence evidence, not an admitted training corpus,
calibrated model or independent physical validation.

## Original histories and experiment identity

The PEER XML/HTML records and their linked University of Washington histories
are retrieved for specimens [1](https://nisee.berkeley.edu/spd/servlet/display?format=html&id=7),
[2](https://nisee.berkeley.edu/spd/servlet/display?format=html&id=8),
[3](https://nisee.berkeley.edu/spd/servlet/display?format=html&id=9) and
[4](https://nisee.berkeley.edu/spd/servlet/display?format=html&id=10).
All four are classified `Flexure`, have a 400 mm square section, 1,600 mm
inflection/measured length, double-ended configuration and 12 longitudinal
16 mm bars. They belong to the same 1986 Soesianawati/Park/Priestley campaign,
not four independent projects.

| PEER ID / specimen | Original pairs | Concrete MPa | Axial kN | Close tie diameter / spacing mm |
| --- | ---: | ---: | ---: | ---: |
| 7 / No. 1 | 744 | 46.5 | 744 | 7 / 85 |
| 8 / No. 2 | 695 | 44 | 2,112 | 8 / 78 |
| 9 / No. 3 | 508 | 44 | 2,112 | 7 / 91 |
| 10 / No. 4 | 613 | 40 | 1,920 | 6 / 94 |

The existing decoder preserves all **2,560 pairs**. A separate Decimal/Fraction
calculation checks every original pair and mm-to-m conversion. These files have
no separately measured axial channel; the table's axial loads remain metadata.
The original 208-page Report 86-10 was not retrieved in this pass. The two
illustrations below are copies distributed with the SimCenter example, not a
newly authenticated copy of the full report.

## The 548-pair example is a subset of No. 1

The [SimCenter calibration example](https://nheri-simcenter.github.io/quoFEM-Documentation/common/user_manual/examples/desktop/qfem-0034/README.html)
provides [displacements](https://github.com/NHERI-SimCenter/quoFEM/blob/c5b184f6a7e622661166fd4840f573e03087d360/Examples/qfem-0034/src/experimentDisp.csv)
and [forces](https://github.com/NHERI-SimCenter/quoFEM/blob/c5b184f6a7e622661166fd4840f573e03087d360/Examples/qfem-0034/src/experimentForce.csv).
The repository is pinned to `c5b184f6a7e622661166fd4840f573e03087d360` before
fetching files. The 548 synchronized pairs are a strict, order-preserving
subsequence of PEER No. 1's 744 pairs:

- Selected zero-based source indices are `0`, then `42` through `588` inclusive.
- Unselected ranges are `1..41` and `589..743`: 196 pairs in total.
- All force values agree exactly as decimal kN values.
- Maximum displacement difference after mm-to-m conversion is `1e-17 m`.
  The explicit matching bound is `1e-12 m`; no interpolation, reordering or
  force adjustment is used.

The initial unordered comparison is followed by a separate monotone-index audit;
matching individual channel values alone is insufficient to establish a paired
history relationship. The full index mapping is retained. This numerical
relationship does not authenticate the upstream chain of custody or establish
why the subset was selected. In particular, the reduced file is not a complete
copy of the 744-point experiment.

The force CSV is one row with a trailing empty field. An initial naive decimal
probe rejected that terminator; the audit explicitly verifies and removes only
that empty CSV field. It does not drop a measured row or fill a missing value.

## The detailed reinforcement picture identifies No. 4

Both downloaded figures are visually inspected. The
[configuration drawing](https://github.com/NHERI-SimCenter/quoFEM/blob/c5b184f6a7e622661166fd4840f573e03087d360/Examples/qfem-0034/figures/column_configuration.png)
shows a double-ended specimen, 1,600 mm on either side of the central stub and
3,900 mm overall length. A 1,600 mm equivalent cantilever therefore requires a
reviewed mapping of applied force, displacement and moment; it is not the full
physical specimen's length.

The right-hand detail in the
[reinforcement image](https://github.com/NHERI-SimCenter/quoFEM/blob/c5b184f6a7e622661166fd4840f573e03087d360/Examples/qfem-0034/figures/column_reinforcement.png)
is explicitly labeled `UNIT 4`: R6 ties at 94 mm in the potential hinge region,
186 mm elsewhere and axial ratio 0.3. The shared section sketch shows 400 mm,
12 HD16 and 13 mm cover. The specimen-specific tie detail matches PEER No. 4,
whereas the example's 744 kN axial load matches No. 1 and all 548 response pairs
match No. 1. The illustration may provide campaign context; it must not silently
supply No. 1's tie arrangement or confinement parameters.

## Consequences for model and learning work

Static inspection of the [example model](https://github.com/NHERI-SimCenter/quoFEM/blob/c5b184f6a7e622661166fd4840f573e03087d360/Examples/qfem-0034/src/ColumnModel.py)
finds an elastic member, a Hysteretic rotational spring, PDelta transformation,
744 kN preload and 20 numerical substeps per supplied displacement. Its fitted
hinge parameters are not measured concrete/steel constitutive parameters for the
current distributed-fiber element. No downloaded Python code was imported or run.
The source's measured-displacement replay also must not be labeled the original
actuator command sequence.

No. 1 is a better mechanism-screening candidate than the previously reviewed
shear-dominated U3, but `Flexure` does not establish model adequacy across crushing,
spalling, bar buckling and fracture. Original No. 1 metadata records such damage;
the complete measured history reaches about 98 mm, while the example subset
reaches about 78 mm. The current element's omitted mechanisms, constant-load
geometry/force mapping, tie detail, material calibration and damage interval need
explicit review. Truncating a history to get a fit would require its own declared
scope and cannot establish full-history validation.

The full PEER history and the SimCenter subset must remain in one campaign
partition. The current exact whole-trajectory content screen does not generally
detect row deletion combined with floating-point serialization; the established
lineage must be retained when assigning IDs. Distinct source URLs and point counts
are not independent evidence. No calibration/training/evaluation split is assigned
here, and no external sample enters the running authored-data experiment.

The repository [license](https://github.com/NHERI-SimCenter/quoFEM/blob/c5b184f6a7e622661166fd4840f573e03087d360/LICENSE)
is retained. PEER's copyright fields are empty. This review does not establish a
source-specific experimental-data redistribution grant from those observations;
raw data and copied drawings are kept in the local source packet.

## Retained evidence

The sealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-soesianawati-intake-4wobdfzh`:
**35 files / 1,261,380 bytes**, inventory SHA-256
`c69e062ac70ae8a674b52ab7ff72a16508772689d0e0d4e0f66352a565481e30`.
It retains upstream commit metadata, fetch outcomes/hashes, CSV/XML/HTML/history
originals, figures, license, audit scripts, the index mapping and the current
Git-bound decoder source. All files are reread at sealing. Do not append to it.

The [machine summary](soesianawati-source-correspondence-20260910.summary.json)
records the counts, numerical matches, visual findings and unresolved boundaries.
The all-source comparison takes 12.883088244 s and the ordered alignment
0.005352007 s; these exclude fetches, visual review and coordination. There are
zero new structural solves, material integrations or training fits. The ongoing
runtime worker shares the host; no isolated timing claim is made.
