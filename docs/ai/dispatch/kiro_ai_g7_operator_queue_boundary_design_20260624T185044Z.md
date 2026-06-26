# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation is needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Align the AI-G7 Dataset/ModelOps/ReleaseOps ledger boundary with the refreshed commercial G7 Korean operator attachment queue evidence.

Current blocker: Commercial G7 is partial because `operator_attachment_manifest.queue.json` has 14 pending operator-fill rows, 0 auto-promotable repo candidates, 14 source-mapping blocked actions, and 5 rights-blocked private candidate actions. The AI-engine ledger must not treat this queue or direct-download review as training corpus, evaluation corpus, or real-project corpus closure.

Scope: Design a compact documentation/evidence refresh that keeps G7 partial and AI-G7 non-autonomous. Allowed files are the AI-engine ledger and derived status/evidence receipts. Do not design new corpus ingestion, external downloads, legal/rights resolution, readiness closure, or production ML promotion.

Candidate files:

- docs/structural-analysis-ai-engine-gap-ledger.md
- docs/commercial-structural-solver-product-gap-ledger.md
- implementation/phase1/open_data/korea/operator_attachment_manifest.queue.json
- implementation/phase1/open_data/korea/operator_attachment_manifest.queue.validation_report.json
- implementation/phase1/open_data/korea/operator_attachment_direct_download_review.json
- implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json
- implementation/phase1/release_evidence/productization/ai_orchestration_preflight_report.json

Verification criteria:

- AI-G7 explicitly records the commercial G7 operator queue as non-closing action-queue evidence.
- The documented counts match current receipts: attachment_count=14, auto_promotable_repo_candidate_count=0, source_mapping_blocked_action_count=14, rights_blocked_private_candidate_action_count=5, validation accepted=0/rejected=14, direct review status=pending_rights_review with 5 direct and 9 portal actions.
- Commercial G7 remains partial; AI-G7 must not claim production dataset/modelops closure from the queue.
- Run focused ledger/status checks and `./scripts/ai-verify.sh`.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
