# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation edits are needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow propagation of G1 shell-material row-target and largest-rows strategy exhaustion boundary evidence into `commercial_gap_ledger_status.json` row G1 evidence without changing readiness status.

Current blocker: `mgt_g1_followup387_shell_material_budgeted_continuation_status.json` exposes `row_target_mode_exhaustion` and `largest_rows_operator_strategy_exhaustion`, and both ledgers describe them, but current commercial G1 evidence does not directly mirror these objects. This makes the commercial status less explicit about why another row-target retuning or largest-rows support/Jacobian replay is non-closing evidence rather than a credible closure claim.

Scope: Add status/report/test evidence fields only. Preserve G1 `partial`, G6 `external_blocked`, G7 `partial`, and all claim boundaries. Do not count exhaustion objects as closure, residual descent, production ROCm/HIP readiness, or proof that a different consistent residual/Jacobian Newton path is impossible.

Candidate files:

- `implementation/phase1/commercial_gap_ledger_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- `./scripts/ai-worker-kiro.sh --check docs/ai/dispatch/kiro_g1_shell_material_exhaustion_commercial_propagation_design_20260624T204002Z.md`
- `./scripts/ai-worker-kiro.sh docs/ai/dispatch/kiro_g1_shell_material_exhaustion_commercial_propagation_design_20260624T204002Z.md`
- `python3 -m pytest -q tests/test_commercial_gap_ledger_status.py`
- Regenerate `commercial_gap_ledger_status.json` and dependent productization readiness/audit receipts.
- Confirm commercial summary remains `closed_count=17`, `partial_count=2`, `external_blocked_count=1`.
- `./scripts/ai-verify.sh`

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
