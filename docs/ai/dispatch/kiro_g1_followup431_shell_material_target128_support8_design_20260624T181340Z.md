# Kiro Design Slice Template

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` will implement the approved scoped slice if implementation is needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the next bounded G1 shell-material continuation receipt after followup430 by changing support from target128/support4 to target128/support8 and resuming from the latest counted compact checkpoint.

Current blocker: G1 remains partial. The latest authoritative status is `mgt_g1_followup387_shell_material_budgeted_continuation_status.json` with counted frontier `1.3277400507770736 N`, residual gate `5e-4 N`, and blockers for direct residual, full-mesh nonlinear equilibrium, production ROCm/HIP residual-row backend, and consistent residual/Jacobian Newton. Followup429 is the latest counted frontier and records target128/support4 no-descent after three promotions. Followup430 target256/support4 from the same checkpoint is non-promoting. Repeating target128/support4 or simply widening target count is not useful.

Scope: Design only the bounded followup431 diagnostic run using `scripts/run_mgt_shell_material_rowcorr_budget_controller.py` from the followup429 compact checkpoint, target rows `128`, support columns `8`, CPU diagnostic boundary, max 4 row promotions, and bounded runtime. Keep all output under `implementation/phase1/release_evidence/productization/`. Non-goals: no readiness closure claim, no production ROCm/HIP substitution, no full-load/full-mesh claim, no externally blocked G6/G7 claim changes, and no broad refactor.

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
- The proposed followup431 command is bounded and resumes from the followup429 compact checkpoint.
- If followup431 promotes, status/ledgers/tests must use it as the latest counted frontier while preserving all G1 blockers.
- If followup431 does not promote, status/ledgers/tests must record it as non-promoting boundary evidence and avoid replacing the followup429 counted frontier.
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
