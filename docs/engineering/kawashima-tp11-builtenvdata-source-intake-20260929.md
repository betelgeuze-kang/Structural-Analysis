# Kawashima TP-11 cyclic RC pier: public-source discovery

This 2026-09-29 intake records one candidate original experiment for later RC
model-correspondence review. **Training rows admitted: 0; locked physical
validation specimens: 0; solver runs or fits: 0.** No source measurement,
drawing, paper, or fitted parameter is committed in this repository.

## Publisher, rights, and original files

The [Built Environment Data (BED) record](https://experiments.builtenvdata.eu/datasets/45/),
DOI [10.60756/titech-vbtz37h429](https://doi.org/10.60756/titech-vbtz37h429),
credits Kasuhiko Kawashima's Tokyo Institute of Technology experimental campaign.
The [publisher API record](https://experiments.builtenvdata.eu/api/v1/datasets/45/)
identifies dataset 45, its ZIP filename, the 1996–2000 experiment period, and
**CC BY 4.0** for the dataset. Retain creator, dataset DOI, version, the
[license link](https://creativecommons.org/licenses/by/4.0/), and any derivation
when reusing data. The cited journal papers have separate publication rights;
the dataset license is not treated as a license for their text or figures.

The publisher's [public ZIP endpoint](https://experiments.builtenvdata.eu/api/v1/datasets/45/download/?filename=Kawashima-RC-Tests.zip)
returned a `200` response header and, after a local storage interruption, a
resumed `206` response with the same
`ETag: "66d84923-bfbf605"` and `Last-Modified: 2024-09-04 11:48:51 GMT`.
The completed file has **201,061,893 bytes** and locally computed SHA-256
`914f7e1100838d1e8b54672472cf1be85cbf66ef725e81c50fc22892f4de8724`.
All **584 ZIP members** passed the archive's CRC test. BED did not publish a
cryptographic checksum in the inspected API response, so this hash identifies
the acquired bytes and does not independently authenticate them against a
publisher-signed digest. The original ZIP remains outside Git at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-kawashima-tp11-source-20260929/Kawashima-RC-Tests.zip`.

| Original ZIP member, under `Kawashima-RC-Tests/` | Bytes | ZIP CRC-32 | Local SHA-256 |
| --- | ---: | --- | --- |
| `TP-010 to 013/Documentation/titech03.pdf` | 805,438 | `f9a2c39c` | `65e5840f47eea6178ae6c9672dfbfebbcedfb3854069653d527ee36cb3420617` |
| `TP-010 to 013/Experimental data/tp011.txt` | 859,735 | `7d4e9f77` | `4a0be0187313afd6cd063426c0db030199492cf7313a0a5ec31b88a7ac08db22` |

The ZIP also lists `TP-010 to 013/Experimental data/tp011.xls`; this screen
reads the TXT history and the group documentation, not the XLS values. The
documentation cites Kawashima, Shoji, and Sakakibara (2000), *A Cyclic Loading
Test for Clarifying the Plastic Hinge Length of Reinforced Concrete Piers*, as
the TP-10–13 experimental publication. That citation identifies the original
campaign; it is not a second independent dataset.

## TP-11 source fields and response boundary

`titech03.pdf` p. 1, Table 1 labels TP-11 `TYPE-B` and reports a square
**400 × 400 mm** section, **1,450 mm effective height**, **360 mm effective
depth**, aspect ratio **4.03**, longitudinal reinforcement ratio **0.95%**, and
volumetric tie ratio **0.77%**. It reports concrete cylinder strength
**20.6 MPa**, longitudinal SD295A D13 bar yield strength **367 MPa**,
transverse SD295 D6 bar yield strength **376 MPa**, and applied axial force
**160 kN**. The reported effective height is retained as named; it has not been
silently equated with a solver element length, actuator height, or gauge datum.
The drawing and cross-section are on pp. 3 and 5, and the repeated-displacement
protocol for TP-11 is shown on p. 7.

The PDF's p. 2, Table 3 maps `CH001` to lateral load, `CH002` to lateral
displacement, `CH003` to vertical load, `CH006` to footing sliding, and
`CH007`/`CH008` to footing rotation. It identifies the `Displacement (mm)` and
`Force (kN)` columns as values obtained from its equations (B-2) and (A-2),
respectively. These source-computed columns must not be relabeled as untouched
instrument channels or commanded displacement targets without a sensor and
correction crosswalk.

The original `tp011.txt` contains **3,553 ordered numeric records**, with
contiguous `STEP` values 1–3,553 and 32 columns per record. It additionally
contains **21 trailing empty CSV records** (14 of width 32 and seven of width
18); those are not measurements. Every selected TP-11 numeric record has a
nonblank finite `CH003`, `Displacement (mm)`, and `Force (kN)` value:

| Source column | Observed range in ordered records | Source role |
| --- | ---: | --- |
| `CH003` | 159.3 to 159.9 kN | Vertical/axial load channel per PDF Table 3 |
| `Displacement (mm)` | −62.135 to 62.080 mm | Source-computed lateral displacement |
| `Force (kN)` | −98.431 to 91.257 kN | Source-computed lateral force |

The nearly constant observed axial-load channel supports screening a fixed
axial-load path, but does not prove the exact force and displacement correction,
boundary condition, or a valid solver input sequence. The 3,553 records are
one specimen's history, not 3,553 independent structures or Newton-state labels.

## Model correspondence and duplicate check: HOLD

This is a **candidate** for the current planar axial–curvature RC fiber model:
the original program studied plastic hinge length in cyclic cantilever piers
and reports an axial force. It is **not yet classified as flexure-dominated**.
The archive's p. 9 includes TP-11 failure-mode imagery and a hysteresis plot,
but a visual damage classification and the original paper's failure account
have not been completed. Shear deformation, reinforcement bond/anchorage slip,
confinement, bar instability, and footing sliding/rotation may matter; the
present Euler–Bernoulli axial–curvature element does not establish those
mechanisms. Bar-centroid coordinates and cover, concrete/steel constitutive
curves, source correction equations, sensor datums, load application geometry,
and a defensible comparison interval remain unverified.

The existing [local PEER rectangular property table](../../implementation/phase1/open_data/pbd_hinge/peer_spd/rectangular_properties.txt)
already has Takemura–Kawashima 1997 tests 1–6 at source rows 248–253,
corresponding to this BED archive's TP-001–006 group. A local text search did
not identify TP-11 in that table, but that is **not proof** that TP-11 is absent
from external PEER, ACI, or other mirrors. Crosswalk original author, year,
specimen and data-file identity before counting a new independent campaign.

**Decision: HOLD for learning and physical validation.** Next review the TP-11
failure image and original report, source-computed channel equations and
footing-motion channels, exact reinforcement placement and materials, and
archive/mirror lineage. Freeze campaign-level training and evaluation roles
before fitting; measured load–displacement pairs do not provide accepted
equilibrium states or a learned warm-start speedup claim.
