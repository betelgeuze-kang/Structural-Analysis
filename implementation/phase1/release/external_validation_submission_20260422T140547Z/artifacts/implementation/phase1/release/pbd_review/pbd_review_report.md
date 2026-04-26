# PBD Review Package (MVP 5-Page)

- Generated at (UTC): `2026-03-22T08:33:17.372524+00:00`
- Earthquake cases: `7`
- Engine wall time: `1.07 min`
- Commercial estimate: `336.0 h`
- Speedup (estimate ratio): `18817.7x`

## 1) Case Summary
- Split counts: `{'train': 5, 'val': 1, 'test': 1}`
- Drift P50/P84/P95 max: `9.200% / `9.200% / `9.200%`
- Dashboard HTML: `implementation/phase1/release/pbd_review/pbd_review_dashboard.html`

## 2) PBD Drift Envelope
- IO/LS/CP window: `1.0% / 1.5% / 1.5%~2.0%`
- Max envelope drift: `9.200%`
- Figure: `implementation/phase1/release/pbd_review/drift_envelope_7eq.png`

## 3) Hysteresis
- Figure: `implementation/phase1/release/pbd_review/core_wall_hysteresis.png`
- Residual top displacement (max abs): `760.16 mm`
- Residual interstory drift (max abs): `1.9136%`
- Cumulative dissipation (system loop): `6.3690e+126 kN·mm`

## 4) 3D Hinge Proxy
- 3D proxy figure: `implementation/phase1/release/pbd_review/plastic_hinge_proxy_3d.png`
- Timeline proxy figure: `implementation/phase1/release/pbd_review/plastic_hinge_proxy_timeline.png`
- Peak hinge-story proxy count: `20`

## 5) Authority
- SAC KPI figure: `implementation/phase1/release/pbd_review/authority_sac_kpi.png`
- NHERI waveform figure: `implementation/phase1/release/pbd_review/authority_nheri_waveform.png`
- Authority catalog: `implementation/phase1/open_data/global_authority/authority_source_catalog.json`

## Solver Integrity
- All cases converged: `True`
- Min converged-step ratio: `1.0000`
- Step tolerance: `1.00e-04`
- Dynamic energy-balance relative error (ref): `8.427672e-05`
- Dynamic equilibrium residual ratio (ref): `2.280637e-13`

## Selected Case IDs
- EQ-1: `opstool_606m_megatall_model-00001`
- EQ-2: `opstool_606m_megatall_model-00005`
- EQ-3: `opstool_606m_megatall_model-00008`
- EQ-4: `opstool_606m_megatall_model-00015`
- EQ-5: `opstool_606m_megatall_model-00017`
- EQ-6: `opstool_606m_megatall_model-00020`
- EQ-7: `opstool_606m_megatall_model-00023`
