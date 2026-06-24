# Kiro Design Slice Template

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` will implement the approved scoped slice.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a compact G7 status/ledger traceability slice that exposes the source receipt paths behind the non-closing `operator_attachment_closure_gate`.

Current blocker: G7 remains partial because the operator attachment queue is not filled, overlay validation rejects all rows, and rights/source-native confirmation is missing. `commercial_gap_ledger_status.json` already carries counts and non-closing reasons, but the closure-gate object should directly name the three source evidence receipts: the operator attachment queue, its validation report, and direct-download review. This improves authoritative evidence traceability without promoting G7.

Scope: Status, docs, and tests only. Do not attach private/public artifacts, do not set rights/source-native flags, do not change any G7 blocker, and do not claim dataset/model/release readiness.

Candidate files:

- implementation/phase1/commercial_gap_ledger_status.py
- tests/test_commercial_gap_ledger_status.py
- docs/commercial-structural-solver-product-gap-ledger.md
- docs/structural-analysis-ai-engine-gap-ledger.md
- implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json

Verification criteria:

- `operator_attachment_closure_gate` includes source receipt paths for queue, validation report, and direct-download review.
- G7 remains `partial`; G7 blockers remain unchanged.
- Gate `contract_pass` remains false and claim boundary remains non-closing.
- Focused tests pass: `python3 -m pytest -q tests/test_commercial_gap_ledger_status.py`.
- Readiness/audit checks remain consistent.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
