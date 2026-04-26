# KDS Compliance Report

- Project: `Phase1 Structural AI Solver`
- Design code basis: `KDS 41 / KDS seismic submission format`
- Generated at (UTC): `2026-04-06T13:53:42.625122+00:00`

## Input Reports
- PBD review package: `implementation/phase1/release/pbd_review/pbd_review_package_report.json`
- Commercial CSV gate: `implementation/phase1/commercial_csv_gate_report.json`
- Member force gate: `implementation/phase1/member_force_soft_accept_report.json`
- Design change evidence: `implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.csv`

## Compliance Table
| Item | Criterion | Value | Status | Evidence |
|---|---|---:|:---:|---|
| Drift Envelope | max drift <= 2.000% | 1.9872% | PASS | PBD drift envelope (compliance slice preferred) |
| Time-Step Convergence | all cases converged and min converged-step ratio == 1.0 | all=True, min_ratio=1.0000 | PASS | NDTHA convergence summary |
| Energy Balance | relative error <= 1.00e-02 | 8.427672e-05 | PASS | thermodynamic integrity check |
| HF Drift Error | commercial gate drift error <= 5% | 1.2752% | PASS | commercial csv direct compare |
| HF Base Shear Error | commercial gate base shear error <= 5% | 0.9328% | PASS | commercial csv direct compare |
| HF Buckling Error | commercial gate buckling factor error <= 5% | 0.9451% | PASS | commercial csv direct compare |
| Mode Shape MAC | commercial gate mode shape MAC >= 0.95 | 1.00000 | PASS | commercial csv direct compare |
| Member Axial Force (p95) | p95 error <= 5.000% | 3.9072% | PASS | member-force soft-accept report |
| Member Force Soft-Accept Ratio | soft-accept ratio <= 0.250 | 0.00000 | PASS | member-force soft-accept report |
| Design Change Evidence | feasible input and cost reduction report present | accepted=32, changed=25, cost_delta=903.463 | PASS | design optimization cost reduction report |
| Code Check D/C | max D/C <= 1.250 | 1.2162 | PASS | code_check_report: implementation/phase1/release/kds_compliance/code_check_report.json |

## RC Governing Checks
| Member | Component | Clause | DCR |
|---|---|---|---:|
| C-TRN-007 | drift | KDS-RC-WALL-DRIFT-001 | 0.9818 |
| C-TRN-007 | boundary_element | KDS-RC-WALL-BE-001 | 0.9802 |
| C-TST-002 | boundary_element | KDS-RC-WALL-BE-001 | 0.8928 |
| C-TST-002 | drift | KDS-RC-WALL-DRIFT-001 | 0.8545 |
| C-TST-003 | axial_flexure | KDS-RC-COL-INT-001 | 0.8028 |
| C-TST-003 | shear | KDS-RC-COL-SHEAR-001 | 0.7759 |
| C-TRN-005 | axial_flexure | KDS-RC-COL-INT-001 | 0.7651 |
| C-TRN-005 | shear | KDS-RC-COL-SHEAR-001 | 0.7394 |
| C-TRN-004 | boundary_element | KDS-RC-WALL-BE-001 | 0.7357 |
| C-TST-001 | axial_flexure | KDS-RC-COL-INT-001 | 0.7342 |
| C-TRN-007 | axial_flexure | KDS-RC-WALL-INT-001 | 0.7206 |
| C-TST-001 | shear | KDS-RC-COL-SHEAR-001 | 0.7096 |
| C-TRN-007 | shear | KDS-RC-WALL-SHEAR-001 | 0.6874 |
| C-TST-002 | axial_flexure | KDS-RC-WALL-INT-001 | 0.6564 |
| C-VAL-001 | flexure | KDS-RC-BEAM-FLEX-001 | 0.6485 |
| C-TRN-004 | drift | KDS-RC-WALL-DRIFT-001 | 0.6455 |
| C-TST-002 | shear | KDS-RC-WALL-SHEAR-001 | 0.6261 |
| C-TRN-003 | flexure | KDS-RC-BEAM-FLEX-001 | 0.6148 |
| C-VAL-001 | shear | KDS-RC-BEAM-SHEAR-001 | 0.5916 |
| C-TRN-003 | shear | KDS-RC-BEAM-SHEAR-001 | 0.5608 |

## NG Members By Combination
| Combination | NG Members | Max DCR |
|---|---:|---:|
| KDS_ULS_2 | 13 | 1.2162 |
| SVC_DRIFT | 2 | 1.0750 |
| RC_DETAIL | 0 | 0.9818 |
| STAB_BUCKLING | 0 | 0.9524 |
| KDS_ULS_1 | 0 | 0.8505 |
| KDS_ULS_3_WX+ | 0 | 0.8505 |
| KDS_ULS_3_WX- | 0 | 0.8505 |
| KDS_ULS_4_WY+ | 0 | 0.8505 |
| KDS_ULS_4_WY- | 0 | 0.8505 |
| KDS_ULS_5_EX+ | 0 | 0.8505 |
| KDS_ULS_5_EX- | 0 | 0.8505 |
| KDS_ULS_6_EY+ | 0 | 0.8505 |
| KDS_ULS_6_EY- | 0 | 0.8505 |
| KDS_ULS_7_RSX+ | 0 | 0.8505 |
| KDS_ULS_7_RSX- | 0 | 0.8505 |
| KDS_ULS_8_RSY+ | 0 | 0.8505 |
| KDS_ULS_8_RSY- | 0 | 0.8505 |

## Member Family DCR Envelope
| Member Type | Max DCR | Governing Clause |
|---|---:|---|
| column | 1.2162 | KDS-MOMENT-Y-001 |
| wall | 1.0774 | KDS-MOMENT-Y-001 |
| brace | 0.9556 | KDS-SVC-DRIFT-001 |
| beam | 0.9455 | KDS-SVC-DRIFT-001 |

## Combination Provenance
| KDS Combination | Runtime Combination | Match Score |
|---|---|---:|
| KDS_ULS_1 | gLCB3 | 0.4167 |
| KDS_ULS_2 | gLCB1 | 0.8333 |
| KDS_ULS_3_WX+ | gLCB3 | 0.3704 |
| KDS_ULS_3_WX- | gLCB3 | 0.3704 |
| KDS_ULS_4_WY+ | gLCB3 | 0.3704 |
| KDS_ULS_4_WY- | gLCB3 | 0.3704 |
| KDS_ULS_5_EX+ | gLCB3 | 0.3704 |
| KDS_ULS_5_EX- | gLCB3 | 0.3704 |
| KDS_ULS_6_EY+ | gLCB3 | 0.3704 |
| KDS_ULS_6_EY- | gLCB3 | 0.3704 |
| KDS_ULS_7_RSX+ | gLCB3 | 0.3226 |
| KDS_ULS_7_RSX- | gLCB3 | 0.3226 |
| KDS_ULS_8_RSY+ | gLCB3 | 0.3226 |
| KDS_ULS_8_RSY- | gLCB3 | 0.3226 |
