# He Ref: reproducible measurement checkpoints and held solver comparison

## Result

**Fixed-input comparison remains HOLD.** The original workbook was freshly downloaded and byte-verified on 2026-10-07, and the existing extractor reproduced all 2,632 ordered pairs with the previously registered derived hash. A second, independent read matched every pair. The new preparation script makes specific displacement checkpoints reproducible without sorting, fitting, zero-shifting or modifying the measured history. No solver was run and no physical error score is claimed.

Reviewed against pinned source base `01d600d07a233fa8e02d999021bfd30a90b457a8`. This four-file research-preparation slice changes no protected productization evidence and makes no solver-dispatch or publication decision.

## Sources and rights

1. He, S., Mustafa, S., Chang, Z., Liang, M., Schlangen, E., and Luković, M. (2023), [Engineering Structures 292, 116584](https://doi.org/10.1016/j.engstruct.2023.116584). [TU Delft final PDF](https://pure.tudelft.nl/ws/portalfiles/portal/155973438/1_s2.0_S0141029623009999_main.pdf), printed pp. 3–6 and 11–12; PDF has an extra repository cover page. Figures 2 and 4 were visually rechecked, not merely text-extracted.
2. Shan He, [Zenodo dataset v1, DOI 10.5281/zenodo.10082010](https://zenodo.org/records/10082010), [record API](https://zenodo.org/api/records/10082010), original `Data summary.xlsx`. Fresh API verifies one file and CC BY 4.0. Attribution, source links, [license](https://creativecommons.org/licenses/by/4.0/) and derivative method are retained here.
3. [Pinned existing source intake](https://github.com/betelgeuze-kang/Structural-Analysis/blob/01d600d07a233fa8e02d999021bfd30a90b457a8/docs/engineering/he-2023-zenodo-rc-reference-source-20260929.md) and [comparison gate](https://github.com/betelgeuze-kang/Structural-Analysis/blob/01d600d07a233fa8e02d999021bfd30a90b457a8/docs/engineering/rc-experimental-physical-validation-gate-20260929.md). Their previously inspected response is not blind evidence.

The original workbook SHA-256 is `96503244fcb5bdebd461a572e8252ce3f39d8b6f9888829fe877e2efcf09c89a`; size 276,386 bytes. Derived ordered JSONL SHA-256 is `f7dc12eb93be7bb22812e502cf6fb1802f9105c657ab2032c8cc1ce4e7673126`. This PDF retrieval is 25,742,495 bytes, SHA-256 `28bd177188410573c0d89347e9a616a868c381007f792808384e4d05a756db7b`; dynamic PDF byte differences previously documented remain relevant. Original files and experimental rows stay outside the proposed repository additions. No Chen article artwork is copied: dataset licensing cannot override separate article restrictions.

## Input-to-observable crosswalk

| Item | Source-backed fact | Required mapping or remaining uncertainty |
|---|---|---|
| Specimen | Conventional `Ref`, one beam, no SHCC layer | Other workbook sheets are different hybrid specimens, not repeats |
| Geometry | Section 2.1/Fig. 2: length 1900, width 150, depth 200 mm | Use metres in the fiber element; nominal drawing dimensions are not as-built survey data |
| Stations | Fig. 2 chain 200+500+500+500+200 mm | Left-end datum: supports 200/1700, noses 700/1200, midpoint 950 mm; exact stations must remain in any mesh |
| Longitudinal steel | Three bottom and two top 8 mm ribbed bars | Areas 150.796 and 100.531 mm² respectively; bar centroid depths unresolved |
| Cover | Section 2.1 calls 31 mm clear cover; Fig. 2 dimension terminates at the bar line | Cases: centroid 31; clear to longitudinal bar gives 35; clear to an 8 mm stirrup gives 43 mm. No case is promoted to as-built truth |
| Reinforcement ratio clue | Paper reports 0.61% | If ratio is As/(b*d), d=165 gives 0.6093%; d=169 gives 0.5949%; d=157 gives 0.6403%. This favors the 35 mm centroid interpretation but neither defines the ratio convention nor resolves the contradictory drawing |
| Stirrups | 8 mm at 150 mm in shear spans | Their presence supports intended flexural failure, not a validated shear/bond model or measured confinement law |
| Force channel | `Ref beam!C3:C4` is Load/kN; Fig. 4 shows actuator and spreader | Neither inspected record identifies whether values are actuator total or one nose. Conditional mapping: total case = sum incremental vertical reactions; per-nose case = half that sum for symmetric equal noses. A factor of two must remain unresolved |
| Displacement channel | `B2:B4`: LVDT results / Deflection / mm; §2.3 midpoint relative to supports | Proposed down-positive observable: −1000[v(950)−(v(200)+v(1700))/2], with v in m. Physical reference-frame compliance, initial datum and tare remain unknown; actuator travel is not this observable |
| History | Original rows B5:C2636, including 74 downward displacement increments | Retain ordering, raw zero and negative readings. 0.01 mm/s is actuator control rate, not an inferred sample period |
| Concrete | §2.2 describes 150 mm cubes; Ref cast in concrete phase; §3.1 gives 47.5 MPa; Table 3 gives 47.9±2.0 MPa | No specimen-linked cube roster, resolution of discrepancy or justified cube-to-fiber-law transformation. The ±2.0 is not treated as a confidence interval |
| Elastic/tensile properties | §4.2 explicitly says concrete modulus/tensile strength were not directly tested | Table 5's 32 GPa / 4 MPa / 70 MPa are lattice inputs, with inverse identification discussed in §4.2. In particular, 70 MPa is not a replacement for measured cube strength |
| Steel law | §4.2/Table 5: simulated B500, 500/550 MPa and 200 GPa; 4.5% assumed ultimate strain | Model/nominal inputs, not measured specimen coupons. Do not treat ultimate stress as an alternative measured yield stress |
| Supports | Fig. 2 two support symbols; Fig. 4 apparatus photograph | No quantitative friction, axial restraint, bearing, self-weight/tare or support-motion uncertainty supplied. An ideal pin/roller case is conditional only |
| Mechanisms | §3.2 reports flexural cracking/yielding and compression-zone failure | Current axial-curvature fiber element does not establish shear deformation, bond-slip or local bearing. Paper's lattice model explicitly contains rebar-concrete interface behavior |

No source search located a correction or acquisition-channel supplement resolving these indispensable inputs. That is a bounded search result, not proof that none exists. No author was contacted.

## Frozen pre-solve comparison criteria

The machine-readable plan `benchmarks/rc_fiber/he_2023_ref_comparison_plan.v1.json` freezes checkpoint positions, transformations, diagnostics, failure accounting and a bounded conditional sensitivity matrix before any solver result. Only extraction and checkpoint interpolation are implemented and tested here; solver scoring, physical acceptance and the sensitivity runs remain plan-only. Since the experimental curve was already seen, this is a retrospective development plan, never blind validation.

The preparer takes the first upward crossing of each target along adjacent original rows and linearly interpolates only within that pair. It records all upward crossings and source rows. No sorting, smoothing, extrapolation, offset correction or force rescaling occurs. This derived statistic does not reconstruct unloading loops.

Fresh measured-channel checkpoints (kN, rounded for display):

| Deflection mm | Channel kN | Deflection mm | Channel kN |
|---:|---:|---:|---:|
| 0.05 | 2.944 | 2 | 24.428 |
| 0.10 | 5.439 | 3 | 31.206 |
| 0.15 | 7.132 | 5 | 44.331 |
| 0.20 | 9.043 | 10 | 53.045 |
| 0.50 | 14.584 | 20 | 57.911 |
| 1.00 | 18.272 | 28 | 51.200 |

The operational early secant between 0.05 and 0.15 mm is **41.886 channel-kN/mm**. It is not a concrete modulus, proof of an uncracked region, or solver accuracy. Seating/cracking may affect it. All listed targets had one upward crossing; the full history still contains 74 reversals.

After mapping resolution and dispatch approval, compare early secant, signed/absolute checkpoint load errors, RMSE and maximum discrepancy on the 0.05–10 mm diagnostic grid, and base/refined increment sensitivity. Base grid has 102 targets (0.1 mm steps plus 0.05/0.15); refined grid has 200 targets at 0.05 mm steps. Both stay under 255, and neither claims to replay the raw reversing history. The 10 mm limit bounds a research diagnostic, not an independently established elastic/flexural validity range. Larger-displacement measurements remain visible but unsupported by this proposed run.

Numerical screen: maximum base/refined load difference divided by measured diagnostic load range ≤2%, an explicitly analyst-selected research criterion. **Physical PASS is unavailable** until measurement uncertainty and intended-use acceptance tolerances are justified. Every attempted target/case remains in coverage and failure denominators; missing or failed predictions cannot be bridged, discarded or scored as zero error. Mesh/section resolution, executable identity, constitutive law, tolerances, reaction units and inputs must be separately pinned before dispatch.

## Precisely bounded next step

Conditional matrix: 3 centroid interpretations × 4 cube-statistic values (45.9, 47.5, 47.9, 49.9 MPa) × base/refined paths = at most 24 solver runs; two alternative force-channel interpretations produce at most 48 diagnostic mappings without choosing the better fit. This is not a statistical uncertainty envelope. The geometric effective depths span 157–169 mm versus 165 mm, a −4.85% to +2.42% change in depth alone; that is not a corresponding capacity prediction. Force convention alone changes inferred total load by 100%.

Steel coupons, concrete constitutive conversion/tension law, top-bar coordinates, support restraint/friction, zero/tare and omitted-mechanism adequacy lack defensible bounds. Therefore this matrix is **NOT executable yet**. These unknowns cannot be replaced with convenient defaults or calibrated against the same curve. The smallest useful unblock is an attributable source defining the force channel and reinforcement datum, plus a defensible specimen-material/support/model boundary. Without it, preserve HOLD and deliver this measurement packet rather than manufacture a solver comparison.

Chen `CM-C` stays separately held for its additional units, LVDT/preload, stations, centroids and material gaps. It is not used to inflate the He specimen count or cross-validation claim.

## Reproduction and tests

Run the existing pinned extractor against fresh original workbook/API bytes. Then run `prepare_he_ref_comparison.py --measurements measurements/measurements.jsonl --plan benchmarks/rc_fiber/he_2023_ref_comparison_plan.v1.json --output measured-checkpoints.json`. Output uses exclusive creation to avoid silently overwriting a frozen packet.

Existing source extractor: 6 tests passed against exact pinned GitHub bytes. Eight new preparation tests cover reversals/multiple crossings, exact endpoints/plateaus, no extrapolation/sorting, wrong measurement bytes, successful preparation, rejected non-HOLD/authorized plans and exclusive output creation. Successful-path unit tests use a clearly synthetic fixture with a test-only digest override; production retains the real pinned digest. Separately, real-file preparation reproduced the recorded checkpoint output, and an independent openpyxl read matched all 2,632 original numeric pairs. These verify data handling only; scoring is not implemented, and these are not solver or physical-validation passes.
