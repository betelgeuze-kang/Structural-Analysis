# Kiro G7 Terminal Attachment Requirements Design

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement an approved scoped slice if implementation edits are needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow G7/AI-G7 evidence-boundary update that exposes each queued operator attachment as a terminal requirement row, without promoting G7 or AI-G7 readiness.

Current blocker: Commercial G7 still has `operator_attachment_manifest.queue.json` with 14 queued attachments, validation accepted count 0, rejected count 14, rights/source-native confirmations missing, and repo benchmark-bridge evidence still present. The status gate summarizes this, but it does not yet expose per-attachment terminal requirements analogous to G6 terminal external receipt requirements.

Scope: Add machine-readable terminal attachment requirement evidence to `operator_attachment_closure_gate`, mirror the relevant non-promotion counts/boundary into AI-G7, update focused tests and ledger wording. Do not attach new source artifacts, do not download external files, do not mark G7 or AI-G7 commercial corpus evidence closed, and do not claim readiness closure.

Candidate files:

- `implementation/phase1/commercial_gap_ledger_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- G7 remains partial/non-closing.
- G7 `operator_attachment_closure_gate` includes 14 terminal attachment requirement rows and missing count 14.
- Each requirement row preserves source id, action/file/provenance/acceptance metadata, rights/source-native/overlay status, and explicit non-closing reasons.
- AI-G7 mirrors the terminal requirement missing boundary without treating queued operator attachments as training/evaluation/production corpus evidence.
- Focused tests and readiness/status artifact checks pass.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
