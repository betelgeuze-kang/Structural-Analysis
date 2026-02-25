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
| `ERR_WINNING_TICKET_FAIL` | Winning-ticket targeted backprop contract failed. | Regenerate winning-ticket report and ensure graph_count=1 with winner-only replay. |

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

- `contract_artifacts_pass`
- `missing_contract_artifacts`


## Priority3 reason codes
- `PASS`
- `ERR_MODULE_FAIL`
- `ERR_METADATA_VERSION_MISMATCH`
