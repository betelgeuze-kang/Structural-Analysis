# Release Evidence Freshness

- `contract_pass`: `False`
- `reason_code`: `ERR_RELEASE_EVIDENCE_FRESHNESS`
- `current_source_commit_sha`: `8593a7269ced257b73eb05c0f8f9f946f80cf6e7`
- `blockers`: `p1_benchmark_breadth_status::input_dependency_newer_than_artifact, customer_shadow_evidence_intake_packet::source_commit_mismatch, fresh_full_validation_lane_status::source_commit_mismatch, fresh_full_validation_lane_status::input_dependency_newer_than_artifact, evidence_console_scope_status::source_commit_mismatch, evidence_console_scope_status::input_dependency_newer_than_artifact`

| Artifact | Status | Blockers | Newer Dependencies |
|---|---|---|---|
| `p0_closure_status` | `pass` | `none` | none |
| `p1_readiness_status` | `pass` | `none` | none |
| `p1_benchmark_breadth_status` | `blocked` | `input_dependency_newer_than_artifact` | `/home/betelgeuze/건축구조분석/implementation/phase1/hf_benchmark_report.atwood_open.json`, `/home/betelgeuze/건축구조분석/implementation/phase1/hf_benchmark_report.rwth_zenodo.json` |
| `real_project_corpus_measured_status` | `pass` | `none` | none |
| `customer_shadow_evidence_status` | `pass` | `none` | none |
| `customer_shadow_evidence_intake_packet` | `blocked` | `source_commit_mismatch` | none |
| `fresh_full_validation_lane_status` | `blocked` | `source_commit_mismatch, input_dependency_newer_than_artifact` | `/home/betelgeuze/건축구조분석/docs/commercialization-gap-current-state.md` |
| `residual_level3_status` | `pass` | `none` | none |
| `g1_direct_residual_terminal_gate_report` | `pass` | `none` | none |
| `g1_shell_material_budgeted_continuation_status` | `pass` | `none` | none |
| `evidence_console_scope_status` | `blocked` | `source_commit_mismatch, input_dependency_newer_than_artifact` | `/home/betelgeuze/건축구조분석/README.md`, `/home/betelgeuze/건축구조분석/docs/commercialization-gap-current-state.md` |
| `developer_preview_rc_status` | `pass` | `none` | none |
| `accuracy_parity_scorecard` | `pass` | `none` | none |
| `product_production_ai_checkpoint_readiness` | `pass` | `none` | none |
