# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation edits are needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow G7 operator-attachment status improvement that exposes the minimum source-native operator evidence batch needed to close the operator-attached real MGT target, without promoting G7 while the overlay is still missing.

Current blocker: G7 remains partial. `operator_attachment_manifest.queue.json` has `attachment_count=14`, `auto_promotable_repo_candidate_count=0`, `source_mapping_blocked_action_count=14`, `rights_blocked_private_candidate_action_count=5`, and `minimum_operator_real_mgt_needed=4`. The priority batch `replace_benchmark_bridge_mgt` identifies four source IDs that could close the operator real MGT target only after source-native/right-cleared attachments pass header, sha256, and ingest replay checks.

Scope: Add machine-readable evidence in `commercial_gap_ledger_status.json` for the minimum G7 closure batch and its acceptance criteria. Keep `contract_pass=false`, `G7.status=partial`, and all source-mapping/rights blockers visible. Do not count repo benchmark bridge MGTs, metadata-only sources, private unmapped candidates, or plan-only rows as closure evidence.

Candidate files:

- `implementation/phase1/commercial_gap_ledger_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- `commercial_gap_ledger_status.json` exposes the minimum closure batch source IDs and target directories from `operator_attachment_manifest.queue.json`.
- The same evidence states that the batch is non-closing until source-native attachments, rights/source mapping, and ingest replay checks pass.
- Focused tests assert the batch source count, acceptance checks, and non-promotion boundary.
- Readiness counts remain `closed=17`, `partial=2`, `external_blocked=1`, `open=0`.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
