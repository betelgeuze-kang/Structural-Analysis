# GPU Bottleneck Audit

## Resolved Bottlenecks
- `wind_preprocess_gpu_strict`: `resolved`
  - evidence: `{"preprocess_backend": "rocm_torch_full", "section_family_coverage_min": 0.96, "material_model_types": ["steel_elastic_plastic"]}`
- `ssi_preprocess_gpu_strict`: `resolved`
  - evidence: `{"preprocess_backend": "rocm_torch_full", "nonlinear_ratio_span": 0.282342448413099, "residual_settle_case_count": 4}`
- `solver_mainloop_gpu_residency`: `resolved`
  - evidence: `{"contract_pass": true, "all_main_loops_gpu_pass": true, "no_cpu_fallback_pass": true, "device_residency_ratio_min": 1.0}`
- `frame_bridge_binary_first_postprocess`: `resolved`
  - evidence: `{"response_storage": "npz_external+inline_summary", "response_binary_consumer": "dlpack_zero_copy_primary"}`
- `ndtha_bridge_binary_first_postprocess`: `resolved`
  - evidence: `{"response_storage": "npz_external+inline_head", "response_binary_consumer": "dlpack_zero_copy_primary"}`
- `ssi_bridge_binary_first_postprocess`: `resolved`
  - evidence: `{"response_storage": "npz_external+inline_summary", "response_binary_consumer": "dlpack_zero_copy_primary", "device_artifact_consumer": "dlpack_zero_copy"}`
- `track_bridge_binary_first_postprocess`: `resolved`
  - evidence: `{"response_storage": "dlpack_external+inline_summary", "response_binary_consumer": "dlpack_zero_copy_primary"}`
- `track_irregularity_gpu_preprocess`: `resolved`
  - evidence: `{"preprocess_backend": "rocm_torch_full", "node_count": 4001, "peak_abs_m": 0.0003696087616409231}`
- `pbd_binary_first_postprocess`: `resolved`
  - evidence: `{"response_storage": "npz_external+inline_summary", "response_binary_consumer": "npz_external_primary", "case_metrics_npz_case_count": 7}`
- `authority_binary_first_postprocess`: `resolved`
  - evidence: `{"response_storage": "npz_external+inline_summary", "response_binary_consumer": "npz_external_primary", "case_metrics_npz_case_count": 8}`

## Remaining Unavoidable Host Ops
- `csv_artifact_ingest`: Input and report artifacts still enter through host I/O. This is expected unless artifact formats are redesigned end-to-end.
  - files: `/home/betelgeuze/건축구조분석/implementation/phase1/run_wind_time_history_gate.py, /home/betelgeuze/건축구조분석/implementation/phase1/run_ssi_boundary_gate.py, /home/betelgeuze/건축구조분석/implementation/phase1/run_damper_validation_gate.py, /home/betelgeuze/건축구조분석/implementation/phase1/generate_pbd_review_package.py, /home/betelgeuze/건축구조분석/implementation/phase1/compute_global_authority_metrics.py`
- `report_generation_json_io`: Committee and external submission packaging are host-side by design.
  - files: `/home/betelgeuze/건축구조분석/implementation/phase1/run_damper_validation_gate.py, /home/betelgeuze/건축구조분석/implementation/phase1/generate_committee_review_package.py, /home/betelgeuze/건축구조분석/implementation/phase1/prepare_external_validation_submission.py, /home/betelgeuze/건축구조분석/implementation/phase1/generate_pbd_review_package.py, /home/betelgeuze/건축구조분석/implementation/phase1/compute_global_authority_metrics.py`

## Remaining Optimizable Host Ops

## Optimization Architecture Limits
- `global_label_broadcast`: Project-global drift and residual labels must not be broadcast directly onto every member row.
  - required_fix: `Keep member-local demand tensors separate from project-global state tensors and reference them by project or case id.`
- `narrow_action_space`: Optimization action space is wider than before, but still not broad enough to cover full commercial redesign workflows.
  - required_fix: `Extend legal action masks across beam, wall, slab thickness, rebar detailing, and connection redesign actions.`
- `simple_objective`: The objective is no longer pure DCR-plus-cost, but it is still short of a full commercial multi-objective surface.
  - required_fix: `Calibrate congestion, detailing complexity, robustness margin, and multi-hazard stability terms against production design decisions.`

## Strict GPU Guards
- `{"solver_hip_e2e_contract_pass": true, "wind_preprocess_backend": "rocm_torch_full", "ssi_preprocess_backend": "rocm_torch_full", "frame_binary_consumer": "dlpack_zero_copy_primary", "ndtha_binary_consumer": "dlpack_zero_copy_primary", "ssi_binary_consumer": "dlpack_zero_copy_primary", "track_binary_consumer": "dlpack_zero_copy_primary", "pbd_binary_consumer": "npz_external_primary", "authority_binary_consumer": "npz_external_primary", "nightly_env_requires": ["PHASE1_DISABLE_CPU_FALLBACK=1", "PHASE1_GPU_PREPROCESS=1", "PHASE1_GPU_PREPROCESS_STRICT=1"]}`
