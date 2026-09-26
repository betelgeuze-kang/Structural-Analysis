# 4TU RC reference-beam history: source intake, not admission

The [4TU.ResearchData/Figshare record](https://figshare.com/articles/dataset/Data_corresponding_to_the_publication_Experimental_and_numerical_data_on_the_role_of_interface_for_crack-width_control_of_hybrid_SHCC_concrete_beams_/14672064/2), version 2, DOI `10.4121/14672064.v2`, declares **CC BY 4.0** for the dataset. Its accompanying [experimental paper](https://doi.org/10.1016/j.engstruct.2021.113378) and linked [open conference paper](https://pure.tudelft.nl/ws/portalfiles/portal/87496941/P0667.pdf) describe four-point bending of conventional reinforced-concrete reference beams alongside SHCC–concrete hybrid beams. This is a candidate for source review, not an admitted training row or physical-validation result.

## Original file and specimen correspondence

The record API identifies `Data_Set.zip` (`8,293,093` bytes; publisher MD5 `82fc529a6392a4569d95c3c1a1a26ca0`). A bounded temporary download matched that size and MD5. Its SHA-256 is `cb0c918cd5e2a9401181a3772ba039feb5a64fa94d82a0185204c30f9651feb0`; the ZIP integrity check passed. It contains only `Read_Me.txt` (`1,848` uncompressed bytes) and `Data_File.xlsx` (`8,568,573` uncompressed bytes; SHA-256 `ade81369b32ad40b28b131062edb72e94091bb4e2723317a2adc090780397e16`). The README calls the workbook a mixture of original experimental, processed, and numerical data. No original file or measurement row was copied into the repository.

| Workbook location | Source label and role | Observed ordered numeric pairs |
| --- | --- | ---: |
| `Fig. 6a and 6b`, `P:Q`, rows 5 onward | `Reference Beam - New Study`: experimental `Load`, `Deflection` | 13,261 |
| `Fig. 15`, `A:B`, and `Fig. 17a and 17b`, `A:B` | `Tested Reference Beam`: exact copies of the preceding 13,261 pairs | 13,261 each, **not new specimens** |
| `Fig. 6a and 6b`, `A:B` | `Reference Beam - Old Study`: separately labeled experimental series | 4,881; source-campaign linkage still open |

All three `New Study`/`Tested Reference Beam` copies agree in row order and numeric values; their load/deflection columns contain no formulas or one-sided missing pairs. In `Fig. 15`, `F:G` is explicitly labeled `Simulated Reference Beam` and has 11,396 pairs, so it must remain separate from measurements. The workbook also has cube-level `Compressive Strength Data ` and lattice-model `Numerical Inputs`; neither sheet alone maps a material measurement or fitted parameter to the new reference beam.

## Model fit and unresolved inputs

The linked papers place the conventional RC control in a four-point bending setup, with section and reinforcement drawings, approximately `0.54%` longitudinal reinforcement, and `8 mm` stirrups at `150 mm` spacing in the shear spans to avoid shear failure. That stated flexural intent makes the **conventional reference**, rather than the SHCC/interface variants, the closest mechanism screen for the current planar axial–curvature fiber beam. The [corotational element](../../src/structural_analysis/elements/stateful_corotational_fiber_beam2d.py) reuses the axial–curvature section integrator; it does not establish a shear, steel–concrete slip, or SHCC–concrete interface response. The hybrid/debonded specimens therefore need different physics, and even the control's whole curve cannot be claimed as a validated model match from this intake.

The experimental columns are headed only `Load`, `Deflection`, `deformation`, and `Max CW`; **the workbook headers do not give units** for the first two or identify the exact deflection reference point. The separate `deformation` and crack-width channels must not be substituted for deflection. Row order is available, but a time scale, imposed actuator history, and machine-compliance correction are not established here. A specimen-specific link from the cube tests and steel properties to the `New Study` reference is also unverified. The four-point setup does not document an axial preload in the inspected source; no axial-load value is inferred.

The next safe step is to reconcile the final paper's figure axes, specimen drawing, material/batch labels, and instrument definition with the `New Study` `P:Q` headers, recording explicit units and source-page citations. Only after that crosswalk passes should a quarantined, source-row-preserving parser be considered. This intake performs no structural solve, fit, row admission, or validation comparison.
