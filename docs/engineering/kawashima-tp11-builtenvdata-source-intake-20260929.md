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
| `TP-010 to 013/Documentation/disp.pdf` | 38,646 | `3d4c6821` | `0ab3083a536f2c0e859f0851c53b27bd37b03c46abdcf86c6fcaea582cf46fc6` |
| `TP-010 to 013/Documentation/force.pdf` | 35,659 | `31f4bb45` | `7c5aca7f8178b8e164a74e1eb255bd6b756901a9991bed55c25d7451541b00c4` |
| `TP-010 to 013/Experimental data/tp011.txt` | 859,735 | `7d4e9f77` | `4a0be0187313afd6cd063426c0db030199492cf7313a0a5ec31b88a7ac08db22` |

The ZIP also lists `TP-010 to 013/Experimental data/tp011.xls`; this screen
reads the TXT history and the group documentation, not the XLS values. The
documentation cites Kawashima, Shoji, and Sakakibara (2000), *A Cyclic Loading
Test for Clarifying the Plastic Hinge Length of Reinforced Concrete Piers*, as
the TP-10–13 experimental publication. That citation identifies the original
campaign; it is not a second independent dataset.
The [J-GLOBAL bibliographic record](https://jglobal.jst.go.jp/en/detail?JGLOBAL_ID=200902171365489905)
lists the Japanese-language article in *Journal of Structural Engineering A*,
46A(2), pp. 767–776 (2000). Its author record spells the first name
`Kazuhiko`, whereas BED's API spells it `Kasuhiko`; this metadata discrepancy
is preserved rather than silently normalized. The catalog record does not
provide the paper's failure-mode account or replace reading its full text.

## TP-11 source fields and response boundary

`titech03.pdf` p. 1, Table 1 labels TP-11 `TYPE-B` and reports a square
**400 × 400 mm** section, **1,450 mm effective height**, **360 mm effective
depth**, aspect ratio **4.03**, longitudinal reinforcement ratio **0.95%**, and
volumetric tie ratio **0.77%**. It reports concrete cylinder strength
**20.6 MPa**, longitudinal SD295A D13 bar yield strength **367 MPa**,
transverse SD295 D6 bar yield strength **376 MPa**, and applied axial force
**160 kN**. The reported effective height is retained as named; it has not been
silently equated with a solver element length, actuator height, or gauge datum.
Figure 1(b) on p. 3 marks the lateral-load point 1,450 mm above the footing
top and the specimen top 1,850 mm above it. Figure 2(b) on p. 5 depicts 12
perimeter D13 longitudinal bars at three 105 mm intervals along each side of
the 315 mm inner dimension. This drawing narrows the geometry crosswalk but
does not by itself establish bar-centroid cover or the solver's boundary
conditions. The repeated-displacement protocol for TP-11 is shown on p. 7.

The PDF's p. 2, Table 3 maps `CH001` to lateral load, `CH002` to lateral
displacement, `CH003` to vertical load, `CH006` to footing sliding, and
`CH007`/`CH008` to footing rotation. It identifies the `Displacement (mm)` and
`Force (kN)` columns as values obtained from its equations (B-2) and (A-2),
respectively. These source-computed columns must not be relabeled as untouched
instrument channels or commanded displacement targets without a sensor and
correction crosswalk.

The separate one-page Appendix B (`disp.pdf`) explicitly defines the specimen
displacement at the load point as `u_P = u - (u_Fs + u_Fr)`: measured lateral
displacement minus footing sliding and the displacement induced by footing
rotation. Its Eq. (B-3) computes the rotation term from two vertical footing
gauges and their spacing. Appendix A (`force.pdf`) defines the reported lateral
force at the load-point height as the horizontal actuator force plus corrections
for horizontal and vertical components of the vertical actuator force, including
its rotation and lever arm (Eq. A-2 through A-6). The appendices establish the
meaning of the corrected columns. The illustrated gauge distances and a numeric
channel crosswalk can be checked below; raw-sensor polarity and the vertical
actuator's dimensions still lack independent source confirmation. The original
PDFs remain outside Git.

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
axial-load path, but does not prove the physical correction geometry,
boundary condition, or a valid solver input sequence. The 3,553 records are
one specimen's history, not 3,553 independent structures or Newton-state labels.

## Numerical channel crosswalk: research only

The original TXT header names `CH001`–`CH008`, `Displacement (mm)`,
`Force (kN)`, and four intermediate columns: `ua Eq.(A-6)`, `theta  Eq.(A-5)`,
`VF-h Eq.(A-3)`, and `VF-v Eq.(A-4)`. The TXT header does not state units for
these intermediates; Appendix A implies mm for `ua`, radians for `theta`, and
kN for `VF-h`/`VF-v`. `titech03.pdf` p. 2, Table 3 gives kN for `CH001`
(lateral load) and `CH003` (vertical load), and mm for `CH002` (lateral
displacement), `CH005` (lateral LVDT), and `CH006`–`CH008` (footing checks).

Appendix B Eq. (B-2)–(B-3) and `titech03.pdf` p. 6, Fig. 3 give the load-point
height `h = 1450 mm` and a footing-gauge span of `250 + 400 + 250 = 900 mm`
(the 400 mm width is also in p. 1, Table 1). The following *empirical raw-TXT
arithmetic* reproduces the printed corrected displacement. Keep `U` unrounded
in all subsequent calculations:

```text
U = CH002 - CH006 - (1450 / 900) * (CH007 - CH008)    [mm]
```

All 3,553 printed `Displacement (mm)` values agree with `U` to at most
`0.000500000003 mm` (mean absolute difference `0.000249617 mm`); decimal
round-half-up to the printed `0.001 mm` matches all 3,553. For example, STEP
42 has `CH002 = 2.940`, `CH006 = 0.040`, `CH007 = 0.000`, and `CH008 =
-0.181 mm`, giving `U = 2.608388889 mm` and printed `2.608 mm`. `CH005`
does not enter this matching arithmetic; this does not establish which physical
sensor supplied the archived worksheet's `u`.

The source-derived columns themselves support the following *numeric* values
for Appendix A's otherwise undimensioned actuator distances. On 3,327 rows
with `|U| > 1 mm`, the median printed `ua / U` is `1.689656318`, consistent
with `1 + h_t / h = 2450 / 1450` and thus `h_t = 1000 mm`. The median printed
`ua / tan(theta)` is `1749.997 mm`, consistent with `h_a = 1750 mm`.
Using those inferred values, Appendix A Eq. (A-2)–(A-6) gives this numerical
reconstruction from raw TXT channels:

```text
c     = 1 + 1000 / 1450
ua    = c * U                               [mm]
theta = atan(ua / 1750)                    [radians]
VF-h  = CH003 * sin(theta)                 [kN]
VF-v  = CH003 * cos(theta)                 [kN]
P     = CH001 + c * VF-h + VF-v * ua / 1450 [kN]
```

`ua` from the unrounded `U` agrees with all 3,553 printed `ua` entries after
decimal round-half-up to `0.001 mm` (maximum absolute difference
`0.000500000003 mm`). Replacing `U` with the already rounded printed
`Displacement (mm)` matches only 2,066 entries, so retaining source-channel
precision matters. Recomputed `VF-h` and `VF-v` each round to all 3,553 printed
entries at `0.001 kN`. Recomputed `P` likewise
rounds to all 3,553 printed `Force (kN)` entries: maximum absolute difference
`0.000499961 kN`, mean absolute difference `0.000249689 kN`. At STEP 42 it
gives `ua = 4.407278 mm`, `theta = 0.002518439 rad`, and `P = 53.513882 kN`,
against printed `4.407 mm`, `0.002518`, and `53.514 kN`.

This is an arithmetic consistency check, not independent calibration of the
experiment. The `1000` and `1750 mm` distances are **inferred from the TXT's
already derived `ua`/`theta` columns**; the inspected PDFs do not dimension
`h_t` or `h_a`. The `400 mm` from lateral load point to specimen top in
`titech03.pdf` p. 3, Fig. 1-1(b) does not identify the lower actuator swivel
and must not be substituted for `h_t`. Appendix B defines footing rotation
with jack-side minus opposite-side vertical displacement; Fig. 3 places
`CH008` on the jack side and `CH007` opposite, whereas the matching raw-column
arithmetic above uses `CH007 - CH008`. The original sensor polarity and
worksheet mapping are not documented here. Appendix B also distinguishes
measured `u` (which includes footing motion) from corrected `u_P`, while
Appendix A writes `u` in Eq. (A-6). Numerically, the TXT's `ua` follows the
**unrounded corrected** `U`; the notation and physical implementation of that
choice remain unresolved. No source-computed column is reclassified as a raw
instrument observation, solver state, or independent force/displacement target.

## Model correspondence and duplicate check: HOLD

This is a **candidate** for the current planar axial–curvature RC fiber model:
the original program studied plastic hinge length in cyclic cantilever piers
and reports an axial force. It is **not yet classified as flexure-dominated**.
The archive's p. 9, Fig. 7(a) sketches cracks and shaded damage zones near the
footing at 11 yield displacements; Fig. 7(b) shows the cyclic force-displacement
loops. The visible damage is concentrated toward the footing, but this sketch
alone cannot establish a unique governing flexural mechanism or exclude shear
and anchorage effects. The original paper's failure account has not been
cross-checked. Shear deformation, reinforcement bond/anchorage slip,
confinement, bar instability, and footing sliding/rotation may matter; the
present Euler–Bernoulli axial–curvature element does not establish those
mechanisms. Bar-centroid coordinates and cover, concrete/steel constitutive
curves, independently confirmed correction geometry and sensor datums, load
application geometry, and a defensible comparison interval remain unverified.

The existing [local PEER rectangular property table](../../implementation/phase1/open_data/pbd_hinge/peer_spd/rectangular_properties.txt)
already has Takemura–Kawashima 1997 tests 1–6 at source rows 248–253,
corresponding to this BED archive's TP-001–006 group. A local text search did
not identify TP-11 in that table, but that is **not proof** that TP-11 is absent
from external PEER, ACI, or other mirrors. Crosswalk original author, year,
specimen and data-file identity before counting a new independent campaign.

**Decision: HOLD for learning and physical validation.** Next review the
original report's failure account, independent channel-sign and actuator
geometry confirmation, footing-motion channels, exact reinforcement placement
and materials, and archive/mirror lineage. Freeze campaign-level training and
evaluation roles before fitting; measured load–displacement pairs do not provide
accepted equilibrium states or a learned warm-start speedup claim.
