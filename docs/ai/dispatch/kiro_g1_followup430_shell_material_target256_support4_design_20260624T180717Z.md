# Kiro Design Slice Template

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` will implement the approved scoped slice if implementation is needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the next bounded G1 shell-material continuation receipt after followup429 by changing the target count from target128/support4 to target256/support4 and resuming from the latest compact checkpoint.

Current blocker: G1 remains partial. The latest authoritative status is `mgt_g1_followup387_shell_material_budgeted_continuation_status.json` with frontier `1.3277400507770736 N`, residual gate `5e-4 N`, `same_operator_exhausted_at_latest_checkpoint=true`, and blockers for direct residual, full-mesh nonlinear equilibrium, production ROCm/HIP residual-row backend, and consistent residual/Jacobian Newton. Followup429 is both counted frontier evidence and a latest target128/support4 no-descent boundary, so repeating target128/support4 is not the next useful diagnostic.

Scope: Design only the bounded followup430 diagnostic run using `scripts/run_mgt_shell_material_rowcorr_budget_controller.py` from the followup429 compact checkpoint, target rows `256`, support columns `4`, CPU diagnostic boundary, max 4 row promotions, and bounded runtime. Keep all output under `implementation/phase1/release_evidence/productization/`. Non-goals: no readiness closure claim, no production ROCm/HIP substitution, no full-load/full-mesh claim, no externally blocked G6/G7 claim changes, and no broad refactor.

Candidate files:

- `scripts/run_mgt_shell_material_rowcorr_budget_controller.py`
- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_compact_checkpoint.npz`

Verification criteria:

- Kiro output keeps the `opus-4.8` design-only boundary explicit.
- The proposed followup430 command is bounded and resumes from the followup429 compact checkpoint.
- If followup430 promotes, status/ledgers/tests must use it as the latest counted frontier while preserving all G1 blockers.
- If followup430 does not promote, status/ledgers/tests must record it as non-promoting boundary evidence and avoid replacing the followup429 counted frontier.
- Focused tests must cover the status builder and commercial gap ledger status.
- Relevant readiness/status gates must be regenerated and checked before Codex acceptance.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
