# Release Evidence Freshness

- `contract_pass`: `False`
- `reason_code`: `ERR_RELEASE_EVIDENCE_FRESHNESS`
- `current_source_commit_sha`: `6804623fb0050c1781b57afa2c556fdbb82f6081`
- `blockers`: `p1_benchmark_breadth_status::input_dependency_newer_than_artifact, customer_shadow_evidence_intake_packet::input_dependency_newer_than_artifact, evidence_console_scope_status::input_dependency_newer_than_artifact, developer_preview_rc_status::input_dependency_newer_than_artifact`

| Artifact | Status | Blockers | Newer Dependencies |
|---|---|---|---|
| `p0_closure_status` | `pass` | `none` | none |
| `p1_readiness_status` | `pass` | `none` | none |
| `p1_benchmark_breadth_status` | `blocked` | `input_dependency_newer_than_artifact` | `/home/betelgeuze/건축구조분석/implementation/phase1/release/external_benchmark_submission_readiness.json`, `/home/betelgeuze/건축구조분석/implementation/phase1/release_evidence/productization/external_benchmark_submission_updates.json`, `/home/betelgeuze/건축구조분석/implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json` |
| `real_project_corpus_measured_status` | `pass` | `none` | none |
| `customer_shadow_evidence_status` | `pass` | `none` | none |
| `customer_shadow_evidence_intake_packet` | `blocked` | `input_dependency_newer_than_artifact` | `/home/betelgeuze/건축구조분석/implementation/phase1/customer_shadow_evidence_status.json` |
| `fresh_full_validation_lane_status` | `pass` | `none` | none |
| `residual_level3_status` | `pass` | `none` | none |
| `g1_direct_residual_terminal_gate_report` | `pass` | `none` | none |
| `g1_shell_material_budgeted_continuation_status` | `pass` | `none` | none |
| `evidence_console_scope_status` | `blocked` | `input_dependency_newer_than_artifact` | `/home/betelgeuze/건축구조분석/implementation/phase1/customer_shadow_evidence_status.json` |
| `developer_preview_rc_status` | `blocked` | `input_dependency_newer_than_artifact` | `/home/betelgeuze/건축구조분석/implementation/phase1/release_evidence/productization/developer_preview_readiness.json`, `/home/betelgeuze/건축구조분석/implementation/phase1/release_evidence/productization/gap_ledger_evidence_audit.json` |
| `public_benchmark_source_of_truth` | `pass` | `none` | none |
| `accuracy_parity_scorecard` | `pass` | `none` | none |
| `product_production_ai_checkpoint_readiness` | `pass` | `none` | none |
