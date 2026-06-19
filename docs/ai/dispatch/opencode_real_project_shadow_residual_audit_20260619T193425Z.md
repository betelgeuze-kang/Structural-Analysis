# OpenCode Worker Slice: Real Project / Customer Shadow / Residual Evidence Audit

Goal: Audit the current repository evidence against the active goal's locally actionable readiness targets after GitHub sync was confirmed blocked only by R4 approval.

Scope:
- Read only; do not modify files.
- Inspect evidence/status files for:
  - real-project corpus measured status and row provenance targets
  - customer completed-project shadow evidence status/schema/intake
  - Level 3 residual closure status
  - README and `docs/commercialization-gap-current-state.md` claim alignment for those areas

Candidate files:
- `implementation/phase1/real_project_corpus_measured_status.json`
- `implementation/phase1/real_project_row_provenance_report.json`
- `implementation/phase1/customer_shadow_evidence_status.json`
- `implementation/phase1/customer_shadow_evidence.schema.json`
- `implementation/phase1/release_evidence/productization/customer_shadow_evidence_intake_packet.json`
- `implementation/phase1/release_evidence/productization/residual_level3_status.json`
- `implementation/phase1/release_evidence/productization/ndtha_residual_gate_report.json`
- `README.md`
- `docs/commercialization-gap-current-state.md`
- `docs/pm-release-gate-milestones.md`

Verification criteria:
- Report only concise findings with changed files as `none`.
- Include current counts/statuses for each target.
- Flag any stale or contradictory claim where docs imply a blocker is closed but evidence says it is open.
- Do not print raw customer data, secrets, full JSON dumps, or long logs.
