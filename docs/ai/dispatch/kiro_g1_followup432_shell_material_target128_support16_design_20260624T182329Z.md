# Kiro Design Slice: G1 Shell-Material Target128 Support16 Boundary

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation is needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the next bounded G1 CPU-diagnostic continuation after target128/support8 lowered the shell-material frontier once but stopped at no-descent.

Current blocker: G1 remains partial. The latest counted frontier is `1.3092276661494922 N`, about `2618.46x` above the `5e-4 N` direct-residual gate, from `mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_children/mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_candidate1_target128_support8.json`. The same operator is exhausted at the latest checkpoint, while target256/support4 was also non-promoting from the earlier checkpoint.

Scope: Propose a compact design for one bounded target128/support16 continuation from the followup431 compact checkpoint. Keep it CPU diagnostic, receipt-visible, and non-promoting unless the residual/increment gates truly close. Do not recommend full-load/full-mesh/material Newton or ROCm/HIP closure claims from this receipt.

Candidate files:

- `scripts/run_mgt_shell_material_rowcorr_budget_controller.py`
- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_compact_checkpoint.npz`

Verification criteria:

- Kiro wrapper receipt confirms `opus-4.8`, no-edit, and no-readiness-closure prompt boundaries.
- The followup432 receipt records the selected target/support counts, source checkpoint, stop reason, final residual, and promotion count.
- If target128/support16 improves the counted frontier, update the frontier chain and tests with exact residual/ratio values.
- If target128/support16 does not improve, record it as non-promoting boundary evidence and keep followup431 as the counted frontier.
- Ledgers continue to show G1 as partial and do not package this CPU-diagnostic receipt as commercial closure.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
