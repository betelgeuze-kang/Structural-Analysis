# Kiro Design Slice Template

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` will implement the approved scoped slice.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a compact status/ledger integration slice for the newly present G1 followup448 receipt so it is counted only as non-promoting boundary evidence.

Current blocker: `mgt_shell_material_rowcorr_budget_controller_followup448_fd_residual_weighted_support8_cpu_continuation.json` exists in productization evidence but is not yet status-bound in `mgt_g1_followup387_shell_material_budgeted_continuation_status.json` or the ledger docs. It combines `row_jacobian_mode=finite_difference` with `row_support_selection=residual_weighted`, records `promotion_count=0`, child `1.3092276661494922 -> 1.3092276661494922 N`, and must not be treated as residual progress or G1 closure.

Scope: Status, tests, and ledger claim-boundary integration only. Do not run long solver probes. Do not promote G1, do not alter frontier selection except to record followup448 as non-promoting/no-descent evidence, and do not hide proxy/partial/fallback evidence.

Candidate files:

- scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py
- tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py
- docs/commercial-structural-solver-product-gap-ledger.md
- docs/structural-analysis-ai-engine-gap-ledger.md
- implementation/phase1/release_evidence/productization/mgt_g1_followup387_shell_material_budgeted_continuation_status.json
- implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json

Verification criteria:

- G1 shell-material status includes followup448 in non-promoting/no-descent evidence with `counted_in_frontier=false`.
- Latest counted frontier remains `1.3092276661494922 N`; G1 remains partial.
- Row-target exhaustion remains true, but followup448 is described as a combined finite-difference/residual-weighted support replay boundary rather than a closure route.
- Focused tests pass: `python3 -m pytest -q tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py tests/test_commercial_gap_ledger_status.py`.
- Readiness/audit checks remain consistent and do not promote G1/G6/G7.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
