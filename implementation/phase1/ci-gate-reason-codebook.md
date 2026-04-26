# CI Gate Reason Codebook

`phase1_ci_gate.py` emits deterministic `reason_code` values for static triage.

## Codes

| reason_code | Meaning | Typical fix |
|---|---|---|
| `PASS` | All gate checks passed. | None. |
| `ERR_MISSING_STRICT_KEY` | strict probe JSON missing `strict_rust_hip_pass`. | Regenerate strict probe report with expected schema. |
| `ERR_MISSING_RCA_KEY` | RCA JSON missing required timing keys. | Regenerate Step5 RCA summary; validate with schema. |
| `ERR_INVALID_RCA_VALUE` | RCA values are non-numeric/NaN/negative. | Fix exporter to emit finite non-negative seconds. |
| `ERR_STRICT_FAIL` | strict Rust/HIP probe failed. | Connect real producer and rerun strict probe. |
| `ERR_HOST_COPY_SHARE` | Host copy share exceeds threshold. | Reduce host-copy path or relax threshold intentionally. |
| `ERR_MISSING_CONTRACT_ARTIFACT` | Required contract artifact is missing/invalid. | Regenerate Step1~Step4 contract reports and rerun gate. |
| `ERR_PRIORITY3_FAIL` | Priority3 summary failed or invalid. | Re-run priority3 modules or inspect mismatch fixture. |
| `ERR_BUCKLING_EIGEN_INVALID` | Buckling eigen contract invalid or critical load factor non-positive. | Re-generate buckling report and verify eigen metadata. |
| `ERR_ENERGY_MONOTONICITY` | Physics residual energy monotonicity check failed. | Fix residual update/policy to enforce residual energy decay. |
| `ERR_META_OOD_FAIL` | Meta-learning report has insufficient OOD generalization coverage. | Add OOD-tagged tasks and set `meta_ood_generalization_pass=true`. |
| `ERR_BENCHMARK_KPI_FAIL` | HF benchmark KPI contract failed. | Improve model/physics calibration until KPI thresholds pass. |
| `ERR_BRANCHING_CONTRACT_FAIL` | Derivative-free branching contract failed or backprop path detected. | Regenerate branching report and ensure `uses_backprop=false`. |
| `ERR_BIFURCATION_CONTRACT_FAIL` | Bifurcation detector contract invalid/unready. | Regenerate bifurcation detector report and verify trigger structure. |
| `ERR_RUST_ONNX_CONTRACT_FAIL` | Rust/HIP/ONNX native contract failed. | Recheck native integration contract checks and regenerate report. |
| `ERR_WINNING_TICKET_FAIL` | Winning-ticket targeted backprop contract failed. | Regenerate winning-ticket report and ensure `selection.strategy=topk_weighted_backprop`, `top_k>=2`, and `graph_count==top_k`. |
| `ERR_RUST_MD3BEAD_PARITY_FAIL` | Rust 3-Bead hook and Python reference are not parity-equivalent. | Re-run parity validation and align Rust/Python forcefield math. |
| `ERR_LJ_MAPPING_FAIL` | Nonlinear Lennard-Jones mapping contract failed. | Re-run LJ mapping validator and recalibrate yield/softening/dissipation parameters. |
| `ERR_DYNAMIC_TIME_HISTORY_FAIL` | Dynamic time-history contract failed. | Re-run Newmark/Rayleigh validation with valid ground-motion CSV and inspect stability/energy checks. |
| `ERR_CACHE_PROFILE_FAIL` | Branch64 microbatch cache profile contract failed. | Re-run cache profile with proper hook command and verify at least one cache-safe chunk exists. |
| `ERR_P0_ENGINE_PROFILE_FAIL` | P0 engine performance profile contract failed. | Re-run `profile_p0_engine_path.py` and verify probe/rust/python/profile fields are all valid. |
| `ERR_P0_CORE_GAP_FAIL` | P0 core-gap pipeline contract failed. | Re-run `run_p0_core_gap_pipeline.py` and verify both P0-1 and P0-2 checks are true. |
| `ERR_NOISE_STRESS_FAIL` | Noise sensitivity stress contract failed. | Re-run `run_noise_sensitivity_stress.py` and inspect high-noise p95 error envelope and scenario completeness. |
| `ERR_SCALEOUT_IO_FAIL` | Scale-out I/O profile contract failed. | Re-run `run_scaleout_io_profile.py` and verify 1M+ DOF microbatch gate passes. |
| `ERR_PHASEA_CONTRACT_FAIL` | Railway/tunnel Phase-A contract pack failed. | Regenerate `phasea_contract_report.json` and fix A1~A5 schema/table/report contract errors. |
| `ERR_PHASEB_TRACK_FAIL` | Phase-B track dynamics contract pack failed. | Re-run `run_phaseb_track_modules.py` and inspect B1~B4 reports for convergence/accuracy violations. |
| `ERR_PHASED_ML_FAIL` | Phase-D multidomain residual-learning contract pack failed. | Re-run `run_phased_multidomain_modules.py` and inspect D1~D4 reports for dataset/attention/metric gate violations. |
| `ERR_PHASEE_INTEGRATED_FAIL` | Phase-E integrated coupling/compliance contract pack failed. | Re-run `run_phasee_integrated_modules.py` and inspect E1/E2/E3/E5 reports. |
| `ERR_PHASEF_RESILIENCE_FAIL` | Phase-F resilience contract pack failed. | Re-run `run_phasef_resilience_modules.py` and inspect F1/F2/F3 reports (cache-safe chunk, phase lag, soil OOD gate). |
| `ERR_PBD_REVIEW_FAIL` | PBD review package gate failed. | Re-run `generate_pbd_review_package.py` and verify 7-GM, convergence, energy, and artifact outputs. |
| `ERR_GLOBAL_AUTHORITY_FAIL` | Global authority gate (OpenSees/SAC/NHERI) failed. | Re-run `run_global_authority_gate.py` and fix missing/invalid authority track artifacts. |
| `ERR_WIND_BENCHMARK_FAIL` | Wind long-duration benchmark gate failed. | Re-run `run_wind_time_history_gate.py` with real-source manifest and verify 10h duration/chunked convergence. |
| `ERR_SSI_BOUNDARY_FAIL` | SSI nonlinear boundary gate failed. | Re-run `run_ssi_boundary_gate.py` and calibrate p-y/t-z boundary parameters + shear delta thresholds. |
| `ERR_DAMPER_VALIDATION_FAIL` | Damper validation gate failed. | Re-run `run_damper_validation_gate.py` and verify damped catalog/source integrity + waveform metrics. |
| `ERR_KDS_FRONTEND_FAIL` | KDS code-check frontend package gate failed. | Re-run `generate_kds_compliance_report.py` and ensure `kds_frontend_payload_json` is generated and valid. |
| `ERR_CONSTRUCTION_SEQUENCE_FAIL` | Construction-sequence gate failed. | Re-run `run_construction_sequence_gate.py` and verify creep/shrinkage, differential shortening, and initial stress checks. |
| `ERR_FLEXIBLE_DIAPHRAGM_FAIL` | Flexible diaphragm gate failed. | Re-run `run_flexible_diaphragm_gate.py` and verify shell-beam mix topology + slab stress/amplification checks. |
| `ERR_REPRO_VERSION_LOCK_FAIL` | Reproducibility/version-lock gate failed. | Re-run `run_reproducibility_version_lock_gate.py` and verify replay hash equality + lock manifest hash freeze. |
| `ERR_SOLVER_HIP_E2E_FAIL` | Solver-wide HIP end-to-end contract failed. | Re-run `run_solver_hip_e2e_contract.py` and inspect which main loop still reports CPU residency. |
| `ERR_RC_BENCHMARK_LOCK_FAIL` | RC benchmark-lock gate failed. | Re-run `run_rc_benchmark_lock_gate.py` and inspect cracking/bond-slip/creep family range failures. |

## Required report fields
- `strict_rust_hip_pass`
- `host_copy_share`
- `host_copy_share_limit`
- `host_copy_share_pass`
- `all_pass`
- `reason_code`
- `reason`
- `physics_energy_monotonic_pass`
- `meta_ood_generalization_pass`
- `buckling_contract_pass`
- `benchmark_kpi_pass`
- `branching_contract_pass`
- `bifurcation_contract_pass`
- `rust_onnx_contract_pass`
- `winning_ticket_contract_pass`
- `rust_md3bead_parity_pass`
- `lj_mapping_contract_pass`
- `dynamic_time_history_pass`
- `cache_profile_pass`
- `p0_engine_perf_pass`
- `p0_core_gap_pass`
- `noise_stress_pass`
- `scaleout_io_pass`
- `phasea_contract_pass`
- `phaseb_track_contract_pass`
- `phased_multidomain_contract_pass`
- `phasee_integrated_contract_pass`
- `phasef_resilience_contract_pass`
- `pbd_review_pass`
- `global_authority_gate_pass`
- `construction_sequence_pass`
- `flexible_diaphragm_pass`
- `repro_version_lock_pass`
- `solver_hip_e2e_pass`
- `rc_benchmark_lock_pass`

- `contract_artifacts_pass`
- `missing_contract_artifacts`


## Priority3 reason codes
- `PASS`
- `ERR_MODULE_FAIL`
- `ERR_METADATA_VERSION_MISMATCH`
