# Kiro G1 Blocker Terminal Requirements Design

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement an approved scoped slice if implementation edits are needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow G1 evidence-boundary update that groups the remaining G1 blockers into blocker-level terminal requirement rows without promoting G1 readiness.

Current blocker: G1 remains partial with `full_load_gate_not_closed`, `full_mesh_nonlinear_equilibrium_not_closed`, `material_newton_breadth_not_closed`, and `production_rocm_hip_residency_not_closed`. Existing `closure_requirements` list individual checks, but the status artifact does not yet expose a concise blocker-level terminal evidence crosswalk that tells which authoritative receipt fields must become true for each blocker.

Scope: Add machine-readable G1 blocker terminal requirement rows to `commercial_gap_ledger_status.json`, update focused tests and ledger wording. Reuse existing evidence fields from `g1_full_load_hip_newton_lane_report.json`, `mgt_g1_followup387_shell_material_budgeted_continuation_status.json`, p-delta/full-mesh receipts, and HIP-required consistency receipts. Do not synthesize closure, do not run long solver jobs, do not claim G1 readiness closure, and do not hide missing/partial/proxy/fallback evidence.

Candidate files:

- `implementation/phase1/commercial_gap_ledger_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `tests/test_build_gap_ledger_evidence_audit.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`

Verification criteria:

- G1 remains partial with the same four blockers.
- G1 evidence includes one blocker-level terminal requirement row per current blocker.
- Each row includes blocker id, terminal evidence target, observed values, source receipt paths, terminal status, and non-closing reasons.
- Closure requirement counts remain honest; no row is marked passed unless current authoritative evidence proves it.
- Focused tests and readiness/status artifact checks pass.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
