# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation edits are needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow propagation of G1 shell-material duplicate-alias receipt evidence into `commercial_gap_ledger_status.json` row G1 evidence without changing readiness status.

Current blocker: `mgt_g1_followup387_shell_material_budgeted_continuation_status.json` exposes `duplicate_alias_receipts`, but current commercial G1 evidence has no duplicate/alias key, so the commercial status does not directly trace that the followup436 shell-normal alias is retained only as non-counted duplicate evidence.

Scope: Add status/report/test evidence fields only. Preserve G1 `partial`, G6 `external_blocked`, G7 `partial`, and all claim boundaries. Do not count duplicate aliases as frontier progress, row-target exhaustion, residual descent, or readiness closure. Do not edit unrelated readiness rows.

Candidate files:

- `implementation/phase1/commercial_gap_ledger_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- `./scripts/ai-worker-kiro.sh --check docs/ai/dispatch/kiro_g1_duplicate_alias_commercial_propagation_design_20260624T203625Z.md`
- `./scripts/ai-worker-kiro.sh docs/ai/dispatch/kiro_g1_duplicate_alias_commercial_propagation_design_20260624T203625Z.md`
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
