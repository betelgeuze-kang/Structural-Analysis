# 4TU conventional RC reference beam: source-to-model quantity crosswalk

This is a **geometry and nominal-section calculation**, not an as-built takeoff, a cost comparison, an admitted training row, or a validation model. The input is the bounded [source review](4tu-shcc-rc-reference-beam-source-20260927.md), which cites the [open final paper, §2.1 and Fig. 2](https://repository.tudelft.nl/file/File_1392daf2-866f-4db3-b65d-217b901a3295). No workbook row or solver input is changed here.

| Source-observed item | Quantity or possible model mapping | Boundary |
| --- | --- | --- |
| Conventional `Reinforced Concrete` reference beam, `1900 × 150 × 200 mm` | Overall member length `1.900 m`; nominal rectangular section width `0.150 m`, depth `0.200 m` | Overall envelope, not a net concrete pour or calibrated fiber section. |
| `1500 mm` support span and `200 mm` end overhangs | If the left beam end is coordinate zero, support stations are derived as `x = 0.200, 1.700 m`. | Coordinates are a paper-geometry interpretation, not surveyed support offsets. |
| Two load positions `500 mm` apart and `500 mm` from their adjacent supports | Under the same coordinate convention, load stations are derived as `x = 0.700, 1.200 m`. | The plotted `Load` total-versus-per-nose convention remains unresolved. |
| `3-Φ8` ribbed bottom bars; `2-Φ8` ribbed top bars | Five nominal longitudinal bars. A circular `8 mm` nominal diameter gives one bar area `16π = 50.265482 mm²`; bottom `48π = 150.796447 mm²`; top `32π = 100.530965 mm²`; combined `80π = 251.327412 mm²`. | Count and diameter do not fix bar centroids, cover, development, bends, laps, or actual cut lengths. The linked conference paper's approximate reinforcement ratio is not independently reconstructed here. |
| `Φ8@150` stirrups in both shear spans | Nominal stirrup bar area is also `50.265482 mm²` per leg; each shear span is `500 mm` by the stated support/load layout. | Neither the first/last stirrup station, exact count, closed shape, hooks, cover, nor cut length is established by the reviewed text. Do not multiply spacing into an actual stirrup quantity. |

Independent arithmetic from the observed rectangular envelope gives gross cross-section `150 × 200 = 30,000 mm²` and **gross envelope volume** `1900 × 150 × 200 = 57,000,000 mm³ = 0.057000 m³`. This is a dimensional reference for a possible model section and full beam length; it has no deductions for bars, voids, construction tolerance, or waste.

For a **strictly illustrative straight-bar assumption**, if all five longitudinal bars were exactly `1900 mm` long, with no bends, hooks, laps, anchorage extensions, or end cover allowance, their combined nominal length would be `5 × 1.900 = 9.500 m` and nominal cylindrical volume would be `251.327412 mm² × 1900 mm = 0.000477522083 m³`. This is neither a bound nor an estimate of the actual bar schedule; the actual cuts may differ in either direction. It excludes stirrups and makes no density or mass assumption.

Reproduce the calculated quantities with Python's `math.pi`:

```sh
python3 - <<'PY'
from math import pi
length_mm, width_mm, depth_mm, diameter_mm = 1900, 150, 200, 8
area_mm2 = pi * diameter_mm**2 / 4
print(f"gross_envelope_m3={length_mm * width_mm * depth_mm / 1e9:.9f}")
print(f"one_phi8_mm2={area_mm2:.9f}")
print(f"bottom_3_phi8_mm2={3 * area_mm2:.9f}")
print(f"top_2_phi8_mm2={2 * area_mm2:.9f}")
print(f"all_5_phi8_mm2={5 * area_mm2:.9f}")
print(f"illustrative_5_straight_bars_m={5 * length_mm / 1000:.9f}")
print(f"illustrative_bar_volume_m3={5 * area_mm2 * length_mm / 1e9:.12f}")
PY
```

An actual member takeoff and common-price design comparison still require the reinforcement layout and cover, bar and stirrup schedules including anchors and laps, any concrete deductions, the same quantity conventions for a changed design, and a traceable unit-price schedule. None is supplied by this crosswalk, so no currency total, saving, or cost-optimality claim follows. Force/deflection semantics and specimen-specific material properties also remain open in the [source review](4tu-shcc-rc-reference-beam-source-20260927.md); no measured response is admitted for training or solver validation.
