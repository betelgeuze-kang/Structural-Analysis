# Kiro Gap Summary Nonclosed Count Design

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement an approved scoped slice if needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow compatibility-preserving summary hardening slice for `commercial_gap_ledger_status.json` so locally closable partial gaps are not described only through an `open`-named counter.

Current blocker: The current summary reports `open_count=0` and `locally_closable_open_count=1`. The latter intentionally counts rows whose status is `open` or `partial`, and today that row is G1. The value is useful but the name can make status reports look internally inconsistent.

Scope: Add a clearer machine-readable alias such as `locally_closable_nonclosed_count` and, if useful, `locally_closable_nonclosed_row_ids`, while keeping `locally_closable_open_count` for backward compatibility. Do not change row statuses, do not promote G1/G6/G7, and do not change readiness blockers.

Candidate files:

- `implementation/phase1/commercial_gap_ledger_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `tests/test_build_product_readiness_snapshot.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- Summary still reports `closed_count=17`, `partial_count=2`, `open_count=0`, `external_blocked_count=1`.
- New alias reports the same value as the legacy counter for the current worktree and identifies G1 as the locally closable nonclosed row.
- Downstream readiness artifacts remain consistent.
- The change is explicitly a wording/summary hardening, not closure evidence.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
