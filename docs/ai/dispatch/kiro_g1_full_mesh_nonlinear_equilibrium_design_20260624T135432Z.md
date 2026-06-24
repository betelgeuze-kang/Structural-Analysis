# Kiro Design Slice: G1 Full-Mesh Nonlinear Equilibrium Frontier

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` will implement the approved scoped slice.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the next smallest locally actionable G1 slice that moves the project toward authoritative full-mesh/full-load nonlinear equilibrium evidence, without promoting G1 readiness.

Current blocker: `G1:full_mesh_nonlinear_equilibrium_not_closed`.

Current readiness boundary:

- `commercial_gap_ledger_status.json` reports G1 as `partial`.
- G1 next gate is `consistent full-load Newton/Jacobian plus material Newton closure`.
- G1 blocker list includes `full_mesh_nonlinear_equilibrium_not_closed`.
- Developer preview readiness is still blocked by:
  - `g1::full_load_gate_not_closed`
  - `g1::full_mesh_nonlinear_equilibrium_not_closed`
  - `g1::material_newton_breadth_not_closed`
  - `g1::production_rocm_hip_residency_not_closed`
  - `human_ux::observation_file_missing`
  - `stale_or_inconsistent:worktree_dirty`

Scope:

- Design only.
- Prefer a narrow implementation slice that can produce non-promoting, authoritative gate-distance evidence or remove one local ambiguity in the G1 blocker path.
- Keep partial/proxy/fallback/frontier evidence visible as partial evidence.
- Do not propose ledger closure, product readiness promotion, developer-preview promotion, or evidence-boundary weakening.
- Do not require external/customer/operator receipts.
- Do not include broad refactors.

Candidate files:

- `implementation/phase1/commercial_gap_ledger_status.py`
- `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `implementation/phase1/run_solver_hip_e2e_contract.py`
- `scripts/build_mgt_g1_direct_residual_terminal_gate_report.py`
- `scripts/report_commercial_gap_ledger_status.py`
- `scripts/build_product_readiness_snapshot.py`
- `scripts/build_developer_preview_readiness.py`
- `scripts/build_developer_preview_rc_status.py`
- `scripts/build_gap_ledger_evidence_audit.py`
- `implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json`
- `implementation/phase1/release_evidence/productization/mgt_g1_direct_residual_terminal_gate_report.json`
- `implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json`
- `implementation/phase1/release_evidence/productization/developer_preview_readiness.json`

Verification criteria:

- Any proposed implementation must preserve G1 as partial unless physical direct residual, increment, full-load, and consistent Newton/Jacobian gates are all proven without fallback.
- Any new evidence must include an explicit claim boundary and reuse/proxy/fallback status.
- The resulting diff must pass:
  - `python3 scripts/report_commercial_gap_ledger_status.py --out implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json --check`
  - `python3 scripts/build_gap_ledger_evidence_audit.py --check --out implementation/phase1/release_evidence/productization/gap_ledger_evidence_audit.json`
  - `python3 scripts/build_product_readiness_snapshot.py --check`
  - `python3 scripts/build_developer_preview_readiness.py --check`
  - `python3 scripts/build_developer_preview_rc_status.py --check`
  - `python3 scripts/report_release_evidence_freshness.py --out /tmp/release_evidence_freshness_g1_design_followup.json --out-md /tmp/release_evidence_freshness_g1_design_followup.md --fail-blocked`
  - `./scripts/ai-preflight.sh`
  - `./scripts/ai-verify.sh`
- Add or update focused tests if gate logic, blocker mapping, receipt schema, or readiness derivation changes.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
