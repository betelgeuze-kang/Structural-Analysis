# Cursor Worker Task: Developer Preview AI Freeze Boundary Audit

Goal:
Audit whether the current Developer Preview and RC readiness surfaces preserve the goal-file boundary that AI/GNN truth claims remain frozen until deterministic solver closure, and that partial/proxy/fallback evidence is not represented as closure.

Scope:
- Read:
  - `/home/betelgeuze/.codex/attachments/98075342-506d-4368-9755-b528a830c410/goal-objective.md`
  - `.betelgeuze/intent_spec.md`
  - `.betelgeuze/project_contract.yaml`
  - `docs/commercial-structural-solver-product-gap-ledger.md`
  - `docs/structural-analysis-ai-engine-gap-ledger.md`
  - `README.md`
  - `docs/commercialization-gap-current-state.md`
  - `implementation/phase1/release_evidence/productization/developer_preview_readiness.json`
  - `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
  - `tests/test_product_readiness_snapshot_doc_sync.py`
- Candidate edit files, only if needed:
  - `README.md`
  - `docs/commercialization-gap-current-state.md`
  - `tests/test_product_readiness_snapshot_doc_sync.py`

Acceptance criteria:
- If docs already preserve the boundary, report no changes.
- If docs are weak, add concise claim-boundary wording that says AI/GNN/surrogate truth claims remain frozen until deterministic reference solver, full residual/Jacobian/Newton, and benchmark truth are fixed.
- Do not claim any G1 full nonlinear/full-mesh/material Newton, AI surrogate, customer shadow, license, SLA, external benchmark, Linux/Windows, UX, or clean-clone gate is closed.
- Add or update focused doc-sync tests only if wording changes.

Verification:
- Run focused tests for any changed test/doc-sync contract.
- Summarize changed files, test results, and blockers only.
