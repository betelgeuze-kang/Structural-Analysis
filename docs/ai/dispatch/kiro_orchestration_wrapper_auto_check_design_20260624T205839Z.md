# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation edits are needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow orchestration wrapper update so Kiro design slices are launched through an automatic `opus-4.8` confirmation path, with verification coverage that prevents accidental direct or unchecked Kiro use.

Current blocker: `scripts/ai-worker-kiro.sh` already performs automatic prelaunch validation on normal launch, but operators can still treat `--check` as a separate manual convention instead of a first-class wrapper-backed workflow.

Scope: Allowed scope is orchestration scripts, AI orchestration documentation, and smoke verification/preflight checks. Do not change readiness ledger status, product evidence semantics, solver behavior, worker model assignments, or claim any readiness closure.

Candidate files:

- `scripts/ai-worker-kiro.sh`
- `scripts/ai-verify.sh`
- `scripts/ai-preflight.sh`
- `docs/ai/ORCHESTRATION.md`
- `docs/ai/prompts/kiro_design_slice.md`

Verification criteria:

- A normal Kiro design launch still validates model `opus-4.8`, design-only no-edit, and no-readiness-closure boundaries before invoking `kiro chat`.
- The wrapper makes model confirmation automatic and records it in receipt evidence.
- `./scripts/ai-worker-kiro.sh --check docs/ai/prompts/kiro_design_slice.md` passes.
- `./scripts/ai-verify.sh` passes.
- No readiness ledger row is promoted by this orchestration-only change.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
