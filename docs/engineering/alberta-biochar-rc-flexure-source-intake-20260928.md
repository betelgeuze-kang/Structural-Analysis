# Alberta biochar RC flexural beams: source and channel intake

This is a read-only source intake, **not** an admitted training set or independent physical validation. No measured row, source workbook, drawing, or fitted parameter is stored in this repository. The three screened beams belong to one experimental program; their time samples are not independent structures or project-level holdouts.

## Sources, access, and rights

The [Mendeley Data version 1 record](https://data.mendeley.com/datasets/znhx7sg9pk/1), DOI [`10.17632/znhx7sg9pk.1`](https://doi.org/10.17632/znhx7sg9pk.1), attributes the 2025 University of Alberta beam tests to Hafiz Asher Muhammad and Douglas Tomlinson and labels the **dataset CC BY 4.0**. Its ordinary public “Download All” URL returned a ZIP on 2026-09-28; the first file preview had failed, so preview availability must not be confused with file access. The published ZIP has 10 entries: nine raw XLS beam files and one crack-width PDF. Its downloaded size is `1,733,666` bytes, SHA-256 `a45ce44f255dd421734d151627fa144ccd668762c74a88998653b563986268ff`; every ZIP entry passed CRC verification. The archive and extracted files remain outside the repository.

The [institutional thesis record](https://ualberta.scholaris.ca/items/eccb2570-5776-45c7-b133-06de18676bd2), DOI [`10.7939/83345`](https://doi.org/10.7939/83345), provides test-method context. Its repository metadata says nine `2000 × 300 × 200 mm` beams underwent four-point bending: three steel-reinforced and three GFRP-reinforced beams were detailed for flexural failure; three steel beams without stirrups were detailed for shear. The thesis text maps `SF` to steel longitudinal bars **with stirrups**, `GF` to GFRP longitudinal bars with steel stirrups, `SS` to steel bars without stirrups, and `0B`/`4B`/`6B` to control/4%/6% biochar concrete. The thesis identifies `SF-0B` as the control plotted against the other series. The institutional record permits access but states that thesis copying/reproduction beyond noncommercial purposes requires the copyright owner's consent. That thesis condition is distinct from the Mendeley dataset's CC BY 4.0 license; it does not authorize copying thesis drawings or text into a training corpus.

## Original-file checks and observed channels

The three `SF` XLS files were read directly from the published ZIP with a legacy-XLS reader. Their OLE signatures, one-sheet `Sheet1` layout, complete numeric rows, and source hashes were inspected. A temporary office-format conversion retained every sheet dimension and text field; numeric cells differed from the original by at most `5.3 × 10⁻¹²` in their recorded units. The counts below are from the **original XLS bytes**. Only `SF-0B` has a separately observed publisher file-page SHA-256, and it matches the downloaded bytes. The other hashes are calculated from the same CRC-valid published ZIP, not independently matched to a publisher checksum.

| Original specimen file | SHA-256 | Numeric rows, Excel rows | Time span |
| --- | --- | --- | --- |
| `SF-0B Raw (MTS_LVDT_Strain Gauge Data.xls` | `ef18b22d938103856c89af4ebe1224c899701e187d7c10d102d73583a651a489` | 2,144, rows 50–2,193 | 0–2,143 s |
| `SF-4B Raw (MTS_LVDT_SG Data).XLS` | `47ad62d04f75a3e35151afef6a501da4f93bb6fdd2833e6dfd6606eac8e6d401` | 1,877, rows 50–1,926 | 0–1,876 s |
| `SF-6B Raw ( MTS_LVDT_SG Data).XLS` | `e9180acfac24e9d95b27cff9eba500a0b4810183efb8ce67fda8e760728d81c9` | 1,996, rows 50–2,045 | 0–1,995 s |

Each original sheet has 11 channels. Row 2 gives the channel names, row 3 the units, and subsequent metadata identifies sensors and a nominal `1000.00 ms (1 Hz)` sampling interval. All 11 values are finite numbers in every listed data row, with no missing value; the time column increases at approximately 1 s per record. This establishes the presence of ordered raw histories, not their suitability as solver targets.

| Channels | Workbook units and source role |
| --- | --- |
| `Time  1 - default sample rate` | Seconds; recorded sample sequence. |
| `MTS_6000_Force`, `MTS_6000_Displacement` | kN and mm; test-machine channels. |
| `Under_Beam_East`, `Under_Beam_West`, `Under_Beam_Middle` | mm; metadata labels these sensors as cable potentiometers. |
| `SG_01`, `SG_02` | µm/m; strain-gauge channels. |
| `LP_East`, `LP_West` | mm; metadata labels these as linear potentiometers. |
| `Load Total` | kN; an **online computation** channel, not another independent load cell. Its metadata states `MTS_6000_Force - 2.5399`, and that equality holds for every checked SF row. |

The XLS filenames mention “LVDT,” and the [dataset description](https://data.mendeley.com/datasets/znhx7sg9pk/1) says LVDTs were calibrated. The sheet does **not** label a channel `LVDT`; its sensor metadata instead calls the under-beam channels cable potentiometers and the `LP` channels potentiometers. The instrument positions and displacement datum must be mapped to the thesis setup before designating a measured midspan-deflection target. In particular, the first `SF-0B` `MTS_6000_Displacement` value is approximately `+24.95 mm` while the under-beam middle channel is near zero; the machine displacement cannot be treated as zeroed beam deflection without a documented transformation. Machine-force values during the main loading interval are negative. Neither their sign normalization nor the physical meaning of the constant `2.5399 kN` correction is established by the XLS header alone.

## Model correspondence still required

These are better **mechanism candidates** than the shear-designed `SS` files for the current axial–curvature Euler–Bernoulli RC element. That classification follows the thesis's design intent; it does not prove negligible shear deformation, bond slip, anchorage effects, or an accurate post-peak law. `GF` specimens also require a GFRP constitutive model and are outside the present steel-bar comparison.

The default [public RC compiler](../../src/structural_analysis/api/nonlinear_fiber_frame.py) accepts one fully fixed chain endpoint; experimental direct control also has explicit two-fixed-endpoint and v4 horizontal pin/roller-beam profiles. The v4 profile permits two distinct support stations, including interior stations, with UX/UY restrained at the pin, UY at the roller, and both rotations free. This removes the former support-type mismatch for a straight simply supported beam **as a software input boundary only**. The Alberta specimen's exact support and loading-nose stations and measured sensor datum still need source mapping, and neither the v4 synthetic test nor a fixed-endpoint replacement admits any SF row for a whole-path measured-versus-solved comparison.

Before any held-out validation or learning admission, establish from authorized primary sources: exact support and loading-nose stations and restraint freedoms; specimen-specific bar coordinates, cover, material and test-day properties; the force sign, tare, actuator-total versus each-nose load convention; sensor positions, datum, time alignment and any preload; the usable response interval and observed failure mode; and the source-specific reuse obligations. Preserve the `0B`/`4B`/`6B` specimens as one campaign when defining leakage-resistant splits. Do not use the 2,144/1,877/1,996 consecutive measurement rows as independent training cases.
