# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation edits are needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow propagation of G1 shell-material same-operator no-descent and counter-evidence lists into `commercial_gap_ledger_status.json` row G1 evidence without changing readiness status.

Current blocker: `mgt_g1_followup387_shell_material_budgeted_continuation_status.json` exposes `same_operator_no_descent_receipts` and `counter_evidence`, but current commercial G1 evidence only exposes the monotonic frontier boolean and larger summary objects. The commercial row should directly show which same-operator replays and counter-evidence receipts are non-closing so future status/routing cannot treat repeated row retuning as hidden closure progress.

Scope: Add status/report/test evidence fields only. Preserve G1 `partial`, G6 `external_blocked`, G7 `partial`, and all claim boundaries. Do not count no-descent receipts or counter-evidence as residual descent, row-target exhaustion beyond the recorded status object, production ROCm/HIP readiness, or G1 closure.

Candidate files:

- `implementation/phase1/commercial_gap_ledger_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- `./scripts/ai-worker-kiro.sh --check docs/ai/dispatch/kiro_g1_shell_material_no_descent_commercial_propagation_design_20260624T205436Z.md`
- `./scripts/ai-worker-kiro.sh docs/ai/dispatch/kiro_g1_shell_material_no_descent_commercial_propagation_design_20260624T205436Z.md`
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
